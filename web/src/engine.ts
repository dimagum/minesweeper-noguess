// Мост к WASM-ядру: инициализация, коды клеток и генерация поля в воркере.

import init, { State, WasmGame, generateBoard } from "../wasm/noguess_wasm.js";
import type { GenRequest, GenResponse } from "./worker";

export { State, WasmGame };

/** Коды клеток из `WasmGame.cells()`: 0–8 — открытая цифра. */
export const Cell = {
  Hidden: 9,
  Flagged: 10,
  Mine: 11,
  Exploded: 12,
  WrongFlag: 13,
} as const;

export const isOpened = (code: number) => code <= 8 || code === Cell.Mine || code === Cell.Exploded;
export const isFlag = (code: number) => code === Cell.Flagged || code === Cell.WrongFlag;

export interface GeneratedBoard {
  mines: Uint8Array;
  noguess: boolean;
}

export async function initEngine(): Promise<void> {
  await init();
}

export function randomSeed(): number {
  return crypto.getRandomValues(new Uint32Array(1))[0];
}

// --- Генерация в Web Worker: UI не подвисает даже на больших полях. ---

let worker: Worker | null = null;
let nextId = 0;
const pending = new Map<number, { resolve: (b: GeneratedBoard) => void; reject: (e: Error) => void }>();

function getWorker(): Worker | null {
  if (worker) return worker;
  try {
    worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  } catch {
    return null;
  }
  worker.onmessage = (e: MessageEvent<GenResponse>) => {
    const p = pending.get(e.data.id);
    if (!p) return;
    pending.delete(e.data.id);
    if ("error" in e.data) p.reject(new Error(e.data.error));
    else p.resolve({ mines: e.data.mines, noguess: e.data.noguess });
  };
  worker.onerror = () => {
    // Воркер недоступен (например, file://) — дальше генерируем в основном потоке.
    for (const p of pending.values()) p.reject(new Error("worker failed"));
    pending.clear();
    worker?.terminate();
    worker = null;
    workerBroken = true;
  };
  return worker;
}

let workerBroken = false;

function generateHere(req: Omit<GenRequest, "id">): GeneratedBoard {
  const b = generateBoard(req.width, req.height, req.mines, req.x, req.y, req.seed);
  const out = { mines: b.mines, noguess: b.noguess };
  b.free();
  return out;
}

export async function generate(req: Omit<GenRequest, "id">): Promise<GeneratedBoard> {
  const w = workerBroken ? null : getWorker();
  if (!w) return generateHere(req);
  const id = nextId++;
  try {
    return await new Promise<GeneratedBoard>((resolve, reject) => {
      pending.set(id, { resolve, reject });
      w.postMessage({ ...req, id } satisfies GenRequest);
    });
  } catch (e) {
    if (workerBroken) return generateHere(req);
    throw e;
  }
}
