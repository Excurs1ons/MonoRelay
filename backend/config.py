"""配置管理，支持热重载。"""
from __future__ import annotations

import copy
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from watchfiles import awatch

from .models import AppConfig
from .secrets import secrets_manager
from .tenant_manager import TenantManager

logger = logging.getLogger("monorelay.config")

def _get_exe_dir() -> str:
    """获取可执行文件所在目录（兼容 PyInstaller 打包）。"""
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.join(os.path.dirname(__file__), "..")

DEFAULT_CONFIG_PATH = os.path.join(_get_exe_dir(), "config.yml")


class ConfigManager:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, tenant_manager: Optional[TenantManager] = None):
        self._config_path = Path(config_path).resolve()
        self._config: Optional[AppConfig] = None
        self._callbacks: list[callable] = []
        self._saving = False
        self._tenant_manager = tenant_manager  # 保存期间阻止重载

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config = self._load()
        return self._config

    @property
    def config_path(self) -> Path:
        return self._config_path

    def _load(self) -> AppConfig:
        if not self._config_path.exists():
            logger.warning(f"配置文件不存在: {self._config_path}，使用默认值")
            return AppConfig()

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            logger.warning(f"配置文件格式错误: {self._config_path}，使用默认值")
            raw = {}

        config = AppConfig(**raw)

        if not config.server.get('access_key'):
            import uuid
            config.server['access_key'] = str(uuid.uuid4())
            logger.warning(f"已生成随机 access_key")

        import sqlite3
        db_path = secrets_manager.db_path
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM secrets")
                for row in cur.fetchall():
                    key, value = row["key"], row["value"]
                    if key == "sso_provider":
                        config.sso['provider'] = value
                    elif key == "github_client_id":
                        config.sso['github_client_id'] = value
                    elif key == "github_client_secret":
                        config.sso['github_client_secret'] = value
                    elif key == "sso_client_secret":
                        config.sso['client_secret'] = value
                    elif key == "google_client_secret":
                        config.sso['google_client_secret'] = value
                    elif key == "local_sso_secret":
                        config.sso['local_sso_secret'] = value
                    elif key == "jwt_secret":
                        config.server['jwt_secret'] = value
                    elif key == "turnstile_secret_key":
                        config.server['turnstile_secret_key'] = value
                conn.close()
            except Exception as e:
                logger.warning(f"加载secrets失败: {e}")

        logger.info(f"配置已加载: {self._config_path}")
        logger.info(f"已启用的提供商: {[k for k, v in config.providers.items() if v.enabled]}")
        return config

    def reload(self) -> AppConfig:
        if self._saving:
            return self._config  # 保存期间跳过重载
        old = self._config
        self._config = self._load()
        for cb in self._callbacks:
            try:
                cb(self._config, old)
            except Exception as e:
                logger.error(f"配置重载回调异常: {e}")
        return self._config

    def on_reload(self, callback: callable):
        self._callbacks.append(callback)

    async def watch(self):
        if not self._config_path.exists():
            return
        async for changes in awatch(str(self._config_path), stop_event=None):
            for change_type, path in changes:
                logger.info(f"配置文件变更: {change_type.name} {path}")
                self.reload()
                break

    def get_provider(self, name: str):
        return self.config.providers.get(name)

    def get_enabled_providers(self) -> dict[str, object]:
        return {k: v for k, v in self.config.providers.items() if v.enabled}

    def save(self, config: AppConfig):
        self._saving = True
        try:
            data = config.model_dump(mode="json")
            # 确保 sync 字段被正确序列化（不含 token，token 存储在本地 sync.json）
            if hasattr(config, 'sync'):
                data['sync'] = {
                    'enabled': config.sync.get('enabled', False),
                    'gist_id': config.sync.get('gist_id', ''),
                    'gist_id_stats': config.sync.get('gist_id_stats', ''),
                }
            # 原子写入：先写临时文件再重命名，避免 watchfiles 读到不完整的文件
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self._config_path.parent, suffix=".tmp")
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                os.replace(tmp_path, str(self._config_path))
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
            self._config = config
            logger.info(f"配置已保存: {self._config_path}")
        finally:
            self._saving = False

    async def get_config_for_user(self, user_id: Optional[int] = None) -> AppConfig:
        """Get config for a specific user, checking tenant-specific config first."""
        if user_id and self._tenant_manager:
            tenant_config = await self._tenant_manager.get_tenant_config(user_id)
            if tenant_config:
                logger.info(f"Using tenant-specific config for user {user_id}")
                return self._build_tenant_config(tenant_config)
        
        return self.config

    def _build_tenant_config(self, tenant_config) -> AppConfig:
        """Build an AppConfig from tenant-specific config."""
        import json
        config_data = json.loads(tenant_config.config_json)
        return AppConfig(**config_data)
