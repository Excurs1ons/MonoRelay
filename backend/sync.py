"""基于 Gist 的配置同步。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("prisma.sync")

GIST_FILENAME = "config.yml"
GIST_STATS_FILENAME = "stats.json"
GIST_DESCRIPTION = "MonoRelay Configuration"


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

    async def push(self, content: str, stats_content: Optional[str] = None) -> bool:
        """推送配置和统计数据到 Gist。如果 gist_id 为空则创建新的。"""
        try:
            files = {GIST_FILENAME: {"content": content}}
            if stats_content is not None:
                files[GIST_STATS_FILENAME] = {"content": stats_content}

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
                        logger.info(f"Gist 已创建: {self._gist_id}")
                        return True
                    else:
                        logger.error(f"创建 Gist 失败: {resp.status_code} {resp.text}")
                        return False
                else:
                    # 更新已有 Gist
                    resp = await client.patch(
                        f"https://api.github.com/gists/{self._gist_id}",
                        headers=self._headers,
                        json={"files": files},
                        timeout=15.0,
                    )
                    if resp.status_code == 200:
                        logger.info(f"Gist 已更新: {self._gist_id}")
                        return True
                    else:
                        logger.error(f"更新 Gist 失败: {resp.status_code} {resp.text}")
                        return False
        except Exception as e:
            logger.error(f"Gist 推送异常: {e}")
            return False

    async def find_gist_by_description(self) -> Optional[str]:
        """通过描述查找 MonoRelay Configuration 的 Gist。"""
        try:
            async with httpx.AsyncClient() as client:
                page = 1
                while page <= 3:  # 最多查找前 3 页（30 个 Gist）
                    resp = await client.get(
                        f"https://api.github.com/gists?per_page=10&page={page}",
                        headers=self._headers,
                        timeout=10.0,
                    )
                    if resp.status_code != 200:
                        break
                    gists = resp.json()
                    if not gists:
                        break
                    for g in gists:
                        if g.get("description") == GIST_DESCRIPTION:
                            logger.info(f"找到 Gist: {g['id']}")
                            return g["id"]
                    page += 1
            return None
        except Exception as e:
            logger.error(f"查找 Gist 失败: {e}")
            return None

    async def pull(self) -> dict[str, str]:
        """从 Gist 拉取配置和统计数据。返回包含 'config' 和可选 'stats' 的字典。"""
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

                    if result:
                        logger.info(f"Gist 已拉取: {self._gist_id}")
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
