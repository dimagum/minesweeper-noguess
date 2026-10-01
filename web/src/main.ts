import "./style.css";

import { BoardView, type Action, type Controls } from "./board";
import { Cell, State, WasmGame, generate, initEngine, randomSeed, type GeneratedBoard } from "./engine";
import { DEFAULT_THEME, THEMES, THEME_ORDER, applyTheme, type ThemeName } from "./themes";

// Пресеты сложности: плавный рост размера и плотности мин (≤ ~20%) —
// генерация остаётся мгновенной, поле гарантированно проходится без угадывания.
const DIFFICULTIES = [
  { name: "Beginner", width: 9, height: 9, mines: 10 },
  { name: "Easy", width: 12, height: 12, mines: 20 },
  { name: "Medium", width: 16, height: 16, mines: 40 },
  { name: "Hard", width: 24, height: 20, mines: 88 },
  { name: "Huge", width: 30, height: 20, mines: 115 },
  { name: "Extreme", width: 40, height: 30, mines: 235 },
] as const;

type Difficulty = (typeof DIFFICULTIES)[number];

const CONTROLS_INFO: Record<Controls, string> = {
  classic: "Click: open · Right-click: flag · Both buttons: chord",
  touchpad: "Click: flag · Double-click: open, or chord on a number",
};

