import "./style.css";

import { BoardView, type Action, type Controls } from "./board";
import { Cell, State, WasmGame, generate, initEngine, randomSeed, type GeneratedBoard } from "./engine";
import { DEFAULT_THEME, THEMES, THEME_ORDER, applyTheme, type ThemeName } from "./themes";

/** Параметры партии: пресет, своё поле или ежедневное поле. */
interface Config {
  /** Ключ статистики: имя пресета, "Custom" или "Daily". */
  id: string;
  name: string;
  width: number;
  height: number;
  mines: number;
  /** Дата ежедневного поля (YYYY-MM-DD) — только для Daily. */
  daily?: string;
}

// Пресеты сложности: плавный рост размера и плотности мин (≤ ~20%) —
// генерация остаётся мгновенной, поле гарантированно проходится без угадывания.
const PRESETS: Config[] = [
  { id: "Beginner", name: "Beginner", width: 9, height: 9, mines: 10 },
  { id: "Easy", name: "Easy", width: 12, height: 12, mines: 20 },
  { id: "Medium", name: "Medium", width: 16, height: 16, mines: 40 },
  { id: "Hard", name: "Hard", width: 24, height: 20, mines: 88 },
  { id: "Huge", name: "Huge", width: 30, height: 20, mines: 115 },
  { id: "Extreme", name: "Extreme", width: 40, height: 30, mines: 235 },
];
/** В меню после пресетов идёт «Custom». */
const CUSTOM_INDEX = PRESETS.length;

// Своё поле: границы размеров и плотности. Чем больше поле, тем ниже
// допустимая плотность — иначе генерация no-guess поля занимает секунды.
const CUSTOM_LIMITS = { minSide: 5, maxWidth: 60, maxHeight: 40 };
const DENSE_WARNING = 0.22;
function maxMines(width: number, height: number): number {
  const cells = width * height;
  const density = cells <= 600 ? 0.28 : cells <= 1200 ? 0.25 : 0.23;
  return Math.min(Math.floor(cells * density), cells - 9);
}

// Ежедневное поле: одно и то же у всех, первая клетка (центр) открыта заранее.
const DAILY_SIZE = { width: 24, height: 20, mines: 88 };

const CONTROLS_INFO: Record<Controls, string> = {
  classic: "Click: open · Right-click: flag · Both buttons: chord",
  touchpad: "Click: flag · Double-click: open, or chord on a number",
};

interface Stats {
  played: number;
  won: number;
  streak: number;
  bestStreak: number;
  /** Сумма и число побед без подсказок — для среднего времени. */
  winSecs: number;
  timedWins: number;
}

interface DailyResult {
  won: boolean;
  secs: number;
  hints: number;
}

const emptyStats = (): Stats => ({ played: 0, won: 0, streak: 0, bestStreak: 0, winSecs: 0, timedWins: 0 });

// --- Настройки, статистика и рекорды в localStorage (недоступен — не сохраняем). ---

const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem(`noguess.${key}`);
      return v === null ? fallback : (JSON.parse(v) as T);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown): void {
    try {
      localStorage.setItem(`noguess.${key}`, JSON.stringify(value));
    } catch {
      /* приватный режим и т.п. */
    }
  },
};

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

class App {
  private diffIndex = Math.min(store.get("difficulty", 0), CUSTOM_INDEX);
  private custom = store.get("custom", { width: 20, height: 15, mines: 50 });
  private themeName: ThemeName = THEME_ORDER.includes(store.get("theme", DEFAULT_THEME))
    ? store.get("theme", DEFAULT_THEME)
    : DEFAULT_THEME;
  private best: Record<string, number> = store.get("best", {});
  private stats: Record<string, Stats> = store.get("stats", {});
  private dailyResults: Record<string, DailyResult> = store.get("daily", {});
  private controls: Controls = store.get<Controls>("controls", "classic") === "touchpad" ? "touchpad" : "classic";

