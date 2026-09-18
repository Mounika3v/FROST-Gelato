from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
try:
    import streamlit as st
except Exception:
    st = None

ROOT = Path(__file__).resolve().parents[1]
try:
    _secret_db = str(st.secrets.get("FROST_DATABASE_URL", "")) if st is not None else ""
except Exception:
    _secret_db = ""
DATABASE_URL = os.getenv("FROST_DATABASE_URL") or _secret_db or ("sqlite:///" + str(ROOT / "data" / "frost.sqlite3"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    password_salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    taste_json: Mapped[str] = mapped_column(Text, default="{}")
    avoid_json: Mapped[str] = mapped_column(Text, default="[]")


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    product_code: Mapped[str] = mapped_column(String(80), primary_key=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    total: Mapped[int] = mapped_column(Integer)
    payment: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="Placed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    Base.metadata.create_all(engine)


def _password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000).hex()


def create_user(name: str, email: str, password: str) -> dict[str, Any] | None:
    with Session(engine) as session:
        if session.scalar(select(User).where(User.email == email.strip().lower())):
            return None
        salt = secrets.token_bytes(16)
        user = User(name=name.strip(), email=email.strip().lower(), password_hash=_password(password, salt), password_salt=salt.hex())
        session.add(user)
        session.flush()
        session.add(Profile(user_id=user.id))
        session.commit()
        return {"id": user.id, "name": user.name, "email": user.email, "password_hash": user.password_hash, "password_salt": user.password_salt}


def get_user(email: str) -> dict[str, Any] | None:
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == email.strip().lower()))
        if not user:
            return None
        return {"id": user.id, "name": user.name, "email": user.email, "password_hash": user.password_hash, "password_salt": user.password_salt}


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    row = get_user(email)
    if not row:
        return None
    expected = _password(password, bytes.fromhex(row["password_salt"]))
    return row if hmac.compare_digest(expected, row["password_hash"]) else None


def update_name(user_id: int, name: str) -> None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            user.name = name.strip()
            session.commit()


def save_profile(user_id: int, taste: dict, avoid: set[str]) -> None:
    with Session(engine) as session:
        profile = session.get(Profile, user_id)
        if not profile:
            profile = Profile(user_id=user_id)
            session.add(profile)
        profile.taste_json = json.dumps(taste)
        profile.avoid_json = json.dumps(sorted(avoid))
        session.commit()


def load_profile(user_id: int) -> tuple[dict, set[str]]:
    with Session(engine) as session:
        profile = session.get(Profile, user_id)
        if not profile:
            return {}, set()
        try:
            return json.loads(profile.taste_json), set(json.loads(profile.avoid_json))
        except Exception:
            return {}, set()


def set_favorite(user_id: int, product_code: str, enabled: bool) -> None:
    with Session(engine) as session:
        key = (user_id, product_code)
        favorite = session.get(Favorite, key)
        if enabled and not favorite:
            session.add(Favorite(user_id=user_id, product_code=product_code))
        elif not enabled and favorite:
            session.delete(favorite)
        session.commit()


def get_favorites(user_id: int) -> set[str]:
    with Session(engine) as session:
        rows = session.scalars(select(Favorite.product_code).where(Favorite.user_id == user_id)).all()
    return set(rows)


def save_order(user_id: int | None, order_number: str, items: list[dict], total: int, payment: str, status: str = "Placed") -> None:
    with Session(engine) as session:
        session.add(Order(user_id=user_id, order_number=order_number, payload_json=json.dumps(items), total=int(total), payment=payment, status=status))
        session.commit()


def get_orders(user_id: int) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())).all()
    return [
        {"order_number": r.order_number, "items": json.loads(r.payload_json), "total": r.total, "payment": r.payment, "status": r.status, "created_at": r.created_at.strftime("%d %b %Y · %H:%M") if r.created_at else ""}
        for r in rows
    ]
