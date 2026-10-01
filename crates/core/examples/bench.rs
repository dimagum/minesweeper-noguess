//! Бенчмарк генератора по пресетам сложности (первый клик — в центре поля).
//!
//!     cargo run --release --example bench [-- RUNS]

use std::time::Instant;

use noguess_core::{Rng, generate};

const PRESETS: [(&str, usize, usize, usize); 6] = [
    ("Beginner", 9, 9, 10),
    ("Easy", 12, 12, 20),
    ("Medium", 16, 16, 40),
    ("Hard", 24, 20, 88),
    ("Huge", 30, 20, 115),
    ("Extreme", 40, 30, 235),
];

fn main() {
    let runs: u64 = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(100);
    println!("{runs} runs per preset");
    for (name, w, h, m) in PRESETS {
        let mut times = Vec::new();
        let mut fails = 0;
        for seed in 0..runs {
            let mut rng = Rng::new(seed);
            let t = Instant::now();
            let g = generate(w, h, m, w / 2, h / 2, &mut rng).unwrap();
            times.push(t.elapsed().as_secs_f64() * 1000.0);
            fails += usize::from(!g.noguess);
        }
        times.sort_by(f64::total_cmp);
        let p = |q: f64| times[((times.len() - 1) as f64 * q) as usize];
        println!(
            "{name:9} median {:8.2} ms   p95 {:8.2} ms   max {:8.2} ms   fails {fails}",
            p(0.5),
            p(0.95),
            p(1.0)
        );
    }
}