  private game: WasmGame | null = null;
  private config: Config = PRESETS[0];
  /** Поле и первый клик текущей партии — для «Retry board». */
  private lastBoard: (GeneratedBoard & { x: number; y: number }) | null = null;
  private generation = 0; // защита от устаревших ответов воркера
  private generating = false;
  private hintsUsed = 0;
  private recorded = false; // результат партии уже учтён в статистике

  // Таймер: копится только пока открыт экран игры. Если первая клетка
  // открыта заранее (Daily, Retry), он стартует с первого хода игрока.
  private elapsedMs = 0;
  private runningSince: number | null = null;
  private clockArmed = false;
  private hudTimer = 0;
  private endTimer = 0;
  private toastTimer = 0;

  private view: BoardView;

  constructor() {
    this.view = new BoardView($("board") as HTMLCanvasElement, THEMES[this.themeName], (a, x, y) =>
      this.onAction(a, x, y),
    );
    this.buildMenu();
    this.bindGameUi();
    this.setTheme(this.themeName);
    this.setControls(this.controls);
    this.renderDifficulty();
    this.renderDaily();
    window.addEventListener("resize", () => this.layout());
  }

  // ------------------------------------------------------------------ //
  // Меню
  // ------------------------------------------------------------------ //

  private buildMenu(): void {
    $("diff-prev").onclick = () => this.shiftDifficulty(-1);
    $("diff-next").onclick = () => this.shiftDifficulty(1);
    $("btn-new").onclick = () => this.newGame();
    $("btn-daily").onclick = () => this.startDaily();
    $("btn-resume").onclick = () => this.showGame();
    $("btn-stats").onclick = () => this.showStats();
    $("stats-back").onclick = () => this.showScreen("menu");
    $("stats-reset").onclick = () => this.resetStats();

    for (const id of ["custom-w", "custom-h", "custom-m"]) {
      $<HTMLInputElement>(id).addEventListener("change", () => this.readCustom());
    }

    for (const el of $("controls").children) {
      const b = el as HTMLButtonElement;
      b.onclick = () => this.setControls(b.dataset.controls as Controls);
    }

    const swatches = $("swatches");
    for (const name of THEME_ORDER) {
      const b = document.createElement("button");
      b.className = "swatch";
      b.title = name;
      b.setAttribute("role", "radio");
      b.setAttribute("aria-label", name);
      b.style.setProperty("--sw-bg", THEMES[name].bg);
      b.style.setProperty("--sw-fg", THEMES[name].fg);
      b.onclick = () => this.setTheme(name);
      b.dataset.theme = name;
      swatches.append(b);
    }
  }

  private setControls(controls: Controls): void {
    this.controls = controls;
    store.set("controls", controls);
    this.view.setControls(controls);
    for (const el of $("controls").children) {
      const b = el as HTMLElement;
      b.setAttribute("aria-checked", String(b.dataset.controls === controls));
    }
    $("controls-info").textContent = CONTROLS_INFO[controls];
  }

  private shiftDifficulty(delta: number): void {
    const n = CUSTOM_INDEX + 1;
    this.diffIndex = (this.diffIndex + delta + n) % n;
    store.set("difficulty", this.diffIndex);
    this.renderDifficulty();
  }

  /** Выбранная в меню конфигурация (пресет или своё поле). */
  private menuConfig(): Config {
    if (this.diffIndex < CUSTOM_INDEX) return PRESETS[this.diffIndex];
    const { width, height, mines } = this.custom;
    return { id: "Custom", name: "Custom", width, height, mines };
  }

  /** Читает и нормализует поля «Custom» (размеры и допустимое число мин). */
  private readCustom(): void {
    const num = (id: string, fallback: number) => {
      const v = parseInt($<HTMLInputElement>(id).value, 10);
      return Number.isFinite(v) ? v : fallback;
    };
    const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
    const width = clamp(num("custom-w", this.custom.width), CUSTOM_LIMITS.minSide, CUSTOM_LIMITS.maxWidth);
    const height = clamp(num("custom-h", this.custom.height), CUSTOM_LIMITS.minSide, CUSTOM_LIMITS.maxHeight);
    const mines = clamp(num("custom-m", this.custom.mines), 1, maxMines(width, height));
    this.custom = { width, height, mines };
    store.set("custom", this.custom);
    this.renderDifficulty();
  }

