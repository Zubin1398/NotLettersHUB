from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from models import AccountConfig, AppSettings


@dataclass(slots=True)
class AccountDialogValues:
    email: str
    password: str
    bearer_token: str
    name: str
    category: str


class AccountDialogForm:
    def __init__(self, account: AccountConfig | None = None) -> None:
        self.email = ft.TextField(
            label="Email",
            value=account.email if account else "",
            autofocus=True,
            border_radius=14,
        )
        self.password = ft.TextField(
            label="Пароль",
            value=account.password if account else "",
            password=True,
            can_reveal_password=True,
            border_radius=14,
        )
        self.bearer_token = ft.TextField(
            label="Bearer token аккаунта (опционально)",
            value=account.bearer_token if account else "",
            password=True,
            can_reveal_password=True,
            helper="Если поле пустое, будет использован глобальный API-ключ из настроек API.",
            border_radius=14,
        )
        self.name = ft.TextField(
            label="Название аккаунта",
            value=account.name if account else "",
            border_radius=14,
        )
        self.category = ft.TextField(
            label="Категория / тег (опционально)",
            value=account.category if account else "",
            border_radius=14,
        )

    def build(self, title: str, on_save: ft.ControlEventHandler, on_cancel: ft.ControlEventHandler) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(
                width=500,
                padding=ft.padding.only(top=4),
                content=ft.Column(
                    controls=[
                        self.email,
                        self.password,
                        self.bearer_token,
                        self.name,
                        self.category,
                    ],
                    tight=True,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("Отмена", on_click=on_cancel),
                ft.FilledButton("Сохранить", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            content_padding=ft.padding.fromLTRB(24, 12, 24, 8),
        )

    def values(self) -> AccountDialogValues:
        return AccountDialogValues(
            email=self.email.value.strip(),
            password=self.password.value,
            bearer_token=self.bearer_token.value.strip(),
            name=self.name.value.strip(),
            category=self.category.value.strip(),
        )


class ImportDialogForm:
    def __init__(self) -> None:
        self.common_token = ft.TextField(
            label="Общий Bearer token для импортируемых аккаунтов (опционально)",
            password=True,
            can_reveal_password=True,
            border_radius=14,
        )
        self.name_prefix = ft.TextField(
            label="Префикс названия",
            value="Импорт",
            border_radius=14,
        )

    def build(self, on_pick_file: ft.ControlEventHandler, on_cancel: ft.ControlEventHandler) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("Импорт аккаунтов из TXT"),
            content=ft.Container(
                width=520,
                padding=ft.padding.only(top=4),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Формат файла: одна строка на аккаунт в виде email:password",
                            color=ft.Colors.WHITE70,
                        ),
                        self.common_token,
                        self.name_prefix,
                    ],
                    tight=True,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("Отмена", on_click=on_cancel),
                ft.FilledButton("Выбрать TXT", on_click=on_pick_file),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            content_padding=ft.padding.fromLTRB(24, 12, 24, 8),
        )


class ApiSettingsDialogForm:
    def __init__(self, settings: AppSettings) -> None:
        self.api_key = ft.TextField(
            label="Глобальный API-ключ NotLetters",
            value=settings.api_key,
            password=True,
            can_reveal_password=True,
            border_radius=14,
        )
        self.batch_size = ft.TextField(
            label="Аккаунтов в одной пачке",
            value=str(settings.bulk_refresh_batch_size),
            border_radius=14,
        )
        self.pause_seconds = ft.TextField(
            label="Пауза между пачками (сек)",
            value=str(settings.bulk_refresh_pause_seconds),
            border_radius=14,
        )

    def build(self, on_save: ft.ControlEventHandler, on_cancel: ft.ControlEventHandler) -> ft.AlertDialog:
        return ft.AlertDialog(
            modal=True,
            title=ft.Text("Настройки API"),
            content=ft.Container(
                width=520,
                padding=ft.padding.only(top=4),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Ключ будет храниться локально в профиле пользователя Windows и использоваться в заголовке Authorization: Bearer ...",
                            color=ft.Colors.WHITE70,
                        ),
                        self.api_key,
                        self.batch_size,
                        self.pause_seconds,
                    ],
                    tight=True,
                    spacing=12,
                ),
            ),
            actions=[
                ft.TextButton("Отмена", on_click=on_cancel),
                ft.FilledButton("Сохранить", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            content_padding=ft.padding.fromLTRB(24, 12, 24, 8),
        )
