class LogicSolver:
    def __init__(self, board):
        self.board = board
        self.width = board.width
        self.height = board.height

    def is_solvable(self, start_x: int, start_y: int) -> bool:
        self.opened = set()
        self.flagged = set()
        opened = self.opened    # Оставляем локальные ссылки для скорости
        flagged = self.flagged

        def open_cell(x, y):
            if (x, y) in opened or (x, y) in flagged:
                return False
            
            cell = self.board.get_cell(x, y)
            if cell.is_mine:
                return False
            
            opened.add((x, y))
            if cell.adjacent_mines == 0:
                for n in self.board.get_neighbors(x, y):
                    open_cell(n.x, n.y)
            return True

        # Делаем стартовый клик
        open_cell(start_x, start_y)

        # Главный цикл решения
        while True:
            # 1. Сначала пытаемся решить тривиальной логикой (быстро)
            changed = self._apply_trivial_logic(opened, flagged, open_cell)
            
            # 2. Если тривиальная логика застряла (ничего не изменилось),
            # применяем тяжелую логику подмножеств.
            if not changed:
                changed = self._apply_subset_logic(opened, flagged, open_cell)
            
            # Если оба метода не дали новых открытий или флагов, значит
            # мы застряли окончательно (нужно угадывать).
            if not changed:
                break

        total_safe_cells = (self.width * self.height) - self.board.num_mines
        return len(opened) == total_safe_cells

    def _apply_trivial_logic(self, opened, flagged, open_cell_func):
        """Базовые правила Сапёра (100% мин найдено или 100% безопасно)."""
        changed = False
        for x, y in list(opened):
            cell = self.board.get_cell(x, y)
            if cell.adjacent_mines == 0:
                continue

            neighbors = self.board.get_neighbors(x, y)
            unknowns = []
            flags_count = 0

            for n in neighbors:
                if (n.x, n.y) in flagged:
                    flags_count += 1
                elif (n.x, n.y) not in opened:
                    unknowns.append(n)

            if not unknowns:
                continue

            # Правило 1: Все оставшиеся - мины
            if cell.adjacent_mines == flags_count + len(unknowns):
                for u in unknowns:
                    flagged.add((u.x, u.y))
                    changed = True
                    
            # Правило 2: Все оставшиеся - безопасны (Аккорд)
            elif cell.adjacent_mines == flags_count:
                for u in unknowns:
                    open_cell_func(u.x, u.y)
                    changed = True
                    
        return changed

    def _apply_subset_logic(self, opened, flagged, open_cell_func):
        """Продвинутый анализ: вычитание пересекающихся множеств (Subset Analysis)."""
        constraints = []
        
        # Шаг 1: Собираем все уравнения для пограничных цифр
        for x, y in opened:
            cell = self.board.get_cell(x, y)
            if cell.adjacent_mines == 0:
                continue
            
            neighbors = self.board.get_neighbors(x, y)
            unknowns = frozenset((n.x, n.y) for n in neighbors 
                                 if (n.x, n.y) not in opened and (n.x, n.y) not in flagged)
            flags_count = sum(1 for n in neighbors if (n.x, n.y) in flagged)
            
            if unknowns:
                target_mines = cell.adjacent_mines - flags_count
                if target_mines > 0:
                    # Добавляем уникальное ограничение (Множество клеток, Сколько в них мин)
                    if (unknowns, target_mines) not in constraints:
                        constraints.append((unknowns, target_mines))
        
        changed = False
        
        # Шаг 2: Сравниваем каждое уравнение с каждым
        for i in range(len(constraints)):
            for j in range(len(constraints)):
                if i == j:
                    continue
                
                set1, target1 = constraints[i]
                set2, target2 = constraints[j]
                
                # Если set1 является строгим подмножеством set2
                if set1.issubset(set2) and set1 != set2:
                    diff_set = set2 - set1
                    diff_target = target2 - target1
                    
                    # Если в оставшихся клетках количество мин равно их числу -> это мины
                    if diff_target == len(diff_set):
                        for cx, cy in diff_set:
                            if (cx, cy) not in flagged:
                                flagged.add((cx, cy))
                                changed = True
                                
                    # Если в оставшихся клетках 0 мин -> они безопасны
                    elif diff_target == 0:
                        for cx, cy in diff_set:
                            if (cx, cy) not in opened and (cx, cy) not in flagged:
                                open_cell_func(cx, cy)
                                changed = True
        return changed