  private renderDifficulty(): void {
    const c = this.menuConfig();
    const isCustom = this.diffIndex === CUSTOM_INDEX;
    $("diff-name").textContent = c.name;
    $("diff-info").textContent = `${c.width} × ${c.height} · ${c.mines} mines`;
    $("custom").hidden = !isCustom;
    if (isCustom) {
      $<HTMLInputElement>("custom-w").value = String(c.width);
      $<HTMLInputElement>("custom-h").value = String(c.height);
      const m = $<HTMLInputElement>("custom-m");
      m.value = String(c.mines);
      m.max = String(maxMines(c.width, c.height));
      const density = c.mines / (c.width * c.height);
      $("custom-info").textContent =
        `${(density * 100).toFixed(1)}% density · max ${maxMines(c.width, c.height)} mines` +
        (density > DENSE_WARNING ? " · dense: generation may take a few seconds" : "");
    }
    const best = isCustom ? undefined : this.best[c.id];
    $("best").textContent = best === undefined ? "" : `Best: ${formatTime(best)}`;
  }

  private renderDaily(): void {
    const key = todayKey();
    const r = this.dailyResults[key];
    $("daily-date").textContent = formatDay(key);
    $("daily-status").textContent = !r
      ? ""
      : r.won
        ? `solved · ${formatTime(r.secs)}${r.hints ? " · hints" : ""}`
        : "failed · replay won't count";
  }

  private setTheme(name: ThemeName): void {
    this.themeName = name;
    store.set("theme", name);
    applyTheme(THEMES[name]);
    this.view.setTheme(THEMES[name]);
    for (const el of $("swatches").children) {
      const b = el as HTMLElement;
      b.setAttribute("aria-checked", String(b.dataset.theme === name));
    }
  }

  private canResume(): boolean {
    return this.game !== null && (this.game.state === State.NotStarted || this.game.state === State.Playing);
  }

  private showScreen(id: "menu" | "game" | "stats"): void {
    for (const s of ["menu", "game", "stats"]) $(s).hidden = s !== id;
  }

  private showMenu(): void {
    this.pauseClock();
    clearTimeout(this.endTimer);
    this.showScreen("menu");
    ($("btn-resume") as HTMLButtonElement).disabled = !this.canResume();
    this.renderDifficulty();
    this.renderDaily();
  }

  private showGame(): void {
    this.showScreen("game");
    this.layout();
    if (this.game?.state === State.Playing && !this.clockArmed) this.resumeClock();
    this.updateHud();
  }

  // ------------------------------------------------------------------ //
  // Статистика
  // ------------------------------------------------------------------ //

  private record(won: boolean): void {
    if (this.recorded) return;
    this.recorded = true;
    const c = this.config;
    const secs = Math.floor(this.elapsedMs / 1000);
    // Ежедневное поле засчитывается только по первой завершённой попытке.
    if (c.daily) {
      if (this.dailyResults[c.daily]) return;
      this.dailyResults[c.daily] = { won, secs, hints: this.hintsUsed };
      store.set("daily", this.dailyResults);
    }

    const s = { ...emptyStats(), ...this.stats[c.id] };
    s.played++;
    if (won) {
      s.won++;
      s.streak++;
      s.bestStreak = Math.max(s.bestStreak, s.streak);
      if (this.hintsUsed === 0) {
        s.winSecs += secs;
        s.timedWins++;
      }
    } else {
      s.streak = 0;
    }
    this.stats[c.id] = s;
    store.set("stats", this.stats);

    // Рекорд — только для пресетов (и Daily), без подсказок.
    if (won && this.hintsUsed === 0 && c.id !== "Custom") {
      const prev = this.best[c.id];
      if (prev === undefined || secs < prev) {
        this.best[c.id] = secs;
        store.set("best", this.best);
      }
    }
  }

