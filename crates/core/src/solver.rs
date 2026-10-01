//! Логический решатель «Сапёра» для проверки поля на решаемость без угадывания.
//!
//! Решатель ЗВУЧНЫЙ (sound): он никогда не объявляет клетку безопасной/миной,
//! если это не следует строго из доступной информации. Поэтому если
//! [`Solver::solve`] вернул `true`, поле гарантированно проходится чистой
//! логикой, без угадывания.
//!
//! Используемые техники (от дешёвых к дорогим):
//!   1. Тривиальная логика одной цифры (все мины / все безопасны).
//!   2. Вычитание пересекающихся множеств (subset logic).
//!   3. Глобальный счётчик оставшихся мин.
//!   4. Ограниченный перебор конфигураций по связным компонентам границы (CSP),
//!      объединённый с глобальным счётчиком — именно это устраняет финальные 50/50.

use std::collections::HashMap;

use crate::board::Board;

/// Максимальный размер связной компоненты границы (в клетках), для которой
/// мы готовы перебирать конфигурации. Компоненты больше этого порога
/// пропускаются (решатель просто ничего из них не выводит — это безопасно).
pub const MAX_COMPONENT_CELLS: usize = 22;
/// Защита от комбинаторного взрыва: предел числа конфигураций на компоненту.
pub const MAX_COMPONENT_SOLUTIONS: usize = 40_000;

const UNKNOWN: u8 = 0;
const OPEN: u8 = 1;
const FLAG: u8 = 2;

/// Уравнение «среди клеток `cells` ровно `mines` мин». `cells` отсортированы.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct Constraint {
    cells: Vec<u32>,
    mines: u8,
}

/// Профиль компоненты: для каждого числа мин `k` — маски клеток, которые
/// бывают миной / бывают безопасны хотя бы в одной конфигурации с `k` минами.
type Profile = Vec<Option<(u64, u64)>>;

pub struct Solver<'a> {
    board: &'a Board,
    state: Vec<u8>,
    opened: usize,
    flagged: usize,
    stack: Vec<u32>,
    contradictions: usize,
}

impl<'a> Solver<'a> {
    pub fn new(board: &'a Board) -> Self {
        Solver {
            board,
            state: vec![UNKNOWN; board.len()],
            opened: 0,
            flagged: 0,
            stack: Vec::new(),
            contradictions: 0,
        }
    }

    // ------------------------------------------------------------------ //
    // Публичный API
    // ------------------------------------------------------------------ //

    /// Проходит поле с первого клика в (x, y). `true` — поле решается целиком.
    pub fn solve(&mut self, start_x: usize, start_y: usize) -> bool {
        self.state.fill(UNKNOWN);
        self.opened = 0;
        self.flagged = 0;
        self.contradictions = 0;

        self.flood_open(self.board.idx(start_x, start_y));
        self.run();
        self.is_complete()
    }

    /// Применяет правила до неподвижной точки.
    fn run(&mut self) {
        loop {
            // 1. Дешёвая логика одной цифры.
            if self.apply_trivial_logic() {
                continue;
            }
            // 2. Логика подмножеств.
            if self.apply_subset_logic() {
                continue;
            }
            // 3. Глобальный счётчик + перебор по компонентам (дорого).
            if self.apply_global_and_csp() {
                continue;
            }
            break;
        }
    }

    pub fn is_complete(&self) -> bool {
        self.opened == self.board.len() - self.board.num_mines()
    }
    pub fn is_opened(&self, i: usize) -> bool {
        self.state[i] == OPEN
    }
    pub fn is_flagged(&self, i: usize) -> bool {
        self.state[i] == FLAG
    }
    pub fn opened_count(&self) -> usize {
        self.opened
    }

    /// Сколько раз решатель пытался «открыть» мину. Для звучного решателя
    /// всегда 0 — ненулевое значение означает ошибку в выводах (для тестов).
    pub fn contradictions(&self) -> usize {
        self.contradictions
    }

    // ------------------------------------------------------------------ //
    // Открытие и отметка клеток
    // ------------------------------------------------------------------ //

