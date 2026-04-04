"""Configuration management with hot-reload support."""
from __future__ import annotations

import copy
import logging
import os
from pathlib import Path
from typing import Optional

import yaml
from watchfiles import awatch

from .models import AppConfig

logger = logging.getLogger("prisma.config")

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yml")


class ConfigManager:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self._config_path = Path(config_path).resolve()
        self._config: Optional[AppConfig] = None
        self._callbacks: list[callable] = []

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
            logger.warning(f"Config file not found at {self._config_path}, using defaults")
            return AppConfig()

        with open(self._config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        config = AppConfig(**raw)
        logger.info(f"Configuration loaded from {self._config_path}")
        logger.info(f"Enabled providers: {[k for k, v in config.providers.items() if v.enabled]}")
        return config

    def reload(self) -> AppConfig:
        old = self._config
        self._config = self._load()
        for cb in self._callbacks:
            try:
                cb(self._config, old)
            except Exception as e:
                logger.error(f"Config reload callback error: {e}")
        return self._config

    def on_reload(self, callback: callable):
        self._callbacks.append(callback)

    async def watch(self):
        if not self._config_path.exists():
            return
        async for changes in awatch(str(self._config_path), stop_event=None):
            for change_type, path in changes:
                logger.info(f"Config file changed: {change_type.name} {path}")
                self.reload()
                break

    def get_provider(self, name: str):
        return self.config.providers.get(name)

    def get_enabled_providers(self) -> dict[str, object]:
        return {k: v for k, v in self.config.providers.items() if v.enabled}

    def save(self, config: AppConfig):
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(config.model_dump(mode="json"), f, default_flow_style=False, allow_unicode=True)
        self._config = config
        logger.info(f"Configuration saved to {self._config_path}")
