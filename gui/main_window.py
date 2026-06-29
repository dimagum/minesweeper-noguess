from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QMessageBox, QStackedWidget, QPushButton)
from PyQt5.QtCore import QTimer, Qt
from core.game import Game, GameState
from gui.board_widget import BoardWidget
from gui.main_menu import MainMenuWidget

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
        self.setMinimumSize(400, 600) # Минимальный размер для красивого меню
        
        self.game = None
        self.board_widget = None
        
        # Настраиваем QStackedWidget для переключения экранов
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # Экран 1: Главное меню
        self.menu_widget = MainMenuWidget(DIFFICULTIES, self.start_new_game, self.resume_game)
        self.stacked_widget.addWidget(self.menu_widget)
        
        # Экран 2: Игровой процесс
        self.game_container = QWidget()
        self.game_layout = QVBoxLayout()
        self.game_layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        self.game_container.setLayout(self.game_layout)
        self.stacked_widget.addWidget(self.game_container)
        
        # Таймер
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_hud)

    def start_new_game(self, difficulty_name):
        width, height, mines = DIFFICULTIES[difficulty_name]
        self.game = Game(width, height, mines)
        
        self.menu_widget.btn_resume.setEnabled(True) # Включаем кнопку Resume
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
        # Возвращаем фиксированный размер окна для меню
        self.setMinimumSize(400, 600)
        self.resize(400, 600)

    def build_game_ui(self):
        # Очищаем старый layout игры
        while self.game_layout.count():
            child = self.game_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        # Верхняя панель (HUD)
        hud_layout = QHBoxLayout()
        
        # Кнопка Назад (Стрелка)
        btn_back = QPushButton("←")
        btn_back.setObjectName("BackButton")
        btn_back.clicked.connect(self.return_to_menu)
        hud_layout.addWidget(btn_back)
        
        # Иконка мины и количество
        self.mines_label = QLabel(f"⚙ {self.game.num_mines}") # Используем ту же шестеренку как иконку
        self.timer_label = QLabel("0S")
        
        hud_layout.addWidget(self.mines_label)
        hud_layout.addStretch() # Раздвигаем края
        hud_layout.addWidget(self.timer_label)
        
        self.game_layout.addLayout(hud_layout)
        
        # Добавляем игровое поле
        self.board_widget = BoardWidget(self.game)
        self.game_layout.addWidget(self.board_widget)

    def update_hud(self):
        if not self.game: return
        
        elapsed = self.game.get_elapsed_time()
        self.timer_label.setText(f"{elapsed}S")

        mines_left = self.game.num_mines - self.game.flags_placed
        self.mines_label.setText(f"⚙ {mines_left}")

        if self.game.state == GameState.WON:
            self.gui_timer.stop()
            self.board_widget.update_board()
            self.menu_widget.btn_resume.setEnabled(False) # Отключаем Resume
            QMessageBox.information(self, "Victory!", f"You won in {elapsed} seconds!")
            self.return_to_menu()
            
        elif self.game.state == GameState.LOST:
            self.gui_timer.stop()
            self.board_widget.update_board()
            self.menu_widget.btn_resume.setEnabled(False)
            QMessageBox.critical(self, "Defeat", "You hit a mine!")
            self.return_to_menu()
