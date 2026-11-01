// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

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
            } else if path.file_name().map_or(false, |name| name == "LOCK") {
                let _ = std::fs::remove_file(&path);
            }
        }
    }
    Ok(())
}

fn main() {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| std::path::PathBuf::from("."));

    let panic_log_path = exe_dir.join("panic.log");
    std::panic::set_hook(Box::new(move |info| {
        let payload = if let Some(s) = info.payload().downcast_ref::<&str>() {
            s.to_string()
        } else if let Some(s) = info.payload().downcast_ref::<String>() {
            s.clone()
        } else {
            format!("{:?}", info)
        };
        let msg = format!("Panic: {}\nLocation: {:?}", payload, info.location());
        let _ = std::fs::write(&panic_log_path, &msg);
    }));

    cleanup_stale_webview_locks();

    app_lib::run();
}
