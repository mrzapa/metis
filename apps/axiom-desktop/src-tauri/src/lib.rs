use tauri_plugin_shell::ShellExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Spawn the bundled Python API sidecar (axiom-api binary, port 8000).
            // Non-fatal: if the binary is absent (e.g. during `tauri dev` before
            // build_api_sidecar.sh has been run), log a warning instead of crashing.
            match app.shell().sidecar("axiom-api") {
                Ok(cmd) => {
                    let _ = cmd.spawn();
                }
                Err(e) => eprintln!("[axiom-desktop] sidecar not available: {e}"),
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
