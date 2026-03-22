from __future__ import annotations

import flet as ft

from ui import MailDesktopApp


def main(page: ft.Page) -> None:
    app = MailDesktopApp(page)
    app.start()


if __name__ == "__main__":
    ft.run(main)
