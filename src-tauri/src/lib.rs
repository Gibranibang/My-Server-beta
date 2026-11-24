mod wizard_state;

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, LogicalPosition, LogicalSize, Manager, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder,
};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    OnceLock,
};

static ALLOW_EXIT: AtomicBool = AtomicBool::new(false);
static CORE_AUTH_TOKEN: OnceLock<String> = OnceLock::new();
static CORE_SPAWNED_BY_TAURI: AtomicBool = AtomicBool::new(false);

fn bytes_to_hex(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 0x0f) as usize] as char);
    }
    out
}

fn fallback_entropy_bytes(buf: &mut [u8]) {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let pid = std::process::id() as u128;
    let addr = (&CORE_AUTH_TOKEN as *const OnceLock<String>) as usize as u128;
    let mut state = nanos ^ pid.rotate_left(37) ^ addr.rotate_left(73) ^ 0x9e3779b97f4a7c15_u128;
    for chunk in buf.chunks_mut(8) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state = state.wrapping_mul(0x5851f42d4c957f2d_u128).wrapping_add(1);
        let bytes = (state as u64).to_le_bytes();
        chunk.copy_from_slice(&bytes[..chunk.len()]);
    }
}

#[cfg(target_os = "windows")]
fn generate_csprng_hex_token() -> String {
    #[allow(non_snake_case)]
    #[link(name = "bcrypt")]
    unsafe extern "system" {
        fn BCryptGenRandom(
            hAlgorithm: *mut core::ffi::c_void,
            pbBuffer: *mut u8,
            cbBuffer: u32,
            dwFlags: u32,
        ) -> i32;
    }
    const BCRYPT_USE_SYSTEM_PREFERRED_RNG: u32 = 0x00000002;
    let mut buf = [0u8; 32];
    let status = unsafe {
        BCryptGenRandom(
            core::ptr::null_mut(),
            buf.as_mut_ptr(),
            buf.len() as u32,
            BCRYPT_USE_SYSTEM_PREFERRED_RNG,
        )
    };
    if status < 0 {
        trace_log(&format!("BCryptGenRandom fallback status={}", status));
        fallback_entropy_bytes(&mut buf);
    }
    bytes_to_hex(&buf)
}

#[cfg(not(target_os = "windows"))]
fn generate_csprng_hex_token() -> String {
    use std::io::Read;
    let mut buf = [0u8; 32];
    if let Ok(mut f) = std::fs::File::open("/dev/urandom") {
        if f.read_exact(&mut buf).is_ok() {
            return bytes_to_hex(&buf);
        }
    }
    trace_log("/dev/urandom read failed; using fallback entropy");
    fallback_entropy_bytes(&mut buf);
    bytes_to_hex(&buf)
}

fn get_or_init_core_token() -> &'static str {
    CORE_AUTH_TOKEN.get_or_init(generate_csprng_hex_token).as_str()
}

fn core_token_file_path() -> Option<std::path::PathBuf> {
    #[cfg(target_os = "windows")]
    {
        std::env::var("LOCALAPPDATA")
            .ok()
            .map(|p| std::path::PathBuf::from(p).join("MyServer").join("core.token"))
    }
    #[cfg(not(target_os = "windows"))]
    {
        if let Ok(local_appdata) = std::env::var("LOCALAPPDATA") {
            return Some(
                std::path::PathBuf::from(local_appdata)
                    .join("MyServer")
                    .join("core.token"),
            );
        }
        std::env::var("HOME").ok().map(|h| {
            std::path::PathBuf::from(h)
                .join(".local")
                .join("share")
                .join("MyServer")
                .join("core.token")
        })
    }
}

fn resolve_core_api_token() -> String {
    if CORE_SPAWNED_BY_TAURI.load(Ordering::SeqCst) {
        return get_or_init_core_token().to_string();
    }
    if let Some(path) = core_token_file_path() {
        if let Ok(contents) = std::fs::read_to_string(path) {
            let trimmed = contents.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }
    get_or_init_core_token().to_string()
}

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

fn cleanup_stale_webview_locks() {
    if let Ok(local_appdata) = std::env::var("LOCALAPPDATA") {
        let webview_dir = std::path::PathBuf::from(local_appdata)
            .join("com.algithaproject.myserver.companion.beta")
            .join("EBWebView");
        if webview_dir.exists() {
            let _ = remove_lock_files_recursive(&webview_dir);
        }
    }
}

fn remove_lock_files_recursive(dir: &std::path::Path) -> std::io::Result<()> {
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                let _ = remove_lock_files_recursive(&path);
            } else if path.file_name().map_or(false, |name| {
                let s = name.to_string_lossy().to_lowercase();
                s == "lock" || s == "lockfile" || s.ends_with(".lock")
            }) {
                let _ = std::fs::remove_file(&path);
            }
        }
    }
    Ok(())
}

