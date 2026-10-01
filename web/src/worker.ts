// Web Worker: генерация no-guess поля вне UI-потока.

import init, { generateBoard } from "../wasm/noguess_wasm.js";

export interface GenRequest {
  id: number;
  width: number;
  height: number;
  mines: number;
  x: number;
  y: number;
  seed: number;
}

export type GenResponse =
  | { id: number; mines: Uint8Array; noguess: boolean }
  | { id: number; error: string };

const ready = init();

self.onmessage = async (e: MessageEvent<GenRequest>) => {
  await ready;
  const { id, width, height, mines, x, y, seed } = e.data;
  let res: GenResponse;
  try {
    const b = generateBoard(width, height, mines, x, y, seed);
    res = { id, mines: b.mines, noguess: b.noguess };
    b.free();
  } catch (err) {
    res = { id, error: err instanceof Error ? err.message : String(err) };
  }
  const transfer = "mines" in res ? [res.mines.buffer as ArrayBuffer] : [];
  postMessage(res, { transfer });
};
