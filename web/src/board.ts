// Игровое поле на Canvas с плавными анимациями в духе «The Clean One»:
//   * каскадное открытие «волной» от точки клика;
//   * pop-появление флага;
//   * плавное появление мин при проигрыше;
//   * мягкая подсветка ячейки под курсором и зоны аккорда;
//   * пульсирующая рамка подсказки.
//
// Ввод (две схемы, выбираются в меню):
//   * classic  — ЛКМ: открыть, ПКМ: флаг, ЛКМ+ПКМ или средняя кнопка: аккорд;
//   * touchpad — клик: флаг, двойной клик: открыть (по цифре — аккорд).
// Сенсорный экран: тап — открыть (по цифре — аккорд), долгое нажатие — флаг.

import { Cell, State, isFlag, isOpened, type WasmGame } from "./engine";
import { TILE_FILL, TILE_HOVER, TILE_PRESS, overlay, type Theme } from "./themes";

const REVEAL_MS = 190; // длительность анимации открытия одной ячейки
const STAGGER_MS = 26; // задержка волны на каждую клетку расстояния от клика
const FLAG_MS = 180; // длительность pop-анимации флага
const HOVER_MS = 120; // сглаживание подсветки под курсором
const HINT_MS = 2600; // сколько живёт рамка подсказки
const LONG_PRESS_MS = 380; // долгое нажатие на сенсорном экране = флаг
// Схема touchpad: одиночный клик (флаг) выжидает столько, не окажется ли он
// первым кликом двойного. Двойной клик, распознанный системой позже,
// всё равно корректен: первый клик просто отменяется.
const SINGLE_CLICK_DELAY_MS = 200;

const MIN_STEP = 20;
const MAX_STEP = 34;
const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

export type Action = "open" | "flag" | "chord";
export type Controls = "classic" | "touchpad";

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;
const easeOutBack = (t: number) => 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2;
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

function progress(start: number, duration: number, now: number): number {
  if (Number.isNaN(start)) return 1; // давно открыта (или не анимировалась)
  return now < start ? 0 : clamp01((now - start) / duration);
}

interface TouchState {
  id: number;
  cell: number;
  x: number;
  y: number;
  timer: number;
  long: boolean;
}

export class BoardView {
  private ctx: CanvasRenderingContext2D;
  private game: WasmGame | null = null;
  private w = 0;
  private h = 0;
  private cells: Uint8Array = new Uint8Array(0);

  // Анимации по ячейкам (NaN — анимации нет).
  private revealStart = new Float64Array(0);
  private flagStart = new Float64Array(0);
  private flagDir = new Int8Array(0);

  // Геометрия.
  private step = 31;
  private gap = 3;
  private cellSize = 28;
  private radius = 6;
  private readonly pad = 6;
  private dpr = 1;

  // Цвета (кэш наложений fg на bg).
  private theme: Theme;
  private colorCache = new Map<number, string>();

  // Ввод.
  private left = false;
  private right = false;
  private chording = false;
  private pressCell = -1;
  private hoverCell = -1;
  private hoverVal = 0;
  private touch: TouchState | null = null;
  private controls: Controls = "classic";
  /** Последний одиночный клик схемы touchpad: клетка, её вид до клика,
   *  таймер отложенного флага и был ли флаг уже переключён. */
  private pendingClick: { cell: number; before: number; timer: number; applied: boolean } | null = null;

  private hint: { cell: number; mine: boolean; start: number } | null = null;
  private raf = 0;
  private lastFrame = 0;

  constructor(
    readonly canvas: HTMLCanvasElement,
    theme: Theme,
    private readonly onAction: (action: Action, x: number, y: number) => void,
  ) {
    this.ctx = canvas.getContext("2d")!;
    this.theme = theme;
    this.bindInput();
  }

  // ------------------------------------------------------------------ //
  // Состояние
  // ------------------------------------------------------------------ //

  setGame(game: WasmGame): void {
    this.game = game;
    this.w = game.width;
    this.h = game.height;
    const n = this.w * this.h;
    this.cells = game.cells();
    this.revealStart = new Float64Array(n).fill(NaN);
    this.flagStart = new Float64Array(n).fill(NaN);
    this.flagDir = new Int8Array(n);
    this.hint = null;
    this.left = this.right = this.chording = false;
    this.pressCell = this.hoverCell = -1;
    this.clearPendingClick();
    this.requestDraw();
  }

