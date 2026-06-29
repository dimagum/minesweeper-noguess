"""Игровое поле с кастомной отрисовкой (QPainter) и плавными анимациями
в духе Minesweeper «The Clean One».

Вся доска рисуется одним виджетом (а не сеткой кнопок) — это даёт полный
контроль над оформлением (скруглённые мягкие плитки, монохромные цифры)
и позволяет делать плавные анимации:
  * каскадное открытие «волной» от точки клика;
  * pop-появление флага;
  * плавное появление мин при проигрыше;
  * мягкая подсветка ячейки под курсором.
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QPolygonF

import gui.themes as themes
from core.game import GameState

CELL = 28          # размер ячейки, px
GAP = 3            # зазор между ячейками
RADIUS = 6         # скругление плитки
PAD = 6            # внутренний отступ поля
STEP = CELL + GAP

REVEAL_MS = 190    # длительность анимации открытия одной ячейки
STAGGER_MS = 26    # задержка волны на каждую клетку расстояния от клика
FLAG_MS = 180      # длительность pop-анимации флага
HOVER_MS = 120     # сглаживание подсветки под курсором


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def clamp01(v):
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


class BoardWidget(QWidget):
    # Сигнал «состояние игры изменилось» — главное окно обновляет HUD.
    state_changed = pyqtSignal()

    def __init__(self, game, theme_name=themes.DEFAULT_THEME):
        super().__init__()
        self.game = game
        self.theme = themes.get(theme_name)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)

        W, H = game.width, game.height
        self.setFixedSize(PAD * 2 + W * STEP - GAP, PAD * 2 + H * STEP - GAP)

        # Состояние анимаций по ячейкам.
        self.reveal_start = {}     # (x,y) -> момент старта открытия (ms)
        self.flag_start = {}       # (x,y) -> момент старта анимации флага
        self.flag_dir = {}         # (x,y) -> +1 ставим / -1 снимаем
        self._prev_open = set()
        self._prev_flag = set()
        self._mines_revealed = False

        # Подсветка под курсором.
        self.hover_cell = None
        self.hover_val = 0.0

        # Состояние мыши для аккорда.
        self._left = False
        self._right = False
        self._chord = False
        self._press_cell = None

        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ #
    # Тема
    # ------------------------------------------------------------------ #
    def set_theme(self, theme_name):
        self.theme = themes.get(theme_name)
        self.update()

    # ------------------------------------------------------------------ #
    # Цветовые помощники (возвращают QColor)
    # ------------------------------------------------------------------ #
    def _bg(self):
        return QColor(self.theme["bg"])

    def _fg(self):
        return QColor(self.theme["fg"])

    def _ov(self, alpha):
        """Непрозрачный QColor: fg поверх bg с прозрачностью alpha."""
        return QColor(themes.overlay(self.theme["fg"], self.theme["bg"], clamp01(alpha)))

    # ------------------------------------------------------------------ #
    # Геометрия
    # ------------------------------------------------------------------ #
    def _cell_rect(self, x, y):
        return QRectF(PAD + x * STEP, PAD + y * STEP, CELL, CELL)

    def _cell_at(self, pos):
        x = pos.x() - PAD
        y = pos.y() - PAD
        if x < 0 or y < 0:
            return None
        cx, cy = int(x // STEP), int(y // STEP)
        if 0 <= cx < self.game.width and 0 <= cy < self.game.height:
            return (cx, cy)
        return None

    # ------------------------------------------------------------------ #
    # Мышь (повторяет логику ЛКМ / ПКМ / аккорд)
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event):
        cell = self._cell_at(event.pos())
        self._press_cell = cell
        if event.button() == Qt.LeftButton:
            self._left = True
        elif event.button() == Qt.RightButton:
            self._right = True
        if event.button() == Qt.MiddleButton or (self._left and self._right):
            if cell:
                self._do_action("chord", cell)
            self._chord = True
        self.update()

    def mouseReleaseEvent(self, event):
        cell = self._cell_at(event.pos())
        if event.button() == Qt.LeftButton:
            self._left = False
            if not self._chord and cell is not None and cell == self._press_cell:
                self._do_action("open", cell)
        elif event.button() == Qt.RightButton:
            self._right = False
            if not self._chord and cell is not None and cell == self._press_cell:
                self._do_action("flag", cell)
        if not self._left and not self._right:
            self._chord = False
            self._press_cell = None
        self.update()

    def mouseMoveEvent(self, event):
        cell = self._cell_at(event.pos())
        if cell != self.hover_cell:
            self.hover_cell = cell
            self._ensure_running()

    def leaveEvent(self, event):
        self.hover_cell = None
        self._ensure_running()

    # ------------------------------------------------------------------ #
    # Применение хода и запуск анимаций
    # ------------------------------------------------------------------ #
    def _do_action(self, kind, cell):
        x, y = cell
        if kind == "open":
            self.game.handle_left_click(x, y)
        elif kind == "flag":
            self.game.handle_right_click(x, y)
        elif kind == "chord":
            self.game.handle_both_click(x, y)
        self._sync(origin=cell)
        self.state_changed.emit()

    def _sync(self, origin):
        """Сверяет состояние игры с предыдущим и заводит анимации для
        новых открытых ячеек (волной от origin) и для флагов."""
        now = self.clock.elapsed()
        game = self.game
        ox, oy = origin

        cur_open = set()
        cur_flag = set()
        for y in range(game.height):
            for x in range(game.width):
                c = game.board.get_cell(x, y)
                if c.is_open:
                    cur_open.add((x, y))
                if c.is_flagged:
                    cur_flag.add((x, y))

        # Новые открытые ячейки — каскад от точки клика.
        for (x, y) in cur_open - self._prev_open:
            dist = max(abs(x - ox), abs(y - oy))
            self.reveal_start[(x, y)] = now + dist * STAGGER_MS

        # Поставленные / снятые флаги.
        for cell in cur_flag - self._prev_flag:
            self.flag_start[cell] = now
            self.flag_dir[cell] = +1
        for cell in self._prev_flag - cur_flag:
            self.flag_start[cell] = now
            self.flag_dir[cell] = -1

        self._prev_open = cur_open
        self._prev_flag = cur_flag

        # Проигрыш — плавно показываем все мины.
        if game.state == GameState.LOST and not self._mines_revealed:
            self._mines_revealed = True
            for y in range(game.height):
                for x in range(game.width):
                    c = game.board.get_cell(x, y)
                    if c.is_mine and not c.is_open:
                        dist = max(abs(x - ox), abs(y - oy))
                        self.reveal_start[(x, y)] = now + dist * (STAGGER_MS * 0.7)

        self._ensure_running()

    def _ensure_running(self):
        if not self.timer.isActive():
            self.timer.start()
        self.update()

    def _tick(self):
        now = self.clock.elapsed()
        active = False

        # Открытия / мины.
        for cell, start in self.reveal_start.items():
            if now < start + REVEAL_MS:
                active = True
                break
        # Флаги.
        if not active:
            for cell, start in self.flag_start.items():
                if now < start + FLAG_MS:
                    active = True
                    break

        # Подсветка под курсором.
        target = 1.0 if self.hover_cell is not None else 0.0
        if abs(self.hover_val - target) > 0.01:
            step = self.timer.interval() / HOVER_MS
            self.hover_val += step if self.hover_val < target else -step
            self.hover_val = clamp01(self.hover_val)
            active = True
        else:
            self.hover_val = target

        self.update()
        if not active:
            self.timer.stop()

    # ------------------------------------------------------------------ #
    # Прогресс анимаций
    # ------------------------------------------------------------------ #
    def _reveal_progress(self, cell, now):
        start = self.reveal_start.get(cell)
        if start is None:
            return 1.0  # давно открыта (или не анимировалась)
        if now < start:
            return 0.0
        return clamp01((now - start) / REVEAL_MS)

    def _flag_progress(self, cell, now):
        start = self.flag_start.get(cell)
        if start is None:
            return 1.0
        return clamp01((now - start) / FLAG_MS)

    # ------------------------------------------------------------------ #
    # Отрисовка
    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self._bg())
        now = self.clock.elapsed()
        game = self.game

        for y in range(game.height):
            for x in range(game.width):
                self._draw_cell(p, x, y, now)

        p.end()

    def _draw_cell(self, p, x, y, now):
        game = self.game
        cell = game.board.get_cell(x, y)
        rect = self._cell_rect(x, y)
        cx, cy = rect.center().x(), rect.center().y()
        key = (x, y)

        is_flagged = cell.is_flagged
        is_open = cell.is_open

        # Открытая ячейка (или появляющаяся мина).
        if is_open or (cell.is_mine and key in self.reveal_start):
            rv = self._reveal_progress(key, now)

            # Уходящая закрытая плитка (растворяется и уменьшается).
            if rv < 1.0:
                fade = 1.0 - rv
                self._draw_tile(p, rect, themes.TILE_FILL * fade,
                                scale=1.0 - 0.3 * rv)

            pop = ease_out_back(rv)
            if cell.is_mine:
                self._draw_mine(p, cx, cy, pop, rv)
            elif cell.adjacent_mines > 0:
                self._draw_number(p, rect, cell.adjacent_mines, rv, pop)
            return

        # Флаг.
        if is_flagged:
            self._draw_tile(p, rect, themes.TILE_FILL)
            fp = self._flag_progress(key, now)
            d = self.flag_dir.get(key, 1)
            scale = ease_out_back(fp) if d > 0 else (1.0 - ease_out_cubic(fp))
            self._draw_flag(p, rect, max(0.0, scale))
            return

        # Закрытая ячейка (с подсветкой под курсором).
        alpha = themes.TILE_FILL
        if self._press_cell == key and self._left and not is_open:
            alpha = themes.TILE_PRESS
        elif self.hover_cell == key:
            alpha = themes.TILE_FILL + (themes.TILE_HOVER - themes.TILE_FILL) * self.hover_val
        self._draw_tile(p, rect, alpha)

    # --- примитивы --- #
    def _draw_tile(self, p, rect, alpha, scale=1.0):
        if scale != 1.0:
            r = QRectF(rect)
            cx, cy = r.center().x(), r.center().y()
            w, h = r.width() * scale, r.height() * scale
            rect = QRectF(cx - w / 2, cy - h / 2, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(self._ov(alpha))
        p.drawRoundedRect(rect, RADIUS * scale, RADIUS * scale)

    def _draw_number(self, p, rect, value, rv, pop):
        f = QFont("Segoe UI")
        f.setBold(True)
        size = max(6, int(CELL * 0.52 * (0.6 + 0.4 * pop)))
        f.setPixelSize(size)
        p.setFont(f)
        p.setPen(self._ov(min(1.0, rv)))
        p.drawText(rect, Qt.AlignCenter, str(value))

    def _draw_mine(self, p, cx, cy, pop, rv):
        fg = self._fg()
        rr = CELL * 0.22 * max(0.0, pop)
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))
        if rv > 0.6:
            qp = QPen(fg)
            qp.setWidthF(max(1.0, CELL * 0.05))
            qp.setCapStyle(Qt.RoundCap)
            p.setPen(qp)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                p.drawLine(int(cx + dx * rr), int(cy + dy * rr),
                           int(cx + dx * rr * 1.8), int(cy + dy * rr * 1.8))

    def _draw_flag(self, p, rect, scale):
        if scale <= 0:
            return
        fg = self._fg()
        cx, cy = rect.center().x(), rect.center().y()
        ph = CELL * 0.40 * scale
        pole_x = cx - 1
        pen = QPen(fg)
        pen.setWidthF(max(2.0, CELL * 0.06))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(int(pole_x), int(cy - ph), int(pole_x), int(cy + ph * 0.7))
        flag_w = CELL * 0.34 * scale
        flag_h = CELL * 0.28 * scale
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        poly = QPolygonF([
            QPointF(pole_x, cy - ph),
            QPointF(pole_x + flag_w, cy - ph + flag_h / 2),
            QPointF(pole_x, cy - ph + flag_h),
        ])
        p.drawPolygon(poly)
