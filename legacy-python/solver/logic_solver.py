"""Логический решатель «Сапёра» для проверки поля на решаемость без угадывания.

Решатель ЗВУЧНЫЙ (sound): он никогда не объявляет клетку безопасной/миной,
если это не следует строго из доступной информации. Поэтому если is_solvable
вернул True, поле гарантированно проходится чистой логикой, без угадывания.

Используемые техники (от дешёвых к дорогим):
  1. Тривиальная логика одной цифры (все мины / все безопасны).
  2. Вычитание пересекающихся множеств (subset logic).
  3. Глобальный счётчик оставшихся мин.
  4. Ограниченный перебор конфигураций по связным компонентам границы (CSP),
     объединённый с глобальным счётчиком — именно это устраняет финальные 50/50.
"""

# Максимальный размер связной компоненты границы (в клетках), для которой
# мы готовы перебирать конфигурации. Компоненты больше этого порога
# пропускаются (решатель просто ничего из них не выводит — это безопасно).
MAX_COMPONENT_CELLS = 22
# Защита от комбинаторного взрыва: предел числа найденных конфигураций
# на одну компоненту.
MAX_COMPONENT_SOLUTIONS = 40000


class LogicSolver:
    def __init__(self, board):
        self.board = board
        self.width = board.width
        self.height = board.height
        self.opened = set()
        self.flagged = set()

    # ------------------------------------------------------------------ #
    # Публичный API
    # ------------------------------------------------------------------ #
    def is_solvable(self, start_x: int, start_y: int) -> bool:
        self.opened = set()
        self.flagged = set()
        opened = self.opened
        flagged = self.flagged

        self._flood_open(start_x, start_y)

        while True:
            # 1. Дешёвая логика одной цифры.
            changed = self._apply_trivial_logic()
            # 2. Логика подмножеств.
            if not changed:
                changed = self._apply_subset_logic()
            # 3. Глобальный счётчик + перебор по компонентам (дорого).
            if not changed:
                changed = self._apply_global_and_csp()
            if not changed:
                break

        total_safe = (self.width * self.height) - self.board.num_mines
        return len(opened) == total_safe

    # ------------------------------------------------------------------ #
    # Открытие клеток (итеративный флуд — без рекурсии!)
    # ------------------------------------------------------------------ #
    def _flood_open(self, x: int, y: int) -> bool:
        """Открывает клетку и каскадно раскрывает нули. Возвращает True,
        если открыта хотя бы одна новая безопасная клетка."""
        opened = self.opened
        flagged = self.flagged
        board = self.board

        if (x, y) in opened or (x, y) in flagged:
            return False
        if board.get_cell(x, y).is_mine:
            # Решатель не должен сюда попадать на корректных выводах.
            return False

        stack = [(x, y)]
        any_opened = False
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in opened or (cx, cy) in flagged:
                continue
            cell = board.grid[cy][cx]
            if cell.is_mine:
                continue
            opened.add((cx, cy))
            any_opened = True
            if cell.adjacent_mines == 0:
                for nx, ny in board.neighbor_coords(cx, cy):
                    if (nx, ny) not in opened and (nx, ny) not in flagged:
                        stack.append((nx, ny))
        return any_opened

    # ------------------------------------------------------------------ #
    # 1. Тривиальная логика
    # ------------------------------------------------------------------ #
    def _apply_trivial_logic(self) -> bool:
        opened = self.opened
        flagged = self.flagged
        board = self.board
        changed = False

        for x, y in list(opened):
            cell = board.grid[y][x]
            if cell.adjacent_mines == 0:
                continue

            unknowns = []
            flags_count = 0
            for nx, ny in board.neighbor_coords(x, y):
                if (nx, ny) in flagged:
                    flags_count += 1
                elif (nx, ny) not in opened:
                    unknowns.append((nx, ny))

            if not unknowns:
                continue

            need = cell.adjacent_mines - flags_count
            # Все оставшиеся неизвестные — мины.
            if need == len(unknowns):
                for u in unknowns:
                    flagged.add(u)
                changed = True
            # Все оставшиеся неизвестные — безопасны.
            elif need == 0:
                for ux, uy in unknowns:
                    if self._flood_open(ux, uy):
                        changed = True

        return changed

    # ------------------------------------------------------------------ #
    # 2. Логика подмножеств
    # ------------------------------------------------------------------ #
    def _build_constraints(self):
        """Собирает уравнения (frozenset неизвестных, число мин в них)."""
        opened = self.opened
        flagged = self.flagged
        board = self.board
        constraints = []
        seen = set()

        for x, y in opened:
            cell = board.grid[y][x]
            if cell.adjacent_mines == 0:
                continue
            unknowns = []
            flags_count = 0
            for nx, ny in board.neighbor_coords(x, y):
                if (nx, ny) in flagged:
                    flags_count += 1
                elif (nx, ny) not in opened:
                    unknowns.append((nx, ny))
            if not unknowns:
                continue
            fs = frozenset(unknowns)
            target = cell.adjacent_mines - flags_count
            key = (fs, target)
            if key not in seen:
                seen.add(key)
                constraints.append((fs, target))
        return constraints

    def _apply_subset_logic(self) -> bool:
        constraints = self._build_constraints()
        flagged = self.flagged
        opened = self.opened
        changed = False

        # Индексируем по клеткам, чтобы сравнивать только пересекающиеся пары.
        n = len(constraints)
        for i in range(n):
            set1, t1 = constraints[i]
            for j in range(n):
                if i == j:
                    continue
                set2, t2 = constraints[j]
                if not set1 < set2:  # строгое подмножество
                    continue
                diff = set2 - set1
                dt = t2 - t1
                if dt == len(diff):
                    for c in diff:
                        if c not in flagged:
                            flagged.add(c)
                            changed = True
                elif dt == 0:
                    for cx, cy in diff:
                        if (cx, cy) not in opened and (cx, cy) not in flagged:
                            if self._flood_open(cx, cy):
                                changed = True
        return changed

    # ------------------------------------------------------------------ #
    # 3+4. Глобальный счётчик мин и перебор по компонентам (CSP)
    # ------------------------------------------------------------------ #
    def _apply_global_and_csp(self) -> bool:
        opened = self.opened
        flagged = self.flagged
        board = self.board
        W, H, = self.width, self.height

        remaining = board.num_mines - len(flagged)

        # Множество всех закрытых неотмеченных клеток.
        unknown_all = set()
        for y in range(H):
            for x in range(W):
                if (x, y) not in opened and (x, y) not in flagged:
                    unknown_all.add((x, y))

        if not unknown_all:
            return False

        # Тривиальные глобальные выводы.
        if remaining == 0:
            # Мин не осталось — все закрытые клетки безопасны.
            changed = False
            for ux, uy in list(unknown_all):
                if self._flood_open(ux, uy):
                    changed = True
            return changed
        if remaining == len(unknown_all):
            # Все закрытые клетки — мины.
            for c in unknown_all:
                flagged.add(c)
            return True
        if remaining < 0 or remaining > len(unknown_all):
            return False  # противоречие — пусть генератор перегенерирует

        # Строим ограничения и разбиваем граничные клетки на компоненты.
        constraints = self._build_constraints()
        if not constraints:
            return False

        border_cells = set()
        for fs, _ in constraints:
            border_cells |= fs
        interior_count = len(unknown_all) - len(border_cells)

        # --- объединение клеток в связные компоненты по общим ограничениям ---
        parent = {c: c for c in border_cells}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for fs, _ in constraints:
            it = iter(fs)
            first = next(it)
            for other in it:
                union(first, other)

        comps = {}
        for c in border_cells:
            comps.setdefault(find(c), set()).add(c)

        # Для каждой компоненты собираем её ограничения и перебираем конфигурации.
        # Результат: список «профилей» по числу мин k -> (cells_can_be_mine,
        # cells_can_be_safe), а также множество достижимых k.
        comp_profiles = []      # list of dict: k -> {"mine": set, "safe": set}
        comp_cells = []         # list of list(cells)
        undecidable = False

        for root, cells in comps.items():
            cell_list = sorted(cells)
            if len(cell_list) > MAX_COMPONENT_CELLS:
                undecidable = True
                comp_profiles.append(None)
                comp_cells.append(cell_list)
                continue

            local_constraints = []
            cellset = set(cell_list)
            for fs, t in constraints:
                if fs & cellset:
                    # все клетки ограничения лежат в одной компоненте
                    local_constraints.append((sorted(fs), t))

            profile = self._enumerate_component(cell_list, local_constraints)
            if profile is None:
                undecidable = True
            comp_profiles.append(profile)
            comp_cells.append(cell_list)

        # Достижимые суммарные числа мин по «решаемым» компонентам.
        # Для нерешённых (None) компонент берём диапазон [0, len] как «любой».
        decided_idx = [i for i, p in enumerate(comp_profiles) if p is not None]
        undecided_idx = [i for i, p in enumerate(comp_profiles) if p is None]

        # Диапазон мин в «непросчитанных» зонах = интерьер + нерешённые компоненты.
        free_min = 0
        free_max = interior_count
        for i in undecided_idx:
            free_max += len(comp_cells[i])

        # DP по достижимым суммам мин среди РЕШЁННЫХ компонент.
        # reachable[s] = True, если можно набрать ровно s мин.
        reachable = {0}
        per_comp_counts = []  # для каждой decided-компоненты — set достижимых k
        for i in decided_idx:
            ks = set(comp_profiles[i].keys())
            per_comp_counts.append((i, ks))
            new = set()
            for s in reachable:
                for k in ks:
                    new.add(s + k)
            reachable = new

        # Функция: достижима ли сумма s по ВСЕМ decided-компонентам, КРОМЕ idx_excl,
        # с учётом того, что у компоненты idx_excl зафиксировано k_excl мин.
        # Чтобы не пересчитывать тяжело, построим DP без одной компоненты по требованию.
        def reachable_without(exclude_i):
            r = {0}
            for i, ks in per_comp_counts:
                if i == exclude_i:
                    continue
                new = set()
                for s in r:
                    for k in ks:
                        new.add(s + k)
                r = new
            return r

        changed = False

        # ---- Выводы по граничным клеткам решённых компонент ----
        for idx, (i, ks) in enumerate(per_comp_counts):
            profile = comp_profiles[i]
            rest = reachable_without(i)  # суммы по прочим decided-компонентам
            for cell in comp_cells[i]:
                can_mine = False
                can_safe = False
                for k in ks:
                    info = profile[k]
                    cell_can_mine = cell in info["mine"]
                    cell_can_safe = cell in info["safe"]
                    if not (cell_can_mine or cell_can_safe):
                        continue
                    # нужно, чтобы остаток мин (remaining - k - s_rest) укладывался
                    # в свободные зоны [free_min, free_max]
                    ok = False
                    for s_rest in rest:
                        free = remaining - k - s_rest
                        if free_min <= free <= free_max:
                            ok = True
                            break
                    if not ok:
                        continue
                    if cell_can_mine:
                        can_mine = True
                    if cell_can_safe:
                        can_safe = True
                if can_mine and not can_safe:
                    if cell not in flagged:
                        flagged.add(cell)
                        changed = True
                elif can_safe and not can_mine:
                    cx, cy = cell
                    if self._flood_open(cx, cy):
                        changed = True
            if changed:
                # После изменения границы лучше пересобрать всё заново.
                return True

        # ---- Выводы по интерьеру (клетки вне всех ограничений) ----
        # Интерьерные клетки взаимозаменяемы: они ВСЕ безопасны тогда и только
        # тогда, когда в любой допустимой конфигурации в интерьере 0 мин.
        if interior_count > 0 and not undecided_idx:
            # число мин в интерьере = remaining - (сумма по компонентам)
            feasible_interior = set()
            for s in reachable:
                m_int = remaining - s
                if 0 <= m_int <= interior_count:
                    feasible_interior.add(m_int)
            if feasible_interior:
                interior_cells = unknown_all - border_cells
                if feasible_interior == {0}:
                    # интерьер гарантированно без мин — открываем всё
                    for ix, iy in list(interior_cells):
                        if self._flood_open(ix, iy):
                            changed = True
                elif feasible_interior == {interior_count}:
                    # интерьер целиком заминирован
                    for c in interior_cells:
                        if c not in flagged:
                            flagged.add(c)
                            changed = True

        return changed

    # ------------------------------------------------------------------ #
    # Перебор конфигураций одной компоненты
    # ------------------------------------------------------------------ #
    def _enumerate_component(self, cells, local_constraints):
        """Перебирает все допустимые расстановки мин в компоненте.

        Возвращает dict: k (число мин) -> {"mine": set(клеток, которые бывают
        миной при k), "safe": set(клеток, которые бывают безопасны при k)}.
        Возвращает None, если перебор слишком большой (компонента «неразрешима»)."""
        n = len(cells)
        index = {c: i for i, c in enumerate(cells)}

        # Ограничения в виде (битовая маска клеток, требуемое число мин).
        masks = []
        for fs_cells, t in local_constraints:
            m = 0
            for c in fs_cells:
                m |= (1 << index[c])
            masks.append((m, t))

        # Порядок клеток для раннего отсечения: по числу ограничений.
        # (простой перебор с проверкой ограничений по ходу)
        # Предвычислим для каждой клетки ограничения, которые ею «закрываются».
        # Используем рекурсивный бэктрекинг по битам, но итеративно через стек,
        # чтобы избежать лимита рекурсии.

        profile = {}
        solutions_found = 0

        # Для отсечения: к моменту, когда мы назначили клетку с индексом i,
        # все ограничения, чья старшая клетка равна i, уже полностью определены
        # и могут быть проверены немедленно.
        constr_complete_at = [[] for _ in range(n)]
        for m, t in masks:
            highest = m.bit_length() - 1
            constr_complete_at[highest].append((m, t))

        results = []

        # Рекурсия глубиной n (<= MAX_COMPONENT_CELLS) — безопасна по стеку.
        def backtrack(i, cur_mask, k):
            nonlocal solutions_found
            if solutions_found > MAX_COMPONENT_SOLUTIONS:
                return False
            if i == n:
                # все ограничения уже проверены по ходу
                results.append((cur_mask, k))
                solutions_found += 1
                return True
            # ветка: клетка i — безопасна (0)
            if not _branch(i, cur_mask, k, 0):
                return False
            # ветка: клетка i — мина (1)
            if not _branch(i, cur_mask, k, 1):
                return False
            return True

        def _branch(i, cur_mask, k, val):
            new_mask = cur_mask | (val << i)
            new_k = k + val
            # Ранняя проверка ограничений, завершающихся на позиции i.
            for m, t in constr_complete_at[i]:
                if bin(new_mask & m).count("1") != t:
                    return True  # ветка отсекается, но перебор продолжается
            return backtrack(i + 1, new_mask, new_k)

        ok = backtrack(0, 0, 0)
        if not ok or solutions_found > MAX_COMPONENT_SOLUTIONS:
            return None

        # Сворачиваем решения в профиль по k.
        for mask, k in results:
            info = profile.get(k)
            if info is None:
                info = {"mine": set(), "safe": set()}
                profile[k] = info
            for c, bit in index.items():
                if mask & (1 << bit):
                    info["mine"].add(c)
                else:
                    info["safe"].add(c)
        return profile if profile else None