  setControls(controls: Controls): void {
    this.controls = controls;
    this.clearPendingClick();
  }

  setTheme(theme: Theme): void {
    this.theme = theme;
    this.colorCache.clear();
    this.requestDraw();
  }

  /** Сверяет поле с игрой и заводит анимации: волной от (ox, oy). */
  sync(ox: number, oy: number): void {
    if (!this.game) return;
    const now = performance.now();
    const next = this.game.cells();
    for (let i = 0; i < next.length; i++) {
      const prev = this.cells[i];
      const cur = next[i];
      if (prev === cur) continue;
      if (!isOpened(prev) && isOpened(cur)) {
        const x = i % this.w;
        const y = (i / this.w) | 0;
        const dist = Math.max(Math.abs(x - ox), Math.abs(y - oy));
        // Мины при проигрыше проявляются чуть быстрее, чем обычный каскад.
        const stagger = cur === Cell.Mine ? STAGGER_MS * 0.7 : STAGGER_MS;
        this.revealStart[i] = now + dist * stagger;
      }
      if (!isFlag(prev) && isFlag(cur)) {
        this.flagStart[i] = now;
        this.flagDir[i] = 1;
      } else if (isFlag(prev) && cur === Cell.Hidden) {
        this.flagStart[i] = now;
        this.flagDir[i] = -1;
      }
    }
    this.cells = next;
    this.hint = null;
    this.requestDraw();
  }

  showHint(x: number, y: number, mine: boolean): void {
    this.hint = { cell: y * this.w + x, mine, start: performance.now() };
    this.requestDraw();
  }

  // ------------------------------------------------------------------ //
  // Геометрия
  // ------------------------------------------------------------------ //

  /** Подбирает размер клетки под доступную область (в CSS-пикселях). */
  layout(maxWidth: number, maxHeight: number): void {
    if (!this.w) return;
    const fit = Math.floor(Math.min((maxWidth - 2 * this.pad) / this.w, (maxHeight - 2 * this.pad) / this.h));
    this.step = Math.max(MIN_STEP, Math.min(MAX_STEP, fit));
    this.gap = Math.max(2, Math.round(this.step * 0.1));
    this.cellSize = this.step - this.gap;
    this.radius = this.cellSize * 0.21;

    const cssW = this.pad * 2 + this.w * this.step - this.gap;
    const cssH = this.pad * 2 + this.h * this.step - this.gap;
    this.dpr = window.devicePixelRatio || 1;
    this.canvas.style.width = `${cssW}px`;
    this.canvas.style.height = `${cssH}px`;
    this.canvas.width = Math.round(cssW * this.dpr);
    this.canvas.height = Math.round(cssH * this.dpr);
    this.requestDraw();
  }

  get cssWidth(): number {
    return this.pad * 2 + this.w * this.step - this.gap;
  }

  private cellAt(clientX: number, clientY: number): number {
    const r = this.canvas.getBoundingClientRect();
    const x = clientX - r.left - this.pad;
    const y = clientY - r.top - this.pad;
    if (x < 0 || y < 0) return -1;
    const cx = Math.floor(x / this.step);
    const cy = Math.floor(y / this.step);
    return cx < this.w && cy < this.h ? cy * this.w + cx : -1;
  }

  // ------------------------------------------------------------------ //
  // Ввод
  // ------------------------------------------------------------------ //

  private act(action: Action, cell: number): void {
    if (cell < 0) return;
    this.onAction(action, cell % this.w, (cell / this.w) | 0);
  }

