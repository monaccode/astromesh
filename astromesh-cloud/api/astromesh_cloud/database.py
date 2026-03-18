from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from astromesh_cloud.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    # Import models to ensure metadata is populated.
    from astromesh_cloud.models import Base  # noqa: WPS433

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with async_session() as session:
        yield session
