use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, LogicalPosition, LogicalSize, Manager, WebviewWindow,
};
use std::sync::atomic::{AtomicBool, Ordering};

static ALLOW_EXIT: AtomicBool = AtomicBool::new(false);

fn trace_log(msg: &str) {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let log_file = dir.join("trace_lib.log");
            let line = format!("[{}] PID {}: {}\n", chrono_now(), std::process::id(), msg);
            let _ = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(log_file)
                .and_then(|mut f| {
                    use std::io::Write;
                    f.write_all(line.as_bytes())
                });
        }
    }
}

fn chrono_now() -> String {
    format!("{:?}", std::time::SystemTime::now())
}

#[tauri::command]
fn log_frontend(msg: String) {
    trace_log(&format!("FRONTEND: {}", msg));
}

#[tauri::command]
fn minimize_window(window: WebviewWindow) {
    trace_log("cmd: minimize_window");
    let _ = window.minimize();
}

#[tauri::command]
fn hide_window(window: WebviewWindow) {
    trace_log("cmd: hide_window");
    let _ = window.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
    let _ = window.hide();
}

#[tauri::command]
fn show_window(window: WebviewWindow) {
    trace_log("cmd: show_window");
    let _ = window.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
    let _ = window.show();
    let _ = window.set_focus();
}

#[tauri::command]
fn exit_app(app_handle: AppHandle) {
    trace_log("cmd: exit_app");
    ALLOW_EXIT.store(true, Ordering::SeqCst);
    app_handle.exit(0);
}

#[tauri::command]
fn start_drag(window: WebviewWindow) {
    let _ = window.start_dragging();
}

#[tauri::command]
fn position_above_taskbar(window: WebviewWindow) {
    trace_log("position_above_taskbar entered");
    let win_w = 370.0;
    let win_h = 412.0;
    let margin_x = 16.0;
    let margin_y = 60.0; // above taskbar

    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten());

    trace_log(&format!("position_above_taskbar monitor: {:?}", monitor.is_some()));

    if let Some(mon) = monitor {
        let screen_size = mon.size().to_logical::<f64>(mon.scale_factor());
        let target_x = screen_size.width - win_w - margin_x;
        let target_y = screen_size.height - win_h - margin_y;

        trace_log(&format!("set_position ({}, {})", target_x, target_y));
        let _ = window.set_position(tauri::Position::Logical(LogicalPosition::new(target_x, target_y)));
    }

    let _ = window.set_size(tauri::Size::Logical(LogicalSize::new(win_w, win_h)));
    
    // Set explicit window icon (updates Windows Taskbar icon immediately via WM_SETICON)
    static TASKBAR_RGBA_128: &[u8] = include_bytes!("../icons/128x128.rgba");
    let taskbar_icon = tauri::image::Image::new(TASKBAR_RGBA_128, 128, 128);
    let _ = window.set_icon(taskbar_icon);

    trace_log("calling window.show, unminimize, set_focus");
    let _ = window.show();
    let _ = window.unminimize();
    let _ = window.set_focus();
}

#[tauri::command]
async fn open_app_window(url: String, title: String) -> Result<(), String> {
    let clean_url = url.trim().to_string();
    if clean_url.is_empty() {
        return Err("URL tidak boleh kosong".to_string());
    }
    let win_title = if title.trim().is_empty() {
        "MyServer App".to_string()
    } else {
        title.trim().to_string()
    };

    let _ = call_core_api(
        "open_app_window".to_string(),
        serde_json::json!({
            "url": clean_url,
            "title": win_title
        }),
    ).await;
    Ok(())
}

#[tauri::command]
async fn open_in_browser(url: String) -> Result<(), String> {
    let clean_url = url.trim().to_string();
    if clean_url.is_empty() {
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let _ = std::process::Command::new("cmd")
            .raw_arg(format!("/c start \"\" \"{}\"", clean_url))
            .creation_flags(CREATE_NO_WINDOW)
            .spawn();
    }
    Ok(())
}

