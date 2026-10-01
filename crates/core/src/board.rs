//! Поле «Сапёра»: расположение мин, цифры и кэш соседей.
//!
//! Клетки хранятся плоско, индекс `i = y * width + x`.

#[derive(Clone, Copy, Debug)]
struct Neighbors {
    idx: [u32; 8],
    len: u8,
}

#[derive(Clone, Debug)]
pub struct Board {
    width: usize,
    height: usize,
    num_mines: usize,
    mines: Vec<bool>,
    numbers: Vec<u8>,
    neighbors: Vec<Neighbors>,
}

impl Board {
    /// Пустое поле без мин (`num_mines` — сколько мин будет расставлено).
    pub fn new(width: usize, height: usize, num_mines: usize) -> Self {
        assert!(width > 0 && height > 0, "board must be non-empty");
        let mut neighbors = Vec::with_capacity(width * height);
        for y in 0..height as isize {
            for x in 0..width as isize {
                let mut n = Neighbors {
                    idx: [0; 8],
                    len: 0,
                };
                for dy in -1..=1 {
                    for dx in -1..=1 {
                        if dx == 0 && dy == 0 {
                            continue;
                        }
                        let (nx, ny) = (x + dx, y + dy);
                        if nx >= 0 && ny >= 0 && (nx as usize) < width && (ny as usize) < height {
                            n.idx[n.len as usize] = (ny as usize * width + nx as usize) as u32;
                            n.len += 1;
                        }
                    }
                }
                neighbors.push(n);
            }
        }
        Board {
            width,
            height,
            num_mines,
            mines: vec![false; width * height],
            numbers: vec![0; width * height],
            neighbors,
        }
    }

    /// Поле с заданной расстановкой мин (цифры считаются сразу).
    pub fn from_mines(width: usize, height: usize, mines: &[bool]) -> Self {
        assert_eq!(mines.len(), width * height, "mines length mismatch");
        let num_mines = mines.iter().filter(|&&m| m).count();
        let mut board = Board::new(width, height, num_mines);
        board.mines.copy_from_slice(mines);
        board.calculate_numbers();
        board
    }

    pub fn width(&self) -> usize {
        self.width
    }
    pub fn height(&self) -> usize {
        self.height
    }
    pub fn len(&self) -> usize {
        self.width * self.height
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub fn num_mines(&self) -> usize {
        self.num_mines
    }

    pub fn idx(&self, x: usize, y: usize) -> usize {
        y * self.width + x
    }
    pub fn xy(&self, i: usize) -> (usize, usize) {
        (i % self.width, i / self.width)
    }
    pub fn in_bounds(&self, x: i64, y: i64) -> bool {
        x >= 0 && y >= 0 && (x as usize) < self.width && (y as usize) < self.height
    }

    pub fn neighbors(&self, i: usize) -> &[u32] {
        let n = &self.neighbors[i];
        &n.idx[..n.len as usize]
    }

    pub fn is_mine(&self, i: usize) -> bool {
        self.mines[i]
    }
    pub fn mines(&self) -> &[bool] {
        &self.mines
    }

    /// Число мин вокруг клетки (для мины — 0).
    pub fn number(&self, i: usize) -> u8 {
        self.numbers[i]
    }

    pub(crate) fn set_mine(&mut self, i: usize, mine: bool) {
        self.mines[i] = mine;
    }

    fn count_around(&self, i: usize) -> u8 {
        self.neighbors(i)
            .iter()
            .filter(|&&n| self.mines[n as usize])
            .count() as u8
    }

    pub fn calculate_numbers(&mut self) {
        for i in 0..self.len() {
            self.numbers[i] = if self.mines[i] {
                0
            } else {
                self.count_around(i)
            };
        }
    }

    /// Инкрементальный пересчёт цифр клетки `i` и её соседей —
    /// после того как генератор поменял местами две клетки.
    pub fn recalc_around(&mut self, i: usize) {
        let n = self.neighbors[i];
        for j in std::iter::once(i).chain(n.idx[..n.len as usize].iter().map(|&j| j as usize)) {
            self.numbers[j] = if self.mines[j] {
                0
            } else {
                self.count_around(j)
            };
        }
    }

    /// Индексы зоны 3×3 вокруг (x, y), обрезанной по краям поля.
    pub fn zone3x3(&self, x: usize, y: usize) -> impl Iterator<Item = usize> + '_ {
        let i = self.idx(x, y);
        std::iter::once(i).chain(self.neighbors(i).iter().map(|&j| j as usize))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_and_neighbors() {
        // . * .
        // . . .
        let b = Board::from_mines(3, 2, &[false, true, false, false, false, false]);
        assert_eq!(b.neighbors(0).len(), 3);
        assert_eq!(b.neighbors(4).len(), 5);
        assert_eq!(b.num_mines(), 1);
        let nums: Vec<u8> = (0..6).map(|i| b.number(i)).collect();
        assert_eq!(nums, vec![1, 0, 1, 1, 1, 1]);
    }

    #[test]
    fn recalc_matches_full() {
        let mut b = Board::from_mines(4, 4, &[false; 16]);
        b.set_mine(5, true);
        b.recalc_around(5);
        let inc: Vec<u8> = (0..16).map(|i| b.number(i)).collect();
        b.calculate_numbers();
        let full: Vec<u8> = (0..16).map(|i| b.number(i)).collect();
        assert_eq!(inc, full);
    }
}
