"""同步凭证本地存储。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("monorelay.sync_storage")

def _get_exe_dir() -> Path:
    """获取可执行文件所在目录（兼容 PyInstaller 打包）。"""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


DEFAULT_STORAGE_PATH = _get_exe_dir() / "data" / "sync.json"


class SyncStorage:
    """将 GitHub Token 等敏感凭证存储在本地 data/sync.json，不写入 config.yml。"""

    def __init__(self, storage_path: Path = DEFAULT_STORAGE_PATH):
        self._path = storage_path
        self._data: dict = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"同步凭证已加载: {self._path}")
            except Exception as e:
                logger.warning(f"同步凭证加载失败，使用空值: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        logger.info(f"同步凭证已保存: {self._path}")

    @property
    def gist_token(self) -> str:
        return self._data.get("gist_token", "")

    @gist_token.setter
    def gist_token(self, value: str):
        self._data["gist_token"] = value
        self._save()

    def clear_token(self):
        self._data.pop("gist_token", None)
        self._save()

    @property
    def has_token(self) -> bool:
        return bool(self._data.get("gist_token", ""))