    /// Открывает клетку и каскадно раскрывает нули (итеративно, без рекурсии).
    /// Возвращает `true`, если открыта хотя бы одна новая клетка.
    fn flood_open(&mut self, i: usize) -> bool {
        if self.state[i] != UNKNOWN {
            return false;
        }
        if self.board.is_mine(i) {
            // На корректных выводах сюда попадать нельзя.
            self.contradictions += 1;
            return false;
        }
        self.stack.clear();
        self.stack.push(i as u32);
        let mut any = false;
        while let Some(c) = self.stack.pop() {
            let c = c as usize;
            if self.state[c] != UNKNOWN || self.board.is_mine(c) {
                continue;
            }
            self.state[c] = OPEN;
            self.opened += 1;
            any = true;
            if self.board.number(c) == 0 {
                for &n in self.board.neighbors(c) {
                    if self.state[n as usize] == UNKNOWN {
                        self.stack.push(n);
                    }
                }
            }
        }
        any
    }

    fn flag(&mut self, i: usize) -> bool {
        if self.state[i] != UNKNOWN {
            return false;
        }
        self.state[i] = FLAG;
        self.flagged += 1;
        true
    }

    /// Закрытые неотмеченные соседи открытой клетки и число мин среди них.
    fn local_constraint(&self, i: usize) -> Option<Constraint> {
        let number = self.board.number(i);
        if self.state[i] != OPEN || number == 0 {
            return None;
        }
        let mut cells = Vec::new();
        let mut flags = 0u8;
        for &n in self.board.neighbors(i) {
            match self.state[n as usize] {
                FLAG => flags += 1,
                UNKNOWN => cells.push(n),
                _ => {}
            }
        }
        if cells.is_empty() {
            return None;
        }
        // Соседи уже идут по возрастанию индекса — `cells` отсортированы.
        Some(Constraint {
            cells,
            mines: number - flags,
        })
    }

    // ------------------------------------------------------------------ //
    // 1. Тривиальная логика
    // ------------------------------------------------------------------ //
    fn apply_trivial_logic(&mut self) -> bool {
        let mut changed = false;
        for i in 0..self.board.len() {
            let Some(c) = self.local_constraint(i) else {
                continue;
            };
            if c.mines as usize == c.cells.len() {
                // Все оставшиеся неизвестные — мины.
                for &u in &c.cells {
                    changed |= self.flag(u as usize);
                }
            } else if c.mines == 0 {
                // Все оставшиеся неизвестные — безопасны.
                for &u in &c.cells {
                    changed |= self.flood_open(u as usize);
                }
            }
        }
        changed
    }

    // ------------------------------------------------------------------ //
    // 2. Логика подмножеств
    // ------------------------------------------------------------------ //
    fn build_constraints(&self) -> Vec<Constraint> {
        let mut cs: Vec<Constraint> = (0..self.board.len())
            .filter_map(|i| self.local_constraint(i))
            .collect();
        cs.sort_unstable();
        cs.dedup();
        cs
    }

    fn apply_subset_logic(&mut self) -> bool {
        let cs = self.build_constraints();

        // Индекс «клетка -> ограничения с ней»: сравниваем только пересекающиеся пары.
        let mut by_cell: HashMap<u32, Vec<usize>> = HashMap::new();
        for (ci, c) in cs.iter().enumerate() {
            for &cell in &c.cells {
                by_cell.entry(cell).or_default().push(ci);
            }
        }

        let mut changed = false;
        for (ai, a) in cs.iter().enumerate() {
            // Любое надмножество A содержит её первую клетку.
            for &bi in &by_cell[&a.cells[0]] {
                let b = &cs[bi];
                if bi == ai || a.cells.len() >= b.cells.len() || !is_subset(&a.cells, &b.cells) {
                    continue;
                }
                let diff: Vec<u32> = b
                    .cells
                    .iter()
                    .copied()
                    .filter(|c| a.cells.binary_search(c).is_err())
                    .collect();
                let dt = b.mines as i32 - a.mines as i32;
                if dt == diff.len() as i32 {
                    for &c in &diff {
                        changed |= self.flag(c as usize);
                    }
                } else if dt == 0 {
                    for &c in &diff {
                        changed |= self.flood_open(c as usize);
                    }
                }
            }
        }
        changed
    }

