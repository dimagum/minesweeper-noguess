//! WebAssembly-обёртка над `noguess-core` для веб-интерфейса.
//!
//! Две точки входа:
//!   * [`WasmGame`] — партия целиком (клики, флаги, аккорд, подсказка);
//!     состояние поля отдаётся одним `Uint8Array` через [`WasmGame::cells`].
//!   * [`generate_board`] — только генерация поля, для Web Worker'а: тяжёлая
//!     работа уходит из UI-потока, а результат передаётся в
//!     [`WasmGame::start_with_mines`].

use noguess_core::{Board, CellView, Game, GameState, Rng, generate};
use wasm_bindgen::prelude::*;

/// Коды клеток в [`WasmGame::cells`]: 0–8 — открытая клетка с цифрой.
pub const CELL_HIDDEN: u8 = 9;
pub const CELL_FLAGGED: u8 = 10;
/// Мина, показанная после поражения.
pub const CELL_MINE: u8 = 11;
/// Мина, на которую нажали.
pub const CELL_EXPLODED: u8 = 12;
/// Флаг не на мине (показывается после поражения).
pub const CELL_WRONG_FLAG: u8 = 13;

#[wasm_bindgen]
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum State {
    NotStarted = 0,
    Playing = 1,
    Won = 2,
    Lost = 3,
}

impl From<GameState> for State {
    fn from(s: GameState) -> Self {
        match s {
            GameState::NotStarted => State::NotStarted,
            GameState::Playing => State::Playing,
            GameState::Won => State::Won,
            GameState::Lost => State::Lost,
        }
    }
}

/// Подсказка: клетка, о которой можно сделать вывод логически.
#[wasm_bindgen]
#[derive(Clone, Copy)]
pub struct HintMove {
    pub x: u32,
    pub y: u32,
    /// `true` — мина (поставить флаг), `false` — клетку можно открыть.
    pub mine: bool,
}

#[wasm_bindgen]
pub struct WasmGame {
    inner: Game,
}

#[wasm_bindgen]
impl WasmGame {
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32, mines: u32, seed: u32) -> Result<WasmGame, JsError> {
        if width == 0 || height == 0 {
            return Err(JsError::new("board must be non-empty"));
        }
        Ok(WasmGame {
            inner: Game::new(width as usize, height as usize, mines as usize, seed as u64),
        })
    }

    #[wasm_bindgen(getter)]
    pub fn width(&self) -> u32 {
        self.inner.width() as u32
    }

    #[wasm_bindgen(getter)]
    pub fn height(&self) -> u32 {
        self.inner.height() as u32
    }

    #[wasm_bindgen(getter)]
    pub fn mines(&self) -> u32 {
        self.inner.num_mines() as u32
    }

    #[wasm_bindgen(getter)]
    pub fn state(&self) -> State {
        self.inner.state().into()
    }

    /// Мины минус флаги — для счётчика в HUD (может быть отрицательным).
    #[wasm_bindgen(getter, js_name = minesLeft)]
    pub fn mines_left(&self) -> i32 {
        self.inner.mines_left() as i32
    }

    #[wasm_bindgen(getter, js_name = isNoguess)]
    pub fn is_noguess(&self) -> bool {
        self.inner.is_noguess()
    }

    /// Левый клик. Первый клик генерирует поле синхронно; чтобы не блокировать
    /// UI, лучше сгенерировать его в воркере и вызвать `startWithMines`.
    pub fn open(&mut self, x: u32, y: u32) -> Result<bool, JsError> {
        self.inner
            .open(x as usize, y as usize)
            .map_err(|e| JsError::new(&e.to_string()))
    }

    #[wasm_bindgen(js_name = toggleFlag)]
    pub fn toggle_flag(&mut self, x: u32, y: u32) -> bool {
        self.inner.toggle_flag(x as usize, y as usize)
    }

    pub fn chord(&mut self, x: u32, y: u32) -> bool {
        self.inner.chord(x as usize, y as usize)
    }

    pub fn hint(&self) -> Option<HintMove> {
        self.inner.hint().map(|h| HintMove {
            x: h.x as u32,
            y: h.y as u32,
            mine: h.mine,
        })
    }

    /// Начинает партию с полем из [`generate_board`] и открывает (x, y).
    #[wasm_bindgen(js_name = startWithMines)]
    pub fn start_with_mines(
        &mut self,
        mines: &[u8],
        noguess: bool,
        x: u32,
        y: u32,
    ) -> Result<(), JsError> {
        let (w, h) = (self.inner.width(), self.inner.height());
        if self.inner.state() != GameState::NotStarted {
            return Err(JsError::new("game already started"));
        }
        if mines.len() != w * h {
            return Err(JsError::new("mines length does not match board size"));
        }
        if x as usize >= w || y as usize >= h {
            return Err(JsError::new("first click is outside the board"));
        }
        let mines: Vec<bool> = mines.iter().map(|&m| m != 0).collect();
        let board = Board::from_mines(w, h, &mines);
        if board.num_mines() != self.inner.num_mines() {
            return Err(JsError::new("mine count does not match the game"));
        }
        self.inner
            .start_with_board(board, noguess, x as usize, y as usize);
        Ok(())
    }

    /// Всё поле одним массивом (по строкам, `y * width + x`), коды — `CELL_*`.
    pub fn cells(&self) -> Vec<u8> {
        let g = &self.inner;
        let mut out = Vec::with_capacity(g.width() * g.height());
        for y in 0..g.height() {
            for x in 0..g.width() {
                out.push(match g.cell(x, y) {
                    CellView::Open(n) => n,
                    CellView::Hidden => CELL_HIDDEN,
                    CellView::Flagged => CELL_FLAGGED,
                    CellView::Mine { exploded: false } => CELL_MINE,
                    CellView::Mine { exploded: true } => CELL_EXPLODED,
                    CellView::WrongFlag => CELL_WRONG_FLAG,
                });
            }
        }
        out
    }
}

/// Результат генерации: мины (1 байт на клетку, 0/1) и флаг гарантии no-guess.
#[wasm_bindgen]
pub struct GeneratedBoard {
    mines: Vec<u8>,
    noguess: bool,
}

#[wasm_bindgen]
impl GeneratedBoard {
    #[wasm_bindgen(getter)]
    pub fn mines(&self) -> Vec<u8> {
        self.mines.clone()
    }

    #[wasm_bindgen(getter)]
    pub fn noguess(&self) -> bool {
        self.noguess
    }
}

/// Генерирует no-guess поле с первым кликом в (x, y). Детерминировано по `seed`.
#[wasm_bindgen(js_name = generateBoard)]
pub fn generate_board(
    width: u32,
    height: u32,
    mines: u32,
    x: u32,
    y: u32,
    seed: u32,
) -> Result<GeneratedBoard, JsError> {
    if width == 0 || height == 0 {
        return Err(JsError::new("board must be non-empty"));
    }
    let mut rng = Rng::new(seed as u64);
    let g = generate(
        width as usize,
        height as usize,
        mines as usize,
        x as usize,
        y as usize,
        &mut rng,
    )
    .map_err(|e| JsError::new(&e.to_string()))?;
    Ok(GeneratedBoard {
        mines: g.board.mines().iter().map(|&m| m as u8).collect(),
        noguess: g.noguess,
    })
}
