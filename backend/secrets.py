import aiosqlite
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("monorelay.secrets")

db_path = Path(__file__).parent.parent / "data" / "secrets.db"


class SecretsManager:
    def __init__(self, db_path: Path = db_path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await self._db.commit()
        logger.info("Secrets manager initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    async def set(self, key: str, value: str):
        if not self._db:
            await self.init()
        import time
        await self._db.execute(
            "INSERT OR REPLACE INTO secrets (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time())
        )
        await self._db.commit()
        logger.info(f"Secret saved: {key}")

    async def get(self, key: str) -> Optional[str]:
        if not self._db:
            await self.init()
        async with self._db.execute(
            "SELECT value FROM secrets WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def delete(self, key: str):
        if not self._db:
            await self.init()
        await self._db.execute("DELETE FROM secrets WHERE key = ?", (key,))
        await self._db.commit()

    async def get_all(self) -> dict[str, str]:
        if not self._db:
            await self.init()
        secrets = {}
        async with self._db.execute("SELECT key, value FROM secrets") as cursor:
            async for row in cursor:
                secrets[row[0]] = row[1]
        return secrets


secrets_manager = SecretsManager()