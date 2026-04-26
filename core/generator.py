import random
from core.board import Board
from solver.logic_solver import LogicSolver

class Generator:
    @staticmethod
    def generate_valid_board(width: int, height: int, num_mines: int, start_x: int, start_y: int) -> Board:
        max_attempts = 200     # Максимум полных пересозданий поля
        max_mutations = 100    # Максимум попыток сдвинуть мину (мутаций)
        
        for attempt in range(max_attempts):
            board = Board(width, height, num_mines)
            Generator._place_mines(board, start_x, start_y)
            board.calculate_numbers()
            
            for mutation in range(max_mutations):
                solver = LogicSolver(board)
                if solver.is_solvable(start_x, start_y):
                    print(f"Поле сгенерировано! Попыток: {attempt + 1}, Мутаций: {mutation}")
                    return board
                
                # Поле не решилось. Пытаемся "распутать" тупик с помощью мутации
                if not Generator._mutate_board(board, solver.opened, start_x, start_y):
                    break # Если мутация не удалась (нет места), генерируем с нуля
                    
        # В крайне редком случае, если лимит превышен, возвращаем то, что есть
        print("Внимание: Превышен лимит генерации. Возвращаем последнюю версию.")
        return board

    @staticmethod
    def _mutate_board(board: Board, opened: set, start_x: int, start_y: int) -> bool:
        """Меняет местами мину на границе с пустой клеткой в неисследованной зоне."""
        frontier = set()
        unreached = set()
        
        # 1. Разделяем закрытые клетки на пограничные и неисследованные
        for y in range(board.height):
            for x in range(board.width):
                if (x, y) in opened:
                    continue
                
                # Проверяем соседей на наличие открытых клеток
                is_frontier = False
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if (x + dx, y + dy) in opened:
                            is_frontier = True
                            break
                    if is_frontier:
                        break
                        
                if is_frontier:
                    frontier.add((x, y))
                else:
                    unreached.add((x, y))
        
        # 2. Группируем мины и пустые клетки
        frontier_mines = [(x, y) for (x, y) in frontier if board.get_cell(x, y).is_mine]
        frontier_safes = [(x, y) for (x, y) in frontier if not board.get_cell(x, y).is_mine]
        
        unreached_mines = [(x, y) for (x, y) in unreached if board.get_cell(x, y).is_mine]
        unreached_safes = [(x, y) for (x, y) in unreached if not board.get_cell(x, y).is_mine]
        
        # Защищаем зону первого клика, чтобы туда случайно не перенеслась мина
        safe_zone = {(start_x + dx, start_y + dy) for dx in [-1, 0, 1] for dy in [-1, 0, 1]}
        unreached_mines = [p for p in unreached_mines if p not in safe_zone]
        unreached_safes = [p for p in unreached_safes if p not in safe_zone]

        # 3. Выбираем пару для обмена (Мина на границе <-> Пустая в глубине)
        # или наоборот (Пустая на границе <-> Мина в глубине)
        c1, c2 = None, None
        
        options = []
        if frontier_mines and unreached_safes:
            options.append((frontier_mines, unreached_safes))
        if frontier_safes and unreached_mines:
            options.append((frontier_safes, unreached_mines))
            
        if options:
            group1, group2 = random.choice(options)
            c1 = random.choice(group1)
            c2 = random.choice(group2)
            
            # Обмениваем состояния клеток
            cell1 = board.get_cell(*c1)
            cell2 = board.get_cell(*c2)
            cell1.is_mine, cell2.is_mine = cell2.is_mine, cell1.is_mine
            
            # Пересчитываем цифры
            board.calculate_numbers()
            return True
            
        return False # Нечего менять

    @staticmethod
    def _place_mines(board: Board, start_x: int, start_y: int):
        safe_zone = set()
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                safe_zone.add((start_x + dx, start_y + dy))

        available_positions = [
            (x, y) for x in range(board.width) for y in range(board.height)
            if (x, y) not in safe_zone
        ]

        mine_positions = random.sample(available_positions, board.num_mines)
        for x, y in mine_positions:
            board.get_cell(x, y).is_mine = True
