"""User authentication models and database operations."""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
from pydantic import BaseModel, Field

logger = logging.getLogger("monorelay.auth")


class User(BaseModel):
    """User model representing a registered user."""
    id: int
    username: str
    email: str
    is_active: bool = True
    is_admin: bool = False
    is_super_admin: bool = False
    sso_provider: Optional[str] = None
    sso_id: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class UserCreate(BaseModel):
    """Model for user registration."""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Model for user login."""
    username: str
    password: str


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: dict


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # user id
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    type: str = "access"  # token type: access or refresh


class UserManager:
    """Manager for user authentication and database operations."""
    
    def __init__(self, db_path: str = "./data/users.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
    
    async def init(self):
        """Initialize the users database."""
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        # Create users table
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_admin INTEGER DEFAULT 0,
                is_super_admin INTEGER DEFAULT 0,
                sso_provider TEXT,
                sso_id TEXT,
                created_at REAL NOT NULL,
                last_login REAL
            )
            """
        )
        
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN is_super_admin INTEGER DEFAULT 0")
        except Exception:
            pass
        
        # Check for missing columns (migration for existing users)
        cursor = await self._db.execute("PRAGMA table_info(users)")
        columns = [row["name"] for row in await cursor.fetchall()]
        if "sso_provider" not in columns:
            await self._db.execute("ALTER TABLE users ADD COLUMN sso_provider TEXT")
        if "sso_id" not in columns:
            await self._db.execute("ALTER TABLE users ADD COLUMN sso_id TEXT")
        
        # Create indexes
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
            """
        )
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
            """
        )
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_sso ON users(sso_provider, sso_id)
            """
        )
        
        await self._db.commit()
        logger.info(f"User manager initialized with database at {self.db_path}")
    
    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
    
    def _hash_password(self, password: str) -> str:
        """Hash password using PBKDF2 with SHA256."""
        salt = secrets.token_hex(16)
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('ascii'),
            100000
        )
        return salt + pwdhash.hex()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        salt = password_hash[:32]
        stored_hash = password_hash[32:]
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('ascii'),
            100000
        )
        return pwdhash.hex() == stored_hash
    
    def _row_to_user(self, row: aiosqlite.Row) -> User:
        """Convert a database row to a User model."""
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            is_active=bool(row["is_active"]),
            is_admin=bool(row["is_admin"]),
            sso_provider=row["sso_provider"],
            sso_id=row["sso_id"],
            created_at=datetime.fromtimestamp(row["created_at"]),
            last_login=datetime.fromtimestamp(row["last_login"]) if row["last_login"] else None
        )
    
    async def create_user(self, user_data: UserCreate, is_admin: bool = False, is_super_admin: bool = False) -> User:
        """Create a new user."""
        if not self._db:
            await self.init()
        
        password_hash = self._hash_password(user_data.password)
        created_at = time.time()
        
        try:
            cursor = await self._db.execute(
                """
                INSERT INTO users (username, email, password_hash, is_active, is_admin, is_super_admin, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_data.username,
                    user_data.email,
                    password_hash,
                    1,
                    1 if is_admin else 0,
                    1 if is_super_admin else 0,
                    created_at
                )
            )
            await self._db.commit()
            
            return User(
                id=cursor.lastrowid,
                username=user_data.username,
                email=user_data.email,
                is_active=True,
                is_admin=is_admin,
                created_at=datetime.fromtimestamp(created_at),
                last_login=None
            )
        except aiosqlite.IntegrityError as e:
            if "username" in str(e).lower():
                raise ValueError(f"Username '{user_data.username}' already exists")
            elif "email" in str(e).lower():
                raise ValueError(f"Email '{user_data.email}' already exists")
            raise ValueError(f"User already exists: {e}")
    
    async def create_sso_user(self, provider: str, sso_id: str, username: str, email: str, is_admin: bool = False, is_super_admin: bool = False) -> User:
        """Create a new user from SSO data."""
        if not self._db:
            await self.init()
        
        password_hash = "SSO:" + secrets.token_hex(32)
        created_at = time.time()
        
        try:
            cursor = await self._db.execute(
                """
                INSERT INTO users (username, email, password_hash, is_active, is_admin, is_super_admin, sso_provider, sso_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (username, email, password_hash, 1, 1 if is_admin else 0, 1 if is_super_admin else 0, provider, sso_id, created_at)
            )
            await self._db.commit()
            
            return await self.get_user_by_id(cursor.lastrowid)
        except aiosqlite.IntegrityError as e:
            # If username exists, try with a suffix
            if "username" in str(e).lower():
                new_username = f"{username}_{secrets.token_hex(4)}"
                return await self.create_sso_user(provider, sso_id, new_username, email, is_admin)
            raise ValueError(f"Failed to create SSO user: {e}")

    async def get_user_by_sso(self, provider: str, sso_id: str) -> Optional[User]:
        """Get user by SSO provider and ID."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE sso_provider = ? AND sso_id = ?",
            (provider, sso_id)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_user(row)
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,)
        )
        row = await cursor.fetchone()
        
        if not row:
            return None
        
        # SSO users might not have a verifyable password hash if it starts with "SSO:"
        if row["password_hash"].startswith("SSO:") or not self._verify_password(password, row["password_hash"]):
            return None
        
        # Update last login
        await self._db.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (time.time(), row["id"])
        )
        await self._db.commit()
        
        return self._row_to_user(row)
    
    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user fields."""
        if not self._db:
            await self.init()
        
        allowed_fields = {"email", "is_active", "is_admin", "last_login", "sso_provider", "sso_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return await self.get_user_by_id(user_id)
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [user_id]
        
        await self._db.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            values
        )
        await self._db.commit()
        
        return await self.get_user_by_id(user_id)
    
    async def list_users(self) -> list[User]:
        """List all users."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        
        return [self._row_to_user(row) for row in rows]
    
    async def has_users(self) -> bool:
        """Check if any users exist."""
        if not self._db:
            await self.init()
        
        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] > 0
