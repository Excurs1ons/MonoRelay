"""Gist-based config sync."""
from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger("prisma.sync")

GIST_FILENAME = "config.yml"
GIST_DESCRIPTION = "PrismaAPIRelay Configuration"


class GistSync:
    def __init__(self, token: str, gist_id: str = ""):
        self._token = token
        self._gist_id = gist_id
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @property
    def gist_id(self) -> str:
        return self._gist_id

    async def push(self, content: str) -> bool:
        """Push config content to Gist. Creates new if gist_id is empty."""
        try:
            async with httpx.AsyncClient() as client:
                if not self._gist_id:
                    # Create new secret gist
                    resp = await client.post(
                        "https://api.github.com/gists",
                        headers=self._headers,
                        json={
                            "description": GIST_DESCRIPTION,
                            "public": False,
                            "files": {GIST_FILENAME: {"content": content}},
                        },
                        timeout=15.0,
                    )
                    if resp.status_code == 201:
                        data = resp.json()
                        self._gist_id = data["id"]
                        logger.info(f"Gist created: {self._gist_id}")
                        return True
                    else:
                        logger.error(f"Failed to create gist: {resp.status_code} {resp.text}")
                        return False
                else:
                    # Update existing gist
                    resp = await client.patch(
                        f"https://api.github.com/gists/{self._gist_id}",
                        headers=self._headers,
                        json={"files": {GIST_FILENAME: {"content": content}}},
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        logger.info(f"Gist updated: {self._gist_id}")
                        return True
                    else:
                        logger.error(f"Failed to update gist: {resp.status_code} {resp.text}")
                        return False
        except Exception as e:
            logger.error(f"Gist push error: {e}")
            return False

    async def pull(self) -> str | None:
        """Pull config content from Gist. Returns content or None on failure."""
        if not self._gist_id:
            logger.error("No gist_id configured for pull")
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.github.com/gists/{self._gist_id}",
                    headers=self._headers,
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    file_data = data.get("files", {}).get(GIST_FILENAME)
                    if file_data and "content" in file_data:
                        logger.info(f"Gist pulled: {self._gist_id}")
                        return file_data["content"]
                    logger.error(f"Gist file '{GIST_FILENAME}' not found")
                    return None
                else:
                    logger.error(f"Failed to pull gist: {resp.status_code} {resp.text}")
                    return None
        except Exception as e:
            logger.error(f"Gist pull error: {e}")
            return None

    async def get_history(self) -> list[dict]:
        """Get gist commit history."""
        if not self._gist_id:
            return []
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.github.com/gists/{self._gist_id}/commits",
                    headers=self._headers,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    commits = resp.json()
                    return [
                        {
                            "version": c.get("version", "")[:7],
                            "committed_at": c.get("committed_at", ""),
                            "change_status": c.get("change_status", {}),
                        }
                        for c in commits[:20]
                    ]
                return []
        except Exception:
            return []
