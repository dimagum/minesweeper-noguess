//! Состояние партии: открытие клеток, флаги, аккорд, победа/поражение.
//!
//! Время здесь не учитывается — таймер живёт в UI.

use crate::board::Board;
use crate::generator::{self, GenError};
use crate::rng::Rng;
use crate::solver::Solver;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GameState {
    NotStarted,
    Playing,
    Won,
    Lost,
}

/// Что видит игрок в клетке.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CellView {
    Hidden,
    Flagged,
    Open(u8),
    /// Мина, показанная после поражения; `exploded` — та, на которую нажали.
    Mine {
        exploded: bool,
    },
    /// Флаг, поставленный не на мину (показывается после поражения).
    WrongFlag,
}

/// Подсказка: клетка, о которой можно сделать вывод чистой логикой.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Hint {
    pub x: usize,
    pub y: usize,
    /// `true` — в клетке мина (ставим флаг), `false` — клетку можно открыть.
    pub mine: bool,
}

pub struct Game {
    width: usize,
    height: usize,
    num_mines: usize,
    board: Board,
    open: Vec<bool>,
    flagged: Vec<bool>,
    state: GameState,
    flags_placed: usize,
    opened_cells: usize,
    exploded: Option<usize>,
    noguess: bool,
    rng: Rng,
}

impl Game {
    /// Новая партия. Мины расставляются при первом открытии клетки.
    pub fn new(width: usize, height: usize, num_mines: usize, seed: u64) -> Self {
        Game {
            width,
            height,
            num_mines,
            // До первого клика — пустое поле, чтобы UI мог нарисовать сетку.
            board: Board::new(width, height, 0),
            open: vec![false; width * height],
            flagged: vec![false; width * height],
            state: GameState::NotStarted,
            flags_placed: 0,
            opened_cells: 0,
            exploded: None,
            noguess: true,
            rng: Rng::new(seed),
        }
    }

    pub fn width(&self) -> usize {
        self.width
    }
    pub fn height(&self) -> usize {
        self.height
    }
    pub fn num_mines(&self) -> usize {
        self.num_mines
    }
    pub fn state(&self) -> GameState {
        self.state
    }
    pub fn flags_placed(&self) -> usize {
        self.flags_placed
    }
    /// Мины минус флаги — счётчик для HUD (может уйти в минус).
    pub fn mines_left(&self) -> i64 {
        self.num_mines as i64 - self.flags_placed as i64
    }
    /// Получена ли гарантия no-guess для текущего поля.
    pub fn is_noguess(&self) -> bool {
        self.noguess
    }
    pub fn board(&self) -> &Board {
        &self.board
    }

    /// Следующий логический ход из того, что видит игрок: сначала безопасная
    /// клетка, иначе мина без флага. Выводы делаются самыми дешёвыми
    /// правилами, какие возможны, — подсказка «простая», насколько можно.
    /// `None` — партия не идёт или вывести нечего.
    pub fn hint(&self) -> Option<Hint> {
        if self.state != GameState::Playing {
            return None;
        }
        let mut solver = Solver::from_opened(&self.board, &self.open);
        while solver.step() {
            let mut mine = None;
            for i in 0..self.open.len() {
                if solver.is_opened(i) && !self.open[i] {
                    return Some(self.hint_at(i, false));
                }
                if mine.is_none() && solver.is_flagged(i) && !self.flagged[i] {
                    mine = Some(i);
                }
            }
            if let Some(i) = mine {
                return Some(self.hint_at(i, true));
            }
        }
        None
    }

    fn hint_at(&self, i: usize, mine: bool) -> Hint {
        let (x, y) = self.board.xy(i);
        Hint { x, y, mine }
    }

