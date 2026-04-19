"""基于 Gist 的配置同步。"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("monorelay.sync")

GIST_FILENAME = "config.yml"
GIST_STATS_FILENAME = "stats.json"
GIST_DESCRIPTION = "MonoRelay Configuration"

SECRET_KEYS = {
    "client_secret",
    "github_client_secret",
    "google_client_secret",
    "local_sso_secret",
    "jwt_secret",
    "turnstile_secret_key",
    "access_key",
    "sync_token",
    "gist_token",
    "webdav_password",
}


def filter_secrets_from_yaml(content: str) -> str:
    """从 YAML 配置中移除 secrets，只保留下游 API keys。"""
    lines = content.split("\n")
    in_secret_block = False
    skip_count = 0
    
    result = []
    for line in lines:
        stripped = line.strip()
        
        if skip_count > 0:
            skip_count -= 1
            continue
        
        if not line.startswith(" ") and not line.startswith("\t"):
            in_secret_block = False
        
        is_secret = False
        for secret_key in SECRET_KEYS:
            if re.match(rf"^\s*{secret_key}:\s*", line) or re.match(rf"^\s*-\s*{secret_key}:\s*", line):
                is_secret = True
                break
        
        if is_secret:
            if ":" in line and not line.strip().endswith(":"):
                key = line.split(":")[0].strip().replace("-", "").strip()
                if any(s in key.lower() for s in SECRET_KEYS):
                    continue
            indent = len(line) - len(line.lstrip())
            result.append(" " * indent + "# " + line.strip() + "  # filtered")
            continue
            
        result.append(line)
    
    return "\n".join(result)


class GistSync:
    def __init__(self, token: str, gist_id: str = ""):
        # 清理 Token：移除所有空白字符
        self._token = "".join(token.split())
        self._gist_id = gist_id
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @property
    def gist_id(self) -> str:
        return self._gist_id

    async def push(self, content: str, stats_content: Optional[str] = None) -> tuple[bool, str]:
        try:
            files = {}
            if content:
                files[GIST_FILENAME] = {"content": filter_secrets_from_yaml(content)}
            if stats_content is not None:
                files[GIST_STATS_FILENAME] = {"content": stats_content}

            if not files:
                return True, ""

            async with httpx.AsyncClient() as client:
                if not self._gist_id:
                    # 创建新的私密 Gist
                    resp = await client.post(
                        "https://api.github.com/gists",
                        headers=self._headers,
                        json={
                            "description": GIST_DESCRIPTION,
                            "public": False,
                            "files": files,
                        },
                        timeout=15.0,
                    )
                    if resp.status_code == 201:
                        data = resp.json()
                        self._gist_id = data["id"]
                        version = data.get("history", [{}])[0].get("version", "")
                        logger.info(f"Gist 已创建: {self._gist_id}, version: {version}")
                        return True, version
                    else:
                        logger.error(f"创建 Gist 失败: {resp.status_code} {resp.text}")
                        return False, ""
                else:
                    # 更新已有 Gist
                    resp = await client.patch(
                        f"https://api.github.com/gists/{self._gist_id}",
                        headers=self._headers,
                        json={"files": files},
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        version = data.get("history", [{}])[0].get("version", "")
                        logger.info(f"Gist 已更新: {self._gist_id}, version: {version}")
                        return True, version
                    else:
                        logger.error(f"更新 Gist 失败: {resp.status_code} {resp.text}")
                        return False, ""
        except Exception as e:
            logger.error(f"Gist 推送异常: {e}")
            return False, ""

    async def pull(self) -> dict[str, str]:
        """从 Gist 拉取配置和统计数据。返回字典，包含 'config', 'stats' 和 'version'。"""
        if not self._gist_id:
            logger.error("未配置 gist_id，无法拉取")
            return {}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.github.com/gists/{self._gist_id}",
                    headers=self._headers,
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = {}
                    file_data = data.get("files", {})

                    config_file = file_data.get(GIST_FILENAME)
                    if config_file and "content" in config_file:
                        result["config"] = config_file["content"]

                    stats_file = file_data.get(GIST_STATS_FILENAME)
                    if stats_file and "content" in stats_file:
                        result["stats"] = stats_file["content"]

                    result["version"] = data.get("history", [{}])[0].get("version", "")

                    if result:
                        logger.info(f"Gist 已拉取: {self._gist_id}, version: {result['version']}")
                    else:
                        logger.error("未找到 Gist 文件")
                    return result
                else:
                    logger.error(f"拉取 Gist 失败: {resp.status_code} {resp.text}")
                    return {}
        except Exception as e:
            logger.error(f"Gist 拉取异常: {e}")
            return {}

    async def pull_stats(self) -> Optional[str]:
        """仅拉取统计数据。"""
        data = await self.pull()
        return data.get("stats")

    async def push_stats_only(self, stats_content: str) -> bool:
        """仅推送统计数据到已有 Gist。"""
        if not self._gist_id:
            logger.error("未配置 gist_id，无法推送统计")
            return False
        return await self.push("", stats_content)

    async def get_info(self) -> Optional[dict]:
        """获取 Gist 的元数据（创建时间、更新时间）。"""
        if not self._gist_id:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.github.com/gists/{self._gist_id}",
                    headers=self._headers,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "id": data.get("id"),
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "description": data.get("description"),
                        "version": data.get("history", [{}])[0].get("version", ""),
                    }
                return None
        except Exception as e:
            logger.error(f"获取 Gist 信息失败: {e}")
            return None

    async def get_history(self) -> list[dict]:
        """获取 Gist 提交历史。"""
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
