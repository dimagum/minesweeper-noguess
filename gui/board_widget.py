from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal
from core.game import GameState

class CellButton(QPushButton):
    # Кастомные сигналы для передачи координат клика
    left_clicked = pyqtSignal(int, int)
    right_clicked = pyqtSignal(int, int)

    def __init__(self, x: int, y: int):
        super().__init__()
        self.x = x
        self.y = y
        self.setFixedSize(30, 30)  # Жестко задаем размер ячейки
        self.setFocusPolicy(Qt.NoFocus) # Убираем рамку фокуса при клике

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.left_clicked.emit(self.x, self.y)
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(self.x, self.y)
        super().mouseReleaseEvent(event)

class BoardWidget(QWidget):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.buttons = {}  # Словарь для быстрого доступа к кнопкам по координатам (x, y)
        self.init_ui()

    def init_ui(self):
        self.layout = QGridLayout()
        self.layout.setSpacing(0) # Убираем отступы между кнопками
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        # Создаем сетку кнопок
        for y in range(self.game.height):
            for x in range(self.game.width):
                btn = CellButton(x, y)
                btn.left_clicked.connect(self.on_left_click)
                btn.right_clicked.connect(self.on_right_click)
                self.layout.addWidget(btn, y, x)
                self.buttons[(x, y)] = btn

    def on_left_click(self, x, y):
        self.game.handle_left_click(x, y)
        self.update_board()

    def on_right_click(self, x, y):
        self.game.handle_right_click(x, y)
        self.update_board()

    def update_board(self):
        """Синхронизирует внешний вид кнопок с состоянием ядра игры."""
        for y in range(self.game.height):
            for x in range(self.game.width):
                cell = self.game.board.get_cell(x, y)
                btn = self.buttons[(x, y)]

                # В будущем здесь мы будем назначать QSS-классы или картинки (icons)
                if cell.is_open:
                    btn.setEnabled(False) # Отключаем нажатие для открытой
                    if cell.is_mine:
                        btn.setText("💣")
                        btn.setStyleSheet("background-color: red; color: black;")
                    elif cell.adjacent_mines > 0:
                        btn.setText(str(cell.adjacent_mines))
                        btn.setStyleSheet("background-color: #ddd; font-weight: bold;")
                    else:
                        btn.setText("")
                        btn.setStyleSheet("background-color: #ddd;")
                else:
                    btn.setEnabled(True)
                    if cell.is_flagged:
                        btn.setText("🚩")
                        btn.setStyleSheet("color: red;")
                    else:
                        btn.setText("")
                        btn.setStyleSheet("") # Сбрасываем стиль до дефолтного
