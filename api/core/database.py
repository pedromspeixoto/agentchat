"""Database connection and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Database URL - using asyncpg driver
DATABASE_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()
# Note: Models are imported in main.py to avoid circular imports


async def get_db() -> AsyncSession:
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables (for development only - use Alembic migrations in production)"""
    from core.config import Environment
    
    # Safeguard: Only allow table creation in local/dev environments
    if settings.ENVIRONMENT == Environment.PROD:
        logger.warning("⚠️ init_db() called in production - skipping. Use Alembic migrations instead.")
        return
    
    # Ensure models are imported and registered with Base.metadata
    from models.chat import ChatSession, ChatMessage, ChatUsage, ChatEvent  # noqa: F401
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables initialized (ENVIRONMENT=%s)", settings.ENVIRONMENT.value)


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("✅ Database connections closed")
