import random

class Cell:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.is_mine = False
        self.is_open = False
        self.is_flagged = False
        self.adjacent_mines = 0

class Board:
    def __init__(self, width: int, height: int, num_mines: int):
        self.width = width
        self.height = height
        self.num_mines = num_mines
        # Создаем двумерный массив (y - строки, x - колонки)
        self.grid = [[Cell(x, y) for x in range(width)] for y in range(height)]

    def get_cell(self, x: int, y: int) -> Cell:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return None

    def get_neighbors(self, x: int, y: int) -> list[Cell]:
        neighbors = []
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                cell = self.get_cell(x + dx, y + dy)
                if cell:
                    neighbors.append(cell)
        return neighbors

    def calculate_numbers(self):
        """Подсчитывает цифры (количество мин вокруг) для каждой клетки"""
        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if cell.is_mine:
                    continue
                mines_count = sum(1 for n in self.get_neighbors(x, y) if n.is_mine)
                cell.adjacent_mines = mines_count
