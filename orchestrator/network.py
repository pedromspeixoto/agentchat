import asyncio
import logging

logger = logging.getLogger(__name__)

class NetworkManager:
    def __init__(self, max_slots: int = 255, host_nic: str = "ens5") -> None:
        self._max_slots = max_slots
        self._host_nic = host_nic
        self._used_slots: set[int] = set()

    def allocate_slot(self) -> int:
        for slot in range(1, self._max_slots + 1):
            if slot not in self._used_slots:
                self._used_slots.add(slot)
                return slot
        raise RuntimeError("No available network slots")

    def release_slot(self, slot: int) -> None:
        self._used_slots.discard(slot)

    async def _run(self, *args: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Command %s failed: %s", args, stderr.decode())
            raise RuntimeError(f"Command {args} failed: {stderr.decode()}")

    async def setup_tap(self, vm_id: str, slot: int) -> tuple[str, str, str]:
        tap_name = f"tap-{vm_id[:8]}"
        host_ip = f"172.16.{slot}.1"
        guest_ip = f"172.16.{slot}.2"
        subnet = f"172.16.{slot}.0/30"

        await self._run("ip", "tuntap", "add", "dev", tap_name, "mode", "tap")
        await self._run("ip", "addr", "add", f"{host_ip}/30", "dev", tap_name)
        await self._run("ip", "link", "set", tap_name, "up")

        logger.info("Created TAP %s: host=%s guest=%s", tap_name, host_ip, guest_ip)
        return tap_name, guest_ip, host_ip

    async def setup_nat(self, tap_name: str, subnet: str, host_nic: str) -> None:
        await self._run(
            "iptables", "-t", "nat", "-A", "POSTROUTING",
            "-o", host_nic, "-s", subnet, "-j", "MASQUERADE",
        )
        await self._run(
            "iptables", "-A", "FORWARD",
            "-i", tap_name, "-o", host_nic, "-j", "ACCEPT",
        )
        await self._run(
            "iptables", "-A", "FORWARD",
            "-i", host_nic, "-o", tap_name, "-m", "state",
            "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT",
        )

    async def teardown(self, vm_id: str, slot: int, tap_name: str) -> None:
        host_nic = self._host_nic
        subnet = f"172.16.{slot}.0/30"

        # Remove iptables rules (ignore errors if already removed)
        for args in [
            ["iptables", "-t", "nat", "-D", "POSTROUTING",
             "-o", host_nic, "-s", subnet, "-j", "MASQUERADE"],
            ["iptables", "-D", "FORWARD",
             "-i", tap_name, "-o", host_nic, "-j", "ACCEPT"],
            ["iptables", "-D", "FORWARD",
             "-i", host_nic, "-o", tap_name, "-m", "state",
             "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
        ]:
            try:
                await self._run(*args)
            except RuntimeError:
                logger.warning("Failed to remove iptables rule: %s", args)

        # Delete TAP device
        try:
            await self._run("ip", "link", "delete", tap_name)
        except RuntimeError:
            logger.warning("Failed to delete TAP device %s", tap_name)

        self.release_slot(slot)
        logger.info("Torn down network for VM %s (slot %d)", vm_id, slot)