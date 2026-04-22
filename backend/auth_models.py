"""User authentication models, redemption codes, and billing database operations."""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiosqlite
from pydantic import BaseModel

logger = logging.getLogger("monorelay.auth")


class User(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    hashed_password: str
    is_admin: bool = False
    is_active: bool = True
    is_super_admin: bool = False
    role: str = "user"
    balance: float = 0.0
    sso_provider: Optional[str] = None
    sso_provider_id: Optional[str] = None
    created_at: float
    updated_at: float


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class RedemptionCode(BaseModel):
    id: int
    code: str
    amount: float
    is_used: bool = False
    used_by: Optional[int] = None
    used_at: Optional[float] = None
    created_at: float


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict
    refresh_token: Optional[str] = None


class UserAPIKey(BaseModel):
    id: int
    user_id: int
    key: str
    label: str = "default"
    enabled: bool = True
    quota_limit: float = -1.0
    quota_used: float = 0.0
    created_at: float
    last_used_at: Optional[float] = None


class UserManager:
    def __init__(self, db_path: str = "./data/users.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        # Table: users
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_super_admin INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at REAL,
                last_login REAL,
                sso_provider TEXT,
                sso_id TEXT,
                balance REAL DEFAULT 0.0
            )
        """)
        
        # Table: user_api_keys
        await self._db.execute("""
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
        """)

        # Table: redemption_codes
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS redemption_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                is_used INTEGER DEFAULT 0,
                used_by INTEGER,
                used_at REAL,
                created_at REAL,
                FOREIGN KEY (used_by) REFERENCES users (id)
            )
        """)

        # Table: tenant_configs (per-tenant configuration)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tenant_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                config_json TEXT NOT NULL,
                created_at REAL,
                updated_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Table: tenant_providers (per-tenant provider definitions)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tenant_providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                base_url TEXT,
                headers_json TEXT,
                models_json TEXT,
                priority INTEGER DEFAULT 100,
                created_at REAL,
                updated_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, provider_name)
            )
        """)

        # Table: tenant_api_keys (per-tenant API keys)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS tenant_api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                provider_name TEXT NOT NULL,
                key_value TEXT NOT NULL,
                label TEXT DEFAULT 'default',
                enabled INTEGER DEFAULT 1,
                weight INTEGER DEFAULT 1,
                rate_limit INTEGER DEFAULT 0,
                cooldown INTEGER DEFAULT 0,
                created_at REAL,
                last_used_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Indexes for performance
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_tenant_providers_user ON tenant_providers(user_id)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_tenant_api_keys_user ON tenant_api_keys(user_id)")

        
        # Migrations
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
        except: pass
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN sso_provider TEXT")
        except: pass
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN sso_provider_id TEXT")
        except: pass
        try:
            await self._db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
        except: pass
        except: pass

        await self._db.commit()

    async def create_user(self, user_in: UserCreate, is_admin: bool = False, is_super_admin: bool = False) -> Optional[User]:
        if not self._db: await self.init()
        hashed = hashlib.sha256(user_in.password.encode()).hexdigest()
        now = time.time()
        role = "admin" if is_admin else "user"
        try:
            cursor = await self._db.execute(
                "INSERT INTO users (username, email, password_hash, is_admin, is_super_admin, is_active, created_at, last_login, balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_in.username, user_in.email, hashed, 1 if is_admin else 0, 1 if is_super_admin else 0, 1, now, None, 0.0)
            )
            await self._db.commit()
            return await self.get_user_by_id(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[User]:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    def _row_to_user(self, row) -> User:
        return User(id=row["id"], username=row["username"], email=row["email"], hashed_password=row["password_hash"],
                    is_admin=bool(row["is_admin"]), is_active=bool(row["is_active"] if "is_active" in row.keys() else 1),
                    is_super_admin=bool(row["is_super_admin"] if "is_super_admin" in row.keys() else 0), role="admin" if row["is_admin"] else "user", balance=row["balance"] if "balance" in row.keys() else 0.0,
                    sso_provider=row["sso_provider"] if "sso_provider" in row.keys() else None, sso_provider_id=row["sso_provider_id"] if "sso_provider_id" in row.keys() else None,
                    created_at=row["created_at"], updated_at=row["created_at"])

    # --- Billing & Balance ---
    async def update_balance(self, user_id: int, amount: float) -> bool:
        """Atomic balance update. amount can be positive or negative."""
        if not self._db: await self.init()
        try:
            await self._db.execute("UPDATE users SET balance = balance + ?, updated_at = ? WHERE id = ?", (amount, time.time(), user_id))
            await self._db.commit()
            return True
        except: return False

    # --- Redemption Codes ---
    async def generate_codes(self, amount: float, count: int = 1, prefix: str = "PRISMA-") -> List[str]:
        if not self._db: await self.init()
        codes = []
        now = time.time()
        for _ in range(count):
            code = f"{prefix}{secrets.token_hex(8).upper()}"
            await self._db.execute("INSERT INTO redemption_codes (code, amount, created_at) VALUES (?, ?, ?)", (code, amount, now))
            codes.append(code)
        await self._db.commit()
        return codes

    async def redeem_code(self, user_id: int, code_str: str) -> Optional[float]:
        """Redeem a code and add balance to user. Returns the amount added."""
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM redemption_codes WHERE code = ? AND is_used = 0", (code_str,))
        row = await cursor.fetchone()
        if not row: return None
        
        amount = row["amount"]
        now = time.time()
        try:
            # Atomic transaction
            await self._db.execute("BEGIN TRANSACTION")
            await self._db.execute("UPDATE redemption_codes SET is_used = 1, used_by = ?, used_at = ? WHERE id = ?", (user_id, now, row["id"]))
            await self._db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
            await self._db.commit()
            return amount
        except Exception as e:
            await self._db.execute("ROLLBACK")
            logger.error(f"Redemption failed: {e}")
            return None

    # --- API Key Management ---
    async def create_api_key(self, user_id: int, label: str = "default") -> Optional[UserAPIKey]:
        if not self._db: await self.init()
        key = f"sk-prisma-{secrets.token_hex(24)}"
        try:
            cursor = await self._db.execute("INSERT INTO user_api_keys (user_id, key, label, created_at) VALUES (?, ?, ?, ?)", (user_id, key, label, time.time()))
            await self._db.commit()
            return await self.get_api_key_by_id(cursor.lastrowid)
        except: return None

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
        return UserAPIKey(id=row["id"], user_id=row["user_id"], key=row["key"], label=row["label"],
                          enabled=bool(row["enabled"]), quota_limit=row["quota_limit"], quota_used=row["quota_used"],
                          created_at=row["created_at"], last_used_at=row["last_used_at"])

    async def has_users(self) -> bool:
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT COUNT(*) FROM users")
        row = await cursor.fetchone()
        return row[0] > 0

    # --- User Authentication & Password ---
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Verify password hash and return User if valid."""
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        if not row:
            return None
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if hashed != row["password_hash"]:
            return None
        return self._row_to_user(row)

    async def change_password(self, user_id: int, new_password: str) -> bool:
        """Update user password. Hash new password with SHA256."""
        if not self._db: await self.init()
        hashed = hashlib.sha256(new_password.encode()).hexdigest()
        now = time.time()
        try:
            await self._db.execute(
                "UPDATE users SET password_hash = ?, last_login = ? WHERE id = ?",
                (hashed, now, user_id)
            )
            await self._db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to change password: {e}")
            return False

    # --- User Lookup ---
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Find user by email."""
        if not self._db: await self.init()
        cursor = await self._db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def list_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """Paginated user list ordered by id DESC."""
        if not self._db: await self.init()
        cursor = await self._db.execute(
            "SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )
        rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    async def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user fields. Allowed: is_active, is_admin, email, role."""
        if not self._db: await self.init()
        # Disallowed fields
        disallowed = {"id", "username", "hashed_password", "sso_provider", "sso_provider_id"}
        allowed = {"is_active", "is_admin", "email", "role", "balance", "is_super_admin"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        
        if not updates:
            return await self.get_user_by_id(user_id)
        
        # Handle boolean conversion
        for key in ("is_active", "is_admin", "is_super_admin"):
            if key in updates:
                updates[key] = 1 if updates[key] else 0
        
        updates["updated_at"] = time.time()
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [user_id]
        
        try:
            await self._db.execute(
                f"UPDATE users SET {set_clause} WHERE id = ?",
                values
            )
            await self._db.commit()
            return await self.get_user_by_id(user_id)
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return None

    async def delete_user(self, user_id: int) -> bool:
        """Delete user. Return True if row affected, False if not found."""
        if not self._db: await self.init()
        try:
            cursor = await self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            await self._db.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            return False

    # --- SSO User Management ---
    async def get_user_by_sso(self, provider: str, provider_id: str) -> Optional[User]:
        """Find user by SSO provider and provider_id."""
        if not self._db: await self.init()
        cursor = await self._db.execute(
            "SELECT * FROM users WHERE sso_provider = ? AND sso_provider_id = ?",
            (provider, provider_id)
        )
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def create_sso_user(
        self,
        username: str,
        email: str,
        sso_provider: str,
        sso_provider_id: str,
        is_admin: bool = False,
        is_super_admin: bool = False
    ) -> Optional[User]:
        """Create user from SSO. Generate random password hash (SSO users don't have passwords)."""
        if not self._db: await self.init()
        # Generate random password hash for SSO users
        hashed = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()
        now = time.time()
        role = "admin" if is_admin else "user"
        try:
            cursor = await self._db.execute(
                """INSERT INTO users (username, email, hashed_password, is_admin, is_super_admin, 
                   role, sso_provider, sso_provider_id, created_at, updated_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (username, email, hashed, 1 if is_admin else 0, 1 if is_super_admin else 0,
                 role, sso_provider, sso_provider_id, now, now)
            )
            await self._db.commit()
            return await self.get_user_by_id(cursor.lastrowid)
        except Exception as e:
            logger.error(f"Failed to create SSO user: {e}")
            return None

    # --- Redemption Codes ---
    async def list_redemption_codes(self, limit: int = 100) -> List[RedemptionCode]:
        """List redemption codes ordered by id DESC."""
        if not self._db: await self.init()
        cursor = await self._db.execute(
            "SELECT * FROM redemption_codes ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_redemption_code(r) for r in rows]

    def _row_to_redemption_code(self, row) -> RedemptionCode:
        return RedemptionCode(
            id=row["id"], code=row["code"], amount=row["amount"],
            is_used=bool(row["is_used"]), used_by=row["used_by"], used_at=row["used_at"],
            created_at=row["created_at"]
        )
