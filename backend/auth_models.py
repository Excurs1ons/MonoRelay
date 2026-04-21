"""User authentication models and database operations."""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, List

import aiosqlite
from pydantic import BaseModel, Field

logger = logging.getLogger("monorelay.auth")


class User(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    hashed_password: str
    is_admin: bool = False
    role: str = "user"  # "admin" or "user"
    balance: float = 0.0
    created_at: float
    updated_at: float


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserAPIKey(BaseModel):
    id: int
    user_id: int
    key: str
    label: str = "default"
    enabled: bool = True
    quota_limit: float = -1.0  # -1.0 = unlimited
    quota_used: float = 0.0
    created_at: float
    last_used_at: Optional[float] = None


class UserManager:
    def __init__(self, db_path: str = "./data/users.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        """Initialize database schema."""
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                hashed_password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                role TEXT DEFAULT 'user',
                balance REAL DEFAULT 0.0,
                created_at REAL,
                updated_at REAL
            )
            """
        )
        
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT UNIQUE NOT NULL,
                label TEXT DEFAULT 'default',
                enabled INTEGER DEFAULT 1,
                quota_limit REAL DEFAULT -1.0,
                quota_used REAL DEFAULT 0.0,
                created_at REAL,
                last_used_at REAL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        
        # Migration: Add role and balance if missing
        columns = {
            "role": "TEXT DEFAULT 'user'",
            "balance": "REAL DEFAULT 0.0"
        }
        for col, spec in columns.items():
            try:
                await self._db.execute(f"ALTER TABLE users ADD COLUMN {col} {spec}")
            except Exception:
                pass
                
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    async def create_user(self, user_in: UserCreate, is_admin: bool = False) -> Optional[User]:
        if not self._db: await self.init()
        
        hashed = self._hash_password(user_in.password)
        now = time.time()
        role = "admin" if is_admin else "user"
        
        try:
            cursor = await self._db.execute(
                "INSERT INTO users (username, email, hashed_password, is_admin, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_in.username, user_in.email, hashed, 1 if is_admin else 0, role, now, now)
            )
            user_id = cursor.lastrowid
            await self._db.commit()
            return await self.get_user_by_id(user_id)
        except aiosqlite.IntegrityError:
            return None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    def _row_to_user(self, row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            hashed_password=row["hashed_password"],
            is_admin=bool(row["is_admin"]),
            role=row["role"],
            balance=row["balance"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # --- API Key Management ---
    async def create_api_key(self, user_id: int, label: str = "default") -> Optional[UserAPIKey]:
        if not self._db: await self.init()
        key = f"sk-prisma-{secrets.token_hex(24)}"
        now = time.time()
        try:
            cursor = await self._db.execute(
                "INSERT INTO user_api_keys (user_id, key, label, created_at) VALUES (?, ?, ?, ?)",
                (user_id, key, label, now)
            )
            await self._db.commit()
            return await self.get_api_key_by_id(cursor.lastrowid)
        except Exception:
            return None

    async def get_api_key_by_id(self, key_id: int) -> Optional[UserAPIKey]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM user_api_keys WHERE id = ?", (key_id,))
        row = await cursor.fetchone()
        return self._row_to_api_key(row) if row else None

    async def get_api_key_by_token(self, key_token: str) -> Optional[UserAPIKey]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM user_api_keys WHERE key = ?", (key_token,))
        row = await cursor.fetchone()
        return self._row_to_api_key(row) if row else None

    async def get_user_api_keys(self, user_id: int) -> List[UserAPIKey]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM user_api_keys WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        return [self._row_to_api_key(r) for r in rows]

    def _row_to_api_key(self, row) -> UserAPIKey:
        return UserAPIKey(
            id=row["id"],
            user_id=row["user_id"],
            key=row["key"],
            label=row["label"],
            enabled=bool(row["enabled"]),
            quota_limit=row["quota_limit"],
            quota_used=row["quota_used"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"]
        )

    async def has_users(self) -> bool:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] > 0
