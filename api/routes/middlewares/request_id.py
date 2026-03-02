"""FastAPI middleware for request tracking and logging."""
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.logging import request_id_ctx, get_logger

logger = get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and propagate request IDs."""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Use incoming header or generate new (short ID for readability)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        
        # Store in request state for access in routes if needed
        request.state.request_id = request_id
        
        # Set in contextvar (available to all loggers in this request)
        token = request_id_ctx.set(request_id)
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            # Log request completion
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)"
            )
            
            return response
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{request.method} {request.url.path} -> ERROR ({duration_ms:.1f}ms): {e}"
            )
            raise
            
        finally:
            request_id_ctx.reset(token)
