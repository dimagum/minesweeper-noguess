"""Главное меню: логотип, выбор сложности, выбор темы (мягкие цвета),
кнопки New Game / Resume. Оформление берётся из активной темы."""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy)
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor

import gui.themes as themes


class MenuButton(QPushButton):
    """Кастомный класс кнопки для применения QSS."""
    pass


class NavButton(QPushButton):
    """Кастомный класс для стрелочек < >."""
    pass


class LogoWidget(QWidget):
    """Минималистичный логотип — мина (точка в кольце) в цвете темы."""
    def __init__(self, theme_name=themes.DEFAULT_THEME):
        super().__init__()
        self.theme = themes.get(theme_name)
        self.setFixedSize(140, 140)

    def set_theme(self, theme_name):
        self.theme = themes.get(theme_name)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        fg = QColor(self.theme["fg"])
        cx, cy = self.width() / 2, self.height() / 2
        ring = 46
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        # кольцо
        p.drawEllipse(QRectF(cx - ring, cy - ring, ring * 2, ring * 2))
        p.setBrush(QColor(self.theme["bg"]))
        inner = ring - 5
        p.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))
        # центральная точка
        p.setBrush(fg)
        dot = 16
        p.drawEllipse(QRectF(cx - dot, cy - dot, dot * 2, dot * 2))
        p.end()


class SwatchButton(QPushButton):
    """Кружок-образец темы. Показывает фон/акцент темы и выделение."""
    picked = pyqtSignal(str)

    def __init__(self, theme_name):
        super().__init__()
        self.theme_name = theme_name
        self.theme = themes.get(theme_name)
        self.selected = False
        self.ring_color = self.theme["fg"]
        self.setFixedSize(34, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(lambda: self.picked.emit(self.theme_name))

    def set_selected(self, selected, ring_color):
        self.selected = selected
        self.ring_color = ring_color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        r = 11
        p.setPen(Qt.NoPen)
        # фон темы
        p.setBrush(QColor(self.theme["bg"]))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # тонкий контур акцентом
        from PyQt5.QtGui import QPen
        pen = QPen(QColor(self.theme["fg"]))
        pen.setWidthF(2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        # точка-акцент
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.theme["fg"]))
        p.drawEllipse(QRectF(cx - 4.5, cy - 4.5, 9, 9))
        # кольцо выделения
        if self.selected:
            pen = QPen(QColor(self.ring_color))
            pen.setWidthF(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            rr = r + 5
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
        p.end()


class MainMenuWidget(QWidget):
    def __init__(self, difficulties, theme_order, current_theme,
                 on_new_game, on_resume, on_theme_change):
        super().__init__()
        self.setObjectName("MainMenuWidget")

        self.difficulties = list(difficulties.keys())
        self.current_diff_index = 0

        self.theme_order = list(theme_order)
        self.current_theme = current_theme

        self.on_new_game_callback = on_new_game
        self.on_resume_callback = on_resume
        self.on_theme_change_callback = on_theme_change

        self.swatches = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        # 1. Логотип
        self.logo = LogoWidget(self.current_theme)
        layout.addWidget(self.logo, alignment=Qt.AlignCenter)

        layout.addSpacing(24)

        # 2. Выбор сложности ( < Medium > )
        diff_layout = QHBoxLayout()
        self.btn_prev = NavButton("<")
        self.btn_prev.setFixedSize(44, 44)
        self.btn_prev.setFocusPolicy(Qt.NoFocus)
        self.btn_prev.clicked.connect(self.prev_difficulty)

        self.diff_label = QLabel(self.difficulties[self.current_diff_index])
        self.diff_label.setObjectName("DifficultyLabel")
        self.diff_label.setFixedWidth(160)

        self.btn_next = NavButton(">")
        self.btn_next.setFixedSize(44, 44)
        self.btn_next.setFocusPolicy(Qt.NoFocus)
        self.btn_next.clicked.connect(self.next_difficulty)

        diff_layout.addStretch()
        diff_layout.addWidget(self.btn_prev)
        diff_layout.addWidget(self.diff_label)
        diff_layout.addWidget(self.btn_next)
        diff_layout.addStretch()
        layout.addLayout(diff_layout)

        layout.addSpacing(18)

        # 3. Выбор темы
        theme_caption = QLabel("THEME")
        theme_caption.setObjectName("ThemeNameLabel")
        layout.addWidget(theme_caption, alignment=Qt.AlignCenter)

        sw_layout = QHBoxLayout()
        sw_layout.setSpacing(8)
        sw_layout.setAlignment(Qt.AlignCenter)
        for name in self.theme_order:
            sw = SwatchButton(name)
            sw.picked.connect(self.pick_theme)
            self.swatches.append(sw)
            sw_layout.addWidget(sw)
        layout.addLayout(sw_layout)
        self._refresh_swatches()

        layout.addSpacing(26)

        # 4. Кнопки
        self.btn_new_game = MenuButton("New Game")
        self.btn_new_game.setFixedWidth(250)
        self.btn_new_game.setFocusPolicy(Qt.NoFocus)
        self.btn_new_game.clicked.connect(self.start_new_game)
        layout.addWidget(self.btn_new_game, alignment=Qt.AlignCenter)

        self.btn_resume = MenuButton("Resume")
        self.btn_resume.setFixedWidth(250)
        self.btn_resume.setFocusPolicy(Qt.NoFocus)
        self.btn_resume.setEnabled(False)
        self.btn_resume.clicked.connect(self.on_resume_callback)
        layout.addWidget(self.btn_resume, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    # --- сложность --- #
    def prev_difficulty(self):
        self.current_diff_index = (self.current_diff_index - 1) % len(self.difficulties)
        self.diff_label.setText(self.difficulties[self.current_diff_index])

    def next_difficulty(self):
        self.current_diff_index = (self.current_diff_index + 1) % len(self.difficulties)
        self.diff_label.setText(self.difficulties[self.current_diff_index])

    def start_new_game(self):
        diff_name = self.difficulties[self.current_diff_index]
        self.on_new_game_callback(diff_name)

    # --- темы --- #
    def pick_theme(self, name):
        self.current_theme = name
        self._refresh_swatches()
        self.logo.set_theme(name)
        self.on_theme_change_callback(name)

    def set_theme(self, name):
        """Вызывается извне при смене темы (например, при инициализации)."""
        self.current_theme = name
        self.logo.set_theme(name)
        self._refresh_swatches()

    def _refresh_swatches(self):
        ring = themes.get(self.current_theme)["fg"]
        for sw in self.swatches:
            sw.set_selected(sw.theme_name == self.current_theme, ring)