  private showStats(): void {
    const rows = [...PRESETS.map((p) => p.id), "Custom", "Daily"];
    const body = $("stats-body");
    body.replaceChildren();
    for (const id of rows) {
      const s = this.stats[id] ?? emptyStats();
      const tr = document.createElement("tr");
      const cells = [
        id,
        String(s.played),
        s.played ? `${Math.round((100 * s.won) / s.played)}%` : "–",
        this.best[id] === undefined ? "–" : formatTime(this.best[id]),
        s.timedWins ? formatTime(Math.round(s.winSecs / s.timedWins)) : "–",
        s.played ? `${s.streak} / ${s.bestStreak}` : "–",
      ];
      for (const [i, text] of cells.entries()) {
        const td = document.createElement(i === 0 ? "th" : "td");
        if (i === 0) td.scope = "row";
        td.textContent = text;
        tr.append(td);
      }
      if (!s.played) tr.className = "empty";
      body.append(tr);
    }
    const streak = dailyStreak(this.dailyResults);
    $("stats-daily").textContent = streak
      ? `Daily streak: ${streak} day${streak > 1 ? "s" : ""} in a row`
      : "Solve today's daily board to start a streak.";
    this.showScreen("stats");
  }

  private resetStats(): void {
    if (!confirm("Reset all statistics and best times?")) return;
    this.stats = {};
    this.best = {};
    this.dailyResults = {};
    store.set("stats", {});
    store.set("best", {});
    store.set("daily", {});
    this.renderDaily();
    this.showStats();
  }

  // ------------------------------------------------------------------ //
  // Партия
  // ------------------------------------------------------------------ //

  private newGame(config: Config = this.menuConfig()): void {
    if (config.daily) {
      this.startDaily();
      return;
    }
    this.resetGame(config);
    this.lastBoard = null;
    this.showGame();
  }

  /** Ежедневное поле: seed из даты, первая клетка — центр, открыта сразу. */
  private async startDaily(): Promise<void> {
    const day = todayKey();
    const config: Config = { id: "Daily", name: `Daily · ${formatDay(day)}`, ...DAILY_SIZE, daily: day };
    const x = config.width >> 1;
    const y = config.height >> 1;
    this.resetGame(config);
    this.showGame();
    const gen = this.generation;
    this.generating = true;
    try {
      const board = await generate({ ...DAILY_SIZE, x, y, seed: hashSeed(`noguess-daily:${day}`) });
      if (gen !== this.generation || !this.game) return;
      this.startPrepared({ ...board, x, y });
    } catch (e) {
      this.toast(`Could not generate the board: ${e instanceof Error ? e.message : e}`);
    } finally {
      if (gen === this.generation) this.generating = false;
    }
  }

  /** «Retry board»: то же поле и тот же первый клик. */
  private retryBoard(): void {
    const b = this.lastBoard;
    if (!b) return;
    this.resetGame(this.config);
    this.startPrepared(b);
    this.showGame();
  }

  /** Старт с готовым полем: первая клетка открыта, таймер — с первого хода. */
  private startPrepared(b: GeneratedBoard & { x: number; y: number }): void {
    this.game!.startWithMines(b.mines, b.noguess, b.x, b.y);
    this.lastBoard = b;
    this.clockArmed = true;
    this.view.sync(b.x, b.y);
    this.updateHud();
  }

  private resetGame(config: Config): void {
    this.game?.free();
    this.config = config;
    this.game = new WasmGame(config.width, config.height, config.mines, randomSeed());
    this.generation++;
    this.generating = false;
    this.hintsUsed = 0;
    this.recorded = false;
    this.elapsedMs = 0;
    this.runningSince = null;
    this.clockArmed = false;
    clearTimeout(this.endTimer);
    $("overlay").hidden = true;
    $("board-scroll").classList.remove("busy");
    $("hud-title").textContent = config.daily ? config.name : "";
    this.view.setGame(this.game);
  }

