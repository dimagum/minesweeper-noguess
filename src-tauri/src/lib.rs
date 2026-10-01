//! Десктоп-оболочка: окно с веб-интерфейсом из `web/`.
//!
//! Вся игровая логика работает во фронтенде (WASM-ядро), поэтому IPC-команды
//! и плагины здесь не нужны.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
