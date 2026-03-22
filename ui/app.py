from __future__ import annotations

import asyncio
import re

import flet as ft

from api_client import ApiClientError, NotLettersClient
from models import AccountConfig, AppSettings, Letter, LetterFilters
from storage import AccountsStorage, AppSettingsStorage, get_app_storage_dir
from ui.dialogs import AccountDialogForm, ApiSettingsDialogForm, ImportDialogForm


class MailDesktopApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        data_dir = get_app_storage_dir()
        self.storage = AccountsStorage(data_dir / "accounts.json")
        self.settings_storage = AppSettingsStorage(data_dir / "app_settings.json")
        self.api_client = NotLettersClient()

        self.accounts: list[AccountConfig] = []
        self.settings = AppSettings()
        self.letters_cache: dict[str, list[Letter]] = {}
        self.account_latest_dates: dict[str, int] = {}
        self.account_has_unread: dict[str, bool] = {}
        self.current_letters: list[Letter] = []
        self.selected_account_id: str | None = None
        self.selected_letter_id: str | None = None
        self.auto_refresh_seconds = 45
        self.auto_refresh_enabled = True
        self.bulk_refresh_batch_size = 10
        self.bulk_refresh_pause_seconds = 2.0
        self.active_requests = 0
        self.request_counter = 0
        self.is_closing = False

        self._build_page()
        self._build_controls()

    def start(self) -> None:
        self.accounts = self.storage.load_accounts()
        self.settings = self.settings_storage.load_settings()
        self.bulk_refresh_batch_size = self.settings.bulk_refresh_batch_size
        self.bulk_refresh_pause_seconds = self.settings.bulk_refresh_pause_seconds
        self.page.add(self.layout)
        self._update_api_key_status()
        self._render_accounts()
        self._render_letters()
        self._show_empty_letter()
        self.page.run_task(self._auto_refresh_loop)

        if self.accounts:
            filtered_accounts = self._get_filtered_accounts()
            self.select_account((filtered_accounts or self.accounts)[0].id)
        else:
            self._set_status("Добавьте аккаунт или импортируйте список из TXT.")

    def _build_page(self) -> None:
        self.page.title = "NotLetters Desktop"
        self.page.padding = 18
        self.page.spacing = 0
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = "#0B1220"
        self.page.dark_theme = ft.Theme(
            color_scheme_seed=ft.Colors.CYAN,
            visual_density=ft.VisualDensity.COMFORTABLE,
            scaffold_bgcolor="#0B1220",
            card_bgcolor="#121A2B",
        )
        self.page.on_close = self._on_page_closed
        self.page.on_disconnect = self._on_page_closed

    def _build_controls(self) -> None:
        self.account_favorites_switch = ft.Switch(
            label="Только избранные",
            value=False,
            on_change=lambda _: self._render_accounts(),
        )
        self.account_sort_dropdown = ft.Dropdown(
            width=180,
            label="Сортировка почт",
            value="messages",
            options=[
                ft.dropdown.Option("messages", "По сообщениям"),
                ft.dropdown.Option("number", "По нумерации"),
                ft.dropdown.Option("alpha", "По алфавиту"),
            ],
            on_select=lambda _: self._render_accounts(),
        )
        self.search_field = ft.TextField(
            hint_text="Поиск по письмам",
            prefix_icon=ft.Icons.SEARCH,
            expand=True,
            bgcolor="#121A2B",
            border_radius=14,
            on_submit=lambda _: self.page.run_task(self.refresh_letters, True, False),
        )
        self.interval_dropdown = ft.Dropdown(
            width=150,
            label="Автообновление",
            value="45",
            options=[
                ft.dropdown.Option("30", "30 сек"),
                ft.dropdown.Option("45", "45 сек"),
                ft.dropdown.Option("60", "60 сек"),
            ],
            on_select=self._on_interval_changed,
        )
        self.auto_refresh_switch = ft.Switch(
            label="Автообновлять все",
            value=True,
            on_change=self._on_auto_refresh_toggled,
        )
        self.loading_ring = ft.ProgressRing(width=18, height=18, visible=False)
        self.refresh_button = ft.FilledButton(
            "Обновить",
            icon=ft.Icons.REFRESH,
            on_click=lambda _: self.page.run_task(self.refresh_letters, True, True),
        )
        self.refresh_all_button = ft.OutlinedButton(
            "Обновить всё",
            icon=ft.Icons.SYNC,
            on_click=lambda _: self.page.run_task(self.refresh_all_accounts, True, True),
        )

        self.accounts_list = ft.ListView(expand=True, spacing=10, padding=ft.padding.only(top=8))
        self.letters_list = ft.ListView(expand=True, spacing=10, padding=ft.padding.only(top=8))

        self.account_summary = ft.Text("Аккаунт не выбран", size=16, weight=ft.FontWeight.W_600)
        self.letters_summary = ft.Text("Писем: 0", color=ft.Colors.WHITE70)

        self.detail_subject = ft.Text("Выберите письмо", size=20, weight=ft.FontWeight.BOLD)
        self.detail_sender = ft.Text("", selectable=True, color=ft.Colors.WHITE70)
        self.detail_date = ft.Text("", color=ft.Colors.WHITE70)
        self.detail_star = ft.Text("", color=ft.Colors.AMBER_300)
        self.detail_text = ft.TextField(
            value="",
            read_only=True,
            multiline=True,
            min_lines=10,
            max_lines=14,
            border_radius=12,
            bgcolor="#0F1727",
        )
        self.detail_html = ft.TextField(
            value="",
            read_only=True,
            multiline=True,
            min_lines=10,
            max_lines=14,
            border_radius=12,
            bgcolor="#0F1727",
        )

        self.status_text = ft.Text("Готово к работе.", color=ft.Colors.WHITE70)
        self.api_key_status = ft.Text("", color=ft.Colors.WHITE70, size=12)

        left_panel = ft.Container(
            width=395,
            padding=18,
            border_radius=20,
            bgcolor="#10192B",
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_CIRCLE_OUTLINED, color=ft.Colors.CYAN_300),
                            ft.Text("Почтовые аккаунты", size=18, weight=ft.FontWeight.BOLD),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Row(
                        controls=[
                            ft.FilledButton("Добавить", icon=ft.Icons.ADD, on_click=self._open_add_account_dialog),
                            ft.OutlinedButton("Импорт TXT", icon=ft.Icons.UPLOAD_FILE, on_click=self._open_import_dialog),
                        ],
                    ),
                    self.refresh_all_button,
                    self.account_favorites_switch,
                    self.account_sort_dropdown,
                    ft.Row(
                        controls=[
                            ft.OutlinedButton("Настройки API", icon=ft.Icons.KEY, on_click=self._open_api_settings_dialog),
                        ],
                    ),
                    self.api_key_status,
                    ft.Divider(color="#25314A"),
                    self.accounts_list,
                ],
                expand=True,
            ),
        )

        center_panel = ft.Container(
            expand=1,
            padding=18,
            border_radius=20,
            bgcolor="#10192B",
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            self.search_field,
                            self.interval_dropdown,
                            self.auto_refresh_switch,
                            self.loading_ring,
                            self.refresh_button,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[self.account_summary, ft.Container(expand=True), self.letters_summary],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Divider(color="#25314A"),
                    self.letters_list,
                ],
                expand=True,
            ),
        )

        detail_panel = ft.Container(
            expand=1,
            padding=18,
            border_radius=20,
            bgcolor="#10192B",
            content=ft.Column(
                controls=[
                    self.detail_subject,
                    self.detail_sender,
                    ft.Row(
                        controls=[self.detail_date, self.detail_star],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color="#25314A"),
                    ft.Text("Текстовая версия", size=15, weight=ft.FontWeight.W_600),
                    self.detail_text,
                    ft.Divider(color="#25314A"),
                    ft.Text("HTML-версия", size=15, weight=ft.FontWeight.W_600),
                    ft.Text(
                        "Если HTML сложно отрисовать в Flet, ниже показывается исходный код письма.",
                        color=ft.Colors.WHITE70,
                    ),
                    self.detail_html,
                ],
                expand=True,
            ),
        )

        status_bar = ft.Container(
            margin=ft.margin.only(top=16),
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
            border_radius=16,
            bgcolor="#10192B",
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ft.Colors.CYAN_300),
                    self.status_text,
                ]
            ),
        )

        self.layout = ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    expand=True,
                    spacing=16,
                    controls=[left_panel, center_panel, detail_panel],
                ),
                status_bar,
            ],
        )

    def _render_accounts(self) -> None:
        self.accounts_list.controls = [
            self._build_account_card(index + 1, account)
            for index, account in enumerate(self._get_filtered_accounts())
        ]
        self._safe_update(self.accounts_list)

    def _build_account_card(self, index: int, account: AccountConfig) -> ft.Control:
        is_selected = account.id == self.selected_account_id
        latest_date = self.account_latest_dates.get(account.id, 0)
        has_unread = self.account_has_unread.get(account.id, False)
        subtitle = account.email
        if latest_date > 0:
            subtitle = f"{subtitle} | последнее письмо: {self._format_timestamp(latest_date)}"

        header_controls: list[ft.Control] = [
            ft.Text(f"{index}.", width=28, color=ft.Colors.WHITE60),
            ft.Text(
                account.display_name,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.GREEN_300 if has_unread else ft.Colors.WHITE,
                expand=True,
            ),
        ]
        if account.category:
            header_controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=12,
                    bgcolor="#17314E",
                    content=ft.Text(account.category, size=11, color=ft.Colors.CYAN_100),
                )
            )
        header_controls.extend(
            [
                ft.IconButton(
                    icon=ft.Icons.STAR if account.favorite else ft.Icons.STAR_BORDER_ROUNDED,
                    icon_color=ft.Colors.AMBER_300 if account.favorite else ft.Colors.WHITE54,
                    tooltip="Избранная почта" if account.favorite else "Добавить почту в избранное",
                    on_click=lambda _, account_id=account.id: self._toggle_account_favorite(account_id),
                ),
                ft.Icon(self._account_status_icon(account), color=self._account_status_color(account), size=18),
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    items=[
                        ft.PopupMenuItem(
                            content="Редактировать",
                            icon=ft.Icons.EDIT,
                            on_click=lambda _, account_id=account.id: self._open_edit_account_by_id(account_id),
                        ),
                        ft.PopupMenuItem(
                            content="Удалить",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda _, account_id=account.id: self._delete_account_by_id(account_id),
                        ),
                    ],
                ),
            ]
        )

        return ft.Container(
            border_radius=16,
            bgcolor="#193150" if is_selected else "#121A2B",
            padding=14,
            ink=True,
            on_click=lambda _, account_id=account.id: self.select_account(account_id),
            content=ft.Column(
                controls=[
                    ft.Row(controls=header_controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text(subtitle, color=ft.Colors.WHITE70, size=12),
                    ft.Text(
                        "Есть новые письма" if has_unread else "Новых писем нет",
                        color=ft.Colors.GREEN_300 if has_unread else ft.Colors.WHITE54,
                        size=12,
                    ),
                ],
                spacing=6,
            ),
        )

    def _render_letters(self) -> None:
        self.letters_list.controls = [self._build_letter_card(letter) for letter in self.current_letters]
        self.letters_summary.value = f"Писем: {len(self.current_letters)}"
        self._safe_update(self.letters_list, self.letters_summary)

    def _build_letter_card(self, letter: Letter) -> ft.Control:
        is_selected = letter.id == self.selected_letter_id
        sender_title = letter.sender_name or letter.sender or "Неизвестный отправитель"
        return ft.Container(
            border_radius=16,
            bgcolor="#193150" if is_selected else "#121A2B",
            padding=14,
            ink=True,
            on_click=lambda _, letter_id=letter.id: self.select_letter(letter_id),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(sender_title, weight=ft.FontWeight.W_600, expand=True),
                            ft.Icon(
                                ft.Icons.MARK_EMAIL_UNREAD_ROUNDED if is_selected else ft.Icons.MAIL_OUTLINE,
                                color=ft.Colors.CYAN_200 if is_selected else ft.Colors.WHITE54,
                                size=18,
                            ),
                        ]
                    ),
                    ft.Text(letter.sender or "Отправитель не указан", color=ft.Colors.WHITE70, size=12),
                    ft.Text(letter.subject or "(Без темы)", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(letter.formatted_date, color=ft.Colors.WHITE60, size=12),
                ],
            ),
        )

    def select_account(self, account_id: str) -> None:
        self.selected_account_id = account_id
        self.selected_letter_id = None
        self.account_has_unread[account_id] = False

        account = self._get_selected_account()
        if account is None:
            self.current_letters = []
            self._render_accounts()
            self._render_letters()
            self._show_empty_letter()
            return

        self.account_summary.value = account.display_name
        self._safe_update(self.account_summary)
        self._render_accounts()

        cached_letters = self.letters_cache.get(account.id, [])
        if cached_letters and not self.search_field.value.strip():
            self.current_letters = cached_letters
            self.selected_letter_id = cached_letters[0].id
            self._render_letters()
            self.select_letter(cached_letters[0].id)
        else:
            self.current_letters = []
            self._render_letters()
            self._show_empty_letter("Загружаем письма выбранного аккаунта...")

        self.page.run_task(self.refresh_letters, False, True)

    def select_letter(self, letter_id: str, mark_read: bool = True) -> None:
        selected_letter = next((item for item in self.current_letters if item.id == letter_id), None)
        if selected_letter is None:
            self._show_empty_letter()
            return

        self.selected_letter_id = letter_id
        if self.selected_account_id and mark_read:
            self.account_has_unread[self.selected_account_id] = False
        account = self._get_selected_account()
        badges: list[str] = []
        if account and account.favorite:
            badges.append("Избранная почта")
        if selected_letter.star:
            badges.append("API star")
        self.detail_subject.value = selected_letter.subject or "(Без темы)"
        self.detail_sender.value = (
            f"Отправитель: {selected_letter.sender_name or 'Без имени'} <{selected_letter.sender or 'не указан'}>"
        )
        self.detail_date.value = f"Дата: {selected_letter.formatted_date}"
        self.detail_star.value = " | ".join(badges)
        self.detail_text.value = selected_letter.body.text or "Текстовая версия письма отсутствует."
        self.detail_html.value = selected_letter.body.html or "HTML-версия письма отсутствует."

        self._safe_update(
            self.detail_subject,
            self.detail_sender,
            self.detail_date,
            self.detail_star,
            self.detail_text,
            self.detail_html,
        )
        self._render_accounts()
        self._render_letters()

    async def refresh_letters(self, user_initiated: bool = False, show_notifications: bool = True) -> None:
        account = self._get_selected_account()
        if account is None:
            if show_notifications:
                self._notify("Сначала выберите аккаунт.", error=True)
            return

        filters = LetterFilters(search=self.search_field.value or "", star_only=False)
        self.request_counter += 1
        request_id = self.request_counter
        previous_letters = self.letters_cache.get(account.id, [])
        previous_ids = {letter.id for letter in previous_letters}

        self.active_requests += 1
        self._set_loading(True)
        self._set_status(f"Загружаем письма для {account.display_name}...")

        try:
            letters = await asyncio.to_thread(self.api_client.fetch_letters, account, filters, self.settings.api_key)
        except asyncio.CancelledError:
            return
        except ApiClientError as exc:
            self.current_letters = []
            self._render_letters()
            self._show_empty_letter("Не удалось получить письма.")
            self._set_status(str(exc))
            if show_notifications:
                self._notify(str(exc), error=True)
        except Exception as exc:  # pragma: no cover - страховка на непредвиденные исключения
            message = f"Непредвиденная ошибка: {exc}"
            self.current_letters = []
            self._render_letters()
            self._show_empty_letter("Произошла непредвиденная ошибка.")
            self._set_status(message)
            if show_notifications:
                self._notify(message, error=True)
        else:
            if request_id != self.request_counter or account.id != self.selected_account_id:
                return

            has_new_letters = bool(previous_ids) and any(letter.id not in previous_ids for letter in letters)
            self._apply_account_refresh_result(
                account=account,
                letters=letters,
                previous_ids=previous_ids,
                allow_mark_unread=True,
            )
            self.current_letters = letters
            self._render_accounts()
            self._render_letters()

            if letters:
                keep_letter_id = self.selected_letter_id if any(letter.id == self.selected_letter_id for letter in letters) else letters[0].id
                self.select_letter(keep_letter_id, mark_read=not has_new_letters)
                self._set_status(f"Загружено писем: {len(letters)}.")
                if user_initiated and show_notifications:
                    self._notify("Письма успешно обновлены.")
            else:
                self.selected_letter_id = None
                self._show_empty_letter("Список писем пуст.")
                self._set_status("Список писем пуст.")
                if show_notifications:
                    self._notify("Писем по заданным фильтрам не найдено.")
        finally:
            self.active_requests = max(0, self.active_requests - 1)
            if self.active_requests == 0 and not self.is_closing:
                self._set_loading(False)

    async def refresh_all_accounts(self, user_initiated: bool = False, show_notifications: bool = True) -> None:
        if not self.accounts:
            if show_notifications:
                self._notify("Список аккаунтов пуст.", error=True)
            return

        self.active_requests += 1
        self._set_loading(True)
        self._set_status("Обновляем все аккаунты...")

        errors: list[str] = []
        selected_account = self._get_selected_account()
        selected_search = self.search_field.value or ""

        try:
            total_accounts = len(self.accounts)
            for batch_index, batch_start in enumerate(range(0, total_accounts, self.bulk_refresh_batch_size), start=1):
                if self.is_closing:
                    return
                batch_accounts = self.accounts[batch_start : batch_start + self.bulk_refresh_batch_size]
                batch_end = min(batch_start + len(batch_accounts), total_accounts)
                self._set_status(
                    f"Обновляем аккаунты {batch_start + 1}-{batch_end} из {total_accounts}..."
                )

                batch_results = await asyncio.gather(
                    *[
                        self._fetch_account_for_bulk_refresh(account)
                        for account in batch_accounts
                    ],
                    return_exceptions=True,
                )

                for account, result in zip(batch_accounts, batch_results):
                    if isinstance(result, asyncio.CancelledError):
                        return
                    if isinstance(result, Exception):
                        errors.append(f"{account.display_name}: {result}")
                        continue

                    letters, previous_ids = result
                    self._apply_account_refresh_result(
                        account=account,
                        letters=letters,
                        previous_ids=previous_ids,
                        allow_mark_unread=True,
                    )

                self._render_accounts()
                if batch_end < total_accounts:
                    await asyncio.sleep(self.bulk_refresh_pause_seconds)

            if selected_account:
                if selected_search.strip():
                    try:
                        filtered_letters = await asyncio.to_thread(
                            self.api_client.fetch_letters,
                            selected_account,
                            LetterFilters(search=selected_search, star_only=False),
                            self.settings.api_key,
                        )
                    except Exception:  # pragma: no cover - не мешаем общему обновлению
                        filtered_letters = self.letters_cache.get(selected_account.id, [])
                else:
                    filtered_letters = self.letters_cache.get(selected_account.id, [])

                self.current_letters = filtered_letters
                self._render_letters()
                if filtered_letters:
                    keep_letter_id = (
                        self.selected_letter_id
                        if any(letter.id == self.selected_letter_id for letter in filtered_letters)
                        else filtered_letters[0].id
                    )
                    self.select_letter(keep_letter_id, mark_read=False)
                else:
                    self.selected_letter_id = None
                    self._show_empty_letter("Список писем пуст.")
            self._render_accounts()

            if errors:
                self._set_status(f"Обновление завершено с ошибками: {len(errors)}.")
                if show_notifications:
                    self._notify(f"Обновление завершено. Ошибок: {len(errors)}.", error=True)
            else:
                self._set_status("Все аккаунты обновлены.")
                if show_notifications:
                    self._notify("Все аккаунты успешно обновлены.")
        finally:
            self.active_requests = max(0, self.active_requests - 1)
            if self.active_requests == 0 and not self.is_closing:
                self._set_loading(False)

    async def _auto_refresh_loop(self) -> None:
        # Фоновая задача не блокирует интерфейс и безопасно завершается при закрытии окна.
        try:
            while not self.is_closing:
                await asyncio.sleep(self.auto_refresh_seconds)
                if self.is_closing:
                    break
                if self.auto_refresh_enabled and self.active_requests == 0:
                    await self.refresh_all_accounts(False, False)
        except asyncio.CancelledError:
            return

    def _open_add_account_dialog(self, _: ft.ControlEvent) -> None:
        form = AccountDialogForm()

        def on_cancel(_: ft.ControlEvent) -> None:
            self._close_dialog()

        def on_save(_: ft.ControlEvent) -> None:
            values = form.values()
            validation_error = self._validate_account_values(values.email, values.password, values.bearer_token)
            if validation_error:
                self._notify(validation_error, error=True)
                return
            if self._email_exists(values.email):
                self._notify("Аккаунт с таким email уже существует.", error=True)
                return

            account = AccountConfig(
                email=values.email,
                password=values.password,
                bearer_token=values.bearer_token,
                name=values.name,
                category=values.category,
            )
            self.accounts.append(account)
            self.storage.save_accounts(self.accounts)
            self._close_dialog()
            self._render_accounts()
            self.select_account(account.id)
            self._notify("Аккаунт добавлен.")

        dialog = form.build("Добавить аккаунт", on_save=on_save, on_cancel=on_cancel)
        self._show_dialog(dialog)

    def _open_edit_account_dialog(self, _: ft.ControlEvent) -> None:
        if self.selected_account_id is None:
            self._notify("Для редактирования сначала выберите аккаунт.", error=True)
            return
        self._open_edit_account_by_id(self.selected_account_id)

    def _open_edit_account_by_id(self, account_id: str) -> None:
        account = self._get_account_by_id(account_id)
        if account is None:
            self._notify("Аккаунт не найден.", error=True)
            return

        form = AccountDialogForm(account)

        def on_cancel(_: ft.ControlEvent) -> None:
            self._close_dialog()

        def on_save(_: ft.ControlEvent) -> None:
            values = form.values()
            validation_error = self._validate_account_values(values.email, values.password, values.bearer_token)
            if validation_error:
                self._notify(validation_error, error=True)
                return
            if self._email_exists(values.email, exclude_id=account.id):
                self._notify("Аккаунт с таким email уже существует.", error=True)
                return

            account.email = values.email
            account.password = values.password
            account.bearer_token = values.bearer_token
            account.name = values.name
            account.category = values.category
            self.storage.save_accounts(self.accounts)
            self._close_dialog()
            self._render_accounts()
            if self.selected_account_id == account.id:
                self.account_summary.value = account.display_name
                self._safe_update(self.account_summary)
            self._notify("Аккаунт обновлён.")

        dialog = form.build("Редактировать аккаунт", on_save=on_save, on_cancel=on_cancel)
        self._show_dialog(dialog)

    def _delete_selected_account(self, _: ft.ControlEvent) -> None:
        if self.selected_account_id is None:
            self._notify("Сначала выберите аккаунт для удаления.", error=True)
            return
        self._delete_account_by_id(self.selected_account_id)

    def _delete_account_by_id(self, account_id: str) -> None:
        account = self._get_account_by_id(account_id)
        if account is None:
            self._notify("Аккаунт не найден.", error=True)
            return

        def on_cancel(_: ft.ControlEvent) -> None:
            self._close_dialog()

        def on_confirm(_: ft.ControlEvent) -> None:
            self._close_dialog()
            self.accounts = [item for item in self.accounts if item.id != account.id]
            self.letters_cache.pop(account.id, None)
            self.account_latest_dates.pop(account.id, None)
            self.account_has_unread.pop(account.id, None)
            if self.selected_account_id == account.id:
                self.selected_account_id = None
                self.selected_letter_id = None
            self.storage.save_accounts(self.accounts)
            self._render_accounts()
            if self.accounts:
                filtered_accounts = self._get_filtered_accounts()
                self.select_account((filtered_accounts or self.accounts)[0].id)
            else:
                self.current_letters = []
                self._render_letters()
                self._show_empty_letter()
                self.account_summary.value = "Аккаунт не выбран"
                self._safe_update(self.account_summary)
                self._set_status("Список аккаунтов пуст.")
            self._notify("Аккаунт удалён.")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Удалить аккаунт"),
            content=ft.Text(f"Удалить аккаунт {account.display_name}?"),
            actions=[
                ft.TextButton("Отмена", on_click=on_cancel),
                ft.FilledButton("Удалить", icon=ft.Icons.DELETE_FOREVER, on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._show_dialog(dialog)

    def _open_import_dialog(self, _: ft.ControlEvent) -> None:
        form = ImportDialogForm()

        def on_cancel(_: ft.ControlEvent) -> None:
            self._close_dialog()

        def on_pick(_: ft.ControlEvent) -> None:
            self.page.run_task(self._pick_import_file, form)

        dialog = form.build(on_pick_file=on_pick, on_cancel=on_cancel)
        self._show_dialog(dialog)

    async def _pick_import_file(self, form: ImportDialogForm) -> None:
        self._close_dialog()
        files = await ft.FilePicker().pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["txt"],
            dialog_title="Выберите TXT-файл со списком аккаунтов",
        )
        if not files:
            return

        picked_file = files[0]
        if not picked_file.path:
            self._notify("Не удалось получить путь к выбранному TXT-файлу.", error=True)
            return

        file_path = Path(picked_file.path)
        try:
            imported_accounts = self.storage.parse_txt_accounts(
                file_path=file_path,
                common_token=form.common_token.value or "",
                name_prefix=form.name_prefix.value or "Импорт",
            )
        except OSError as exc:
            self._notify(f"Не удалось прочитать файл: {exc}", error=True)
            return

        if not imported_accounts:
            self._notify("В TXT-файле не найдено валидных записей вида email:password.", error=True)
            return

        self.accounts, added, updated = self.storage.merge_accounts(self.accounts, imported_accounts)
        self.storage.save_accounts(self.accounts)
        self._render_accounts()

        if self.accounts and not self.selected_account_id:
            filtered_accounts = self._get_filtered_accounts()
            self.select_account((filtered_accounts or self.accounts)[0].id)

        suffix = ""
        if not form.common_token.value.strip():
            suffix = " Общий Bearer token не был указан, поэтому будет использован глобальный API-ключ."

        self._notify(f"Импорт завершён. Добавлено: {added}, обновлено: {updated}.{suffix}")

    def _on_interval_changed(self, _: ft.ControlEvent) -> None:
        try:
            self.auto_refresh_seconds = int(self.interval_dropdown.value or "45")
        except ValueError:
            self.auto_refresh_seconds = 45
            self.interval_dropdown.value = "45"
            self._safe_update(self.interval_dropdown)
        self._set_status(f"Интервал автообновления: {self.auto_refresh_seconds} сек.")

    def _on_auto_refresh_toggled(self, _: ft.ControlEvent) -> None:
        self.auto_refresh_enabled = bool(self.auto_refresh_switch.value)
        state = "включено" if self.auto_refresh_enabled else "выключено"
        self._set_status(f"Массовое автообновление {state}.")

    def _validate_account_values(self, email: str, password: str, token: str) -> str | None:
        if not email:
            return "Email не может быть пустым."
        if not password:
            return "Пароль не может быть пустым."
        if not token and not self.settings.api_key.strip():
            return "Укажите Bearer token у аккаунта или сохраните глобальный API-ключ в настройках API."
        return None

    def _toggle_account_favorite(self, account_id: str) -> None:
        account = self._get_account_by_id(account_id)
        if account is None:
            return
        account.favorite = not account.favorite
        self.storage.save_accounts(self.accounts)
        self._render_accounts()
        self._notify("Избранное обновлено.")

    def _email_exists(self, email: str, exclude_id: str | None = None) -> bool:
        normalized = email.lower()
        for account in self.accounts:
            if exclude_id and account.id == exclude_id:
                continue
            if account.email.lower() == normalized:
                return True
        return False

    def _get_selected_account(self) -> AccountConfig | None:
        return self._get_account_by_id(self.selected_account_id)

    def _get_account_by_id(self, account_id: str | None) -> AccountConfig | None:
        if not account_id:
            return None
        return next((account for account in self.accounts if account.id == account_id), None)

    def _show_empty_letter(self, message: str = "Выберите письмо для просмотра.") -> None:
        self.detail_subject.value = message
        self.detail_sender.value = ""
        self.detail_date.value = ""
        self.detail_star.value = ""
        self.detail_text.value = ""
        self.detail_html.value = ""
        self._safe_update(
            self.detail_subject,
            self.detail_sender,
            self.detail_date,
            self.detail_star,
            self.detail_text,
            self.detail_html,
        )

    def _set_loading(self, state: bool) -> None:
        self.loading_ring.visible = state
        self.refresh_button.disabled = state
        self._safe_update(self.loading_ring, self.refresh_button)

    def _set_status(self, text: str) -> None:
        self.status_text.value = text
        self._safe_update(self.status_text)

    async def _fetch_account_for_bulk_refresh(self, account: AccountConfig) -> tuple[list[Letter], set[str]]:
        previous_letters = self.letters_cache.get(account.id, [])
        previous_ids = {letter.id for letter in previous_letters}
        letters = await asyncio.to_thread(
            self.api_client.fetch_letters,
            account,
            LetterFilters(search="", star_only=False),
            self.settings.api_key,
        )
        return letters, previous_ids

    def _apply_account_refresh_result(
        self,
        account: AccountConfig,
        letters: list[Letter],
        previous_ids: set[str],
        allow_mark_unread: bool,
    ) -> None:
        self.letters_cache[account.id] = letters
        self.account_latest_dates[account.id] = letters[0].date if letters else 0
        has_new_letters = bool(previous_ids) and any(letter.id not in previous_ids for letter in letters)
        if allow_mark_unread and has_new_letters and self.selected_letter_id != (letters[0].id if letters else None):
            self.account_has_unread[account.id] = True

    def _open_api_settings_dialog(self, _: ft.ControlEvent) -> None:
        form = ApiSettingsDialogForm(self.settings)

        def on_cancel(_: ft.ControlEvent) -> None:
            self._close_dialog()

        def on_save(_: ft.ControlEvent) -> None:
            try:
                batch_size = max(1, int(form.batch_size.value.strip() or "10"))
            except ValueError:
                self._notify("Размер пачки должен быть целым числом.", error=True)
                return
            try:
                pause_seconds = max(0.0, float(form.pause_seconds.value.strip().replace(",", ".") or "2"))
            except ValueError:
                self._notify("Пауза между пачками должна быть числом.", error=True)
                return

            self.settings.api_key = form.api_key.value.strip()
            self.settings.bulk_refresh_batch_size = batch_size
            self.settings.bulk_refresh_pause_seconds = pause_seconds
            self.bulk_refresh_batch_size = batch_size
            self.bulk_refresh_pause_seconds = pause_seconds
            self.settings_storage.save_settings(self.settings)
            self._close_dialog()
            self._update_api_key_status()
            self._render_accounts()
            self._set_status(
                f"Настройки сохранены. Пачка: {self.bulk_refresh_batch_size}, пауза: {self.bulk_refresh_pause_seconds} сек."
            )
            self._notify("Настройки API и пакетного обновления сохранены.")

        dialog = form.build(on_save=on_save, on_cancel=on_cancel)
        self._show_dialog(dialog)

    def _update_api_key_status(self) -> None:
        if self.settings.api_key.strip():
            self.api_key_status.value = "Глобальный API-ключ сохранён и используется по умолчанию."
            self.api_key_status.color = ft.Colors.GREEN_300
        else:
            self.api_key_status.value = "Глобальный API-ключ не задан. Можно указать его в настройках API."
            self.api_key_status.color = ft.Colors.AMBER_300
        self._safe_update(self.api_key_status)

    def _account_status_icon(self, account: AccountConfig) -> str:
        if account.bearer_token.strip():
            return ft.Icons.KEY_OUTLINED
        if self.settings.api_key.strip():
            return ft.Icons.VPN_KEY_OUTLINED
        return ft.Icons.WARNING_AMBER_ROUNDED

    def _account_status_color(self, account: AccountConfig) -> str:
        if account.bearer_token.strip():
            return ft.Colors.CYAN_200
        if self.settings.api_key.strip():
            return ft.Colors.GREEN_300
        return ft.Colors.AMBER_300

    def _notify(self, message: str, error: bool = False) -> None:
        self._show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                bgcolor=ft.Colors.RED_400 if error else ft.Colors.GREEN_400,
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )

    def _show_dialog(self, dialog: ft.Control) -> None:
        if not self._page_alive():
            return
        try:
            self.page.show_dialog(dialog)
        except RuntimeError:
            self.is_closing = True

    def _close_dialog(self) -> None:
        if not self._page_alive():
            return
        try:
            self.page.pop_dialog()
            self.page.update()
        except RuntimeError:
            self.is_closing = True

    def _safe_update(self, *controls: ft.Control) -> None:
        if not self._page_alive():
            return
        try:
            if controls:
                for control in controls:
                    control.update()
            else:
                self.page.update()
        except RuntimeError:
            self.is_closing = True

    def _page_alive(self) -> bool:
        if self.is_closing:
            return False
        try:
            _ = self.page.session
        except RuntimeError:
            self.is_closing = True
            return False
        return True

    def _on_page_closed(self, _: ft.ControlEvent) -> None:
        self.is_closing = True

    def _get_filtered_accounts(self) -> list[AccountConfig]:
        accounts = list(self.accounts)
        if self.account_favorites_switch.value:
            accounts = [account for account in accounts if account.favorite]

        sort_mode = self.account_sort_dropdown.value or "messages"
        if sort_mode == "alpha":
            accounts.sort(
                key=lambda account: (
                    not self.account_has_unread.get(account.id, False),
                    not account.favorite,
                    self._alpha_sort_key(account),
                )
            )
        elif sort_mode == "number":
            accounts.sort(
                key=lambda account: (
                    not self.account_has_unread.get(account.id, False),
                    not account.favorite,
                    self._natural_sort_key(account.display_name),
                )
            )
        else:
            accounts.sort(
                key=lambda account: (
                    not self.account_has_unread.get(account.id, False),
                    not account.favorite,
                    -self.account_latest_dates.get(account.id, 0),
                    self._alpha_sort_key(account),
                )
            )
        return accounts

    def _natural_sort_key(self, value: str) -> list[object]:
        parts = re.split(r"(\d+)", value.casefold())
        return [int(part) if part.isdigit() else part for part in parts]

    def _alpha_sort_key(self, account: AccountConfig) -> tuple[str, str]:
        return (account.display_name.casefold(), account.email.casefold())

    def _format_timestamp(self, timestamp: int) -> str:
        if timestamp <= 0:
            return "неизвестно"
        return next(
            (
                letter.formatted_date
                for letters in self.letters_cache.values()
                for letter in letters
                if letter.date == timestamp
            ),
            "неизвестно",
        )