// --- Настройки и рекорды в localStorage (недоступен — просто не сохраняем). ---

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
  private diffIndex = Math.min(store.get("difficulty", 0), DIFFICULTIES.length - 1);
  private themeName: ThemeName = THEME_ORDER.includes(store.get("theme", DEFAULT_THEME))
    ? store.get("theme", DEFAULT_THEME)
    : DEFAULT_THEME;
  private best: Record<string, number> = store.get("best", {});
  private controls: Controls = store.get<Controls>("controls", "classic") === "touchpad" ? "touchpad" : "classic";

  private game: WasmGame | null = null;
  private diff: Difficulty = DIFFICULTIES[0];
  /** Поле и первый клик текущей партии — для «Retry board». */
  private lastBoard: (GeneratedBoard & { x: number; y: number }) | null = null;
  private generation = 0; // защита от устаревших ответов воркера
  private generating = false;
  private hintsUsed = 0;

  // Таймер: копится только пока открыт экран игры.
  private elapsedMs = 0;
  private runningSince: number | null = null;
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
    window.addEventListener("resize", () => this.layout());
  }

  // ------------------------------------------------------------------ //
  // Меню
  // ------------------------------------------------------------------ //

  private buildMenu(): void {
    $("diff-prev").onclick = () => this.shiftDifficulty(-1);
    $("diff-next").onclick = () => this.shiftDifficulty(1);
    $("btn-new").onclick = () => this.newGame();
    $("btn-resume").onclick = () => this.showGame();

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
    this.diffIndex = (this.diffIndex + delta + DIFFICULTIES.length) % DIFFICULTIES.length;
    store.set("difficulty", this.diffIndex);
    this.renderDifficulty();
  }

  private renderDifficulty(): void {
    const d = DIFFICULTIES[this.diffIndex];
    $("diff-name").textContent = d.name;
    $("diff-info").textContent = `${d.width} × ${d.height} · ${d.mines} mines`;
    const best = this.best[d.name];
    $("best").textContent = best === undefined ? "" : `Best: ${formatTime(best)}`;
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

  private showMenu(): void {
    this.pauseClock();
    clearTimeout(this.endTimer);
    $("game").hidden = true;
    $("menu").hidden = false;
    ($("btn-resume") as HTMLButtonElement).disabled = !this.canResume();
    this.renderDifficulty();
  }

  private showGame(): void {
    $("menu").hidden = true;
    $("game").hidden = false;
    this.layout();
    if (this.game?.state === State.Playing) this.resumeClock();
    this.updateHud();
  }

  // ------------------------------------------------------------------ //
  // Партия
  // ------------------------------------------------------------------ //

  private newGame(diff: Difficulty = DIFFICULTIES[this.diffIndex]): void {
    this.resetGame(diff);
    this.lastBoard = null;
    this.showGame();
  }

  /** «Retry board»: то же поле и тот же первый клик. */
  private retryBoard(): void {
    const b = this.lastBoard;
    if (!b) return;
    this.resetGame(this.diff);
    this.lastBoard = b;
    this.game!.startWithMines(b.mines, b.noguess, b.x, b.y);
    this.view.sync(b.x, b.y);
    this.startClock();
    this.showGame();
  }

  private resetGame(diff: Difficulty): void {
    this.game?.free();
    this.diff = diff;
    this.game = new WasmGame(diff.width, diff.height, diff.mines, randomSeed());
    this.generation++;
    this.generating = false;
    this.hintsUsed = 0;
    this.elapsedMs = 0;
    this.runningSince = null;
    clearTimeout(this.endTimer);
    $("overlay").hidden = true;
    $("board-scroll").classList.remove("busy");
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
    if (changed) this.afterMove(x, y);
  }

  /** Первый клик: поле генерируется в воркере под эту клетку. */
  private async firstClick(x: number, y: number): Promise<void> {
    const gen = ++this.generation;
    this.generating = true;
    const busy = window.setTimeout(() => $("board-scroll").classList.add("busy"), 150);
    const d = this.diff;
    try {
      const board = await generate({ width: d.width, height: d.height, mines: d.mines, x, y, seed: randomSeed() });
      if (gen !== this.generation || !this.game) return; // партию уже сменили
      this.game.startWithMines(board.mines, board.noguess, x, y);
      this.lastBoard = { ...board, x, y };
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
      // Даём анимациям доиграть, затем показываем результат.
      this.endTimer = window.setTimeout(() => this.showResult(), game.state === State.Lost ? 900 : 650);
    }
  }

  private showResult(): void {
    const game = this.game!;
    const won = game.state === State.Won;
    const secs = Math.floor(this.elapsedMs / 1000);
    let text: string;
    if (won) {
      const prev = this.best[this.diff.name];
      if (this.hintsUsed > 0) {
        text = `${formatTime(secs)} · ${this.hintsUsed} hint${this.hintsUsed > 1 ? "s" : ""} used`;
      } else if (prev === undefined || secs < prev) {
        this.best[this.diff.name] = secs;
        store.set("best", this.best);
        text = `${formatTime(secs)} · new best!`;
      } else {
        text = `${formatTime(secs)} · best ${formatTime(prev)}`;
      }
    } else {
      text = "You hit a mine.";
    }
    $("ov-title").textContent = won ? "Solved" : "Boom";
    $("ov-text").textContent = text;
    $("ov-retry").hidden = won || !this.lastBoard;
    $("overlay").hidden = false;
    ($(won ? "ov-new" : "ov-retry") as HTMLButtonElement).focus();
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

  // ------------------------------------------------------------------ //
  // HUD, таймер, раскладка
  // ------------------------------------------------------------------ //

  private bindGameUi(): void {
    $("btn-back").onclick = () => this.showMenu();
    $("btn-restart").onclick = () => this.newGame(this.diff);
    $("btn-hint").onclick = () => this.showHint();
    $("ov-new").onclick = () => this.newGame(this.diff);
    $("ov-retry").onclick = () => this.retryBoard();
    $("ov-menu").onclick = () => this.showMenu();

    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const inGame = !$("game").hidden;
      if (!inGame) {
        if (e.key === "ArrowLeft") this.shiftDifficulty(-1);
        else if (e.key === "ArrowRight") this.shiftDifficulty(1);
        else if (e.key === "Enter" && document.activeElement === document.body) this.newGame();
        else return;
      } else if (e.key === "Escape") this.showMenu();
      else if (e.key === "h" || e.key === "H") this.showHint();
      else if (e.key === "r" || e.key === "R") this.newGame(this.diff);
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

initEngine()
  .then(() => {
    const app = new App();
    // Хук для ручной отладки и автотестов в dev-сборке; в production его нет.
    if (import.meta.env.DEV) Object.assign(window, { __app: app });
  })
  .catch((e) => {
    document.body.textContent = `Failed to load the game engine: ${e}`;
  });
