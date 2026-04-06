from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import Settings


@dataclass(frozen=True)
class CachedCredentials:
    api_key: str
    api_secret: str
    api_passphrase: str
    created_at: datetime
    expires_at: datetime | None = None

    def is_valid(self) -> bool:
        if self.expires_at is None:
            return True
        return datetime.now(timezone.utc) < self.expires_at


class PolymarketAuthClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: CachedCredentials | None = None

    def get_or_create_api_credentials(self) -> CachedCredentials | None:
        if self._cache is not None and self._cache.is_valid():
            return self._cache

        if self.settings.poly_api_key and self.settings.poly_api_secret and self.settings.poly_api_passphrase:
            self._cache = CachedCredentials(
                api_key=self.settings.poly_api_key,
                api_secret=self.settings.poly_api_secret,
                api_passphrase=self.settings.poly_api_passphrase,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            )
            return self._cache

        return None

    def save_credentials_to_env_file(self, path: str = ".env") -> bool:
        creds = self.get_or_create_api_credentials()
        if creds is None:
            return False

        env_path = Path(path)
        if not env_path.exists():
            return False

        content = env_path.read_text(encoding="utf-8")
        lines = [
            f"POLYMARKET_API_KEY={creds.api_key}",
            f"POLYMARKET_API_SECRET={creds.api_secret}",
            f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}",
        ]

        updated = content
        for line in lines:
            key = line.split("=", 1)[0]
            if f"{key}=" in updated:
                continue
            if not updated.endswith("\n"):
                updated += "\n"
            updated += line + "\n"

        if updated != content:
            env_path.write_text(updated, encoding="utf-8")
        return True
