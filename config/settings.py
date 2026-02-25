from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    cg_api_key: str = Field(..., description="CoinGlass API Key")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    db_path: str = "data/whale_orders.db"

    # polling intervals (seconds)
    poll_interval_large_order: int = 10
    poll_interval_liquidation: int = 10
    poll_interval_whale_alert: int = 10
    poll_interval_onchain: int = 60

    exchanges: str = "Binance,OKX,Bybit"

    large_order_threshold: float = 500_000
    liquidation_threshold: float = 100_000

    webhook_urls: str = ""

    ws_push_enabled: bool = True
    webhook_push_enabled: bool = False

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
    }

    @property
    def exchange_list(self) -> list[str]:
        return [e.strip() for e in self.exchanges.split(",") if e.strip()]

    @property
    def webhook_url_list(self) -> list[str]:
        if not self.webhook_urls:
            return []
        return [u.strip() for u in self.webhook_urls.split(",") if u.strip()]

    @property
    def abs_db_path(self) -> Path:
        p = Path(self.db_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cg_rest_base(self) -> str:
        return "https://open-api-v4.coinglass.com"

    @property
    def cg_ws_url(self) -> str:
        return f"wss://open-ws.coinglass.com/ws-api?cg-api-key={self.cg_api_key}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
