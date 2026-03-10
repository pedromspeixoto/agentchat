import asyncio
import json
import logging
import os
import signal
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import asyncssh

from .config import OrchestratorSettings
from .models import CreateVMRequest, VMInfo
from .network import NetworkManager
from .rootfs import RootfsManager

logger = logging.getLogger(__name__)

class VMManager:
    def __init__(
        self,
        config: OrchestratorSettings,
        network_manager: NetworkManager,
        rootfs_manager: RootfsManager,
    ) -> None:
        self._config = config
        self._network = network_manager
        self._rootfs = rootfs_manager
        self._vms: dict[str, VMInfo] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._tap_names: dict[str, str] = {}
        self._timeout_task: asyncio.Task | None = None

    @property
    def active_vms(self) -> dict[str, VMInfo]:
        return dict(self._vms)

    def start_background_tasks(self) -> None:
        self._timeout_task = asyncio.create_task(self._auto_destroy_loop())

    async def stop_background_tasks(self) -> None:
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

    async def create_vm(self, request: CreateVMRequest) -> VMInfo:
        vm_id = uuid.uuid4().hex[:12]

        # 1. Allocate network slot
        slot = self._network.allocate_slot()
        logger.info("Allocated slot %d for VM %s", slot, vm_id)

        try:
            # 2. Download/cache rootfs
            cached_path = self._rootfs.download_rootfs(request.image_url)

            # 3. Create per-VM directory
            vm_dir = os.path.join(self._config.VM_DIR, vm_id)
            os.makedirs(vm_dir, exist_ok=True)

            # 4. Create per-VM rootfs copy
            rootfs_path = await self._rootfs.create_vm_copy(cached_path, vm_dir)

            # 5. Setup TAP device + NAT
            tap_name, guest_ip, host_ip = await self._network.setup_tap(vm_id, slot)
            self._tap_names[vm_id] = tap_name
            subnet = f"172.16.{slot}.0/30"
            await self._network.setup_nat(tap_name, subnet, self._config.HOST_NIC)

            # 6. Generate Firecracker config
            fc_config = {
                "boot-source": {
                    "kernel_image_path": self._config.KERNEL_PATH,
                    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
                },
                "drives": [
                    {
                        "drive_id": "rootfs",
                        "path_on_host": rootfs_path,
                        "is_root_device": True,
                        "is_read_only": False,
                    }
                ],
                "network-interfaces": [
                    {
                        "iface_id": "eth0",
                        "guest_mac": f"AA:FC:00:00:{slot:02X}:01",
                        "host_dev_name": tap_name,
                    }
                ],
                "machine-config": {
                    "vcpu_count": 2,
                    "mem_size_mib": 512,
                },
            }

            config_path = os.path.join(vm_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(fc_config, f, indent=2)

            # 7. Start Firecracker process
            sock_path = f"/tmp/firecracker-{vm_id}.sock"
            proc = await asyncio.create_subprocess_exec(
                self._config.FIRECRACKER_BIN,
                "--api-sock", sock_path,
                "--config-file", config_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._processes[vm_id] = proc
            logger.info("Started Firecracker process PID %d for VM %s", proc.pid, vm_id)

            # 8. Wait for SSH availability
            await self._wait_for_ssh(guest_ip)

            # 9. Build and return VMInfo
            vm_info = VMInfo(
                vm_id=vm_id,
                ip_address=guest_ip,
                status="running",
                created_at=datetime.now(timezone.utc),
                slot=slot,
            )
            self._vms[vm_id] = vm_info
            return vm_info

        except Exception:
            self._network.release_slot(slot)
            raise

    async def write_files(self, vm_id: str, files: dict[str, str]) -> None:
        vm = self._vms.get(vm_id)
        if not vm:
            raise KeyError(f"VM {vm_id} not found")

        async with await self._ssh_connect(vm.ip_address) as conn:
            async with conn.start_sftp_client() as sftp:
                for path, content in files.items():
                    # Ensure parent directory exists
                    parent = os.path.dirname(path)
                    if parent:
                        await conn.run(f"mkdir -p {parent}")
                    await sftp.open(path, "w").write(content)
        logger.info("Wrote %d files to VM %s", len(files), vm_id)

    async def exec_command(
        self,
        vm_id: str,
        command: list[str],
        env_vars: dict[str, str],
        timeout: int,
    ) -> AsyncIterator[str]:
        vm = self._vms.get(vm_id)
        if not vm:
            raise KeyError(f"VM {vm_id} not found")

        cmd_str = " ".join(command)
        env_prefix = " ".join(f"{k}={v}" for k, v in env_vars.items())
        if env_prefix:
            cmd_str = f"{env_prefix} {cmd_str}"

        async with await self._ssh_connect(vm.ip_address) as conn:
            async with conn.create_process(cmd_str) as proc:
                try:
                    async with asyncio.timeout(timeout):
                        async for line in proc.stdout:
                            yield line.rstrip("\n")
                except TimeoutError:
                    proc.kill()
                    yield "[timeout] Command exceeded time limit"

                await proc.wait()
                exit_status = proc.exit_status
                if exit_status != 0:
                    stderr_output = await proc.stderr.read()
                    if stderr_output:
                        yield f"[stderr] {stderr_output.rstrip()}"
                    yield f"[exit] {exit_status}"

    async def read_file(self, vm_id: str, path: str) -> bytes:
        vm = self._vms.get(vm_id)
        if not vm:
            raise KeyError(f"VM {vm_id} not found")

        async with await self._ssh_connect(vm.ip_address) as conn:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(path, "rb") as f:
                    return await f.read()

    async def destroy_vm(self, vm_id: str) -> None:
        vm = self._vms.pop(vm_id, None)
        if not vm:
            raise KeyError(f"VM {vm_id} not found")

        # Kill Firecracker process
        proc = self._processes.pop(vm_id, None)
        if proc and proc.returncode is None:
            try:
                proc.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            except ProcessLookupError:
                pass
        logger.info("Killed Firecracker process for VM %s", vm_id)

        # Teardown network
        tap_name = self._tap_names.pop(vm_id, f"tap-{vm_id[:8]}")
        await self._network.teardown(vm_id, vm.slot, tap_name)

        # Cleanup rootfs and VM directory
        vm_dir = os.path.join(self._config.VM_DIR, vm_id)
        self._rootfs.cleanup(vm_dir)

        # Remove socket
        sock_path = f"/tmp/firecracker-{vm_id}.sock"
        if os.path.exists(sock_path):
            os.remove(sock_path)

        logger.info("Destroyed VM %s", vm_id)

    async def destroy_all(self) -> None:
        vm_ids = list(self._vms.keys())
        for vm_id in vm_ids:
            try:
                await self.destroy_vm(vm_id)
            except Exception:
                logger.exception("Error destroying VM %s during shutdown", vm_id)

    async def _ssh_connect(self, ip: str) -> asyncssh.SSHClientConnection:
        return await asyncssh.connect(
            ip,
            username="root",
            client_keys=[self._config.SSH_KEY_PATH],
            known_hosts=None,
        )

    async def _wait_for_ssh(self, ip: str, max_wait: float = 30.0) -> None:
        deadline = asyncio.get_event_loop().time() + max_wait
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with await self._ssh_connect(ip):
                    logger.info("SSH available at %s", ip)
                    return
            except (OSError, asyncssh.Error):
                await asyncio.sleep(0.5)
        raise TimeoutError(f"SSH not available at {ip} within {max_wait}s")

    async def _auto_destroy_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = datetime.now(timezone.utc)
            expired = [
                vm_id
                for vm_id, vm in self._vms.items()
                if (now - vm.created_at).total_seconds() > self._config.VM_TIMEOUT
            ]
            for vm_id in expired:
                logger.warning("Auto-destroying expired VM %s", vm_id)
                try:
                    await self.destroy_vm(vm_id)
                except Exception:
                    logger.exception("Error auto-destroying VM %s", vm_id)
