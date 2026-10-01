class Cell:
    __slots__ = ("x", "y", "is_mine", "is_open", "is_flagged", "adjacent_mines")

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

        # Кэш координат соседей: для каждой клетки заранее вычисляем
        # список (nx, ny). Это убирает повторные проверки границ и
        # заметно ускоряет генерацию/решатель на больших полях.
        self._neighbor_coords = [[None] * width for _ in range(height)]
        for y in range(height):
            for x in range(width):
                coords = []
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            coords.append((nx, ny))
                self._neighbor_coords[y][x] = coords

    def get_cell(self, x: int, y: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return None

    def neighbor_coords(self, x: int, y: int):
        """Возвращает закэшированный список координат соседей (nx, ny)."""
        return self._neighbor_coords[y][x]

    def get_neighbors(self, x: int, y: int):
        grid = self.grid
        return [grid[ny][nx] for nx, ny in self._neighbor_coords[y][x]]

    def calculate_numbers(self):
        """Подсчитывает цифры (количество мин вокруг) для каждой клетки."""
        grid = self.grid
        for row in grid:
            for cell in row:
                if cell.is_mine:
                    cell.adjacent_mines = 0
                    continue
                cell.adjacent_mines = sum(
                    1 for nx, ny in self._neighbor_coords[cell.y][cell.x]
                    if grid[ny][nx].is_mine
                )

    def recalc_around(self, x: int, y: int):
        """Инкрементальный пересчёт цифр для клетки (x, y) и её соседей.

        Используется генератором после обмена ровно двух клеток местами,
        чтобы не пересчитывать всё поле каждый раз."""
        grid = self.grid
        affected = {(x, y)}
        affected.update(self._neighbor_coords[y][x])
        for cx, cy in affected:
            cell = grid[cy][cx]
            if cell.is_mine:
                cell.adjacent_mines = 0
                continue
            cell.adjacent_mines = sum(
                1 for nx, ny in self._neighbor_coords[cy][cx]
                if grid[ny][nx].is_mine
            )
