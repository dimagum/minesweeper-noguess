"""Генерирует фикстуру для tests/parity.rs: поля + вердикт Python-решателя.

Запуск из корня репозитория:
    python3 crates/core/tests/make_parity_fixture.py
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "legacy-python"))

from core.board import Board  # noqa: E402
from core.generator import Generator  # noqa: E402
from solver.logic_solver import LogicSolver  # noqa: E402

# (ширина, высота, мины, число полей): от простых к плотным.
CASES = [
    (9, 9, 10, 120),
    (12, 12, 20, 100),
    (16, 16, 40, 100),
    (16, 16, 30, 60),
    (24, 20, 70, 40),
    (24, 20, 88, 30),
    (30, 20, 115, 20),
]


def random_board(rng, w, h, m):
    sx, sy = rng.randrange(w), rng.randrange(h)
    safe = {(sx + dx, sy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    cells = [(x, y) for y in range(h) for x in range(w) if (x, y) not in safe]
    b = Board(w, h, m)
    for x, y in rng.sample(cells, m):
        b.grid[y][x].is_mine = True
    b.calculate_numbers()
    return b, sx, sy


def record(b, sx, sy, kind):
    mines = "".join("1" if b.grid[y][x].is_mine else "0"
                    for y in range(b.height) for x in range(b.width))
    return {"kind": kind, "w": b.width, "h": b.height, "sx": sx, "sy": sy,
            "mines": mines, "solvable": LogicSolver(b).is_solvable(sx, sy)}


def main():
    rng = random.Random(20261002)
    out = []
    for w, h, m, n in CASES:
        for _ in range(n):
            b, sx, sy = random_board(rng, w, h, m)
            out.append(record(b, sx, sy, "random"))
        # Поля от генератора — заведомо решаемые.
        for _ in range(max(5, n // 10)):
            sx, sy = rng.randrange(w), rng.randrange(h)
            b = Generator.generate_valid_board(w, h, m, sx, sy, rng=rng)
            out.append(record(b, sx, sy, "generated"))
    # Формат строки: kind w h sx sy solvable(0/1) mines(строка 0/1 по строкам поля)
    path = os.path.join(os.path.dirname(__file__), "fixtures", "parity.txt")
    with open(path, "w") as f:
        for r in out:
            f.write(f"{r['kind']} {r['w']} {r['h']} {r['sx']} {r['sy']} "
                    f"{int(r['solvable'])} {r['mines']}\n")
    solvable = sum(r["solvable"] for r in out)
    print(f"{len(out)} boards, {solvable} solvable -> {path}")


if __name__ == "__main__":
    main()
