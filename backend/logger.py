"""Request logging with async SQLite storage."""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import aiosqlite

logger = logging.getLogger("monorelay.logger")


class RequestLogger:
    def __init__(self, db_path: str = "./data/requests.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self.content_preview_length = 200

    async def init(self):
        """Initialize database and ensure columns exist."""
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                user_id INTEGER,
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
        
        # Migration: Add missing columns if any
        # 1. Full JSON columns and new multi-tenant columns
        new_cols = [
            ("request_full", "TEXT"),
            ("response_full", "TEXT"),
            ("user_id", "INTEGER"),
            ("error_type", "TEXT"),
            ("error_code", "TEXT"),
            ("error_details", "TEXT")
        ]
        
        for col_name, col_type in new_cols:
            try:
                await self._db.execute(f"ALTER TABLE requests ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_requests_provider ON requests(provider)")
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_requests_user ON requests(user_id)")
        
        await self._db.commit()

    async def log_request(
        self,
        model: str,
        provider: str,
        user_id: Optional[int] = None,
        key_label: Optional[str] = None,
        status_code: Optional[int] = None,
        latency_ms: Optional[float] = None,
        first_token_ms: Optional[float] = None,
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
                timestamp, user_id, model, provider, key_label, status_code, latency_ms,
                first_token_ms, input_tokens, output_tokens, estimated_cost, request_preview,
                response_preview, request_full, response_full, error_message, error_type, error_code, error_details,
                streaming, temperature, top_p, presence_penalty, frequency_penalty, max_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                user_id,
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

    async def get_recent_requests(self, limit: int = 50, user_id: Optional[int] = None) -> list[dict]:
        if not self._db:
            await self.init()
        
        query = "SELECT * FROM requests"
        params = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(user_id)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = await self._db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def clear_all(self, user_id: Optional[int] = None):
        if not self._db:
            await self.init()

        if user_id is not None:
            await self._db.execute("DELETE FROM requests WHERE user_id = ?", (user_id,))
        else:
            await self._db.execute("DELETE FROM requests")
        await self._db.commit()
        deleted = self._db.total_changes
        if deleted:
            logger.info(f"Cleaned up {deleted} log entries")

    async def get_stats_summary(self) -> dict:
        if not self._db:
            logger.info("get_stats_summary: DB not initialized, initializing now")
            await self.init()

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
        result = dict(zip([c[0] for c in cursor.description], row))
        result["input_tokens"] = result.pop("total_input_tokens", 0)
        result["output_tokens"] = result.pop("total_output_tokens", 0)
        return result

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
