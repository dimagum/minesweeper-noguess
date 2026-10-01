//! Детерминированный ГПСЧ (xoshiro256**, инициализация через SplitMix64).
//!
//! Свой генератор вместо крейта `rand`: никаких зависимостей, одинаковая
//! последовательность на любой платформе (нативно и в WASM) — значит, поле
//! полностью определяется seed'ом и его можно воспроизвести.

#[derive(Clone, Debug)]
pub struct Rng {
    s: [u64; 4],
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        let mut sm = seed;
        let mut next = || {
            sm = sm.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = sm;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        };
        Rng {
            s: [next(), next(), next(), next()],
        }
    }

    pub fn next_u64(&mut self) -> u64 {
        let s = &mut self.s;
        let result = s[1].wrapping_mul(5).rotate_left(7).wrapping_mul(9);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        result
    }

    /// Равномерное число в диапазоне `0..n` (метод Лемира, без смещения).
    pub fn below(&mut self, n: usize) -> usize {
        assert!(n > 0, "Rng::below(0)");
        let n = n as u64;
        loop {
            let m = (self.next_u64() as u128) * (n as u128);
            let low = m as u64;
            if low >= n.wrapping_neg() % n {
                return (m >> 64) as usize;
            }
        }
    }

    pub fn choose<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[self.below(items.len())]
    }

    /// Перемешивает первые `k` элементов (частичный Фишер–Йетс):
    /// `items[..k]` становится случайной выборкой без повторов.
    pub fn partial_shuffle<T>(&mut self, items: &mut [T], k: usize) {
        let n = items.len();
        for i in 0..k.min(n) {
            let j = i + self.below(n - i);
            items.swap(i, j);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deterministic() {
        let a: Vec<u64> = (0..5)
            .map({
                let mut r = Rng::new(42);
                move |_| r.next_u64()
            })
            .collect();
        let b: Vec<u64> = (0..5)
            .map({
                let mut r = Rng::new(42);
                move |_| r.next_u64()
            })
            .collect();
        assert_eq!(a, b);
    }

    #[test]
    fn below_in_range() {
        let mut r = Rng::new(1);
        let mut seen = [false; 7];
        for _ in 0..1000 {
            seen[r.below(7)] = true;
        }
        assert!(seen.iter().all(|&s| s));
    }
}
