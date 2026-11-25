use std::sync::atomic::{AtomicBool, Ordering};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ExplorerHotkeyAction {
    Copy,
    Paste,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExplorerHotkeyEvent {
    pub action: ExplorerHotkeyAction,
    pub fg_hwnd: isize,
    pub top_tab_hwnd: isize,
}

static HOOK_ENABLED: AtomicBool = AtomicBool::new(true);

pub fn set_explorer_hotkey_enabled(enabled: bool) {
    HOOK_ENABLED.store(enabled, Ordering::SeqCst);
}

pub fn is_explorer_hotkey_enabled() -> bool {
    HOOK_ENABLED.load(Ordering::SeqCst)
}

#[cfg(target_os = "windows")]
mod imp {
    use super::{ExplorerHotkeyAction, ExplorerHotkeyEvent, HOOK_ENABLED};
    use std::ffi::c_void;
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::sync::{mpsc, Mutex};

    const WH_KEYBOARD_LL: i32 = 13;
    const WM_KEYDOWN: usize = 0x0100;
    const WM_SYSKEYDOWN: usize = 0x0104;
    const WM_QUIT: u32 = 0x0012;

    const VK_SHIFT: i32 = 0x10;
    const VK_CONTROL: i32 = 0x11;
    const VK_MENU: i32 = 0x12;
    const VK_C: u32 = 0x43;
    const VK_V: u32 = 0x56;
    const VK_LWIN: i32 = 0x5B;
    const VK_RWIN: i32 = 0x5C;
    const VK_LCONTROL: i32 = 0xA2;
    const VK_RMENU: i32 = 0xA5;

    // "ShellTabWindowClass\0" in UTF-16LE (zero-allocation in hook callback)
    const SHELL_TAB_WINDOW_CLASS_UTF16: &[u16] = &[
        b'S' as u16, b'h' as u16, b'e' as u16, b'l' as u16, b'l' as u16, b'T' as u16,
        b'a' as u16, b'b' as u16, b'W' as u16, b'i' as u16, b'n' as u16, b'd' as u16,
        b'o' as u16, b'w' as u16, b'C' as u16, b'l' as u16, b'a' as u16, b's' as u16,
        b's' as u16, 0,
    ];

    #[repr(C)]
    struct Point {
        x: i32,
        y: i32,
    }

    #[repr(C)]
    struct Msg {
        hwnd: *mut c_void,
        message: u32,
        w_param: usize,
        l_param: isize,
        time: u32,
        pt: Point,
        l_private: u32,
    }

    type HookProc = unsafe extern "system" fn(i32, usize, isize) -> isize;

    #[allow(non_snake_case)]
    #[link(name = "user32")]
    unsafe extern "system" {
        fn SetWindowsHookExW(
            idHook: i32,
            lpfn: HookProc,
            hmod: *mut c_void,
            dwThreadId: u32,
        ) -> *mut c_void;
        fn UnhookWindowsHookEx(hhk: *mut c_void) -> i32;
        fn CallNextHookEx(
            hhk: *mut c_void,
            nCode: i32,
            wParam: usize,
            lParam: isize,
        ) -> isize;
        fn GetMessageW(
            lpMsg: *mut Msg,
            hWnd: *mut c_void,
            wMsgFilterMin: u32,
            wMsgFilterMax: u32,
        ) -> i32;
        fn TranslateMessage(lpMsg: *const Msg) -> i32;
        fn DispatchMessageW(lpMsg: *const Msg) -> isize;
        fn PostThreadMessageW(
            idThread: u32,
            Msg: u32,
            wParam: usize,
            lParam: isize,
        ) -> i32;
        fn GetAsyncKeyState(vKey: i32) -> i16;
        fn GetKeyState(nVirtKey: i32) -> i16;
        fn GetForegroundWindow() -> *mut c_void;
        fn GetClassNameW(
            hWnd: *mut c_void,
            lpClassName: *mut u16,
            nMaxCount: i32,
        ) -> i32;
        fn FindWindowExW(
            hWndParent: *mut c_void,
            hWndChildAfter: *mut c_void,
            lpszClass: *const u16,
            lpszWindow: *const u16,
        ) -> *mut c_void;
    }

    #[allow(non_snake_case)]
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetModuleHandleW(lpModuleName: *const u16) -> *mut c_void;
        fn GetCurrentThreadId() -> u32;
    }

    static HOOK_THREAD_ID: AtomicU32 = AtomicU32::new(0);
    static HOOK_SENDER: Mutex<Option<mpsc::SyncSender<ExplorerHotkeyEvent>>> = Mutex::new(None);

    fn is_explorer_class(hwnd: *mut c_void) -> bool {
        if hwnd.is_null() {
            return false;
        }
        let mut buf = [0u16; 64];
        let len = unsafe { GetClassNameW(hwnd, buf.as_mut_ptr(), buf.len() as i32) };
        if len <= 0 {
            return false;
        }
        let class_name = String::from_utf16_lossy(&buf[..len as usize]);
        class_name == "CabinetWClass" || class_name == "ExploreWClass"
    }

    unsafe extern "system" fn low_level_keyboard_proc(
        n_code: i32,
        w_param: usize,
        l_param: isize,
    ) -> isize {
        if n_code >= 0
            && HOOK_ENABLED.load(Ordering::Relaxed)
            && (w_param == WM_KEYDOWN || w_param == WM_SYSKEYDOWN)
            && l_param != 0
        {
            let vk_code = unsafe { *(l_param as *const u32) };
            let action = match vk_code {
                VK_C => Some(ExplorerHotkeyAction::Copy),
                VK_V => Some(ExplorerHotkeyAction::Paste),
                _ => None,
            };

            if let Some(action) = action {
                let ctrl_down = unsafe { GetAsyncKeyState(VK_CONTROL) } < 0;
                let alt_down = unsafe { GetAsyncKeyState(VK_MENU) } < 0;
                let shift_up = unsafe { GetAsyncKeyState(VK_SHIFT) } >= 0;
                let lwin_up = unsafe { GetAsyncKeyState(VK_LWIN) } >= 0;
                let rwin_up = unsafe { GetAsyncKeyState(VK_RWIN) } >= 0;
                let altgr_only = unsafe { GetKeyState(VK_RMENU) } < 0
                    && unsafe { GetKeyState(VK_LCONTROL) } >= 0;

                if ctrl_down && alt_down && shift_up && lwin_up && rwin_up && !altgr_only {
                    let fg = unsafe { GetForegroundWindow() };
                    if is_explorer_class(fg) {
                        let top_tab_hwnd = unsafe {
                            FindWindowExW(
                                fg,
                                core::ptr::null_mut(),
                                SHELL_TAB_WINDOW_CLASS_UTF16.as_ptr(),
                                core::ptr::null(),
                            )
                        };
                        if let Ok(guard) = HOOK_SENDER.try_lock() {
                            if let Some(tx) = guard.as_ref() {
                                let _ = tx.try_send(ExplorerHotkeyEvent {
                                    action,
                                    fg_hwnd: fg as isize,
                                    top_tab_hwnd: top_tab_hwnd as isize,
                                });
                            }
                        }
                        return 1;
                    }
                }
            }
        }

        unsafe { CallNextHookEx(core::ptr::null_mut(), n_code, w_param, l_param) }
    }

    pub fn start_explorer_hook<F>(mut on_event: F)
    where
        F: FnMut(ExplorerHotkeyEvent) + Send + 'static,
    {
        let (tx, rx) = mpsc::sync_channel::<ExplorerHotkeyEvent>(16);
        if let Ok(mut guard) = HOOK_SENDER.lock() {
            *guard = Some(tx);
        }

        std::thread::Builder::new()
            .name("myserver-explorer-hook-worker".to_string())
            .spawn(move || {
                while let Ok(ev) = rx.recv() {
                    on_event(ev);
                }
            })
            .ok();

        std::thread::Builder::new()
            .name("myserver-explorer-ll-hook".to_string())
            .spawn(move || {
                let tid = unsafe { GetCurrentThreadId() };
                HOOK_THREAD_ID.store(tid, Ordering::SeqCst);

                let hmod = unsafe { GetModuleHandleW(core::ptr::null()) };
                let hook = unsafe {
                    SetWindowsHookExW(WH_KEYBOARD_LL, low_level_keyboard_proc, hmod, 0)
                };
                if hook.is_null() {
                    HOOK_THREAD_ID.store(0, Ordering::SeqCst);
                    if let Ok(mut guard) = HOOK_SENDER.lock() {
                        *guard = None;
                    }
                    return;
                }

                let mut msg = Msg {
                    hwnd: core::ptr::null_mut(),
                    message: 0,
                    w_param: 0,
                    l_param: 0,
                    time: 0,
                    pt: Point { x: 0, y: 0 },
                    l_private: 0,
                };
                while unsafe { GetMessageW(&mut msg, core::ptr::null_mut(), 0, 0) } > 0 {
                    unsafe {
                        TranslateMessage(&msg);
                        DispatchMessageW(&msg);
                    }
                }

                unsafe {
                    UnhookWindowsHookEx(hook);
                }
                HOOK_THREAD_ID.store(0, Ordering::SeqCst);
                if let Ok(mut guard) = HOOK_SENDER.lock() {
                    *guard = None;
                }
            })
            .ok();
    }

    pub fn stop_explorer_hook() {
        let tid = HOOK_THREAD_ID.load(Ordering::SeqCst);
        if tid != 0 {
            unsafe {
                PostThreadMessageW(tid, WM_QUIT, 0, 0);
            }
        }
    }
}

#[cfg(not(target_os = "windows"))]
mod imp {
    use super::ExplorerHotkeyEvent;

    pub fn start_explorer_hook<F>(_on_event: F)
    where
        F: FnMut(ExplorerHotkeyEvent) + Send + 'static,
    {
    }

    pub fn stop_explorer_hook() {}
}

pub use imp::{start_explorer_hook, stop_explorer_hook};