    pub fn cell(&self, x: usize, y: usize) -> CellView {
        let i = y * self.width + x;
        let lost = self.state == GameState::Lost;
        if self.open[i] {
            if self.board.is_mine(i) {
                CellView::Mine {
                    exploded: self.exploded == Some(i),
                }
            } else {
                CellView::Open(self.board.number(i))
            }
        } else if self.flagged[i] {
            if lost && !self.board.is_mine(i) {
                CellView::WrongFlag
            } else {
                CellView::Flagged
            }
        } else if lost && self.board.is_mine(i) {
            CellView::Mine { exploded: false }
        } else {
            CellView::Hidden
        }
    }

    fn in_bounds(&self, x: usize, y: usize) -> bool {
        x < self.width && y < self.height
    }

    fn is_over(&self) -> bool {
        matches!(self.state, GameState::Won | GameState::Lost)
    }

    /// Начинает партию с заранее сгенерированным полем (например, из Web
    /// Worker'а) и открывает первую клетку.
    pub fn start_with_board(&mut self, board: Board, noguess: bool, x: usize, y: usize) {
        assert_eq!(self.state, GameState::NotStarted, "game already started");
        assert_eq!((board.width(), board.height()), (self.width, self.height));
        self.board = board;
        self.noguess = noguess;
        self.state = GameState::Playing;
        self.open_cell(x, y);
    }

    /// Левый клик: открыть клетку. Возвращает `true`, если что-то изменилось.
    pub fn open(&mut self, x: usize, y: usize) -> Result<bool, GenError> {
        if self.is_over() || !self.in_bounds(x, y) {
            return Ok(false);
        }
        let i = y * self.width + x;
        // Клетка с флагом или уже открытая одиночным кликом не открывается.
        if self.open[i] || self.flagged[i] {
            return Ok(false);
        }
        if self.state == GameState::NotStarted {
            let g =
                generator::generate(self.width, self.height, self.num_mines, x, y, &mut self.rng)?;
            self.start_with_board(g.board, g.noguess, x, y);
            return Ok(true);
        }
        self.open_cell(x, y);
        Ok(true)
    }

    /// Правый клик: поставить/снять флаг.
    pub fn toggle_flag(&mut self, x: usize, y: usize) -> bool {
        if self.is_over() || !self.in_bounds(x, y) {
            return false;
        }
        let i = y * self.width + x;
        if self.open[i] {
            return false;
        }
        self.flagged[i] = !self.flagged[i];
        if self.flagged[i] {
            self.flags_placed += 1;
        } else {
            self.flags_placed -= 1;
        }
        true
    }

    /// Аккорд (средняя кнопка или ЛКМ+ПКМ) по открытой цифре: если вокруг
    /// стоит ровно столько флагов, сколько показывает цифра, открывает
    /// остальных соседей.
    pub fn chord(&mut self, x: usize, y: usize) -> bool {
        if self.state != GameState::Playing || !self.in_bounds(x, y) {
            return false;
        }
        let i = y * self.width + x;
        let number = self.board.number(i);
        if !self.open[i] || number == 0 {
            return false;
        }
        let neighbors: Vec<usize> = self
            .board
            .neighbors(i)
            .iter()
            .map(|&n| n as usize)
            .collect();
        let flags = neighbors.iter().filter(|&&n| self.flagged[n]).count();
        if flags != number as usize {
            return false;
        }
        let mut changed = false;
        for n in neighbors {
            if !self.open[n] && !self.flagged[n] {
                let (nx, ny) = self.board.xy(n);
                self.open_cell(nx, ny);
                changed = true;
            }
        }
        changed
    }

    /// Открытие с каскадным раскрытием нулей (через явный стек: на больших
    /// полях рекурсия могла бы переполнить стек).
    fn open_cell(&mut self, x: usize, y: usize) {
        let mut stack = vec![self.board.idx(x, y)];
        while let Some(i) = stack.pop() {
            if self.open[i] || self.flagged[i] || self.is_over() {
                continue;
            }
            self.open[i] = true;
            self.opened_cells += 1;

            // Мина может оказаться только стартовой клеткой каскада:
            // соседи нуля минами не бывают.
            if self.board.is_mine(i) {
                self.state = GameState::Lost;
                self.exploded = Some(i);
                return;
            }
            if self.board.number(i) == 0 {
                stack.extend(
                    self.board
                        .neighbors(i)
                        .iter()
                        .map(|&n| n as usize)
                        .filter(|&n| !self.open[n]),
                );
            }
        }
        self.check_win();
    }