    // ------------------------------------------------------------------ //
    // 3+4. Глобальный счётчик мин и перебор по компонентам (CSP)
    // ------------------------------------------------------------------ //
    fn apply_global_and_csp(&mut self) -> bool {
        let n = self.board.len();
        let unknown_all: Vec<usize> = (0..n).filter(|&i| self.state[i] == UNKNOWN).collect();
        if unknown_all.is_empty() {
            return false;
        }
        let remaining = self.board.num_mines() as i64 - self.flagged as i64;

        // Тривиальные глобальные выводы.
        if remaining == 0 {
            // Мин не осталось — все закрытые клетки безопасны.
            let mut changed = false;
            for &u in &unknown_all {
                changed |= self.flood_open(u);
            }
            return changed;
        }
        if remaining == unknown_all.len() as i64 {
            // Все закрытые клетки — мины.
            for &u in &unknown_all {
                self.flag(u);
            }
            return true;
        }
        if remaining < 0 || remaining > unknown_all.len() as i64 {
            return false; // противоречие — пусть генератор перегенерирует
        }
        let remaining = remaining as usize;

        let cs = self.build_constraints();
        if cs.is_empty() {
            return false;
        }

        // --- объединение граничных клеток в связные компоненты ---
        let mut parent: Vec<u32> = (0..n as u32).collect();
        let mut is_border = vec![false; n];
        for c in &cs {
            for &cell in &c.cells {
                is_border[cell as usize] = true;
                union(&mut parent, c.cells[0], cell);
            }
        }
        let mut comp_of_root: HashMap<u32, usize> = HashMap::new();
        let mut comp_cells: Vec<Vec<u32>> = Vec::new();
        for &u in &unknown_all {
            if !is_border[u] {
                continue;
            }
            let root = find(&mut parent, u as u32);
            let id = *comp_of_root.entry(root).or_insert_with(|| {
                comp_cells.push(Vec::new());
                comp_cells.len() - 1
            });
            comp_cells[id].push(u as u32);
        }
        let border_count: usize = comp_cells.iter().map(Vec::len).sum();
        let interior_count = unknown_all.len() - border_count;

        let mut comp_constraints: Vec<Vec<&Constraint>> = vec![Vec::new(); comp_cells.len()];
        for c in &cs {
            let root = find(&mut parent, c.cells[0]);
            comp_constraints[comp_of_root[&root]].push(c);
        }

        // Перебор конфигураций по каждой компоненте.
        let profiles: Vec<Option<Profile>> = comp_cells
            .iter()
            .zip(&comp_constraints)
            .map(|(cells, cons)| {
                if cells.len() > MAX_COMPONENT_CELLS {
                    None
                } else {
                    enumerate_component(cells, cons)
                }
            })
            .collect();

        let decided: Vec<usize> = (0..profiles.len())
            .filter(|&i| profiles[i].is_some())
            .collect();
        let undecided_cells: usize = (0..profiles.len())
            .filter(|&i| profiles[i].is_none())
            .map(|i| comp_cells[i].len())
            .sum();

        // Мины в «непросчитанных» зонах: интерьер + нерешённые компоненты.
        let free_min = 0;
        let free_max = interior_count + undecided_cells;

        // Достижимые суммы мин по решённым компонентам (кроме `exclude`),
        // ограниченные сверху `remaining` — большие суммы всё равно недопустимы.
        let reachable_without = |exclude: Option<usize>| -> Vec<bool> {
            let mut r = vec![false; remaining + 1];
            r[0] = true;
            for &i in &decided {
                if Some(i) == exclude {
                    continue;
                }
                let p = profiles[i].as_ref().unwrap();
                let mut next = vec![false; remaining + 1];
                for (s, _) in r.iter().enumerate().filter(|(_, ok)| **ok) {
                    for k in (0..p.len()).filter(|&k| p[k].is_some()) {
                        if s + k <= remaining {
                            next[s + k] = true;
                        }
                    }
                }
                r = next;
            }
            r
        };

        let mut changed = false;

        // ---- Выводы по граничным клеткам решённых компонент ----
        for &i in &decided {
            let profile = profiles[i].as_ref().unwrap();
            let rest = reachable_without(Some(i));
            // k допустимо, если остаток мин укладывается в свободные зоны.
            let mut mine_any = 0u64;
            let mut safe_any = 0u64;
            for (k, info) in profile.iter().enumerate() {
                let Some((mine_mask, safe_mask)) = info else {
                    continue;
                };
                let feasible = rest.iter().enumerate().any(|(s, &ok)| {
                    ok && remaining >= k + s && (free_min..=free_max).contains(&(remaining - k - s))
                });
                if feasible {
                    mine_any |= mine_mask;
                    safe_any |= safe_mask;
                }
            }
            for (b, &cell) in comp_cells[i].iter().enumerate() {
                let can_mine = mine_any >> b & 1 == 1;
                let can_safe = safe_any >> b & 1 == 1;
                if can_mine && !can_safe {
                    changed |= self.flag(cell as usize);
                } else if can_safe && !can_mine {
                    changed |= self.flood_open(cell as usize);
                }
            }
            if changed {
                // После изменения границы лучше пересобрать всё заново.
                return true;
            }
        }

        // ---- Выводы по интерьеру (клетки вне всех ограничений) ----
        // Интерьерные клетки взаимозаменяемы: они ВСЕ безопасны тогда и только
        // тогда, когда в любой допустимой конфигурации в интерьере 0 мин.
        if interior_count > 0 && undecided_cells == 0 {
            let reachable = reachable_without(None);
            let feasible: Vec<usize> = reachable
                .iter()
                .enumerate()
                .filter(|(s, ok)| **ok && remaining - s <= interior_count)
                .map(|(s, _)| remaining - s)
                .collect();
            let interior = unknown_all.iter().copied().filter(|&u| !is_border[u]);
            if feasible == [0] {
                // Интерьер гарантированно без мин — открываем всё.
                for u in interior.collect::<Vec<_>>() {
                    changed |= self.flood_open(u);
                }
            } else if feasible == [interior_count] {
                // Интерьер целиком заминирован.
                for u in interior.collect::<Vec<_>>() {
                    changed |= self.flag(u);
                }
            }
        }

        changed
    }
}