  private bindInput(): void {
    const c = this.canvas;
    c.addEventListener("contextmenu", (e) => e.preventDefault());

    // Мышь: отдельные mousedown/mouseup на каждую кнопку — так ловится
    // аккорд ЛКМ+ПКМ (pointer events второй кнопки шлют лишь pointermove).
    c.addEventListener("mousedown", (e) => {
      const cell = this.cellAt(e.clientX, e.clientY);
      if (this.controls === "touchpad" && e.button === 0) {
        this.touchpadClick(cell, e.detail);
        return;
      }
      this.pressCell = cell;
      if (e.button === 0) this.left = true;
      else if (e.button === 2) this.right = true;
      if (e.button === 1 || (this.left && this.right)) {
        e.preventDefault(); // без автоскролла средней кнопкой
        this.chording = true;
        this.act("chord", cell);
      }
      this.requestDraw();
    });

    window.addEventListener("mouseup", (e) => {
      if (!this.left && !this.right && !this.chording) return;
      const cell = this.cellAt(e.clientX, e.clientY);
      if (e.button === 0) {
        this.left = false;
        if (!this.chording && cell === this.pressCell) this.act("open", cell);
      } else if (e.button === 2) {
        this.right = false;
        if (!this.chording && cell === this.pressCell) this.act("flag", cell);
      }
      if (!this.left && !this.right) {
        this.chording = false;
        this.pressCell = -1;
      }
      this.requestDraw();
    });

    c.addEventListener("mousemove", (e) => {
      const cell = this.cellAt(e.clientX, e.clientY);
      if (cell !== this.hoverCell) {
        this.hoverCell = cell;
        this.requestDraw();
      }
    });
    c.addEventListener("mouseleave", () => {
      this.hoverCell = -1;
      this.requestDraw();
    });

    // Сенсорный экран и перо.
    c.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse") return;
      e.preventDefault(); // без эмуляции mouse-событий
      this.cancelTouch();
      const cell = this.cellAt(e.clientX, e.clientY);
      const t: TouchState = { id: e.pointerId, cell, x: e.clientX, y: e.clientY, long: false, timer: 0 };
      t.timer = window.setTimeout(() => {
        t.long = true;
        this.pressCell = -1;
        this.act("flag", cell);
        navigator.vibrate?.(15);
      }, LONG_PRESS_MS);
      this.touch = t;
      this.pressCell = cell;
      this.left = true;
      this.requestDraw();
    });
    c.addEventListener("pointermove", (e) => {
      const t = this.touch;
      if (t && t.id === e.pointerId && Math.hypot(e.clientX - t.x, e.clientY - t.y) > 10) this.cancelTouch();
    });
    c.addEventListener("pointerup", (e) => {
      const t = this.touch;
      if (!t || t.id !== e.pointerId) return;
      const tapped = !t.long;
      const cell = t.cell;
      this.cancelTouch();
      if (tapped && cell >= 0) {
        const code = this.cells[cell];
        this.act(code >= 1 && code <= 8 ? "chord" : "open", cell);
      }
    });
    c.addEventListener("pointercancel", () => this.cancelTouch());
  }

  /** Схема touchpad: клик — флаг, двойной клик — открыть / аккорд. */
  private touchpadClick(cell: number, clicks: number): void {
    if (cell < 0) return;
    // До первого хода флаги бессмысленны — одиночный клик сразу открывает.
    if (this.game?.state === State.NotStarted) {
      if (clicks === 1) this.act("open", cell);
      return;
    }
    if (clicks === 1) {
      this.clearPendingClick();
      const before = this.cells[cell];
      const p = { cell, before, timer: 0, applied: false };
      if (before === Cell.Hidden || isFlag(before)) {
        p.timer = window.setTimeout(() => {
          p.applied = true;
          this.act("flag", cell);
        }, SINGLE_CLICK_DELAY_MS);
      }
      this.pendingClick = p;
      return;
    }
    if (clicks !== 2) return; // тройные клики игнорируем

    // Двойной клик: откатываем первый клик и действуем по исходному виду клетки.
    const p = this.pendingClick;
    let before = this.cells[cell];
    if (p && p.cell === cell) {
      clearTimeout(p.timer);
      if (p.applied) this.act("flag", cell);
      before = p.before;
    }
    this.pendingClick = null;
    if (before === Cell.Hidden) this.act("open", cell);
    else if (before >= 1 && before <= 8) this.act("chord", cell);
    // По клетке с флагом двойной клик ничего не открывает — защита от взрыва.
  }

  private clearPendingClick(): void {
    if (this.pendingClick) clearTimeout(this.pendingClick.timer);
    this.pendingClick = null;
  }

  private cancelTouch(): void {
    if (!this.touch) return;
    clearTimeout(this.touch.timer);
    this.touch = null;
    this.left = false;
    this.pressCell = -1;
    this.requestDraw();
  }

  // ------------------------------------------------------------------ //
  // Кадры
  // ------------------------------------------------------------------ //

  private requestDraw(): void {
    if (this.raf) return;
    this.raf = requestAnimationFrame(this.frame);
  }

  private frame = (now: number): void => {
    this.raf = 0;
    const dt = this.lastFrame ? Math.min(64, now - this.lastFrame) : 16;
    this.lastFrame = now;
    let active = false;

    // Подсветка под курсором.
    const target = this.hoverCell >= 0 ? 1 : 0;
    if (Math.abs(this.hoverVal - target) > 0.01) {
      this.hoverVal = clamp01(this.hoverVal + (target > this.hoverVal ? 1 : -1) * (dt / HOVER_MS));
      active = true;
    } else {
      this.hoverVal = target;
    }

    // Открытия, мины, флаги, подсказка.
    for (let i = 0; i < this.revealStart.length && !active; i++) {
      if (now < this.revealStart[i] + REVEAL_MS || now < this.flagStart[i] + FLAG_MS) active = true;
    }
    if (this.hint && now < this.hint.start + HINT_MS) active = true;
    else this.hint = null;

    this.draw(now);
    if (active) this.requestDraw();
    else this.lastFrame = 0;
  };

  // ------------------------------------------------------------------ //
  // Отрисовка
  // ------------------------------------------------------------------ //

  /** Непрозрачный цвет: fg поверх bg с прозрачностью alpha (кэшируется). */
  private ov(alpha: number): string {
    const key = Math.round(clamp01(alpha) * 400);
    let c = this.colorCache.get(key);
    if (!c) {
      c = overlay(this.theme.fg, this.theme.bg, key / 400);
      this.colorCache.set(key, c);
    }
    return c;
  }

  private draw(now: number): void {
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = this.theme.bg;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    for (let i = 0; i < this.cells.length; i++) this.drawCell(i, now);
    if (this.hint) this.drawHint(now);
  }

  private isChordZone(i: number): boolean {
    if (!this.chording || this.pressCell < 0) return false;
    const dx = Math.abs((i % this.w) - (this.pressCell % this.w));
    const dy = Math.abs(((i / this.w) | 0) - ((this.pressCell / this.w) | 0));
    return dx <= 1 && dy <= 1;
  }

  private drawCell(i: number, now: number): void {
    const code = this.cells[i];
    const x0 = this.pad + (i % this.w) * this.step;
    const y0 = this.pad + ((i / this.w) | 0) * this.step;
    const s = this.cellSize;
    const cx = x0 + s / 2;
    const cy = y0 + s / 2;

    // Открытая ячейка (или проявляющаяся мина).
    if (isOpened(code)) {
      const rv = progress(this.revealStart[i], REVEAL_MS, now);
      // Уходящая закрытая плитка: растворяется и уменьшается.
      if (rv < 1) this.drawTile(x0, y0, TILE_FILL * (1 - rv), 1 - 0.3 * rv);
      const pop = easeOutBack(rv);
      if (code === Cell.Exploded) {
        this.drawTile(x0, y0, 0.85 * clamp01(rv * 1.5));
        this.drawMine(cx, cy, pop, rv, this.theme.bg);
      } else if (code === Cell.Mine) {
        this.drawMine(cx, cy, pop, rv, this.theme.fg);
      } else if (code > 0) {
        this.drawNumber(cx, cy, code, rv, pop);
      }
      return;
    }

    // Флаг.
    if (isFlag(code)) {
      this.drawTile(x0, y0, TILE_FILL);
      const fp = progress(this.flagStart[i], FLAG_MS, now);
      this.drawFlag(cx, cy, Math.max(0, easeOutBack(fp)), code === Cell.WrongFlag ? 0.45 : 1);
      if (code === Cell.WrongFlag) this.drawCross(cx, cy);
      return;
    }

    // Закрытая ячейка: снимаемый флаг, нажатие, подсветка под курсором.
    let alpha = TILE_FILL;
    const pressed = (this.left && !this.chording && this.pressCell === i) || this.isChordZone(i);
    if (pressed) alpha = TILE_PRESS;
    else if (this.hoverCell === i) alpha = TILE_FILL + (TILE_HOVER - TILE_FILL) * this.hoverVal;
    this.drawTile(x0, y0, alpha);
    if (this.flagDir[i] < 0) {
      const fp = progress(this.flagStart[i], FLAG_MS, now);
      if (fp < 1) this.drawFlag(cx, cy, 1 - easeOutCubic(fp), 1);
    }
  }

  private drawHint(now: number): void {
    const { cell, mine, start } = this.hint!;
    const t = clamp01((now - start) / HINT_MS);
    const pulse = 0.5 + 0.5 * Math.sin(t * Math.PI * 8);
    const fade = t < 0.8 ? 1 : 1 - (t - 0.8) / 0.2;
    const x0 = this.pad + (cell % this.w) * this.step;
    const y0 = this.pad + ((cell / this.w) | 0) * this.step;
    const grow = 1 + 2 * pulse;
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = fade;
    ctx.strokeStyle = this.theme.fg;
    ctx.lineWidth = Math.max(2, this.cellSize * 0.08);
    ctx.beginPath();
    ctx.roundRect(x0 - grow, y0 - grow, this.cellSize + grow * 2, this.cellSize + grow * 2, this.radius + grow);
    ctx.stroke();
    if (mine && this.cells[cell] === Cell.Hidden) {
      ctx.globalAlpha = fade * 0.45;
      this.drawFlag(x0 + this.cellSize / 2, y0 + this.cellSize / 2, 1, 1);
    }
    ctx.restore();
  }

  // --- примитивы --- //

  private drawTile(x0: number, y0: number, alpha: number, scale = 1): void {
    const s = this.cellSize * scale;
    const off = (this.cellSize - s) / 2;
    const ctx = this.ctx;
    ctx.fillStyle = this.ov(alpha);
    ctx.beginPath();
    ctx.roundRect(x0 + off, y0 + off, s, s, this.radius * scale);
    ctx.fill();
  }

  private drawNumber(cx: number, cy: number, value: number, rv: number, pop: number): void {
    const size = Math.max(6, Math.round(this.cellSize * 0.52 * (0.6 + 0.4 * pop)));
    const ctx = this.ctx;
    ctx.font = `700 ${size}px ${FONT}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = this.ov(rv);
    ctx.fillText(String(value), cx, cy + size * 0.05);
  }

  private drawMine(cx: number, cy: number, pop: number, rv: number, color: string): void {
    const ctx = this.ctx;
    const rr = this.cellSize * 0.22 * Math.max(0, pop);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy, rr, 0, Math.PI * 2);
    ctx.fill();
    if (rv > 0.6) {
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(1, this.cellSize * 0.05);
      ctx.lineCap = "round";
      ctx.beginPath();
      for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
        ctx.moveTo(cx + dx * rr, cy + dy * rr);
        ctx.lineTo(cx + dx * rr * 1.8, cy + dy * rr * 1.8);
      }
      ctx.stroke();
    }
  }

  private drawFlag(cx: number, cy: number, scale: number, alpha: number): void {
    if (scale <= 0) return;
    const ctx = this.ctx;
    const s = this.cellSize * scale;
    // Габарит флажка (древко + полотнище) центрируется в клетке.
    const height = s * 0.5;
    const fw = s * 0.3; // ширина полотнища
    const fh = height * 0.56; // высота полотнища
    const lw = Math.max(1.5, this.cellSize * 0.07) * Math.min(1, scale);
    // Древко выступает влево на lw/2 — сдвигаем, чтобы габарит был симметричен.
    const poleX = cx - fw / 2 + lw / 4;
    const top = cy - height / 2;
    const color = alpha < 1 ? this.ov(alpha) : this.theme.fg;
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(poleX, top);
    ctx.lineTo(poleX, top + height);
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(poleX, top);
    ctx.lineTo(poleX + fw, top + fh / 2);
    ctx.lineTo(poleX, top + fh);
    ctx.closePath();
    ctx.fill();
  }

  private drawCross(cx: number, cy: number): void {
    const ctx = this.ctx;
    const r = this.cellSize * 0.3;
    ctx.strokeStyle = this.theme.fg;
    ctx.lineWidth = Math.max(2, this.cellSize * 0.07);
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(cx - r, cy - r);
    ctx.lineTo(cx + r, cy + r);
    ctx.moveTo(cx + r, cy - r);
    ctx.lineTo(cx - r, cy + r);
    ctx.stroke();
  }
}
