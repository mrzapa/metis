use std::sync::Mutex;

use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// Holds the negotiated API base URL once the sidecar prints it.
struct ApiState {
    base_url: Mutex<Option<String>>,
    // Keeps the child process alive for the lifetime of the app.
    _child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
}

/// Tauri command: returns the sidecar's base URL, or None if not yet ready.
#[tauri::command]
fn get_api_base_url(state: tauri::State<'_, ApiState>) -> Option<String> {
    state.base_url.lock().unwrap().clone()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(ApiState {
            base_url: Mutex::new(None),
            _child: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![get_api_base_url])
        .setup(|app| {
            match app.shell().sidecar("axiom-api") {
                Ok(cmd) => match cmd.spawn() {
                    Ok((mut rx, child)) => {
                        *app.state::<ApiState>()._child.lock().unwrap() = Some(child);

                        let app_handle = app.handle().clone();
                        tauri::async_runtime::spawn(async move {
                            let mut found = false;
                            let timeout =
                                tokio::time::sleep(std::time::Duration::from_secs(15));
                            tokio::pin!(timeout);

                            loop {
                                tokio::select! {
                                    _ = &mut timeout => break,
                                    event = rx.recv() => match event {
                                        Some(CommandEvent::Stdout(bytes)) => {
                                            let line = String::from_utf8_lossy(&bytes);
                                            if let Some(url) = line
                                                .trim()
                                                .strip_prefix("AXIOM_API_LISTENING=")
                                            {
                                                *app_handle
                                                    .state::<ApiState>()
                                                    .base_url
                                                    .lock()
                                                    .unwrap() = Some(url.trim().to_string());
                                                found = true;
                                                break;
                                            }
                                        }
                                        Some(CommandEvent::Terminated(_)) | None => break,
                                        _ => {}
                                    }
                                }
                            }

                            if !found {
                                let _ = app_handle.emit(
                                    "sidecar-timeout",
                                    "The local API did not start in time. \
                                     Please quit and restart the application.",
                                );
                            }
                        });
                    }
                    Err(e) => eprintln!("[axiom-desktop] sidecar spawn failed: {e}"),
                },
                Err(e) => eprintln!("[axiom-desktop] sidecar not available: {e}"),
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