fn non_empty_str(val: Option<&serde_json::Value>) -> bool {
    val.and_then(|v| v.as_str())
        .map(|s| !s.trim().is_empty())
        .unwrap_or(false)
}

fn resolve_config_path() -> Option<std::path::PathBuf> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let exe_cfg = exe_dir.join("config.json");
            if exe_cfg.exists() {
                return Some(exe_cfg);
            }
            if let Some(dir_name) = exe_dir.file_name().and_then(|n| n.to_str()) {
                let lower = dir_name.to_ascii_lowercase();
                if lower == "bin" || lower == "sandbox" {
                    if let Some(parent_cfg) = exe_dir.parent().map(|p| p.join("config.json")) {
                        if parent_cfg.exists() {
                            return Some(parent_cfg);
                        }
                    }
                }
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        let cwd_cfg = cwd.join("config.json");
        if cwd_cfg.exists() {
            return Some(cwd_cfg);
        }
    }
    None
}

fn load_config_json() -> Option<serde_json::Value> {
    let config_path = resolve_config_path()?;
    let content = std::fs::read_to_string(&config_path).ok()?;
    serde_json::from_str::<serde_json::Value>(&content).ok()
}

fn extract_wizard_startup_flags(cfg: &serde_json::Value) -> (Option<bool>, bool) {
    let explicit_flag = cfg.get("first_run_setup").and_then(|v| v.as_bool());
    let easytier_remote_id = non_empty_str(cfg.get("easytier").and_then(|e| e.get("remote_id")));

    let mut has_valid_server_and_creds = false;
    if let Some(servers) = cfg.get("servers").and_then(|s| s.as_array()) {
        for srv in servers {
            let srv_id = srv
                .get("id")
                .and_then(|v| v.as_str())
                .map(str::trim)
                .unwrap_or("");
            if srv_id.is_empty() {
                continue;
            }

            let creds_ok = srv
                .get("credentials")
                .and_then(|c| c.as_object())
                .map(|creds| {
                    let flat_ok =
                        non_empty_str(creds.get("username")) && non_empty_str(creds.get("password"));
                    let profile_ok = creds.values().any(|entry| {
                        non_empty_str(entry.get("username")) && non_empty_str(entry.get("password"))
                    });
                    flat_ok || profile_ok
                })
                .unwrap_or(false);

            let has_conn_url = srv
                .get("connections")
                .and_then(|c| c.as_array())
                .map(|conns| conns.iter().any(|c| non_empty_str(c.get("url"))))
                .unwrap_or(false);

            let has_target = srv_id != "srv_default"
                || has_conn_url
                || easytier_remote_id
                || [
                    "url",
                    "zerotier_network_id",
                    "remote_id",
                    "zerotierNetworkId",
                    "remoteId",
                ]
                .iter()
                .any(|key| non_empty_str(srv.get(*key)));

            if creds_ok && has_target {
                has_valid_server_and_creds = true;
                break;
            }
        }
    }

    (explicit_flag, has_valid_server_and_creds)
}

fn set_window_taskbar_icon(window: &WebviewWindow) {
    // Set explicit window icon (updates Windows Taskbar icon immediately via WM_SETICON)
    static TASKBAR_RGBA_128: &[u8] = include_bytes!("../icons/128x128.rgba");
    let taskbar_icon = tauri::image::Image::new(TASKBAR_RGBA_128, 128, 128);
    let _ = window.set_icon(taskbar_icon);
}

fn focus_existing_wizard_window(window: &WebviewWindow) {
    let _ = window.set_always_on_top(false);
    let _ = window.center();
    set_window_taskbar_icon(window);
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
}

fn show_centered_wizard(window: &WebviewWindow, width: Option<f64>, height: Option<f64>) {
    let (w, h) = wizard_state::clamp_wizard_dimensions(width, height);
    let _ = window.set_always_on_top(false);
    let _ = window.set_size(tauri::Size::Logical(LogicalSize::new(w, h)));
    let _ = window.center();
    set_window_taskbar_icon(window);
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
}

