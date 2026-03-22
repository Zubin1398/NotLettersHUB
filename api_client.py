from __future__ import annotations

from typing import Any

import requests

from models import AccountConfig, Letter, LetterFilters


class ApiClientError(Exception):
    """Человеко-понятная ошибка работы с API."""


class NotLettersClient:
    def __init__(self, base_url: str = "https://api.notletters.com", timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_letters(self, account: AccountConfig, filters: LetterFilters, api_key: str = "") -> list[Letter]:
        effective_token = account.bearer_token.strip() or api_key.strip()
        if not effective_token:
            raise ApiClientError("Не указан API-ключ. Добавьте его в настройках API или в аккаунте.")

        url = f"{self.base_url}/v1/letters"
        payload: dict[str, Any] = {
            "email": account.email,
            "password": account.password,
            "filters": filters.to_payload(),
        }
        headers = {
            "Authorization": f"Bearer {effective_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.Timeout as exc:
            raise ApiClientError("Сервер NotLetters не ответил вовремя.") from exc
        except requests.RequestException as exc:
            raise ApiClientError(f"Сетевая ошибка: {exc}") from exc

        if response.status_code in {401, 403}:
            raise ApiClientError("Невалидный Bearer token или доступ запрещён.")
        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise ApiClientError(f"Ошибка API {response.status_code}: {message}")

        try:
            body = response.json()
        except ValueError as exc:
            raise ApiClientError("API вернул некорректный JSON.") from exc

        letters_payload = body.get("data", {}).get("letters")
        if letters_payload is None:
            raise ApiClientError("В ответе API отсутствует поле data.letters.")
        if not isinstance(letters_payload, list):
            raise ApiClientError("Поле data.letters имеет неожиданный формат.")

        letters: list[Letter] = []
        for item in letters_payload:
            try:
                letters.append(Letter.from_dict(item))
            except (TypeError, ValueError) as exc:
                raise ApiClientError(f"Не удалось разобрать письмо: {exc}") from exc

        letters.sort(key=lambda letter: letter.date, reverse=True)
        return letters

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or "Неизвестная ошибка"

        if isinstance(payload, dict):
            for key in ("message", "error", "detail"):
                value = payload.get(key)
                if value:
                    return str(value)
        return response.text.strip() or "Неизвестная ошибка"
