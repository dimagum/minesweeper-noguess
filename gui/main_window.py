from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QMessageBox, QMenuBar)
from PyQt5.QtCore import QTimer, Qt
from core.game import Game, GameState
from gui.board_widget import BoardWidget

# Настройки уровней сложности
DIFFICULTIES = {
    "Beginner": (9, 9, 10),
    "Easy": (12, 12, 20),
    "Medium": (16, 16, 40),
    "Hard": (30, 16, 99),
    "Huge": (30, 24, 150),
    "Extreme": (40, 30, 250)
}

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("No-Guess Minesweeper")
        self.current_difficulty = "Beginner"
        
        # UI элементы
        self.timer_label = None
        self.mines_label = None
        self.board_widget = None
        
        # Системный таймер GUI
        self.gui_timer = QTimer(self)
        self.gui_timer.timeout.connect(self.update_hud)
        self.gui_timer.start(100) # Обновляем UI 10 раз в секунду

        self.init_menu()
        self.start_new_game()

    def init_menu(self):
        menu_bar = self.menuBar()
        game_menu = menu_bar.addMenu("Игра")

        new_game_action = game_menu.addAction("Новая игра")
        new_game_action.triggered.connect(self.start_new_game)
        
        game_menu.addSeparator()

        # Добавляем уровни сложности
        for diff_name in DIFFICULTIES.keys():
            action = game_menu.addAction(diff_name)
            # Захватываем текущее значение diff_name через lambda
            action.triggered.connect(lambda checked, d=diff_name: self.change_difficulty(d))

    def change_difficulty(self, difficulty_name):
        self.current_difficulty = difficulty_name
        self.start_new_game()

    def start_new_game(self):
        width, height, mines = DIFFICULTIES[self.current_difficulty]
        self.game = Game(width, height, mines)

        # Создаем центральный виджет
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSizeConstraint(QVBoxLayout.SetFixedSize) # Окно подстраивается под содержимое

        # Верхняя панель (HUD)
        hud_layout = QHBoxLayout()
        self.mines_label = QLabel(f"Мин: {self.game.num_mines}")
        self.timer_label = QLabel("Время: 0")
        
        # Стилизуем HUD
        font = self.mines_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.mines_label.setFont(font)
        self.timer_label.setFont(font)
        self.timer_label.setAlignment(Qt.AlignRight)

        hud_layout.addWidget(self.mines_label)
        hud_layout.addWidget(self.timer_label)

        # Добавляем игровое поле
        self.board_widget = BoardWidget(self.game)

        # Собираем всё вместе
        main_layout.addLayout(hud_layout)
        main_layout.addWidget(self.board_widget)
        central_widget.setLayout(main_layout)
        
        self.setCentralWidget(central_widget)
        self.adjustSize() # Подгоняем размер окна под новую сетку

    def update_hud(self):
        """Обновление таймера, счетчика мин и проверка на победу/поражение."""
        # Обновляем время
        elapsed = self.game.get_elapsed_time()
        self.timer_label.setText(f"Время: {elapsed}")

        # Обновляем оставшиеся мины
        mines_left = self.game.num_mines - self.game.flags_placed
        self.mines_label.setText(f"Мин: {mines_left}")

        # Проверка конца игры
        if self.game.state == GameState.WON:
            self.gui_timer.stop()
            self.board_widget.update_board() # Финальная перерисовка (чтобы показать авто-флажки)
            QMessageBox.information(self, "Победа!", f"Вы победили за {elapsed} секунд!")
            self.start_new_game()
            
        elif self.game.state == GameState.LOST:
            self.gui_timer.stop()
            self.board_widget.update_board()
            QMessageBox.critical(self, "Поражение", "Вы подорвались на мине!")
            self.start_new_game()
