//! Ядро No-Guess Сапёра: поле, логический решатель, генератор и состояние игры.
//!
//! Крейт не зависит ни от UI, ни от платформы — он одинаково собирается
//! нативно (тесты, бенчмарки, Tauri) и в WASM (браузер).

pub mod board;
pub mod game;
pub mod generator;
pub mod rng;
pub mod solver;

pub use board::Board;
pub use game::{CellView, Game, GameState};
pub use generator::{GenError, Generated, generate};
pub use rng::Rng;
pub use solver::Solver;
