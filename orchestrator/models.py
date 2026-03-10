from datetime import datetime
from pydantic import BaseModel

class CreateVMRequest(BaseModel):
    image_url: str
    timeout: int = 600
    idle_timeout: int = 120

class CreateVMResponse(BaseModel):
    vm_id: str
    ip_address: str
    status: str

class WriteFilesRequest(BaseModel):
    files: dict[str, str]

class ExecRequest(BaseModel):
    command: list[str]
    env_vars: dict[str, str] = {}
    timeout: int = 600

class FileReadResponse(BaseModel):
    content: bytes
    filename: str

class HealthResponse(BaseModel):
    status: str
    active_vms: int

class VMInfo(BaseModel):
    vm_id: str
    ip_address: str
    status: str
    created_at: datetime
    slot: int