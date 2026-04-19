"""Request logging with async SQLite storage."""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import aiosqlite

logger = logging.getLogger("monorelay.logger")


class RequestLogger:
    def __init__(self, db_path: str = "./data/requests.db", max_age_days: int = 30, content_preview_length: int = 200):
        self.db_path = db_path
        self.max_age_days = max_age_days
        self.content_preview_length = content_preview_length
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                key_label TEXT,
                status_code INTEGER,
                latency_ms REAL,
                first_token_ms REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost REAL,
                request_preview TEXT,
                response_preview TEXT,
                request_full TEXT,
                response_full TEXT,
                error_message TEXT,
                error_type TEXT,
                error_code TEXT,
                error_details TEXT,
                streaming INTEGER DEFAULT 0,
                temperature REAL,
                top_p REAL,
                presence_penalty REAL,
                frequency_penalty REAL,
                max_tokens INTEGER
            )
            """
        )
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)
            """
        )
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model)
            """
        )
        await self._db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_provider ON requests(provider)
            """
        )
        # 迁移：为已有数据库添加 first_token_ms 字段
        try:
            await self._db.execute(
                "ALTER TABLE requests ADD COLUMN first_token_ms REAL"
            )
        except Exception:
            pass
        # 迁移：添加请求参数字段
        for col in ["temperature REAL", "top_p REAL", "presence_penalty REAL", "frequency_penalty REAL", "max_tokens INTEGER"]:
            try:
                await self._db.execute(f"ALTER TABLE requests ADD COLUMN {col}")
            except Exception:
                pass
        # 迁移：添加错误详情字段
        for col in ["error_type TEXT", "error_code TEXT", "error_details TEXT"]:
            try:
                await self._db.execute(f"ALTER TABLE requests ADD COLUMN {col}")
            except Exception:
                pass
        # 迁移：添加完整请求/响应字段
        for col in ["request_full TEXT", "response_full TEXT"]:
            try:
                await self._db.execute(f"ALTER TABLE requests ADD COLUMN {col}")
            except Exception:
                pass
        await self._db.commit()
        logger.info(f"Request logger initialized with database at {self.db_path}")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def log_request(
        self,
        model: str,
        provider: str,
        key_label: Optional[str],
        status_code: int,
        latency_ms: float,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
        request_preview: Optional[str] = None,
        response_preview: Optional[str] = None,
        request_full: Optional[str] = None,
        response_full: Optional[str] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        error_code: Optional[str] = None,
        error_details: Optional[str] = None,
        streaming: bool = False,
        first_token_ms: Optional[float] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        if not self._db:
            await self.init()

        await self._db.execute(
            """
            INSERT INTO requests (
                timestamp, model, provider, key_label, status_code, latency_ms,
                first_token_ms, input_tokens, output_tokens, estimated_cost, request_preview,
                response_preview, request_full, response_full, error_message, error_type, error_code, error_details,
                streaming, temperature, top_p, presence_penalty, frequency_penalty, max_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                model,
                provider,
                key_label,
                status_code,
                latency_ms,
                first_token_ms,
                input_tokens,
                output_tokens,
                estimated_cost,
                request_preview,
                response_preview,
                request_full,
                response_full,
                error_message,
                error_type,
                error_code,
                error_details,
                1 if streaming else 0,
                temperature,
                top_p,
                presence_penalty,
                frequency_penalty,
                max_tokens,
            ),
        )
        await self._db.commit()

    async def cleanup_old_entries(self):
        if not self._db:
            return
        cutoff = time.time() - (self.max_age_days * 86400)
        cursor = await self._db.execute("DELETE FROM requests WHERE timestamp < ?", (cutoff,))
        await self._db.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info(f"Cleaned up {deleted} old log entries")

    async def get_recent_requests(self, limit: int = 50) -> list[dict]:
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT * FROM requests ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def clear_all(self):
        if not self._db:
            return
        await self._db.execute("DELETE FROM requests")
        await self._db.commit()
        logger.info("All request logs cleared")

    async def get_stats_summary(self) -> dict:
        if not self._db:
            return {"total_requests": 0, "total_cost": 0.0, "avg_latency_ms": 0.0}

        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) as total_requests,
                COALESCE(SUM(estimated_cost), 0) as total_cost,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens
            FROM requests
            """
        )
        row = await cursor.fetchone()
        return dict(row)

    async def get_provider_stats(self) -> list[dict]:
        if not self._db:
            return []
        cursor = await self._db.execute(
            """
            SELECT
                provider,
                COUNT(*) as request_count,
                COALESCE(SUM(estimated_cost), 0) as total_cost,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
                COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count
            FROM requests
            GROUP BY provider
            ORDER BY request_count DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_model_stats(self) -> list[dict]:
        if not self._db:
            return []
        cursor = await self._db.execute(
            """
            SELECT
                model,
                COUNT(*) as request_count,
                COALESCE(SUM(estimated_cost), 0) as total_cost,
                COALESCE(AVG(latency_ms), 0) as avg_latency_ms
            FROM requests
            GROUP BY model
            ORDER BY request_count DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    def truncate_content(self, content: str) -> str:
        if not content:
            return ""
        if len(content) <= self.content_preview_length:
            return content
        return content[: self.content_preview_length] + "..."