fn is_subset(a: &[u32], b: &[u32]) -> bool {
    a.iter().all(|x| b.binary_search(x).is_ok())
}

fn find(parent: &mut [u32], mut a: u32) -> u32 {
    while parent[a as usize] != a {
        parent[a as usize] = parent[parent[a as usize] as usize];
        a = parent[a as usize];
    }
    a
}

fn union(parent: &mut [u32], a: u32, b: u32) {
    let (ra, rb) = (find(parent, a), find(parent, b));
    if ra != rb {
        parent[ra as usize] = rb;
    }
}

// ---------------------------------------------------------------------- //
// Перебор конфигураций одной компоненты
// ---------------------------------------------------------------------- //

/// Перебирает все допустимые расстановки мин в компоненте.
///
/// Возвращает профиль по числу мин `k` (маски по позициям в `cells`)
/// или `None`, если конфигураций слишком много или нет ни одной.
fn enumerate_component(cells: &[u32], constraints: &[&Constraint]) -> Option<Profile> {
    let n = cells.len();
    let local: HashMap<u32, usize> = cells.iter().enumerate().map(|(i, &c)| (c, i)).collect();

    let mut cell_cons: Vec<Vec<usize>> = vec![Vec::new(); n];
    let mut cons_cells: Vec<Vec<usize>> = Vec::with_capacity(constraints.len());
    for (ci, c) in constraints.iter().enumerate() {
        let lc: Vec<usize> = c.cells.iter().map(|x| local[x]).collect();
        for &l in &lc {
            cell_cons[l].push(ci);
        }
        cons_cells.push(lc);
    }

    // Порядок обхода — BFS по общим ограничениям: соседние по смыслу клетки
    // назначаются подряд, ограничения быстро «закрываются» и отсекают ветки.
    // Множество найденных конфигураций от порядка не зависит.
    let mut order = Vec::with_capacity(n);
    let mut seen = vec![false; n];
    for start in 0..n {
        if seen[start] {
            continue;
        }
        seen[start] = true;
        let mut head = order.len();
        order.push(start);
        while head < order.len() {
            let c = order[head];
            head += 1;
            for &ci in &cell_cons[c] {
                for &o in &cons_cells[ci] {
                    if !seen[o] {
                        seen[o] = true;
                        order.push(o);
                    }
                }
            }
        }
    }

    let mut e = Enumerator {
        order,
        cell_cons,
        target: constraints.iter().map(|c| c.mines).collect(),
        assigned: vec![0; constraints.len()],
        unassigned: cons_cells.iter().map(|c| c.len() as u8).collect(),
        mask: 0,
        k: 0,
        solutions: 0,
        aborted: false,
        profile: vec![None; n + 1],
    };
    e.rec(0);

    if e.aborted || e.solutions == 0 {
        return None;
    }
    Some(e.profile)
}

