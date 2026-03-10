import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from .auth import bearer_auth
from .config import settings
from .models import (
    CreateVMRequest,
    CreateVMResponse,
    ExecRequest,
    HealthResponse,
    WriteFilesRequest,
)
from .network import NetworkManager
from .rootfs import RootfsManager
from .vm_manager import VMManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

network_manager = NetworkManager(max_slots=settings.MAX_VMS, host_nic=settings.HOST_NIC)
rootfs_manager = RootfsManager(
    cache_dir=settings.ROOTFS_CACHE_DIR,
    s3_bucket=settings.S3_BUCKET,
    s3_region=settings.S3_REGION,
)
vm_manager = VMManager(
    config=settings,
    network_manager=network_manager,
    rootfs_manager=rootfs_manager,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    vm_manager.start_background_tasks()
    logger.info("Orchestrator started")
    yield
    logger.info("Shutting down orchestrator, destroying all VMs...")
    await vm_manager.stop_background_tasks()
    await vm_manager.destroy_all()
    logger.info("Orchestrator shutdown complete")

app = FastAPI(title="Firecracker VM Orchestrator", lifespan=lifespan)

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        active_vms=len(vm_manager.active_vms),
    )

@app.post("/vms", response_model=CreateVMResponse, dependencies=[Depends(bearer_auth)])
async def create_vm(request: CreateVMRequest):
    if len(vm_manager.active_vms) >= settings.MAX_VMS:
        raise HTTPException(status_code=503, detail="Maximum VM limit reached")

    try:
        vm_info = await vm_manager.create_vm(request)
    except Exception as e:
        logger.exception("Failed to create VM")
        raise HTTPException(status_code=500, detail=str(e))

    return CreateVMResponse(
        vm_id=vm_info.vm_id,
        ip_address=vm_info.ip_address,
        status=vm_info.status,
    )

@app.post("/vms/{vm_id}/files", dependencies=[Depends(bearer_auth)])
async def write_files(vm_id: str, request: WriteFilesRequest):
    try:
        await vm_manager.write_files(vm_id, request.files)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
    except Exception as e:
        logger.exception("Failed to write files to VM %s", vm_id)
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}

@app.post("/vms/{vm_id}/exec", dependencies=[Depends(bearer_auth)])
async def exec_command(vm_id: str, request: ExecRequest):
    if vm_id not in vm_manager.active_vms:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")

    async def stream():
        async for line in vm_manager.exec_command(
            vm_id, request.command, request.env_vars, request.timeout
        ):
            yield f"data: {json.dumps(line)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.get("/vms/{vm_id}/files/read", dependencies=[Depends(bearer_auth)])
async def read_file(vm_id: str, path: str = Query(...)):
    try:
        content = await vm_manager.read_file(vm_id, path)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
    except Exception as e:
        logger.exception("Failed to read file from VM %s", vm_id)
        raise HTTPException(status_code=500, detail=str(e))

    filename = os.path.basename(path)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.delete("/vms/{vm_id}", dependencies=[Depends(bearer_auth)])
async def destroy_vm(vm_id: str):
    try:
        await vm_manager.destroy_vm(vm_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"VM {vm_id} not found")
    except Exception as e:
        logger.exception("Failed to destroy VM %s", vm_id)
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "destroyed"}