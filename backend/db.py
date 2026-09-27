"""
Database layer — Azure Managed PostgreSQL
------------------------------------------
Async SQLAlchemy engine + session factory. Tables are created on startup.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv
from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text, func, select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to backend/.env "
        "(see .env.example for the Azure PostgreSQL format)."
    )

_connect_args: Dict[str, Any] = {}
if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    _connect_args["ssl"] = "require"
    if "ssl=require" in DATABASE_URL:
        DATABASE_URL = (
            DATABASE_URL.replace("?ssl=require", "").replace("&ssl=require", "")
        )

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args=_connect_args,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    analyses: Mapped[List["Analysis"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    resource_group: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resources_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_savings: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    analysis_result: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[Optional[User]] = relationship(back_populates="analyses")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


# ---------- User queries ----------

async def create_user(email: str, password_hash: str) -> User:
    async with SessionLocal() as session:
        user = User(email=email.lower().strip(), password_hash=password_hash)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_by_email(email: str) -> Optional[User]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()


# ---------- Analysis queries ----------

async def create_analysis(
    user_id: Optional[int], resource_group: str, status: str = "pending",
) -> Analysis:
    async with SessionLocal() as session:
        row = Analysis(
            user_id=user_id,
            resource_group=resource_group,
            status=status,
            analysis_result={},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def finalize_analysis(
    analysis_id: int,
    *,
    resources_scanned: int,
    issues_found: int,
    estimated_savings: str,
    analysis_result: Dict[str, Any],
    status: str = "complete",
) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Analysis).where(Analysis.id == analysis_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.resources_scanned = resources_scanned
        row.issues_found = issues_found
        row.estimated_savings = estimated_savings
        row.analysis_result = analysis_result
        row.status = status
        await session.commit()


async def fail_analysis(analysis_id: int, reason: str) -> None:
    await finalize_analysis(
        analysis_id,
        resources_scanned=0,
        issues_found=0,
        estimated_savings="0",
        analysis_result={"error": reason},
        status="failed",
    )


async def list_analyses_for_user(
    user_id: int, limit: int = 50, offset: int = 0
) -> List[Analysis]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Analysis)
            .where(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())


async def get_analysis_for_user(
    analysis_id: int, user_id: int
) -> Optional[Analysis]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Analysis).where(
                Analysis.id == analysis_id,
                Analysis.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()