fn apply_position_above_taskbar_internal(window: &WebviewWindow, show_window: bool) {
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
        let scale = mon.scale_factor();
        let screen_pos = mon.position().to_logical::<f64>(scale);
        let screen_size = mon.size().to_logical::<f64>(scale);
        let target_x = screen_pos.x + screen_size.width - win_w - margin_x;
        let target_y = screen_pos.y + screen_size.height - win_h - margin_y;

        trace_log(&format!("set_position ({}, {})", target_x, target_y));
        let _ = window.set_position(tauri::Position::Logical(LogicalPosition::new(target_x, target_y)));
    }

    let _ = window.set_size(tauri::Size::Logical(LogicalSize::new(win_w, win_h)));
    set_window_taskbar_icon(window);

    if show_window {
        trace_log("calling window.show, unminimize, set_focus");
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn apply_position_above_taskbar(window: &WebviewWindow) {
    apply_position_above_taskbar_internal(window, true);
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
fn hide_window(window: WebviewWindow, state: tauri::State<'_, wizard_state::WizardWindowState>) {
    trace_log("cmd: hide_window");
    if !wizard_state::should_suppress_home_reset(state.is_active()) {
        let _ = window.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
    }
    let _ = window.hide();
}

#[tauri::command]
fn show_window(window: WebviewWindow, state: tauri::State<'_, wizard_state::WizardWindowState>) {
    trace_log("cmd: show_window");
    if state.is_active() {
        focus_existing_wizard_window(&window);
    } else {
        let _ = window.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
        let _ = window.show();
        let _ = window.set_focus();
    }
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
fn position_above_taskbar(
    window: WebviewWindow,
    state: tauri::State<'_, wizard_state::WizardWindowState>,
) {
    if state.is_active() {
        trace_log("position_above_taskbar suppressed (wizard active)");
        return;
    }
    apply_position_above_taskbar(&window);
}

#[tauri::command]
fn set_wizard_mode(
    window: WebviewWindow,
    state: tauri::State<'_, wizard_state::WizardWindowState>,
    active: bool,
    width: Option<f64>,
    height: Option<f64>,
) -> Result<(), String> {
    trace_log(&format!("cmd: set_wizard_mode active={}", active));
    if active {
        state.set_active(true);
        show_centered_wizard(&window, width, height);
    } else {
        let was_visible = window.is_visible().unwrap_or(false);
        state.set_active(false);
        let _ = window.set_always_on_top(true);
        let _ = window.set_size(tauri::Size::Logical(LogicalSize::new(370.0, 412.0)));
        apply_position_above_taskbar_internal(&window, was_visible);
    }
    Ok(())
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

    let res = call_core_api(
        "open_app_window".to_string(),
        serde_json::json!({
            "url": clean_url,
            "title": win_title
        }),
    )
    .await?;

    if res.get("success").and_then(|v| v.as_bool()) == Some(false)
        || res.get("status").and_then(|v| v.as_str()) == Some("error")
    {
        return Err(res
            .get("message")
            .or_else(|| res.get("error"))
            .and_then(|v| v.as_str())
            .unwrap_or("Gagal membuka jendela aplikasi")
            .to_string());
    }
    Ok(())
}

pub fn validate_external_browser_url(raw: &str) -> Result<String, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("URL tidak boleh kosong".to_string());
    }
    if trimmed
        .chars()
        .any(|c| c.is_control() || c.is_whitespace() || matches!(c, '"' | '\'' | '`' | '<' | '>' | '\\'))
    {
        return Err("URL mengandung karakter tidak diizinkan".to_string());
    }
    let lower = trimmed.to_ascii_lowercase();
    let rest = if lower.starts_with("https://") {
        &trimmed[8..]
    } else if lower.starts_with("http://") {
        &trimmed[7..]
    } else {
        return Err("Hanya URL http:// atau https:// yang diizinkan".to_string());
    };
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    if authority.is_empty() || authority.starts_with('@') {
        return Err("Host URL tidak valid".to_string());
    }
    let host_port = if let Some((_, after_at)) = authority.rsplit_once('@') {
        if after_at.is_empty() {
            return Err("Host URL tidak valid".to_string());
        }
        after_at
    } else {
        authority
    };
    let host = if host_port.starts_with('[') {
        match host_port.find(']') {
            Some(end) if end > 1 => {
                let after_bracket = &host_port[end + 1..];
                if !after_bracket.is_empty() && !after_bracket.starts_with(':') {
                    return Err("Host URL tidak valid".to_string());
                }
                &host_port[1..end]
            }
            _ => return Err("Host URL tidak valid".to_string()),
        }
    } else {
        host_port.split(':').next().unwrap_or("")
    };
    if host.is_empty() || host.starts_with('.') || host.ends_with('.') || host.contains("..") {
        return Err("Host URL tidak valid".to_string());
    }
    Ok(trimmed.to_string())
}

#[cfg(target_os = "windows")]
fn launch_url_windows(validated_url: &str) -> Result<(), String> {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    #[allow(non_snake_case)]
    #[link(name = "shell32")]
    unsafe extern "system" {
        fn ShellExecuteW(
            hwnd: *mut core::ffi::c_void,
            lpOperation: *const u16,
            lpFile: *const u16,
            lpParameters: *const u16,
            lpDirectory: *const u16,
            nShowCmd: i32,
        ) -> isize;
    }
    let op: Vec<u16> = OsStr::new("open").encode_wide().chain(Some(0)).collect();
    let file: Vec<u16> = OsStr::new(validated_url).encode_wide().chain(Some(0)).collect();
    let rc = unsafe {
        ShellExecuteW(
            core::ptr::null_mut(),
            op.as_ptr(),
            file.as_ptr(),
            core::ptr::null(),
            core::ptr::null(),
            1, // SW_SHOWNORMAL
        )
    };
    if rc <= 32 {
        return Err(format!("ShellExecuteW gagal membuka URL (kode {})", rc));
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn launch_url_non_windows(validated_url: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    let launcher = "open";
    #[cfg(not(target_os = "macos"))]
    let launcher = "xdg-open";

    std::process::Command::new(launcher)
        .arg(validated_url)
        .spawn()
        .map_err(|e| format!("Gagal membuka URL dengan {}: {}", launcher, e))?;
    Ok(())
}

#[tauri::command]
async fn open_in_browser(url: String) -> Result<(), String> {
    let validated = validate_external_browser_url(&url)?;
    #[cfg(target_os = "windows")]
    {
        launch_url_windows(&validated)?;
    }
    #[cfg(not(target_os = "windows"))]
    {
        launch_url_non_windows(&validated)?;
    }
    Ok(())
}

#[tauri::command]
async fn call_core_api(endpoint: String, payload: serde_json::Value) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<serde_json::Value, String> {
        use std::io::{Read, Write};
        use std::net::{SocketAddr, TcpStream};
        use std::time::Duration;

        let addr = SocketAddr::from(([127, 0, 0, 1], 48123));
        let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(2000))
            .map_err(|e| format!("Gagal terhubung ke Core Service (127.0.0.1:48123): {}", e))?;
        let ep = endpoint
            .split('?')
            .next()
            .unwrap_or(&endpoint)
            .trim_start_matches('/');
        let read_timeout_ms = if ep.starts_with("server/backend_action")
            || ep.starts_with("server_backend_action")
        {
            420000
        } else if matches!(
            ep,
            "choose_log_folder"
                | "choose_folder"
                | "save_log_as"
                | "execute_backup_dialog"
                | "execute_restore_dialog"
                | "dialog_configure_local_syncthing"
                | "dialog_configure_server_syncthing"
                | "add_server"
                | "edit_server"
                | "delete_server"
                | "add_route"
                | "edit_route"
                | "delete_route"
                | "add_profile"
                | "edit_profile"
                | "delete_profile"
                | "config_credentials"
        ) {
            300000
        } else if ep == "download_and_install_update" || ep == "install_update_from_zip" {
            210000
        } else if matches!(
            ep,
            "instabox/smart_reset"
                | "instabox/sync"
                | "vms/migrate"
                | "easytier/start"
                | "wizard/verify_zimaos"
        ) {
            180000
        } else {
            60000
        };
        stream.set_read_timeout(Some(Duration::from_millis(read_timeout_ms))).ok();
        stream.set_write_timeout(Some(Duration::from_millis(15000))).ok();

        let body = serde_json::to_string(&payload).unwrap_or_else(|_| "{}".to_string());
        let core_token = resolve_core_api_token();
        let req = format!(
            "POST /api/{} HTTP/1.1\r\nHost: 127.0.0.1:48123\r\nContent-Type: application/json\r\nX-MyServer-Core-Token: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            endpoint,
            core_token,
            body.len(),
            body
        );

        stream.write_all(req.as_bytes()).map_err(|e| e.to_string())?;

        let mut response_bytes = Vec::new();
        stream.read_to_end(&mut response_bytes).map_err(|e| e.to_string())?;

        let response_str = String::from_utf8_lossy(&response_bytes);
        if let Some(pos) = response_str.find("\r\n\r\n") {
            let headers_str = &response_str[..pos];
            let json_str = &response_str[pos + 4..];
            let status_code = headers_str
                .lines()
                .next()
                .and_then(|l| l.split_whitespace().nth(1))
                .and_then(|c| c.parse::<u16>().ok())
                .unwrap_or(200);

            if status_code >= 400 {
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(json_str) {
                    if json_val.is_object() {
                        return Ok(json_val);
                    }
                }
                return Err(format!("HTTP {}: {}", status_code, json_str.trim()));
            }

            let json_val: serde_json::Value = serde_json::from_str(json_str)
                .map_err(|e| format!("Gagal mem-parsing JSON: {} (Konten: {})", e, json_str))?;
            Ok(json_val)
        } else {
            Err("Format respons HTTP dari Core Service tidak valid".to_string())
        }
    })
    .await
    .map_err(|e| format!("Core API task gagal dijalankan: {}", e))?
}

