from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

class CellButton(QPushButton):
    left_clicked = pyqtSignal(int, int)
    right_clicked = pyqtSignal(int, int)
    both_clicked = pyqtSignal(int, int)

    def __init__(self, x: int, y: int):
        super().__init__()
        self.x = x
        self.y = y
        self.setFixedSize(30, 30)
        self.setFocusPolicy(Qt.NoFocus)
        
        # Надежный трекер состояния кнопок мыши
        self._left_pressed = False
        self._right_pressed = False
        self._chord_executed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._left_pressed = True
        elif event.button() == Qt.RightButton:
            self._right_pressed = True
            
        # Аккорд срабатывает: Колесиком ИЛИ (ЛКМ + ПКМ)
        if event.button() == Qt.MiddleButton or (self._left_pressed and self._right_pressed):
            self.both_clicked.emit(self.x, self.y)
            self._chord_executed = True

    def mouseReleaseEvent(self, event):
        # Отпускание кнопок
        if event.button() == Qt.LeftButton:
            self._left_pressed = False
            # Если это был обычный клик (не аккорд), вызываем открытие
            if not self._chord_executed:
                self.left_clicked.emit(self.x, self.y)
                
        elif event.button() == Qt.RightButton:
            self._right_pressed = False
            if not self._chord_executed:
                self.right_clicked.emit(self.x, self.y)
                
        # Когда отпустили ВСЕ кнопки, сбрасываем статус аккорда
        if not self._left_pressed and not self._right_pressed:
            self._chord_executed = False

class BoardWidget(QWidget):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.buttons = {}
        self.init_ui()

    def init_ui(self):
        self.layout = QGridLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        for y in range(self.game.height):
            for x in range(self.game.width):
                btn = CellButton(x, y)
                # Подключаем все три сигнала
                btn.left_clicked.connect(self.on_left_click)
                btn.right_clicked.connect(self.on_right_click)
                btn.both_clicked.connect(self.on_both_click)
                
                self.layout.addWidget(btn, y, x)
                self.buttons[(x, y)] = btn

    def on_left_click(self, x, y):
        self.game.handle_left_click(x, y)
        self.update_board()

    def on_right_click(self, x, y):
        self.game.handle_right_click(x, y)
        self.update_board()

    def on_both_click(self, x, y):
        self.game.handle_both_click(x, y)
        self.update_board()

    def update_board(self):
        """Синхронизирует внешний вид кнопок с состоянием ядра игры."""
        for y in range(self.game.height):
            for x in range(self.game.width):
                cell = self.game.board.get_cell(x, y)
                btn = self.buttons[(x, y)]

                btn.setEnabled(True) 

                if cell.is_open:
                    btn.setProperty("is_open", True)
                    btn.setProperty("is_flagged", False)
                    
                    if cell.is_mine:
                        btn.setText("💣")
                        btn.setProperty("is_mine", True)
                    elif cell.adjacent_mines > 0:
                        btn.setText(str(cell.adjacent_mines))
                        btn.setProperty("is_mine", False)
                    else:
                        btn.setText("")
                        btn.setProperty("is_mine", False)
                else:
                    btn.setProperty("is_open", False)
                    btn.setProperty("is_mine", False)
                    
                    if cell.is_flagged:
                        btn.setText("🚩")
                        btn.setProperty("is_flagged", True)
                    else:
                        btn.setText("")
                        btn.setProperty("is_flagged", False)

                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
