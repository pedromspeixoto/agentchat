from pydantic_settings import BaseSettings

class OrchestratorSettings(BaseSettings):
    API_KEY: str
    S3_BUCKET: str
    S3_REGION: str = "us-east-1"
    HOST_NIC: str = "ens5"
    KERNEL_PATH: str = "/opt/firecracker/kernel/vmlinux"
    SSH_KEY_PATH: str = "/opt/firecracker/ssh/id_rsa"
    ROOTFS_CACHE_DIR: str = "/opt/firecracker/rootfs-cache"
    VM_DIR: str = "/opt/firecracker/vms"
    FIRECRACKER_BIN: str = "/usr/local/bin/firecracker"
    MAX_VMS: int = 255
    VM_TIMEOUT: int = 660
    PORT: int = 8090
    model_config = {"env_file": ".env"}

settings = OrchestratorSettings()