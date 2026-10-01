//! No-guess генератор поля «Сапёра».
//!
//! Стратегия «создать и проверить» с локальным поиском (мутациями):
//!   1. Случайно расставляем мины (3×3 вокруг первого клика — всегда пусто).
//!   2. Решатель симулирует прохождение чистой логикой.
//!   3. Если застряли — переносим мину у «застрявшей» границы в глубину
//!      (или наоборот), пересчитываем только затронутые цифры и пробуем снова.
//!   4. Если мутации не помогают — генерируем поле заново.
//!
//! Если решатель сказал «решаемо», поле гарантированно проходится без угадывания.

use std::fmt;

use crate::board::Board;
use crate::rng::Rng;
use crate::solver::Solver;

pub const MAX_ATTEMPTS: usize = 300;
pub const MAX_MUTATIONS: usize = 80;

#[derive(Debug)]
pub struct Generated {
    pub board: Board,
    /// `false` — гарантию no-guess за лимит попыток получить не удалось
    /// (бывает лишь при экстремальной плотности мин).
    pub noguess: bool,
    pub attempts: usize,
    pub mutations: usize,
}

#[derive(Debug, PartialEq, Eq)]
pub enum GenError {
    StartOutOfBounds,
    TooManyMines { max: usize },
}

impl fmt::Display for GenError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GenError::StartOutOfBounds => write!(f, "first click is outside the board"),
            GenError::TooManyMines { max } => write!(f, "too many mines: at most {max} fit"),
        }
    }
}

impl std::error::Error for GenError {}

pub fn generate(
    width: usize,
    height: usize,
    num_mines: usize,
    start_x: usize,
    start_y: usize,
    rng: &mut Rng,
) -> Result<Generated, GenError> {
    if start_x >= width || start_y >= height {
        return Err(GenError::StartOutOfBounds);
    }
    let template = Board::new(width, height, num_mines);
    let safe_zone: Vec<usize> = template.zone3x3(start_x, start_y).collect();
    let max = template.len() - safe_zone.len();
    if num_mines > max {
        return Err(GenError::TooManyMines { max });
    }
    let mut in_safe_zone = vec![false; template.len()];
    for &i in &safe_zone {
        in_safe_zone[i] = true;
    }

    let mut total_mutations = 0;
    let mut board = template.clone();
    for attempt in 1..=MAX_ATTEMPTS {
        board = template.clone();
        place_mines(&mut board, &in_safe_zone, rng);

        for _ in 0..MAX_MUTATIONS {
            let mut solver = Solver::new(&board);
            if solver.solve(start_x, start_y) {
                return Ok(Generated {
                    board,
                    noguess: true,
                    attempts: attempt,
                    mutations: total_mutations,
                });
            }
            // Поле застряло — «распутываем» тупик мутацией возле
            // фактической границы, где решатель остановился.
            let opened: Vec<bool> = (0..board.len()).map(|i| solver.is_opened(i)).collect();
            if !mutate(&mut board, &opened, &in_safe_zone, rng) {
                break; // менять нечего — генерируем с нуля
            }
            total_mutations += 1;
        }
    }

    // Сюда попадаем лишь при экстремальной плотности мин: возвращаем поле,
    // но честно помечаем, что гарантия no-guess не достигнута.
    Ok(Generated {
        board,
        noguess: false,
        attempts: MAX_ATTEMPTS,
        mutations: total_mutations,
    })
}

fn place_mines(board: &mut Board, in_safe_zone: &[bool], rng: &mut Rng) {
    let mut available: Vec<usize> = (0..board.len()).filter(|&i| !in_safe_zone[i]).collect();
    let k = board.num_mines();
    rng.partial_shuffle(&mut available, k);
    for &i in &available[..k] {
        board.set_mine(i, true);
    }
    board.calculate_numbers();
}

/// Меняет местами мину и пустую клетку, чтобы разрушить тупик.
///
/// Приоритет — клетки на границе открытой области (где решатель встал),
/// обмениваемые с клетками в ещё не исследованной глубине.
fn mutate(board: &mut Board, opened: &[bool], in_safe_zone: &[bool], rng: &mut Rng) -> bool {
    let mut frontier_mines = Vec::new();
    let mut frontier_safes = Vec::new();
    let mut unreached_mines = Vec::new();
    let mut unreached_safes = Vec::new();

    for i in 0..board.len() {
        if opened[i] {
            continue;
        }
        let is_frontier = board.neighbors(i).iter().any(|&n| opened[n as usize]);
        let bucket = match (is_frontier, board.is_mine(i)) {
            (true, true) => &mut frontier_mines,
            (true, false) => &mut frontier_safes,
            // Не переносим мину в зону первого клика (и не забираем оттуда).
            (false, _) if in_safe_zone[i] => continue,
            (false, true) => &mut unreached_mines,
            (false, false) => &mut unreached_safes,
        };
        bucket.push(i);
    }

    let mut options: Vec<(&[usize], &[usize])> = Vec::with_capacity(2);
    if !frontier_mines.is_empty() && !unreached_safes.is_empty() {
        options.push((&frontier_mines, &unreached_safes));
    }
    if !frontier_safes.is_empty() && !unreached_mines.is_empty() {
        options.push((&frontier_safes, &unreached_mines));
    }
    if options.is_empty() {
        return false;
    }

    let (g1, g2) = *rng.choose(&options);
    let a = *rng.choose(g1);
    let b = *rng.choose(g2);

    let (ma, mb) = (board.is_mine(a), board.is_mine(b));
    board.set_mine(a, mb);
    board.set_mine(b, ma);

    // Инкрементально пересчитываем только затронутые клетки.
    board.recalc_around(a);
    board.recalc_around(b);
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_bad_input() {
        let mut rng = Rng::new(0);
        assert_eq!(
            generate(5, 5, 3, 5, 0, &mut rng).unwrap_err(),
            GenError::StartOutOfBounds
        );
        assert_eq!(
            generate(5, 5, 17, 2, 2, &mut rng).unwrap_err(),
            GenError::TooManyMines { max: 16 }
        );
    }

    #[test]
    fn same_seed_same_board() {
        let a = generate(16, 16, 40, 3, 4, &mut Rng::new(7)).unwrap();
        let b = generate(16, 16, 40, 3, 4, &mut Rng::new(7)).unwrap();
        assert_eq!(a.board.mines(), b.board.mines());
    }
}