  private onAction(action: Action, x: number, y: number): void {
    const game = this.game;
    if (!game || this.generating) return;

    if (game.state === State.NotStarted && action === "open") {
      this.firstClick(x, y);
      return;
    }
    const changed =
      action === "open" ? game.open(x, y) : action === "flag" ? game.toggleFlag(x, y) : game.chord(x, y);
    if (changed && this.clockArmed) {
      this.clockArmed = false;
      this.startClock();
    }
    if (changed) this.afterMove(x, y);
  }

  /** Первый клик: поле генерируется в воркере под эту клетку. */
  private async firstClick(x: number, y: number): Promise<void> {
    const gen = ++this.generation;
    this.generating = true;
    const busy = window.setTimeout(() => $("board-scroll").classList.add("busy"), 150);
    const { width, height, mines } = this.config;
    try {
      const board = await generate({ width, height, mines, x, y, seed: randomSeed() });
      if (gen !== this.generation || !this.game) return; // партию уже сменили
      this.game.startWithMines(board.mines, board.noguess, x, y);
      this.lastBoard = { ...board, x, y };
      if (!board.noguess) this.toast("Mine density too high: this board may need a guess");
      this.startClock();
      this.afterMove(x, y);
    } catch (e) {
      this.toast(`Could not generate the board: ${e instanceof Error ? e.message : e}`);
    } finally {
      clearTimeout(busy);
      if (gen === this.generation) {
        this.generating = false;
        $("board-scroll").classList.remove("busy");
      }
    }
  }

  private afterMove(x: number, y: number): void {
    const game = this.game!;
    this.view.sync(x, y);
    this.updateHud();
    if (game.state === State.Won || game.state === State.Lost) {
      this.pauseClock();
      this.record(game.state === State.Won);
      // Даём анимациям доиграть, затем показываем результат.
      this.endTimer = window.setTimeout(() => this.showResult(), game.state === State.Lost ? 900 : 650);
    }
  }

  private showResult(): void {
    const game = this.game!;
    const c = this.config;
    const won = game.state === State.Won;
    const secs = Math.floor(this.elapsedMs / 1000);
    const parts = [won ? formatTime(secs) : "You hit a mine."];
    if (won && this.hintsUsed > 0) {
      parts.push(`${this.hintsUsed} hint${this.hintsUsed > 1 ? "s" : ""} used`);
    } else if (won && c.id !== "Custom" && this.best[c.id] !== undefined) {
      parts.push(this.best[c.id] === secs ? "best time!" : `best ${formatTime(this.best[c.id])}`);
    }
    const s = this.stats[c.id];
    if (s && s.streak > 1) parts.push(`streak ${s.streak}`);

    $("ov-title").textContent = c.daily ? (won ? "Daily solved" : "Boom") : won ? "Solved" : "Boom";
    $("ov-text").textContent = parts.join(" · ");
    $("ov-retry").hidden = won || !this.lastBoard;
    $("ov-new").hidden = !!c.daily;
    $("overlay").hidden = false;
    ($(won ? (c.daily ? "ov-menu" : "ov-new") : "ov-retry") as HTMLButtonElement).focus();
  }

  private showHint(): void {
    const game = this.game;
    if (!game || game.state !== State.Playing) {
      this.toast(game?.state === State.NotStarted ? "Click any cell to start" : "");
      return;
    }
    const h = game.hint();
    if (!h) {
      this.toast("No logical move found");
      return;
    }
    const { x, y, mine } = h;
    h.free();
    this.hintsUsed++;
    const code = game.cells()[y * game.width + x];
    if (!mine && code === Cell.Flagged) this.toast("This flag is wrong — the cell is safe");
    this.view.showHint(x, y, mine);
  }

  /** ↻ / R: новое поле той же конфигурации; ежедневное — заново то же. */
  private restart(): void {
    if (this.config.daily) this.retryBoard();
    else this.newGame(this.config);
  }

  // ------------------------------------------------------------------ //
  // HUD, таймер, раскладка
  // ------------------------------------------------------------------ //

