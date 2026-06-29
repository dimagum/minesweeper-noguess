import random
from core.board import Board
from solver.logic_solver import LogicSolver


class Generator:
    """No-guess генератор поля «Сапёра».

    Стратегия «создать и проверить» с локальным поиском (мутациями):
      1. Случайно расставляем мины (3x3 вокруг первого клика — всегда пусто).
      2. Решатель симулирует прохождение чистой логикой.
      3. Если застряли — переносим мину у «застрявшей» границы в глубину
         (или наоборот), пересчитываем только затронутые цифры и пробуем снова.
      4. Если мутации не помогают — генерируем поле заново.

    Если решатель сказал «решаемо», поле гарантированно проходится без угадывания.
    """

    @staticmethod
    def generate_valid_board(width: int, height: int, num_mines: int,
                             start_x: int, start_y: int,
                             max_attempts: int = 300,
                             max_mutations: int = 80,
                             rng: random.Random = None) -> Board:
        rng = rng or random

        for attempt in range(max_attempts):
            board = Board(width, height, num_mines)
            Generator._place_mines(board, start_x, start_y, rng)
            board.calculate_numbers()

            solver = LogicSolver(board)
            for mutation in range(max_mutations):
                if solver.is_solvable(start_x, start_y):
                    board.is_noguess = True
                    return board

                # Поле застряло — пытаемся «распутать» тупик мутацией возле
                # фактической границы, где решатель остановился.
                if not Generator._mutate_board(board, solver.opened,
                                               start_x, start_y, rng):
                    break  # менять нечего — генерируем с нуля
                solver = LogicSolver(board)

        # Сюда попадаем лишь при экстремальной плотности мин. Возвращаем поле,
        # но честно помечаем, что гарантия no-guess не достигнута.
        board.is_noguess = False
        print("Внимание: не удалось гарантировать no-guess за лимит попыток. "
              "Стоит снизить плотность мин для этого размера поля.")
        return board

    @staticmethod
    def _mutate_board(board: Board, opened: set,
                      start_x: int, start_y: int, rng: random.Random) -> bool:
        """Меняет местами мину и пустую клетку, чтобы разрушить тупик.

        Приоритет — клетки на границе открытой области (где решатель встал),
        обмениваемые с клетками в ещё не исследованной глубине."""
        width, height = board.width, board.height
        grid = board.grid

        frontier = []      # закрытые клетки, граничащие с открытыми
        unreached = []     # закрытые клетки без открытых соседей
        for y in range(height):
            for x in range(width):
                if (x, y) in opened:
                    continue
                is_frontier = any((nx, ny) in opened
                                  for nx, ny in board.neighbor_coords(x, y))
                (frontier if is_frontier else unreached).append((x, y))

        frontier_mines = [(x, y) for (x, y) in frontier if grid[y][x].is_mine]
        frontier_safes = [(x, y) for (x, y) in frontier if not grid[y][x].is_mine]
        unreached_mines = [(x, y) for (x, y) in unreached if grid[y][x].is_mine]
        unreached_safes = [(x, y) for (x, y) in unreached if not grid[y][x].is_mine]

        # Не переносим мину в зону первого клика.
        safe_zone = {(start_x + dx, start_y + dy)
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        unreached_mines = [p for p in unreached_mines if p not in safe_zone]
        unreached_safes = [p for p in unreached_safes if p not in safe_zone]

        options = []
        if frontier_mines and unreached_safes:
            options.append((frontier_mines, unreached_safes))
        if frontier_safes and unreached_mines:
            options.append((frontier_safes, unreached_mines))
        if not options:
            return False

        group1, group2 = rng.choice(options)
        (x1, y1) = rng.choice(group1)
        (x2, y2) = rng.choice(group2)

        c1, c2 = grid[y1][x1], grid[y2][x2]
        c1.is_mine, c2.is_mine = c2.is_mine, c1.is_mine

        # Инкрементально пересчитываем только затронутые клетки.
        board.recalc_around(x1, y1)
        board.recalc_around(x2, y2)
        return True

    @staticmethod
    def _place_mines(board: Board, start_x: int, start_y: int, rng: random.Random):
        safe_zone = {(start_x + dx, start_y + dy)
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        available = [(x, y) for x in range(board.width)
                     for y in range(board.height) if (x, y) not in safe_zone]
        for x, y in rng.sample(available, board.num_mines):
            board.grid[y][x].is_mine = True
