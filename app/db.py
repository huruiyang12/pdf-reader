from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    uploaded_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Share(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False)
    mode = Column(String, nullable=False)  # preview | browse
    allowed_pages = Column(Integer, nullable=True)
    recipient_name = Column(String, nullable=True)
    recipient_email = Column(String, nullable=True)
    token = Column(String, unique=True, index=True, nullable=False)
    verification_code = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    watermark_text = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


@contextmanager
def get_session() -> Iterator[Session]:
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
