from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class LetterBody:
    text: str = ""
    html: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LetterBody":
        payload = payload or {}
        return cls(
            text=str(payload.get("text") or ""),
            html=str(payload.get("html") or ""),
        )


@dataclass(slots=True)
class Letter:
    id: str
    sender: str
    sender_name: str
    subject: str
    body: LetterBody
    star: bool
    date: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Letter":
        if not isinstance(payload, dict):
            raise ValueError("Письмо должно быть объектом.")

        return cls(
            id=str(payload.get("id") or ""),
            sender=str(payload.get("sender") or ""),
            sender_name=str(payload.get("sender_name") or ""),
            subject=str(payload.get("subject") or "(Без темы)"),
            body=LetterBody.from_dict(payload.get("letter")),
            star=bool(payload.get("star", False)),
            date=int(payload.get("date") or 0),
        )

    @property
    def formatted_date(self) -> str:
        if self.date <= 0:
            return "Неизвестно"
        return datetime.fromtimestamp(self.date).strftime("%d.%m.%Y %H:%M:%S")


@dataclass(slots=True)
class AccountConfig:
    email: str
    password: str
    bearer_token: str = ""
    name: str = ""
    category: str = ""
    favorite: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def display_name(self) -> str:
        return self.name.strip() or self.email

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AccountConfig":
        return cls(
            id=str(payload.get("id") or uuid4()),
            email=str(payload.get("email") or "").strip(),
            password=str(payload.get("password") or ""),
            bearer_token=str(payload.get("bearer_token") or ""),
            name=str(payload.get("name") or ""),
            category=str(payload.get("category") or ""),
            favorite=bool(payload.get("favorite", False)),
        )


@dataclass(slots=True)
class LetterFilters:
    search: str = ""
    star_only: bool = False

    def to_payload(self) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if self.search.strip():
            filters["search"] = self.search.strip()
        if self.star_only:
            filters["star"] = True
        return filters


@dataclass(slots=True)
class AppSettings:
    api_key: str = ""
    bulk_refresh_batch_size: int = 10
    bulk_refresh_pause_seconds: float = 2.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AppSettings":
        payload = payload or {}
        return cls(
            api_key=str(payload.get("api_key") or "").strip(),
            bulk_refresh_batch_size=max(1, int(payload.get("bulk_refresh_batch_size") or 10)),
            bulk_refresh_pause_seconds=max(0.0, float(payload.get("bulk_refresh_pause_seconds") or 2.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key": self.api_key,
            "bulk_refresh_batch_size": self.bulk_refresh_batch_size,
            "bulk_refresh_pause_seconds": self.bulk_refresh_pause_seconds,
        }
