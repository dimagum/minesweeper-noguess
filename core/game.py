import time
from enum import Enum
from core.board import Board
from core.generator import Generator

class GameState(Enum):
    NOT_STARTED = 0
    PLAYING = 1
    WON = 2
    LOST = 3

class Game:
    def __init__(self, width: int, height: int, num_mines: int):
        self.width = width
        self.height = height
        self.num_mines = num_mines
        
        # До первого клика создаем пустую доску-"пустышку" без мин, 
        # чтобы GUI мог отрисовать сетку.
        self.board = Board(width, height, 0) 
        
        self.state = GameState.NOT_STARTED
        self.flags_placed = 0
        self.opened_cells = 0
        
        self.start_time = 0.0
        self.end_time = 0.0

    def get_elapsed_time(self) -> int:
        """Возвращает прошедшее время в секундах."""
        if self.state == GameState.NOT_STARTED:
            return 0
        elif self.state == GameState.PLAYING:
            return int(time.time() - self.start_time)
        else:
            # Если игра окончена, возвращаем зафиксированное время
            return int(self.end_time - self.start_time)

    def handle_left_click(self, x: int, y: int):
        if self.state in (GameState.WON, GameState.LOST):
            return
        
        cell = self.board.get_cell(x, y)
        # Если клетка с флагом или уже открыта - одиночный клик ничего не делает
        if not cell or cell.is_flagged or cell.is_open:
            return

        if self.state == GameState.NOT_STARTED:
            self._start_game(x, y)
            cell = self.board.get_cell(x, y)

        self._open_cell(x, y)
        self._check_win_condition()

    def handle_right_click(self, x: int, y: int):
        """Обработка правого клика: установка/снятие флага."""
        if self.state not in (GameState.NOT_STARTED, GameState.PLAYING):
            return

        cell = self.board.get_cell(x, y)
        if not cell or cell.is_open:
            return

        # Переключаем статус флага
        cell.is_flagged = not cell.is_flagged
        self.flags_placed += 1 if cell.is_flagged else -1

    def handle_both_click(self, x: int, y: int):
        """Обработка Аккорда (колесико мыши или ЛКМ+ПКМ)."""
        if self.state in (GameState.WON, GameState.LOST):
            return
            
        cell = self.board.get_cell(x, y)
        # Аккорд работает только если кликнуть по ОТКРЫТОЙ клетке с цифрой
        if not cell or not cell.is_open or cell.adjacent_mines == 0:
            return
            
        # Считаем флаги вокруг
        neighbors = self.board.get_neighbors(x, y)
        flags_count = sum(1 for n in neighbors if n.is_flagged)

        # Если количество флагов СТРОГО равно цифре
        if flags_count == cell.adjacent_mines:
            for n in neighbors:
                if not n.is_flagged and not n.is_open:
                    self._open_cell(n.x, n.y)
                    
        self._check_win_condition()

    def _start_game(self, start_x: int, start_y: int):
        """Инициализация поля при первом клике."""
        # Вызываем наш no-guess генератор
        self.board = Generator.generate_valid_board(
            self.width, self.height, self.num_mines, start_x, start_y
        )
        self.state = GameState.PLAYING
        self.start_time = time.time()

    def _open_cell(self, x: int, y: int):
        """Рекурсивное открытие клеток."""
        cell = self.board.get_cell(x, y)
        if not cell or cell.is_open or cell.is_flagged:
            return

        cell.is_open = True
        self.opened_cells += 1

        # Если наткнулись на мину
        if cell.is_mine:
            self.state = GameState.LOST
            self.end_time = time.time()
            return

        # Если открыли "0" - автоматически открываем всех соседей
        if cell.adjacent_mines == 0:
            for neighbor in self.board.get_neighbors(x, y):
                self._open_cell(neighbor.x, neighbor.y)

    def _handle_chording(self, x: int, y: int):
        """
        Логика Аккорда: если вокруг цифры стоит нужное количество флагов,
        остальные соседние клетки автоматически открываются.
        """
        cell = self.board.get_cell(x, y)
        if not cell or not cell.is_open or cell.adjacent_mines == 0:
            return

        neighbors = self.board.get_neighbors(x, y)
        flags_count = sum(1 for n in neighbors if n.is_flagged)

        # Если количество флагов равно цифре на клетке
        if flags_count == cell.adjacent_mines:
            for n in neighbors:
                if not n.is_flagged and not n.is_open:
                    self._open_cell(n.x, n.y)

    def _check_win_condition(self):
        """Проверяет победу путем прямого подсчета неоткрытых безопасных ячеек."""
        if self.state != GameState.PLAYING:
            return

        # Надежный способ: считаем, сколько осталось закрытых клеток
        closed_cells_count = 0
        for y in range(self.height):
            for x in range(self.width):
                if not self.board.get_cell(x, y).is_open:
                    closed_cells_count += 1

        # Если количество закрытых клеток равно количеству мин - это победа!
        if closed_cells_count == self.num_mines:
            self.state = GameState.WON
            self.end_time = time.time()
            
            # Автоматически ставим флаги на все оставшиеся закрытые мины (для красоты)
            for y in range(self.height):
                for x in range(self.width):
                    cell = self.board.get_cell(x, y)
                    if not cell.is_open and not cell.is_flagged:
                        cell.is_flagged = True
                        self.flags_placed += 1