#[tauri::command]
async fn call_core_api(endpoint: String, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;

    let mut stream = TcpStream::connect("127.0.0.1:48123")
        .map_err(|e| format!("Gagal terhubung ke Core Service (127.0.0.1:48123): {}", e))?;
    stream.set_read_timeout(Some(Duration::from_millis(60000))).ok();
    stream.set_write_timeout(Some(Duration::from_millis(15000))).ok();

    let body = serde_json::to_string(&payload).unwrap_or_else(|_| "{}".to_string());
    let req = format!(
        "POST /api/{} HTTP/1.1\r\nHost: 127.0.0.1:48123\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        endpoint,
        body.len(),
        body
    );

    stream.write_all(req.as_bytes()).map_err(|e| e.to_string())?;

    let mut response_bytes = Vec::new();
    stream.read_to_end(&mut response_bytes).map_err(|e| e.to_string())?;

    let response_str = String::from_utf8_lossy(&response_bytes);
    if let Some(pos) = response_str.find("\r\n\r\n") {
        let json_str = &response_str[pos + 4..];
        let json_val: serde_json::Value = serde_json::from_str(json_str)
            .map_err(|e| format!("Gagal mem-parsing JSON: {} (Konten: {})", e, json_str))?;
        Ok(json_val)
    } else {
        Err("Format respons HTTP dari Core Service tidak valid".to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(target_os = "windows")]
    {
        unsafe {
            std::env::set_var(
                "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
                "--disable-background-timer-throttling --disable-renderer-backgrounding",
            );
        }
    }
    trace_log("app_lib::run entered");
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            trace_log("single_instance callback triggered!");
            if let Some(win) = app.get_webview_window("main").or_else(|| app.webview_windows().into_values().next()) {
                let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                position_above_taskbar(win.clone());
                let _ = win.unminimize();
                let _ = win.show();
                let _ = win.set_focus();
            } else {
                trace_log("single_instance callback: window 'main' NOT found!");
            }
        }))
        .setup(|app| {
            trace_log("setup hook entered");
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Spawn companion Python core backend if present
            let current_exe = std::env::current_exe().unwrap_or_default();
            let exe_dir = current_exe.parent().unwrap_or_else(|| std::path::Path::new("."));
            let core_candidates = [
                exe_dir.join("myserver-core.exe"),
                exe_dir.join("bin").join("myserver-core.exe"),
                exe_dir.join("_internal").join("myserver-core.exe"),
            ];
            for candidate in &core_candidates {
                if candidate.exists() {
                    let mut cmd = std::process::Command::new(candidate);
                    cmd.arg("--parent-pid").arg(std::process::id().to_string());
                    cmd.current_dir(exe_dir);
                    #[cfg(windows)]
                    {
                        use std::os::windows::process::CommandExt;
                        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
                    }
                    match cmd.spawn() {
                        Ok(child) => trace_log(&format!("Spawned core child PID: {}", child.id())),
                        Err(e) => trace_log(&format!("Core spawn error: {}", e)),
                    }
                    break;
                }
            }

            // Create Tray Menu
            let quit_i = MenuItem::with_id(app, "quit", "Keluar MyServer", true, Option::<&str>::None)?;
            let show_i = MenuItem::with_id(app, "show", "Buka Companion", true, Option::<&str>::None)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

            // Create Tray Icon with compile-time embedded 32x32 RGBA icon
            static TRAY_RGBA_32: &[u8] = include_bytes!("../icons/32x32.rgba");
            let tray_icon = tauri::image::Image::new(TRAY_RGBA_32, 32, 32);

            let tray_builder = TrayIconBuilder::with_id("main-tray")
                .tooltip(concat!("MyServer v", env!("CARGO_PKG_VERSION"), " Beta"))
                .icon(tray_icon)
                .menu(&menu)
                .show_menu_on_left_click(false);

            let _tray = tray_builder
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        trace_log("tray menu: quit");
                        ALLOW_EXIT.store(true, Ordering::SeqCst);
                        app.exit(0);
                    }
                    "show" => {
                        trace_log("tray menu: show");
                        if let Some(win) = app.get_webview_window("main").or_else(|| app.webview_windows().into_values().next()) {
                            let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                            position_above_taskbar(win.clone());
                            let _ = win.show();
                            let _ = win.unminimize();
                            let _ = win.set_focus();
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        trace_log("tray icon left click");
                        let app = tray.app_handle();
                        if let Some(win) = app.get_webview_window("main").or_else(|| app.webview_windows().into_values().next()) {
                            if win.is_visible().unwrap_or(false) && !win.is_minimized().unwrap_or(false) {
                                let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                                let _ = win.hide();
                            } else {
                                let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                                position_above_taskbar(win.clone());
                                let _ = win.unminimize();
                                let _ = win.show();
                                let _ = win.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            let main_win = app.get_webview_window("main");
            trace_log(&format!("setup: get_webview_window('main') is_some: {}", main_win.is_some()));

            let should_auto_open = {
                let mut config_path = exe_dir.join("config.json");
                if !config_path.exists() {
                    if let Ok(cwd) = std::env::current_dir() {
                        let cwd_config = cwd.join("config.json");
                        if cwd_config.exists() {
                            config_path = cwd_config;
                        }
                    }
                }
                if let Ok(content) = std::fs::read_to_string(&config_path) {
                    if let Ok(val) = serde_json::from_str::<serde_json::Value>(&content) {
                        val.get("auto_open_mini_tray")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true)
                    } else {
                        true
                    }
                } else {
                    true
                }
            };
            trace_log(&format!("setup: should_auto_open: {}", should_auto_open));

            if should_auto_open {
                if let Some(win) = main_win.or_else(|| app.webview_windows().into_values().next()) {
                    position_above_taskbar(win.clone());
                    let win_clone = win.clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(std::time::Duration::from_millis(200));
                        position_above_taskbar(win_clone);
                    });
                }
            }

            trace_log("setup hook finished successfully");
            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                trace_log("window CloseRequested -> hiding");
                api.prevent_close();
                if let Some(wv) = window.app_handle().get_webview_window(window.label()) {
                    let _ = wv.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                }
                let _ = window.hide();
            }
            _ => {}
        })
        .invoke_handler(tauri::generate_handler![
            log_frontend,
            minimize_window,
            hide_window,
            show_window,
            exit_app,
            start_drag,
            position_above_taskbar,
            open_app_window,
            open_in_browser,
            call_core_api
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    trace_log("builder.build() returned, calling app.run()");
    app.run(|_app_handle, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            trace_log("RunEvent::ExitRequested");
            if !ALLOW_EXIT.load(Ordering::SeqCst) {
                api.prevent_exit();
            }
        }
    });
    trace_log("app.run() finished");
}
