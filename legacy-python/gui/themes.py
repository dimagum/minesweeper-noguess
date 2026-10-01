"""Система мягких двухцветных тем в духе Minesweeper «The Clean One».

Каждая тема описывается всего двумя базовыми цветами:
  * bg  — фон окна/поля (мягкий, приглушённый);
  * fg  — основной цвет (контуры ячеек, цифры, текст, иконки).

Все остальные оттенки (заливка закрытой ячейки, hover, выделение)
получаются наложением fg на bg с разной прозрачностью — поэтому
интерфейс остаётся «чистым» и согласованным в любой теме.

Модуль НЕ зависит от Qt: только данные о цветах и сборка QSS-строки,
поэтому его легко тестировать и переиспользовать для рендера-превью.
"""

# Порядок тем в меню. Микс светлых и тёмных мягких палитр.
THEME_ORDER = [
    "Cream",      # тёплый светлый (фирменный «clean» вид)
    "Sage",       # светлый приглушённо-зелёный
    "Sky",        # светлый приглушённо-синий
    "Blush",      # светлый тёпло-розовый
    "Lavender",   # светлый лавандовый (отсылка к прежней теме)
    "Slate",      # мягкий тёмный сине-серый
    "Mocha",      # мягкий тёмный кофейный
    "Forest",     # глубокий тёмно-зелёный
]

THEMES = {
    "Cream":    {"bg": "#F1EADF", "fg": "#5B554C"},
    "Sage":     {"bg": "#E6ECE6", "fg": "#5E7A63"},
    "Sky":      {"bg": "#E7EDF3", "fg": "#566F88"},
    "Blush":    {"bg": "#F4E9E6", "fg": "#9E6B66"},
    "Lavender": {"bg": "#ECE9F3", "fg": "#6E6396"},
    "Slate":    {"bg": "#2B2F36", "fg": "#C7CCD4"},
    "Mocha":    {"bg": "#2E2926", "fg": "#D6C4B2"},
    "Forest":   {"bg": "#222B27", "fg": "#A9C4B0"},
}

DEFAULT_THEME = "Cream"


# --------------------------------------------------------------------------- #
# Утилиты работы с цветом (чистые функции над hex-строками)
# --------------------------------------------------------------------------- #
def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % (int(round(rgb[0])), int(round(rgb[1])), int(round(rgb[2])))


def mix(c1: str, c2: str, t: float) -> str:
    """Линейно смешивает два hex-цвета: t=0 -> c1, t=1 -> c2."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def overlay(fg: str, bg: str, alpha: float) -> str:
    """Непрозрачный результат наложения fg поверх bg с прозрачностью alpha."""
    return mix(bg, fg, alpha)


def is_dark(theme_name: str) -> bool:
    r, g, b = hex_to_rgb(THEMES[theme_name]["bg"])
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def get(theme_name: str) -> dict:
    return THEMES.get(theme_name, THEMES[DEFAULT_THEME])


# Прозрачности наложения fg на bg для разных состояний закрытой ячейки.
TILE_FILL = 0.12      # обычная закрытая ячейка
TILE_HOVER = 0.22     # ячейка под курсором
TILE_PRESS = 0.30     # нажатая ячейка / зона аккорда
SURFACE = 0.06        # лёгкая «поверхность» панелей
HAIRLINE = 0.18       # тонкие разделители


# --------------------------------------------------------------------------- #
# Сборка QSS под выбранную тему (для меню, HUD и обычных QWidget-ов)
# --------------------------------------------------------------------------- #
def build_qss(theme_name: str) -> str:
    t = get(theme_name)
    bg, fg = t["bg"], t["fg"]
    surface = overlay(fg, bg, SURFACE)
    surface_hi = overlay(fg, bg, TILE_FILL)
    hairline = overlay(fg, bg, HAIRLINE)
    muted = overlay(fg, bg, 0.55)

    return f"""
/* ===== Базовый фон и текст ===== */
QMainWindow, QWidget#MainMenuWidget, QWidget {{
    background-color: {bg};
    color: {fg};
    font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif;
}}

QLabel {{
    color: {fg};
    background: transparent;
}}

/* ===== HUD (мины / таймер) ===== */
QLabel#HudLabel {{
    color: {fg};
    font-size: 18px;
    font-weight: 600;
    background: transparent;
}}

/* ===== Главное меню ===== */
QLabel#LogoLabel {{
    color: {fg};
    font-size: 88px;
    qproperty-alignment: AlignCenter;
}}

QLabel#DifficultyLabel {{
    color: {fg};
    font-size: 20px;
    font-weight: 600;
    qproperty-alignment: AlignCenter;
}}

QLabel#ThemeNameLabel {{
    color: {muted};
    font-size: 13px;
    letter-spacing: 1px;
    qproperty-alignment: AlignCenter;
}}

/* Округлые кнопки меню */
MenuButton {{
    background-color: transparent;
    color: {fg};
    border: 2px solid {hairline};
    border-radius: 22px;
    padding: 13px;
    font-size: 16px;
    font-weight: 600;
}}
MenuButton:hover {{
    background-color: {surface_hi};
    border: 2px solid {fg};
}}
MenuButton:pressed {{
    background-color: {overlay(fg, bg, TILE_PRESS)};
}}
MenuButton:disabled {{
    color: {muted};
    border: 2px solid {surface};
}}

/* Стрелки переключения сложности */
NavButton {{
    background-color: transparent;
    color: {fg};
    border: none;
    font-size: 22px;
    font-weight: bold;
    border-radius: 20px;
}}
NavButton:hover {{
    background-color: {surface_hi};
}}

/* Кнопка «Назад» в игре */
QPushButton#BackButton {{
    background-color: transparent;
    color: {fg};
    border: none;
    font-size: 22px;
    font-weight: bold;
    border-radius: 18px;
    padding: 4px 10px;
}}
QPushButton#BackButton:hover {{
    background-color: {surface_hi};
}}

/* ===== Диалоги ===== */
QMessageBox {{
    background-color: {bg};
    color: {fg};
}}
QMessageBox QPushButton {{
    background-color: transparent;
    color: {fg};
    border: 2px solid {hairline};
    border-radius: 14px;
    padding: 6px 18px;
    font-weight: 600;
}}
QMessageBox QPushButton:hover {{
    background-color: {surface_hi};
    border: 2px solid {fg};
}}
"""
