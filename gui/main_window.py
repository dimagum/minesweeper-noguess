from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QMessageBox, QStackedWidget, QPushButton)
from PyQt5.QtCore import QTimer, Qt
from core.game import Game, GameState
from gui.board_widget import BoardWidget
from gui.main_menu import MainMenuWidget
import gui.themes as themes

# Пресеты сложности: (ширина, высота, число мин).
# Подобраны под no-guess генерацию: плавный рост размера И плотности мин,
# плотность держится в пределах ~20% — так генерация поля остаётся быстрой
# (доли секунды) и поле гарантированно проходится без угадывания.
#   Уровень    Размер   Мин   Плотность
#   Beginner    9×9      10    12.3%
#   Easy       12×12     20    13.9%
#   Medium     16×16     40    15.6%
#   Hard       24×20     88    18.3%
#   Huge       30×20    115    19.2%
#   Extreme    40×30    235    19.6%
DIFFICULTIES = {
    "Beginner": (9, 9, 10),
    "Easy": (12, 12, 20),
    "Medium": (16, 16, 40),
    "Hard": (24, 20, 88),
    "Huge": (30, 20, 115),
    "Extreme": (40, 30, 235)
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("No-Guess Minesweeper")
        self.setMinimumSize(440, 620)

        self.game = None
        self.board_widget = None
        self.current_theme = themes.DEFAULT_THEME
        self._endgame_shown = False

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Экран 1: Главное меню
        self.menu_widget = MainMenuWidget(
            DIFFICULTIES, themes.THEME_ORDER, self.current_theme,
            self.start_new_game, self.resume_game, self.apply_theme
        )
        self.stacked_widget.addWidget(self.menu_widget)

        # Экран 2: Игровой процесс
        self.game_container = QWidget()
        self.game_layout = QVBoxLayout()
        self.game_layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        self.game_layout.setContentsMargins(16, 12, 16, 16)
        self.game_container.setLayout(self.game_layout)
        self.stacked_widget.addWidget(self.game_container)

        # Таймер обновления HUD
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_hud)

        # Применяем стартовую тему
        self.apply_theme(self.current_theme)

    # ------------------------------------------------------------------ #
    # Темы
    # ------------------------------------------------------------------ #
    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(themes.build_qss(theme_name))
        if self.menu_widget.current_theme != theme_name:
            self.menu_widget.set_theme(theme_name)
        if self.board_widget is not None:
            self.board_widget.set_theme(theme_name)

    # ------------------------------------------------------------------ #
    # Игра
    # ------------------------------------------------------------------ #
    def start_new_game(self, difficulty_name):
        width, height, mines = DIFFICULTIES[difficulty_name]
        self.game = Game(width, height, mines)
        self._endgame_shown = False

        self.menu_widget.btn_resume.setEnabled(True)
        self.build_game_ui()
        self.gui_timer.start(100)
        self.stacked_widget.setCurrentWidget(self.game_container)
        self.adjustSize()

    def resume_game(self):
        if self.game and self.game.state in (GameState.NOT_STARTED, GameState.PLAYING):
            self.stacked_widget.setCurrentWidget(self.game_container)
            self.adjustSize()

    def return_to_menu(self):
        self.stacked_widget.setCurrentWidget(self.menu_widget)
        self.setMinimumSize(440, 620)
        self.resize(440, 620)

    def build_game_ui(self):
        # Очищаем старый layout игры
        while self.game_layout.count():
            child = self.game_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Верхняя панель (HUD)
        hud_layout = QHBoxLayout()

        btn_back = QPushButton("←")
        btn_back.setObjectName("BackButton")
        btn_back.setFocusPolicy(Qt.NoFocus)
        btn_back.clicked.connect(self.return_to_menu)
        hud_layout.addWidget(btn_back)

        self.mines_label = QLabel(f"⚑ {self.game.num_mines}")
        self.mines_label.setObjectName("HudLabel")
        self.timer_label = QLabel("0")
        self.timer_label.setObjectName("HudLabel")

        hud_layout.addWidget(self.mines_label)
        hud_layout.addStretch()
        hud_layout.addWidget(self.timer_label)

        self.game_layout.addLayout(hud_layout)
        self.game_layout.addSpacing(10)

        # Игровое поле (кастомная отрисовка + анимации)
        self.board_widget = BoardWidget(self.game, self.current_theme)
        self.board_widget.state_changed.connect(self.update_hud)
        self.game_layout.addWidget(self.board_widget, alignment=Qt.AlignCenter)

    def update_hud(self):
        if not self.game:
            return

        elapsed = self.game.get_elapsed_time()
        self.timer_label.setText(f"{elapsed}")

        mines_left = self.game.num_mines - self.game.flags_placed
        self.mines_label.setText(f"⚑ {mines_left}")

        if self.game.state in (GameState.WON, GameState.LOST) and not self._endgame_shown:
            self._endgame_shown = True
            self.gui_timer.stop()
            self.menu_widget.btn_resume.setEnabled(False)
            # Даём анимациям доиграть, затем показываем результат.
            delay = 650 if self.game.state == GameState.LOST else 450
            QTimer.singleShot(delay, self._show_endgame)

    def _show_endgame(self):
        if self.board_widget:
            self.board_widget.update()
        if self.game.state == GameState.WON:
            elapsed = self.game.get_elapsed_time()
            QMessageBox.information(self, "Victory!", f"You won in {elapsed} seconds!")
        else:
            QMessageBox.critical(self, "Defeat", "You hit a mine!")
        self.return_to_menu()