struct Enumerator {
    order: Vec<usize>,
    cell_cons: Vec<Vec<usize>>,
    target: Vec<u8>,
    assigned: Vec<u8>,
    unassigned: Vec<u8>,
    mask: u64,
    k: usize,
    solutions: usize,
    aborted: bool,
    profile: Profile,
}

impl Enumerator {
    // Глубина рекурсии ≤ MAX_COMPONENT_CELLS — безопасно по стеку.
    fn rec(&mut self, pos: usize) {
        if self.aborted {
            return;
        }
        if pos == self.order.len() {
            self.solutions += 1;
            if self.solutions > MAX_COMPONENT_SOLUTIONS {
                self.aborted = true;
                return;
            }
            let full = (1u64 << self.order.len()) - 1;
            let entry = self.profile[self.k].get_or_insert((0, 0));
            entry.0 |= self.mask;
            entry.1 |= !self.mask & full;
            return;
        }
        let cell = self.order[pos];
        for v in [0u8, 1] {
            let mut ok = true;
            for j in 0..self.cell_cons[cell].len() {
                let ci = self.cell_cons[cell][j];
                self.unassigned[ci] -= 1;
                self.assigned[ci] += v;
                if self.assigned[ci] > self.target[ci]
                    || self.assigned[ci] + self.unassigned[ci] < self.target[ci]
                {
                    ok = false;
                }
            }
            if ok {
                self.mask |= (v as u64) << cell;
                self.k += v as usize;
                self.rec(pos + 1);
                self.mask &= !(1u64 << cell);
                self.k -= v as usize;
            }
            for j in 0..self.cell_cons[cell].len() {
                let ci = self.cell_cons[cell][j];
                self.unassigned[ci] += 1;
                self.assigned[ci] -= v;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn board(rows: &[&str]) -> Board {
        let w = rows[0].len();
        let mines: Vec<bool> = rows
            .iter()
            .flat_map(|r| r.chars().map(|c| c == '*'))
            .collect();
        Board::from_mines(w, rows.len(), &mines)
    }

    #[test]
    fn trivial_board_is_solvable() {
        let b = board(&["....", "....", "...*"]);
        let mut s = Solver::new(&b);
        assert!(s.solve(0, 0));
        assert_eq!(s.contradictions(), 0);
    }

    #[test]
    fn final_fifty_fifty_is_not_solvable() {
        // После каскада остаются две клетки справа с одной миной на двоих —
        // ни цифры, ни глобальный счётчик их не различают.
        let b = board(&["...*", "...."]);
        let mut s = Solver::new(&b);
        assert!(!s.solve(0, 0));
        assert_eq!(s.contradictions(), 0);
    }
}
