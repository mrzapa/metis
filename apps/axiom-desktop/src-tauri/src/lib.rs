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

fn emit_sidecar_error(app_handle: &tauri::AppHandle, message: &str) {
    let _ = app_handle.emit("sidecar-error", message);
    eprintln!("[axiom-desktop] {}", message);
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
                            let mut stdout_buf = String::new();
                            let mut stderr_buf = String::new();
                            let timeout =
                                tokio::time::sleep(std::time::Duration::from_secs(15));
                            tokio::pin!(timeout);

                            loop {
                                tokio::select! {
                                    _ = &mut timeout => break,
                                    event = rx.recv() => match event {
                                        Some(CommandEvent::Stdout(bytes)) => {
                                            let line = String::from_utf8_lossy(&bytes);
                                            stdout_buf.push_str(&line);
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
                                        Some(CommandEvent::Stderr(bytes)) => {
                                            let line = String::from_utf8_lossy(&bytes);
                                            stderr_buf.push_str(&line);
                                        }
                                        Some(CommandEvent::Terminated(status)) => {
                                            if !found {
                                                let msg = if !stderr_buf.is_empty() {
                                                    format!(
                                                        "API sidecar terminated unexpectedly (exit code: {:?}). stderr: {}",
                                                        status.code, stderr_buf.trim()
                                                    )
                                                } else {
                                                    format!(
                                                        "API sidecar terminated unexpectedly (exit code: {:?})",
                                                        status.code
                                                    )
                                                };
                                                emit_sidecar_error(&app_handle, &msg);
                                            }
                                            break;
                                        }
                                        None => break,
                                        _ => {}
                                    }
                                }
                            }

                            if !found {
                                let msg = if !stdout_buf.is_empty() {
                                    format!(
                                        "API did not start in time. stdout: {}",
                                        stdout_buf.trim()
                                    )
                                } else {
                                    "The local API did not start in time. Please quit and restart the application.".to_string()
                                };
                                emit_sidecar_error(&app_handle, &msg);
                            }
                        });
                    }
                    Err(e) => {
                        let msg = format!("Failed to start API sidecar: {}", e);
                        emit_sidecar_error(&app_handle, &msg);
                    }
                },
                Err(e) => {
                    let msg = format!("Sidecar binary not found: {}. Make sure the sidecar was built.", e);
                    emit_sidecar_error(&app_handle, &msg);
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