fn restore_or_present_window(app: &AppHandle, win: &WebviewWindow) {
    let wizard_active = app.state::<wizard_state::WizardWindowState>().is_active();
    if wizard_active {
        focus_existing_wizard_window(win);
    } else {
        let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
        apply_position_above_taskbar(win);
    }
}

#[derive(Default)]
pub struct ShareWindowState(std::sync::Mutex<Option<serde_json::Value>>);

#[derive(Debug, Clone, PartialEq, Eq)]
enum ShareCliAction {
    Share(String),
    QuickShare(String),
}

fn sanitize_cli_share_path(raw: &str) -> Option<String> {
    let mut s = raw.trim().to_string();
    if s.is_empty() {
        return None;
    }
    while s.len() >= 2 && s.starts_with('"') && s.ends_with('"') {
        s = s[1..s.len() - 1].trim().to_string();
    }
    let bytes = s.as_bytes();
    let is_drive_prefixed = bytes.len() >= 3 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':';
    let is_unc_prefixed = s.starts_with("\\\\") && s.len() >= 5;
    if (is_drive_prefixed || is_unc_prefixed) && s.ends_with("\\\"") {
        s.pop();
    } else if (is_drive_prefixed || is_unc_prefixed)
        && s.ends_with('"')
        && !s[..s.len() - 1].contains('"')
    {
        s.pop();
        s.push('\\');
    }
    let trimmed = s.trim().to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

fn parse_share_cli_action(args: &[String]) -> Option<ShareCliAction> {
    let mut i = 0;
    while i < args.len() {
        let arg = args[i].trim();
        if let Some(val) = arg.strip_prefix("--quick-share=") {
            return sanitize_cli_share_path(val).map(ShareCliAction::QuickShare);
        }
        if arg == "--quick-share" {
            let next = args.get(i + 1).map(|s| s.as_str()).unwrap_or("");
            return sanitize_cli_share_path(next).map(ShareCliAction::QuickShare);
        }
        if let Some(val) = arg.strip_prefix("--share=") {
            return sanitize_cli_share_path(val).map(ShareCliAction::Share);
        }
        if arg == "--share" {
            let next = args.get(i + 1).map(|s| s.as_str()).unwrap_or("");
            return sanitize_cli_share_path(next).map(ShareCliAction::Share);
        }
        i += 1;
    }
    None
}

fn open_or_focus_share_window(
    app: &AppHandle,
    target_json: serde_json::Value,
) -> Result<(), String> {
    {
        let state = app.state::<ShareWindowState>();
        let mut guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
        *guard = Some(target_json.clone());
    }

    if let Some(wv) = app.get_webview_window("share-window") {
        let json_str = serde_json::to_string(&target_json)
            .map_err(|e| format!("Gagal serialisasi target share: {}", e))?;
        let _ = wv.eval(&format!(
            "window.dispatchEvent(new CustomEvent('myserver:share-target', {{ detail: {} }}));",
            json_str
        ));
        let _ = wv.unminimize();
        let _ = wv.show();
        let _ = wv.set_focus();
        return Ok(());
    }

    let win = match WebviewWindowBuilder::new(
        app,
        "share-window",
        WebviewUrl::App("index.html?window=share".into()),
    )
    .title("Share via MyServer")
    .inner_size(400.0, 560.0)
    .resizable(false)
    .decorations(false)
    .transparent(true)
    .shadow(false)
    .always_on_top(false)
    .center()
    .build()
    {
        Ok(w) => w,
        Err(e) => {
            let state = app.state::<ShareWindowState>();
            let mut guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
            *guard = None;
            return Err(format!("Gagal membuka share-window: {}", e));
        }
    };

    set_window_taskbar_icon(&win);
    let _ = win.show();
    let _ = win.set_focus();
    Ok(())
}

async fn wait_for_core_service_ready(max_wait_ms: u64) -> bool {
    tauri::async_runtime::spawn_blocking(move || -> bool {
        use std::io::{Read, Write};
        use std::net::{SocketAddr, TcpStream};
        use std::time::{Duration, Instant};

        let addr = SocketAddr::from(([127, 0, 0, 1], 48123));
        let deadline = Instant::now() + Duration::from_millis(max_wait_ms);
        loop {
            if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(300)) {
                let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
                let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
                let req = "GET /api/ping HTTP/1.1\r\nHost: 127.0.0.1:48123\r\nConnection: close\r\n\r\n";
                if stream.write_all(req.as_bytes()).is_ok() {
                    let mut buf = [0u8; 256];
                    if let Ok(n) = stream.read(&mut buf) {
                        let head = String::from_utf8_lossy(&buf[..n]);
                        if head.starts_with("HTTP/1.1 200") || head.starts_with("HTTP/1.0 200") {
                            return true;
                        }
                    }
                }
            }
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    })
    .await
    .unwrap_or(false)
}

async fn handle_share_cli_action(
    app: AppHandle,
    action: ShareCliAction,
    wait_for_core: bool,
) {
    if wait_for_core {
        let ready = wait_for_core_service_ready(15000).await;
        if !ready {
            trace_log("handle_share_cli_action: Core Service not ready within 15000ms");
            return;
        }
    }

    match action {
        ShareCliAction::Share(path) => {
            trace_log(&format!("handle_share_cli_action: Share path={}", path));
            match call_core_api(
                "shares/resolve".to_string(),
                serde_json::json!({ "path": path, "notify_on_error": true }),
            )
            .await
            {
                Ok(res) => {
                    let ok = res.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
                    if ok {
                        if let Some(target) = res.get("target").filter(|v| v.is_object()) {
                            if let Err(e) = open_or_focus_share_window(&app, target.clone()) {
                                trace_log(&format!("open_or_focus_share_window error: {}", e));
                            }
                        } else {
                            trace_log("shares/resolve ok=true but target object missing");
                        }
                    } else {
                        let code = res.get("code").and_then(|v| v.as_str()).unwrap_or("UNKNOWN");
                        trace_log(&format!("shares/resolve rejected: code={}", code));
                    }
                }
                Err(e) => {
                    trace_log(&format!("shares/resolve call_core_api error: {}", e));
                }
            }
        }
        ShareCliAction::QuickShare(path) => {
            trace_log(&format!("handle_share_cli_action: QuickShare path={}", path));
            if let Err(e) = call_core_api(
                "shares/quick".to_string(),
                serde_json::json!({ "path": path }),
            )
            .await
            {
                trace_log(&format!("shares/quick call_core_api error: {}", e));
            }
        }
    }
}

#[tauri::command]
async fn open_share_window(app: AppHandle, target: serde_json::Value) -> Result<(), String> {
    open_or_focus_share_window(&app, target)
}

#[tauri::command]
fn close_share_window(app: AppHandle) -> Result<(), String> {
    {
        let state = app.state::<ShareWindowState>();
        let mut guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
        *guard = None;
    }
    if let Some(wv) = app.get_webview_window("share-window") {
        wv.close()
            .map_err(|e| format!("Gagal menutup share-window: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
fn get_share_window_target(app: AppHandle) -> Option<serde_json::Value> {
    let state = app.state::<ShareWindowState>();
    let guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
    guard.clone()
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
        .manage(wizard_state::WizardWindowState::default())
        .manage(ShareWindowState::default())
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            trace_log("single_instance callback triggered!");
            if let Some(action) = parse_share_cli_action(&args) {
                let app_handle = app.clone();
                tauri::async_runtime::spawn(handle_share_cli_action(app_handle, action, true));
                return;
            }
            if let Some(win) = app.get_webview_window("main").or_else(|| app.webview_windows().into_values().next()) {
                restore_or_present_window(app, &win);
            } else {
                trace_log("single_instance callback: window 'main' NOT found!");
            }
        }))
        .setup(|app| {
            trace_log("setup hook entered");
            cleanup_stale_webview_locks();
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
                    cmd.env("MYSERVER_CORE_TOKEN", get_or_init_core_token());
                    #[cfg(windows)]
                    {
                        use std::os::windows::process::CommandExt;
                        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
                    }
                    match cmd.spawn() {
                        Ok(child) => {
                            CORE_SPAWNED_BY_TAURI.store(true, Ordering::SeqCst);
                            trace_log(&format!("Spawned core child PID: {}", child.id()));
                        }
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
                            restore_or_present_window(app, &win);
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
                        let wizard_active = app.state::<wizard_state::WizardWindowState>().is_active();
                        if let Some(win) = app.get_webview_window("main").or_else(|| app.webview_windows().into_values().next()) {
                            if win.is_visible().unwrap_or(false) && !win.is_minimized().unwrap_or(false) {
                                if !wizard_state::should_suppress_home_reset(wizard_active) {
                                    let _ = win.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                                }
                                let _ = win.hide();
                            } else {
                                restore_or_present_window(app, &win);
                            }
                        }
                    }
                })
                .build(app)?;

            let main_win = app.get_webview_window("main");
            trace_log(&format!("setup: get_webview_window('main') is_some: {}", main_win.is_some()));

            let cfg_opt = load_config_json();
            let (explicit_flag, has_valid_server_and_creds) = cfg_opt
                .as_ref()
                .map(extract_wizard_startup_flags)
                .unwrap_or((None, false));
            let open_wizard = wizard_state::should_open_wizard_on_startup(
                explicit_flag,
                has_valid_server_and_creds,
            );
            trace_log(&format!(
                "setup: open_wizard={}, explicit_flag={:?}, has_valid_server_and_creds={}",
                open_wizard, explicit_flag, has_valid_server_and_creds
            ));

            let should_auto_open = cfg_opt
                .as_ref()
                .and_then(|val| val.get("auto_open_mini_tray"))
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            trace_log(&format!("setup: should_auto_open: {}", should_auto_open));

            let raw_cli_args: Vec<String> = std::env::args().collect();
            let cli_share_action = parse_share_cli_action(&raw_cli_args);

            if open_wizard {
                app.state::<wizard_state::WizardWindowState>().set_active(true);
                if let Some(win) = main_win.or_else(|| app.webview_windows().into_values().next()) {
                    show_centered_wizard(&win, Some(460.0), Some(560.0));
                }
            } else if should_auto_open && cli_share_action.is_none() {
                if let Some(win) = main_win.or_else(|| app.webview_windows().into_values().next()) {
                    apply_position_above_taskbar(&win);
                    let win_clone = win.clone();
                    let app_handle = app.handle().clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(std::time::Duration::from_millis(200));
                        if !app_handle.state::<wizard_state::WizardWindowState>().is_active() {
                            apply_position_above_taskbar(&win_clone);
                        }
                    });
                }
            }

            if let Some(action) = cli_share_action {
                if !open_wizard {
                    let app_handle = app.handle().clone();
                    tauri::async_runtime::spawn(handle_share_cli_action(app_handle, action, true));
                }
            }

            trace_log("setup hook finished successfully");
            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                if window.label() == "share-window" {
                    trace_log("share-window CloseRequested -> closing share-window only");
                    let state = window.app_handle().state::<ShareWindowState>();
                    let mut guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
                    *guard = None;
                    return;
                }
                trace_log("window CloseRequested -> hiding");
                if !ALLOW_EXIT.load(Ordering::SeqCst) {
                    api.prevent_close();
                }
                let wizard_active = window
                    .app_handle()
                    .state::<wizard_state::WizardWindowState>()
                    .is_active();
                if !wizard_state::should_suppress_home_reset(wizard_active) {
                    if let Some(wv) = window.app_handle().get_webview_window(window.label()) {
                        let _ = wv.eval("window.dispatchEvent(new CustomEvent('myserver:reset-home'));");
                    }
                }
                let _ = window.hide();
            }
            tauri::WindowEvent::DragDrop(drop_event) => {
                if window.label() != "main" {
                    return;
                }
                let wizard_active = window
                    .app_handle()
                    .state::<wizard_state::WizardWindowState>()
                    .is_active();
                if wizard_active {
                    return;
                }
                if let Some(wv) = window.app_handle().get_webview_window("main") {
                    let payload = match drop_event {
                        tauri::DragDropEvent::Enter { paths, .. } => Some(serde_json::json!({
                            "type": "enter",
                            "count": paths.len(),
                        })),
                        tauri::DragDropEvent::Drop { paths, .. } => {
                            let strs: Vec<String> =
                                paths.iter().map(|p| p.to_string_lossy().to_string()).collect();
                            Some(serde_json::json!({
                                "type": "drop",
                                "paths": strs,
                            }))
                        }
                        tauri::DragDropEvent::Leave { .. } => Some(serde_json::json!({
                            "type": "leave",
                        })),
                        _ => None,
                    };
                    if let Some(val) = payload {
                        if let Ok(json_str) = serde_json::to_string(&val) {
                            let _ = wv.eval(&format!(
                                "window.dispatchEvent(new CustomEvent('myserver:drag-drop', {{ detail: {} }}));",
                                json_str
                            ));
                        }
                    }
                }
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
            set_wizard_mode,
            open_app_window,
            open_in_browser,
            call_core_api,
            open_share_window,
            close_share_window,
            get_share_window_target
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_external_browser_url_accepts_valid_http_and_https() {
        assert_eq!(
            validate_external_browser_url("https://nas.local:8080/share?a=1&b=2").unwrap(),
            "https://nas.local:8080/share?a=1&b=2"
        );
        assert_eq!(
            validate_external_browser_url("  http://192.0.2.10/ui  ").unwrap(),
            "http://192.0.2.10/ui"
        );
        assert_eq!(
            validate_external_browser_url("HTTPS://example.com/Path?x=1#frag").unwrap(),
            "HTTPS://example.com/Path?x=1#frag"
        );
    }

    #[test]
    fn validate_external_browser_url_rejects_dangerous_schemes_and_chars() {
        for bad in [
            "",
            "   ",
            "file:///C:/Windows/calc.exe",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ms-msdt:/id PCWDiagnostic",
            "\\\\server\\share",
            "https://evil.com\" & calc",
            "https://evil.com/'test'",
            "https://evil.com/`id`",
            "https://evil.com/<script>",
            "https://example.com/a\nb",
            "https://example.com/a\0b",
            "https:///path",
            "https://@evil.com/path",
            "https://user@/path",
            "https://.evil.com/path",
            "https://evil.com./path",
            "https://a..b.com/path",
        ] {
            assert!(
                validate_external_browser_url(bad).is_err(),
                "expected Err for {:?}",
                bad
            );
        }
    }

    #[test]
    fn generate_csprng_hex_token_returns_64_hex_chars() {
        let t1 = generate_csprng_hex_token();
        let t2 = generate_csprng_hex_token();
        assert_eq!(t1.len(), 64);
        assert_eq!(t2.len(), 64);
        assert!(t1.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
        assert!(t2.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
        assert_ne!(t1, t2);
    }

    #[test]
    fn parse_share_cli_action_parses_share_and_quick_share_forms() {
        let exe = "MyServer-Beta.exe".to_string();
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--share".into(), "Z:\\docs\\a.pdf".into()]),
            Some(ShareCliAction::Share("Z:\\docs\\a.pdf".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--share=Z:\\docs\\b.pdf".into()]),
            Some(ShareCliAction::Share("Z:\\docs\\b.pdf".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--quick-share".into(), "Y:\\media".into()]),
            Some(ShareCliAction::QuickShare("Y:\\media".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[exe, "--quick-share=Y:\\media\\clip.mp4".into()]),
            Some(ShareCliAction::QuickShare("Y:\\media\\clip.mp4".into()))
        );
    }

    #[test]
    fn parse_share_cli_action_sanitizes_quotes_spaces_and_drive_root_artifact() {
        let exe = "MyServer-Beta.exe".to_string();
        assert_eq!(
            parse_share_cli_action(&[
                exe.clone(),
                "--share".into(),
                "\"Z:\\Folder With Spaces\\file name.txt\"".into()
            ]),
            Some(ShareCliAction::Share(
                "Z:\\Folder With Spaces\\file name.txt".into()
            ))
        );
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--share".into(), "Z:\"".into()]),
            Some(ShareCliAction::Share("Z:\\".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--quick-share=Z:\"".into()]),
            Some(ShareCliAction::QuickShare("Z:\\".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--share".into(), "Z:\\Folder\"".into()]),
            Some(ShareCliAction::Share("Z:\\Folder\\".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[
                exe.clone(),
                "--quick-share".into(),
                "Z:\\Folder With Spaces\"".into()
            ]),
            Some(ShareCliAction::QuickShare("Z:\\Folder With Spaces\\".into()))
        );
        assert_eq!(
            parse_share_cli_action(&[
                exe,
                "--share".into(),
                "\\\\192.168.1.10\\Disk1\\Folder\"".into()
            ]),
            Some(ShareCliAction::Share(
                "\\\\192.168.1.10\\Disk1\\Folder\\".into()
            ))
        );
    }

    #[test]
    fn parse_share_cli_action_returns_none_for_missing_empty_or_unrelated_args() {
        let exe = "MyServer-Beta.exe".to_string();
        assert_eq!(parse_share_cli_action(&[]), None);
        assert_eq!(parse_share_cli_action(&[exe.clone()]), None);
        assert_eq!(parse_share_cli_action(&[exe.clone(), "--share".into()]), None);
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--share".into(), "   ".into()]),
            None
        );
        assert_eq!(parse_share_cli_action(&[exe.clone(), "--share=".into()]), None);
        assert_eq!(
            parse_share_cli_action(&[exe.clone(), "--quick-share".into(), "\"\"".into()]),
            None
        );
        assert_eq!(
            parse_share_cli_action(&[exe, "--minimized".into(), "--foo=bar".into()]),
            None
        );
    }
}
