from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL, DATA


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer)
    variant: Mapped[str] = mapped_column(String(1))
    seed: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    runtime: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="ready")
    epoch: Mapped[int] = mapped_column(Integer, default=0)
    token_hash: Mapped[str] = mapped_column(String(64))
    initial: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    manifest: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def make_database(url=DATABASE_URL):
    DATA.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
