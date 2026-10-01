//! Сверка Rust-решателя с исходной Python-версией и проверки генератора.
//!
//! Фикстура `fixtures/parity.txt` создаётся скриптом `make_parity_fixture.py`
//! на Python-решателе (legacy-python/). Каждая строка: поле, первый клик и
//! вердикт «решаемо / нет». Rust-порт обязан выдавать тот же вердикт.

use noguess_core::{Board, Rng, Solver, generate};

struct Case {
    kind: String,
    w: usize,
    h: usize,
    sx: usize,
    sy: usize,
    solvable: bool,
    mines: Vec<bool>,
}

fn load_cases() -> Vec<Case> {
    include_str!("fixtures/parity.txt")
        .lines()
        .map(|line| {
            let f: Vec<&str> = line.split_whitespace().collect();
            Case {
                kind: f[0].to_string(),
                w: f[1].parse().unwrap(),
                h: f[2].parse().unwrap(),
                sx: f[3].parse().unwrap(),
                sy: f[4].parse().unwrap(),
                solvable: f[5] == "1",
                mines: f[6].bytes().map(|b| b == b'1').collect(),
            }
        })
        .collect()
}

#[test]
fn solver_matches_python_verdicts() {
    let cases = load_cases();
    assert!(cases.len() > 500);
    let mut mismatches = Vec::new();
    for (n, c) in cases.iter().enumerate() {
        let board = Board::from_mines(c.w, c.h, &c.mines);
        let mut solver = Solver::new(&board);
        let got = solver.solve(c.sx, c.sy);
        assert_eq!(
            solver.contradictions(),
            0,
            "case #{n}: solver tried to open a mine"
        );
        if got != c.solvable {
            mismatches.push(format!(
                "#{n} {} {}x{} python={} rust={got}",
                c.kind, c.w, c.h, c.solvable
            ));
        }
    }
    assert!(
        mismatches.is_empty(),
        "{} mismatches:\n{}",
        mismatches.len(),
        mismatches.join("\n")
    );
}

/// Решатель звучный: всё, что он пометил флагом, — мины; открыть мину он
/// не пытается — даже на заведомо нерешаемых полях высокой плотности.
#[test]
fn solver_is_sound_on_random_boards() {
    let mut rng = Rng::new(99);
    for _ in 0..300 {
        let (w, h) = (16, 16);
        let mines_n = 40 + rng.below(30);
        let mut mines = vec![false; w * h];
        let (sx, sy) = (rng.below(w), rng.below(h));
        let template = Board::new(w, h, 0);
        let safe: Vec<usize> = template.zone3x3(sx, sy).collect();
        let mut cells: Vec<usize> = (0..w * h).filter(|i| !safe.contains(i)).collect();
        rng.partial_shuffle(&mut cells, mines_n);
        for &i in &cells[..mines_n] {
            mines[i] = true;
        }
        let board = Board::from_mines(w, h, &mines);
        let mut solver = Solver::new(&board);
        solver.solve(sx, sy);
        assert_eq!(solver.contradictions(), 0);
        for i in 0..board.len() {
            if solver.is_flagged(i) {
                assert!(board.is_mine(i), "flagged a safe cell");
            }
        }
    }
}

/// Все пресеты сложности: поле решаемо, мин ровно столько, сколько нужно,
/// и зона 3×3 первого клика пуста.
#[test]
fn generator_presets_are_noguess() {
    let presets = [
        (9, 9, 10),
        (12, 12, 20),
        (16, 16, 40),
        (24, 20, 88),
        (30, 20, 115),
        (40, 30, 235),
    ];
    for (pi, &(w, h, m)) in presets.iter().enumerate() {
        for seed in 0..8u64 {
            let mut rng = Rng::new(seed * 1000 + pi as u64);
            let (sx, sy) = (rng.below(w), rng.below(h));
            let g = generate(w, h, m, sx, sy, &mut rng).unwrap();
            assert!(g.noguess, "{w}x{h}/{m} seed {seed}: no-guess not reached");
            assert_eq!(g.board.mines().iter().filter(|&&x| x).count(), m);
            assert!(g.board.zone3x3(sx, sy).all(|i| !g.board.is_mine(i)));
            assert!(Solver::new(&g.board).solve(sx, sy));
        }
    }
}
