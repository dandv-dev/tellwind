"""Data model.

Everything a workspace owns hangs off ``workspace_id`` so access control is one
check. File contents live in the database (``bytea``) because the free Render
web service has an ephemeral disk; files here are small (reports, briefs).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC datetime that also round-trips through SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


ROLES = ("viewer", "member", "owner")  # ordered by power


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # random token
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime())
    user: Mapped[User] = relationship(lazy="joined")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(200))
    subject_description: Mapped[str] = mapped_column(Text, default="")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_time: Mapped[str] = mapped_column(String(5), default="06:00")  # HH:MM UTC
    last_scheduled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    # Collection high-water mark: news up to this moment has been gathered.
    collected_until: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    user: Mapped[User] = relationship(lazy="joined")


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(10))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending/accepted/declined/revoked
    invited_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    # Search phrases used by the collectors; generated from name if empty.
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    embedding_key: Mapped[str] = mapped_column(String(64), default="")  # hash of text embedded
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class File(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # upload | brief | trace | news
    kind: Mapped[str] = mapped_column(String(10), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    uploaded_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    brief_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # For uploads: parse status and how many chunks became sources
    parse_status: Mapped[str] = mapped_column(String(10), default="")
    chunks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    uploader: Mapped[User | None] = relationship(lazy="joined")


class Item(Base):
    """One source: a news article or a chunk of an uploaded file."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "content_hash"),
        Index("ix_items_ws_published", "workspace_id", "published_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(10))  # news | upload
    source: Mapped[str] = mapped_column(String(120))  # e.g. "Hacker News", "theverge.com"
    collector: Mapped[str] = mapped_column(String(20), default="")  # hn | gdelt | gnews | upload
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(TZDateTime())
    collected_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    collected_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64))
    engagement: Mapped[float] = mapped_column(Float, default=0.0)  # e.g. HN points
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    # Set once the item has been through classification (relevant or not).
    classified_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    # When set, this item is a near-duplicate of another and is not counted twice.
    duplicate_of: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Evidence(Base):
    """What one item says about one topic. Produced once per item by the classifier."""

    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("item_id", "topic_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    relevance: Mapped[float] = mapped_column(Float)
    signal: Mapped[int] = mapped_column(Integer)  # -2 strongly cooling .. +2 strongly heating
    quote: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")  # one-line why
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    item: Mapped[Item] = relationship(lazy="joined")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(10))  # manual | schedule | demo
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued/running/succeeded/failed
    as_of: Mapped[date] = mapped_column(Date)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    brief_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    creator: Mapped[User | None] = relationship(lazy="joined")


class Brief(Base):
    __tablename__ = "briefs"
    __table_args__ = (Index("ix_briefs_ws_date", "workspace_id", "date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    date: Mapped[date] = mapped_column(Date)
    # Full brief payload rendered by the Brief tab and the standalone HTML.
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("workspace_id", "norm"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    norm: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class CompanyMention(Base):
    __tablename__ = "company_mentions"
    __table_args__ = (UniqueConstraint("company_id", "item_id", "topic_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    topic_id: Mapped[str | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    alias: Mapped[str] = mapped_column(String(200))  # how the source named it
    event_type: Mapped[str] = mapped_column(String(20), default="other")
    event: Mapped[str] = mapped_column(Text, default="")  # what the company did
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    brief_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
