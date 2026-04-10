"""WebDAV-based configuration backup module."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("monorelay.sync_webdav")


class WebDAVSync:
    def __init__(self, base_url: str, username: str = "", password: str = ""):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._auth = (username, password) if username else None

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/xml; charset=utf-8",
            "User-Agent": "MonoRelay/1.0",
        }

    async def push(self, filename: str, content: str) -> bool:
        url = f"{self.base_url}/{filename.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    "PUT", url, content=content.encode("utf-8"),
                    headers=self._headers(), auth=self._auth,
                )
                if resp.status_code in (200, 201, 204):
                    logger.info(f"WebDAV push succeeded: {filename}")
                    return True
                logger.error(f"WebDAV push failed: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"WebDAV push error: {e}")
            return False

    async def pull(self, filename: str) -> Optional[str]:
        url = f"{self.base_url}/{filename.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=self._headers(), auth=self._auth)
                if resp.status_code == 200:
                    logger.info(f"WebDAV pull succeeded: {filename}")
                    return resp.text
                logger.warning(f"WebDAV pull failed: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"WebDAV pull error: {e}")
            return None

    async def list_files(self, path: str = "/") -> list[str]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        body = '<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    "PROPFIND", url, content=body,
                    headers={**self._headers(), "Depth": "1"},
                    auth=self._auth,
                )
                if resp.status_code not in (200, 207):
                    return []
                files = []
                try:
                    root = ET.fromstring(resp.text)
                    ns = {"d": "DAV:"}
                    for href in root.findall(".//d:href", ns):
                        f = href.text or ""
                        if f and f != path and f != f"{path}/":
                            files.append(f.lstrip("/"))
                except ET.ParseError:
                    pass
                return files
        except Exception as e:
            logger.error(f"WebDAV list error: {e}")
            return []

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.request(
                    "PROPFIND", self.base_url,
                    content='<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>',
                    headers={**self._headers(), "Depth": "0"},
                    auth=self._auth,
                )
                if resp.status_code in (200, 207):
                    return {"ok": True, "message": "Connection successful"}
                return {"ok": False, "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}