    fn check_win(&mut self) {
        if self.state != GameState::Playing {
            return;
        }
        if self.opened_cells == self.width * self.height - self.num_mines {
            self.state = GameState::Won;
            // Автоматически ставим флаги на все оставшиеся закрытые мины.
            for i in 0..self.open.len() {
                if !self.open[i] && !self.flagged[i] {
                    self.flagged[i] = true;
                    self.flags_placed += 1;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn game_with(rows: &[&str]) -> Game {
        let w = rows[0].len();
        let mines: Vec<bool> = rows
            .iter()
            .flat_map(|r| r.chars().map(|c| c == '*'))
            .collect();
        let board = Board::from_mines(w, rows.len(), &mines);
        let mut g = Game::new(w, rows.len(), board.num_mines(), 0);
        g.start_with_board(board, true, 0, 0);
        g
    }

    #[test]
    fn first_click_generates_safe_cascade() {
        let mut g = Game::new(16, 16, 40, 123);
        assert!(g.open(5, 5).unwrap());
        assert_eq!(g.state(), GameState::Playing);
        assert_eq!(g.cell(5, 5), CellView::Open(0));
        assert!(g.is_noguess());
    }

    #[test]
    fn win_auto_flags_mines() {
        let g = game_with(&["...", "...", "..*"]);
        // Каскад от (0,0) открывает всё, кроме мины.
        assert_eq!(g.state(), GameState::Won);
        assert_eq!(g.cell(2, 2), CellView::Flagged);
        assert_eq!(g.mines_left(), 0);
    }

    #[test]
    fn chord_opens_and_can_lose() {
        // ..*.   Каскад от (0,0) открывает два левых столбца.
        // ....
        let mut g = game_with(&["..*.", "...."]);
        assert_eq!(g.state(), GameState::Playing);
        assert_eq!(g.cell(1, 1), CellView::Open(1));
        // Без флага аккорд ничего не делает.
        assert!(!g.chord(1, 1));
        // Неверный флаг на (2,1) + аккорд по (1,1) => открывается мина (2,0).
        assert!(g.toggle_flag(2, 1));
        assert!(g.chord(1, 1));
        assert_eq!(g.state(), GameState::Lost);
        assert_eq!(g.cell(2, 0), CellView::Mine { exploded: true });
        assert_eq!(g.cell(2, 1), CellView::WrongFlag);
    }

    #[test]
    fn hints_play_the_whole_game() {
        // Играем только по подсказкам: на no-guess поле это всегда победа.
        for seed in 0..20 {
            let mut g = Game::new(16, 16, 40, seed);
            g.open(8, 8).unwrap();
            while g.state() == GameState::Playing {
                let h = g.hint().expect("no-guess board must always have a hint");
                if h.mine {
                    assert!(g.board().is_mine(g.board().idx(h.x, h.y)));
                    g.toggle_flag(h.x, h.y);
                } else {
                    g.open(h.x, h.y).unwrap();
                }
            }
            assert_eq!(g.state(), GameState::Won);
        }
    }

    #[test]
    fn flag_blocks_open() {
        let mut g = Game::new(9, 9, 10, 1);
        g.open(0, 0).unwrap();
        let (x, y) = (0..81)
            .map(|i| (i % 9, i / 9))
            .find(|&(x, y)| g.cell(x, y) == CellView::Hidden)
            .unwrap();
        assert!(g.toggle_flag(x, y));
        assert!(!g.open(x, y).unwrap());
        assert_eq!(g.cell(x, y), CellView::Flagged);
    }
}
