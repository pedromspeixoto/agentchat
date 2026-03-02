from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db

router = APIRouter()


@router.get("/health")
def health_check():
    """Health check endpoint - defines the liveness probe"""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check endpoint - defines the readiness probe"""
    try:
        result = await db.execute(select(1))
        result.scalar_one()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")

    return {"status": "ready"}