  private bindGameUi(): void {
    $("btn-back").onclick = () => this.showMenu();
    $("btn-restart").onclick = () => this.restart();
    $("btn-hint").onclick = () => this.showHint();
    $("ov-new").onclick = () => this.newGame(this.config);
    $("ov-retry").onclick = () => this.retryBoard();
    $("ov-menu").onclick = () => this.showMenu();

    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const inInput = e.target instanceof HTMLInputElement;
      if (!$("menu").hidden) {
        if (inInput) {
          if (e.key !== "Enter") return;
          this.readCustom();
          this.newGame();
        } else if (e.key === "ArrowLeft") this.shiftDifficulty(-1);
        else if (e.key === "ArrowRight") this.shiftDifficulty(1);
        else if (e.key === "Enter" && document.activeElement === document.body) this.newGame();
        else return;
      } else if (!$("stats").hidden) {
        if (e.key !== "Escape") return;
        this.showScreen("menu");
      } else if (e.key === "Escape") this.showMenu();
      else if (e.key === "h" || e.key === "H") this.showHint();
      else if (e.key === "r" || e.key === "R") this.restart();
      else return;
      e.preventDefault();
    });
  }

  private updateHud(): void {
    if (!this.game) return;
    $("hud-mines").textContent = `⚑ ${this.game.minesLeft}`;
    $("hud-time").textContent = formatTime(Math.floor(this.currentMs() / 1000));
  }

  private currentMs(): number {
    return this.elapsedMs + (this.runningSince === null ? 0 : performance.now() - this.runningSince);
  }

  private startClock(): void {
    this.elapsedMs = 0;
    this.resumeClock();
  }

  private resumeClock(): void {
    if (this.runningSince !== null) return;
    this.runningSince = performance.now();
    clearInterval(this.hudTimer);
    this.hudTimer = window.setInterval(() => this.updateHud(), 250);
  }

  private pauseClock(): void {
    if (this.runningSince !== null) {
      this.elapsedMs += performance.now() - this.runningSince;
      this.runningSince = null;
    }
    clearInterval(this.hudTimer);
    this.updateHud();
  }

  private layout(): void {
    if ($("game").hidden || !this.game) return;
    const hud = $("hud").getBoundingClientRect().height;
    const maxW = window.innerWidth - 24;
    const maxH = window.innerHeight - hud - 40;
    this.view.layout(maxW, maxH);
    $("hud").style.width = `${Math.min(this.view.cssWidth, maxW)}px`;
  }

  private toast(text: string): void {
    const el = $("toast");
    el.textContent = text;
    el.classList.toggle("show", text !== "");
    clearTimeout(this.toastTimer);
    this.toastTimer = window.setTimeout(() => el.classList.remove("show"), 2400);
  }
}

function formatTime(secs: number): string {
  if (secs < 60) return String(secs);
  const m = Math.floor(secs / 60);
  return `${m}:${String(secs % 60).padStart(2, "0")}`;
}

/** Локальная дата в виде YYYY-MM-DD (ежедневное поле меняется в полночь). */
function todayKey(date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}

function formatDay(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en", { month: "short", day: "numeric" });
}

/** FNV-1a: строка → 32-битный seed (одинаковый на всех устройствах). */
function hashSeed(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Сколько дней подряд (до сегодня или вчера) ежедневное поле решено. */
function dailyStreak(results: Record<string, DailyResult>): number {
  const day = new Date();
  if (!results[todayKey(day)]?.won) day.setDate(day.getDate() - 1);
  let streak = 0;
  while (results[todayKey(day)]?.won) {
    streak++;
    day.setDate(day.getDate() - 1);
  }
  return streak;
}

// Системное контекстное меню (Reload / Inspect) в игре не нужно — ПКМ ставит флаги.
document.addEventListener("contextmenu", (e) => e.preventDefault());

initEngine()
  .then(() => {
    const app = new App();
    // Хук для ручной отладки и автотестов в dev-сборке; в production его нет.
    if (import.meta.env.DEV) Object.assign(window, { __app: app });
  })
  .catch((e) => {
    document.body.textContent = `Failed to load the game engine: ${e}`;
  });
