from __future__ import annotations

import json
from pathlib import Path

from models import AccountConfig, AppSettings


class AccountsStorage:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def load_accounts(self) -> list[AccountConfig]:
        if not self.file_path.exists():
            return []

        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        accounts_raw = payload.get("accounts", []) if isinstance(payload, dict) else []
        accounts: list[AccountConfig] = []
        for item in accounts_raw:
            if not isinstance(item, dict):
                continue
            account = AccountConfig.from_dict(item)
            if account.email:
                accounts.append(account)
        return accounts

    def save_accounts(self, accounts: list[AccountConfig]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [account.to_dict() for account in accounts]}
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def parse_txt_accounts(
        self,
        file_path: Path,
        common_token: str = "",
        name_prefix: str = "Импорт",
    ) -> list[AccountConfig]:
        content = file_path.read_text(encoding="utf-8").splitlines()
        accounts: list[AccountConfig] = []
        counter = 1

        for line in content:
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue

            email, separator, password = raw_line.partition(":")
            if not separator:
                continue

            account = AccountConfig(
                email=email.strip(),
                password=password.strip(),
                bearer_token=common_token.strip(),
                name=f"{name_prefix} {counter}".strip(),
            )
            if account.email and account.password:
                accounts.append(account)
                counter += 1

        return accounts

    @staticmethod
    def merge_accounts(
        existing_accounts: list[AccountConfig],
        imported_accounts: list[AccountConfig],
    ) -> tuple[list[AccountConfig], int, int]:
        existing_map = {account.email.lower(): account for account in existing_accounts}
        added = 0
        updated = 0

        for imported in imported_accounts:
            key = imported.email.lower()
            if key in existing_map:
                current = existing_map[key]
                current.password = imported.password
                if imported.bearer_token:
                    current.bearer_token = imported.bearer_token
                if imported.name:
                    current.name = imported.name
                if imported.category:
                    current.category = imported.category
                updated += 1
                continue

            existing_accounts.append(imported)
            existing_map[key] = imported
            added += 1

        return existing_accounts, added, updated


class AppSettingsStorage:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def load_settings(self) -> AppSettings:
        if not self.file_path.exists():
            return AppSettings()

        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return AppSettings()

        if not isinstance(payload, dict):
            return AppSettings()
        return AppSettings.from_dict(payload)

    def save_settings(self, settings: AppSettings) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
