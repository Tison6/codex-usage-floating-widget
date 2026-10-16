#![windows_subsystem = "windows"]

mod bluetooth;
mod codex;
mod config;
mod relay;
mod servers;

use bluetooth::BluetoothScanner;
use codex::{CodexActivityTracker, CodexUsageClient, QuotaTracker};
use config::ConfigManager;
use relay::{AIHubClient, SquareClient};
use servers::ServerManager;
use slint::{ComponentHandle, Model, VecModel};

fn parse_hex_color(hex: &str) -> slint::Color {
    let hex = hex.trim_start_matches('#');
    if hex.len() == 6 {
        if let (Ok(r), Ok(g), Ok(b)) = (
            u8::from_str_radix(&hex[0..2], 16),
            u8::from_str_radix(&hex[2..4], 16),
            u8::from_str_radix(&hex[4..6], 16),
        ) {
            return slint::Color::from_rgb_u8(r, g, b);
        }
    }
    slint::Color::from_rgb_u8(59, 130, 246)
}

macro_rules! app_log {
    ($($arg:tt)*) => {{
        let msg = format!($($arg)*);
        let _ = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open("app_debug.log")
            .map(|mut f| {
                use std::io::Write;
                let _ = writeln!(f, "{}", msg);
                let _ = f.flush();
            });
    }};
}
use std::rc::Rc;
use std::sync::Arc;
use std::time::Duration;
use windows::core::w;
use windows::Win32::Foundation::{BOOL, HWND, LPARAM, POINT, RECT, WPARAM};
use windows::Win32::System::Threading::GetCurrentProcessId;
use windows::Win32::UI::Input::KeyboardAndMouse::{ReleaseCapture, GetAsyncKeyState, VK_LBUTTON, VK_RBUTTON};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromWindow, MONITORINFO, MONITOR_DEFAULTTONEAREST};
use windows::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, CreatePopupMenu, DestroyMenu, EnumWindows, FindWindowW, GetClassNameW,
    GetCursorPos, GetWindowRect, GetWindowTextW, GetWindowThreadProcessId,
    SendMessageW, IsWindow, SetForegroundWindow, SetWindowPos, TrackPopupMenu, HTCAPTION, MF_CHECKED,
    MF_POPUP, MF_SEPARATOR, MF_STRING, MF_UNCHECKED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER,
    TPM_RETURNCMD, TPM_RIGHTBUTTON, WM_NCLBUTTONDOWN, GetWindowLongW, SetWindowLongW, GWL_EXSTYLE, GWL_STYLE,
    WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, HWND_TOPMOST, HWND_NOTOPMOST, SWP_FRAMECHANGED,
};
use tray_icon::{
    menu::{Menu, MenuItem, MenuEvent},
    TrayIconBuilder, Icon, TrayIconEvent,
};

slint::include_modules!();

unsafe extern "system" fn enum_windows_callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let mut pid = 0u32;
    GetWindowThreadProcessId(hwnd, Some(&mut pid));
    if pid == GetCurrentProcessId() {
        let mut class_buf = [0u16; 64];
        let len = GetClassNameW(hwnd, &mut class_buf);
        let class_name = String::from_utf16_lossy(&class_buf[..len as usize]);
        let mut rect = RECT::default();
        let _ = GetWindowRect(hwnd, &mut rect);
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;

        let mut title_buf = [0u16; 64];
        let t_len = GetWindowTextW(hwnd, &mut title_buf);
        let title = String::from_utf16_lossy(&title_buf[..t_len as usize]);

        if (title.contains("状态小组件") || class_name == "Window Class") && w > 50 && h > 20 {
            let found = &mut *(lparam.0 as *mut Option<HWND>);
            *found = Some(hwnd);
            return BOOL(0); // Found the real Slint UI window!
        }
    }
    BOOL(1) // Continue
}

static CACHED_HWND: std::sync::atomic::AtomicIsize = std::sync::atomic::AtomicIsize::new(0);

fn get_window_hwnd() -> Option<HWND> {
    let val = CACHED_HWND.load(std::sync::atomic::Ordering::Relaxed);
    if val != 0 {
        let hwnd = HWND(val as *mut std::ffi::c_void);
        unsafe {
            if IsWindow(hwnd).as_bool() {
                return Some(hwnd);
            }
        }
    }

    unsafe {
        let mut found: Option<HWND> = None;
        let lparam = LPARAM(&mut found as *mut _ as isize);
        let _ = EnumWindows(Some(enum_windows_callback), lparam);
        if let Some(h) = found {
            CACHED_HWND.store(h.0 as isize, std::sync::atomic::Ordering::Relaxed);
            return Some(h);
        }

        if let Ok(hwnd) = FindWindowW(w!("Window Class"), w!("状态小组件")) {
            if !hwnd.0.is_null() {
                CACHED_HWND.store(hwnd.0 as isize, std::sync::atomic::Ordering::Relaxed);
                return Some(hwnd);
            }
        }
        None
    }
}

fn apply_tool_window_style(hwnd: HWND, always_on_top: bool) {
    unsafe {
        let style = GetWindowLongW(hwnd, GWL_STYLE);
        let ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE);

        let ws_popup = 0x80000000u32 as i32;
        let ws_caption = 0x00C00000i32;
        let ws_thickframe = 0x00040000i32;
        let ws_minimizebox = 0x00020000i32;
        let ws_sysmenu = 0x00080000i32;

        let new_style = (style & !(ws_caption | ws_thickframe | ws_minimizebox | ws_sysmenu)) | ws_popup;
        let new_ex = (ex_style | WS_EX_TOOLWINDOW.0 as i32) & !(WS_EX_APPWINDOW.0 as i32);

        if style != new_style || ex_style != new_ex {
            SetWindowLongW(hwnd, GWL_STYLE, new_style);
            SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex);
            let top_flag = if always_on_top { HWND_TOPMOST } else { HWND_NOTOPMOST };
            let _ = SetWindowPos(hwnd, top_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED);
        }

        // Explicitly remove from Taskbar using ITaskbarList::DeleteTab
        use windows::Win32::UI::Shell::{ITaskbarList, TaskbarList};
        use windows::Win32::System::Com::{CoCreateInstance, CLSCTX_INPROC_SERVER};
        if let Ok(taskbar) = CoCreateInstance::<_, ITaskbarList>(&TaskbarList, None, CLSCTX_INPROC_SERVER) {
            let _ = taskbar.HrInit();
            let _ = taskbar.DeleteTab(hwnd);
        }
    }
}

fn resize_window_for_mode(hwnd: HWND, is_mini: bool, scale: f32) {
    unsafe {
        let dpi = GetDpiForWindow(hwnd);
        let dpi_scale = if dpi == 0 { 1.0 } else { dpi as f32 / 96.0 };
        let (base_w, base_h) = if is_mini {
            (178.0, 35.0)
        } else {
            (775.0, 365.0)
        };
        let phys_w = (base_w * scale * dpi_scale).round() as i32;
        let phys_h = (base_h * scale * dpi_scale).round() as i32;

        let mut rect = RECT::default();
        if GetWindowRect(hwnd, &mut rect).is_ok() && (rect.right > rect.left) && (rect.bottom > rect.top) {
            let cx = rect.left + (rect.right - rect.left) / 2;
            let cy = rect.top + (rect.bottom - rect.top) / 2;

            let mut new_x = cx - phys_w / 2;
            let mut new_y = cy - phys_h / 2;

            let hmon = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
            let mut mi = MONITORINFO {
                cbSize: std::mem::size_of::<MONITORINFO>() as u32,
                ..Default::default()
            };
            if GetMonitorInfoW(hmon, &mut mi).as_bool() {
                let margin = 6;
                let min_x = mi.rcWork.left + margin;
                let max_x = (mi.rcWork.right - phys_w - margin).max(min_x);
                let min_y = mi.rcWork.top + margin;
                let max_y = (mi.rcWork.bottom - phys_h - margin).max(min_y);

                new_x = new_x.clamp(min_x, max_x);
                new_y = new_y.clamp(min_y, max_y);
            }

            let _ = SetWindowPos(
                hwnd,
                HWND::default(),
                new_x,
                new_y,
                phys_w,
                phys_h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            );
        } else {
            let _ = SetWindowPos(
                hwnd,
                HWND::default(),
                0,
                0,
                phys_w,
                phys_h,
                SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE,
            );
        }
        apply_tool_window_style(hwnd, true);
    }
}

fn load_tray_icon() -> Result<Icon, Box<dyn std::error::Error>> {
    let width = 16u32;
    let height = 16u32;
    let mut rgba = Vec::with_capacity((width * height * 4) as usize);
    for y in 0..height {
        for x in 0..width {
            let dx = (x as f32 - 7.5).abs();
            let dy = (y as f32 - 7.5).abs();
            let dist_sq = dx * dx + dy * dy;
            if dist_sq <= 49.0 {
                if dist_sq <= 16.0 {
                    // Bright emerald #10B981
                    rgba.extend_from_slice(&[16, 185, 129, 255]);
                } else {
                    // Dark Slate #1E293B
                    rgba.extend_from_slice(&[30, 41, 59, 255]);
                }
            } else {
                rgba.extend_from_slice(&[0, 0, 0, 0]);
            }
        }
    }
    Ok(Icon::from_rgba(rgba, width, height)?)
}

fn set_autostart(enable: bool) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        if let Ok(exe_path) = std::env::current_exe() {
            let exe_str = exe_path.to_string_lossy().to_string();
            if enable {
                let _ = std::process::Command::new("reg")
                    .args([
                        "add",
                        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                        "/v",
                        "DesktopFloatingWidget",
                        "/t",
                        "REG_SZ",
                        "/d",
                        &exe_str,
                        "/f",
                    ])
                    .creation_flags(0x08000000)
                    .output();
            } else {
                let _ = std::process::Command::new("reg")
                    .args([
                        "delete",
                        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                        "/v",
                        "DesktopFloatingWidget",
                        "/f",
                    ])
                    .creation_flags(0x08000000)
                    .output();
            }
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    std::panic::set_hook(Box::new(|info| {
        let msg = format!("PANIC: {:?}\n", info);
        let _ = std::fs::write("panic.log", msg);
    }));
    app_log!("[INIT] Starting desktop floating widget...");
    let rt = match tokio::runtime::Runtime::new() {
        Ok(r) => r,
        Err(e) => {
            app_log!("[FATAL] Failed to initialize Tokio runtime: {:?}", e);
            return Err(Box::new(e));
        }
    };
    app_log!("[INIT] Tokio runtime initialized");
    let _rt_guard = rt.enter();
    let rt_handle = rt.handle().clone();
    let config_mgr = Arc::new(ConfigManager::new("config.json"));
    let cfg = config_mgr.get();
    app_log!("[INIT] Config loaded. Mini mode: {}", cfg.is_mini_mode);

    app_log!("[INIT] Creating MainWindow...");
    let ui = match MainWindow::new() {
        Ok(u) => {
            app_log!("[INIT] MainWindow instantiated successfully");
            u
        },
        Err(e) => {
            app_log!("[FATAL] Failed to instantiate MainWindow: {:?}", e);
            return Err(Box::new(e));
        }
    };

    // Initial properties from config
    ui.set_is_mini(cfg.is_mini_mode);
    ui.set_ui_scale(cfg.scale);
    ui.set_cfg_always_on_top(cfg.always_on_top);
    ui.set_aihub_auto_mode(cfg.aihub_auto_mode);
    ui.set_cfg_codex_interval(cfg.codex_interval_sec as i32);
    ui.set_cfg_relay_interval(cfg.relay_interval_sec as i32);
    ui.set_cfg_autostart(cfg.autostart);

    app_log!("[INIT] Showing MainWindow...");
    if let Err(e) = ui.show() {
        app_log!("[FATAL] Failed to show MainWindow: {:?}", e);
        return Err(Box::new(e));
    }
    app_log!("[INIT] MainWindow shown successfully");

    // Initial Window Position
    ui.window().set_position(slint::PhysicalPosition::new(
        cfg.window_pos[0],
        cfg.window_pos[1],
    ));
    app_log!("[INIT] Window position set to [{}, {}]", cfg.window_pos[0], cfg.window_pos[1]);

    if let Some(hwnd) = get_window_hwnd() {
        apply_tool_window_style(hwnd, cfg.always_on_top);
        resize_window_for_mode(hwnd, cfg.is_mini_mode, cfg.scale);
        app_log!("[INIT] Window native size initialized for mini_mode={} scale={}", cfg.is_mini_mode, cfg.scale);
    }

    // Channels for explicit user refresh triggers
    let (codex_trigger_tx, mut codex_trigger_rx) = tokio::sync::mpsc::channel::<()>(8);
    let (relay_trigger_tx, mut relay_trigger_rx) = tokio::sync::mpsc::channel::<()>(8);
    let (servers_trigger_tx, mut servers_trigger_rx) = tokio::sync::mpsc::channel::<()>(8);

    // Setup System Tray Icon & Context Menu
    let tray_menu = Menu::new();
    let item_toggle = MenuItem::new("展开 / 收起卡片", true, None);
    let item_refresh = MenuItem::new("🔄 强制刷新数据", true, None);
    let item_quit = MenuItem::new("❌ 退出程序", true, None);
    let _ = tray_menu.append(&item_toggle);
    let _ = tray_menu.append(&item_refresh);
    let _ = tray_menu.append(&item_quit);

    let _tray_icon = match load_tray_icon() {
        Ok(icon) => TrayIconBuilder::new()
            .with_menu(Box::new(tray_menu))
            .with_tooltip("状态小组件 (Rust + Slint)")
            .with_icon(icon)
            .build()
            .ok(),
        Err(e) => {
            eprintln!("[WARN] Failed to load tray icon: {}", e);
            None
        }
    };

    // Tray event handler timer (every 100ms)
    let tray_timer = slint::Timer::default();
    let ui_weak_tray = ui.as_weak();
    let config_mgr_tray = config_mgr.clone();
    let codex_tx_tray = codex_trigger_tx.clone();
    let relay_tx_tray = relay_trigger_tx.clone();
    let servers_tx_tray = servers_trigger_tx.clone();
    let toggle_id = item_toggle.id().clone();
    let refresh_id = item_refresh.id().clone();
    let quit_id = item_quit.id().clone();

    tray_timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(100),
        move || {
            while let Ok(event) = MenuEvent::receiver().try_recv() {
                if event.id == toggle_id {
                    if let Some(ui) = ui_weak_tray.upgrade() {
                        let cur = ui.get_is_mini();
                        let next = !cur;
                        ui.set_is_mini(next);
                        config_mgr_tray.update(|c| c.is_mini_mode = next);
                        if let Some(hwnd) = get_window_hwnd() {
                            resize_window_for_mode(hwnd, next, ui.get_ui_scale());
                        }
                    }
                } else if event.id == refresh_id {
                    let _ = codex_tx_tray.try_send(());
                    let _ = relay_tx_tray.try_send(());
                    let _ = servers_tx_tray.try_send(());
                } else if event.id == quit_id {
                    let _ = slint::quit_event_loop();
                }
            }

            while let Ok(event) = TrayIconEvent::receiver().try_recv() {
                match event {
                    TrayIconEvent::Click { button: tray_icon::MouseButton::Left, .. } => {
                        if let Some(ui) = ui_weak_tray.upgrade() {
                            let cur = ui.get_is_mini();
                            let next = !cur;
                            ui.set_is_mini(next);
                            config_mgr_tray.update(|c| c.is_mini_mode = next);
                            if let Some(hwnd) = get_window_hwnd() {
                                resize_window_for_mode(hwnd, next, ui.get_ui_scale());
                            }
                        }
                    }
                    _ => {}
                }
            }
        },
    );

    let aihub_client = AIHubClient::new();
    let thumb_cache: Arc<tokio::sync::Mutex<std::collections::HashMap<String, slint::SharedPixelBuffer<slint::Rgba8Pixel>>>> =
        Arc::new(tokio::sync::Mutex::new(std::collections::HashMap::new()));

    // --- UI Callbacks ---

    // Window Dragging Callback
    let config_mgr_drag = config_mgr.clone();
    ui.on_drag_window(move || {
        unsafe {
            if let Some(hwnd) = get_window_hwnd() {
                let mut pt = POINT::default();
                let _ = GetCursorPos(&mut pt);
                let lparam = ((pt.y as u32) << 16) | ((pt.x as u32) & 0xFFFF);
                let _ = ReleaseCapture();
                let _ = SendMessageW(
                    hwnd,
                    WM_NCLBUTTONDOWN,
                    WPARAM(HTCAPTION as usize),
                    LPARAM(lparam as isize),
                );
                let mut rect = RECT::default();
                if GetWindowRect(hwnd, &mut rect).is_ok() {
                    config_mgr_drag.update(|c| {
                        c.window_pos = [rect.left, rect.top];
                    });
                }
            }
        }
    });

    let last_expand_time = Arc::new(std::sync::atomic::AtomicU64::new(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    ));
    let last_expand_time_cb = last_expand_time.clone();
    let config_mgr_exp = config_mgr.clone();
    let ui_weak_exp = ui.as_weak();
    ui.on_expand_clicked(move || {
        if let Some(ui) = ui_weak_exp.upgrade() {
            ui.set_is_mini(false);
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            last_expand_time_cb.store(now_ms, std::sync::atomic::Ordering::SeqCst);
            config_mgr_exp.update(|c| c.is_mini_mode = false);

            if let Some(hwnd) = get_window_hwnd() {
                resize_window_for_mode(hwnd, false, ui.get_ui_scale());
                unsafe {
                    let _ = SetForegroundWindow(hwnd);
                }
            }
        }
    });

    let config_mgr_col = config_mgr.clone();
    let ui_weak_col = ui.as_weak();
    ui.on_collapse_clicked(move || {
        if let Some(ui) = ui_weak_col.upgrade() {
            ui.set_is_mini(true);
            config_mgr_col.update(|c| c.is_mini_mode = true);
            if let Some(hwnd) = get_window_hwnd() {
                resize_window_for_mode(hwnd, true, ui.get_ui_scale());
            }
        }
    });

    // Right-Click Context Menu Callback
    let ui_weak_rc = ui.as_weak();
    let config_mgr_rc = config_mgr.clone();
    let codex_tx_rc = codex_trigger_tx.clone();
    let relay_tx_rc = relay_trigger_tx.clone();
    let servers_tx_rc = servers_trigger_tx.clone();
    ui.on_right_clicked(move || {
        unsafe {
            if let Some(hwnd) = get_window_hwnd() {
                if let Ok(hmenu) = CreatePopupMenu() {
                    let cur_scale = ui_weak_rc.upgrade().map(|u| u.get_ui_scale()).unwrap_or(1.0);
                    let is_mini = ui_weak_rc.upgrade().map(|u| u.get_is_mini()).unwrap_or(true);
                    let toggle_text = if is_mini { w!("📖 展开详细面板") } else { w!("💊 切换为迷你胶囊") };
                    let _ = AppendMenuW(hmenu, MF_STRING, 1, toggle_text);
                    let _ = AppendMenuW(hmenu, MF_SEPARATOR, 0, None);

                    // Size Scaling Submenu (80%, 100%, 120%, 140%)
                    if let Ok(hsub) = CreatePopupMenu() {
                        let check_flag = |s: f32| if (cur_scale - s).abs() < 0.05 { MF_CHECKED } else { MF_UNCHECKED };
                        let _ = AppendMenuW(hsub, MF_STRING | check_flag(0.80), 201, w!("80%"));
                        let _ = AppendMenuW(hsub, MF_STRING | check_flag(1.00), 202, w!("100% (标准)"));
                        let _ = AppendMenuW(hsub, MF_STRING | check_flag(1.20), 203, w!("120%"));
                        let _ = AppendMenuW(hsub, MF_STRING | check_flag(1.40), 204, w!("140%"));
                        let _ = AppendMenuW(hmenu, MF_POPUP, hsub.0 as usize, w!("📏 窗口缩放尺寸"));
                    }

                    let is_top = config_mgr_rc.get().always_on_top;
                    let top_text = if is_top { w!("📌 窗口置顶 (已开启)") } else { w!("📌 窗口置顶 (已关闭)") };
                    let _ = AppendMenuW(hmenu, MF_STRING | if is_top { MF_CHECKED } else { MF_UNCHECKED }, 5, top_text);
                    let _ = AppendMenuW(hmenu, MF_SEPARATOR, 0, None);
                    let _ = AppendMenuW(hmenu, MF_STRING, 2, w!("🔄 立即刷新数据"));
                    let _ = AppendMenuW(hmenu, MF_STRING, 3, w!("⚙️ 偏好设置..."));
                    let _ = AppendMenuW(hmenu, MF_SEPARATOR, 0, None);
                    let _ = AppendMenuW(hmenu, MF_STRING, 4, w!("✕ 退出程序"));

                    let mut pt = POINT::default();
                    let _ = GetCursorPos(&mut pt);
                    let _ = SetForegroundWindow(hwnd);
                    let cmd = TrackPopupMenu(
                        hmenu,
                        TPM_RETURNCMD | TPM_RIGHTBUTTON,
                        pt.x,
                        pt.y,
                        0,
                        hwnd,
                        None,
                    );
                    let _ = DestroyMenu(hmenu);

                    match cmd.0 {
                        1 => {
                            if let Some(ui) = ui_weak_rc.upgrade() {
                                let cur = ui.get_is_mini();
                                let next = !cur;
                                ui.set_is_mini(next);
                                config_mgr_rc.update(|c| c.is_mini_mode = next);
                                resize_window_for_mode(hwnd, next, ui.get_ui_scale());
                            }
                        }
                        201..=204 => {
                            let new_scale = match cmd.0 {
                                201 => 0.80,
                                202 => 1.00,
                                203 => 1.20,
                                204 => 1.40,
                                _ => 1.00,
                            };
                            if let Some(ui) = ui_weak_rc.upgrade() {
                                ui.set_ui_scale(new_scale);
                                config_mgr_rc.update(|c| c.scale = new_scale);
                                resize_window_for_mode(hwnd, ui.get_is_mini(), new_scale);
                            }
                        }
                        5 => {
                            if let Some(ui) = ui_weak_rc.upgrade() {
                                let next_top = !config_mgr_rc.get().always_on_top;
                                config_mgr_rc.update(|c| c.always_on_top = next_top);
                                ui.set_cfg_always_on_top(next_top);
                                let top_flag = if next_top { HWND_TOPMOST } else { HWND_NOTOPMOST };
                                let _ = SetWindowPos(hwnd, top_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
                            }
                        }
                        2 => {
                            let _ = codex_tx_rc.try_send(());
                            let _ = relay_tx_rc.try_send(());
                            let _ = servers_tx_rc.try_send(());
                        }
                        3 => {
                            if let Some(ui) = ui_weak_rc.upgrade() {
                                ui.set_is_mini(false);
                                resize_window_for_mode(hwnd, false, ui.get_ui_scale());
                                ui.set_settings_dialog_open(true);
                            }
                        }
                        4 => {
                            let _ = slint::quit_event_loop();
                        }
                        _ => {}
                    }
                }
            }
        }
    });

    // Manual Refresh Callbacks
    let codex_tx_clone = codex_trigger_tx.clone();
    ui.on_refresh_codex_clicked(move || {
        let _ = codex_tx_clone.try_send(());
    });

    let relay_tx_clone = relay_trigger_tx.clone();
    ui.on_refresh_relay_clicked(move || {
        let _ = relay_tx_clone.try_send(());
    });

    let servers_tx_clone = servers_trigger_tx.clone();
    ui.on_refresh_servers_clicked(move || {
        let _ = servers_tx_clone.try_send(());
    });

    let gantt_range_days = Arc::new(std::sync::atomic::AtomicI64::new(1));
    let gantt_range_days_cycle = gantt_range_days.clone();
    let gantt_range_days_loop = gantt_range_days.clone();
    let ui_weak_cycle = ui.as_weak();
    let servers_tx_cycle = servers_trigger_tx.clone();

    ui.on_cycle_history_range(move || {
        if let Some(ui) = ui_weak_cycle.upgrade() {
            let cur = gantt_range_days_cycle.load(std::sync::atomic::Ordering::SeqCst);
            let next = match cur {
                1 => 3,
                3 => 7,
                _ => 1,
            };
            gantt_range_days_cycle.store(next, std::sync::atomic::Ordering::SeqCst);
            ui.set_gantt_range_days(next as i32);
            let _ = servers_tx_cycle.try_send(());
        }
    });

    let servers_tx_hist = servers_trigger_tx.clone();
    ui.on_load_history_clicked(move || {
        let _ = servers_tx_hist.try_send(());
    });

    // AIHub Auto / Manual Mode Toggle
    let relay_tx_mode = relay_trigger_tx.clone();
    let config_mgr_mode = config_mgr.clone();
    let ui_weak_mode = ui.as_weak();
    ui.on_toggle_aihub_mode_clicked(move || {
        if let Some(ui) = ui_weak_mode.upgrade() {
            let next = !ui.get_aihub_auto_mode();
            ui.set_aihub_auto_mode(next);
            config_mgr_mode.update(|c| c.aihub_auto_mode = next);
            let _ = relay_tx_mode.try_send(());
        }
    });

    // Filter Dialog Callbacks
    let ui_weak_dlg_open = ui.as_weak();
    ui.on_open_aihub_filter_clicked(move || {
        if let Some(ui) = ui_weak_dlg_open.upgrade() {
            ui.set_filter_dialog_open(true);
        }
    });

    let ui_weak_dlg_close = ui.as_weak();
    ui.on_close_filter_clicked(move || {
        if let Some(ui) = ui_weak_dlg_close.upgrade() {
            ui.set_filter_dialog_open(false);
        }
    });

    let ui_weak_dlg_save = ui.as_weak();
    let config_mgr_dlg = config_mgr.clone();
    let relay_tx_save = relay_trigger_tx.clone();
    ui.on_save_filter_clicked(move || {
        if let Some(ui) = ui_weak_dlg_save.upgrade() {
            let providers_model = ui.get_dlg_providers();
            let mut selected = Vec::new();
            let mut excluded = Vec::new();

            for i in 0..providers_model.row_count() {
                if let Some(item) = providers_model.row_data(i) {
                    let code = item.code.to_string();
                    if item.is_excluded {
                        excluded.push(code);
                    } else if item.is_selected {
                        selected.push(code);
                    }
                }
            }

            config_mgr_dlg.update(|c| {
                c.aihub_selected_providers = selected;
                c.aihub_excluded_providers = excluded;
                c.aihub_auto_mode = ui.get_aihub_auto_mode();
            });

            ui.set_filter_dialog_open(false);
            let _ = relay_tx_save.try_send(());
        }
    });

    let ui_weak_dlg_toggle_sel = ui.as_weak();
    ui.on_toggle_dlg_selected(move |idx, sel| {
        if let Some(ui) = ui_weak_dlg_toggle_sel.upgrade() {
            let model = ui.get_dlg_providers();
            if let Some(mut item) = model.row_data(idx as usize) {
                if !item.is_excluded {
                    item.is_selected = sel;
                    model.set_row_data(idx as usize, item);
                    let mut count = 0;
                    for i in 0..model.row_count() {
                        if let Some(it) = model.row_data(i) {
                            if it.is_selected && !it.is_excluded {
                                count += 1;
                            }
                        }
                    }
                    ui.set_dlg_selected_count(count);
                }
            }
        }
    });

    let ui_weak_dlg_toggle_exc = ui.as_weak();
    ui.on_toggle_dlg_excluded(move |idx, exc| {
        if let Some(ui) = ui_weak_dlg_toggle_exc.upgrade() {
            let model = ui.get_dlg_providers();
            if let Some(mut item) = model.row_data(idx as usize) {
                item.is_excluded = exc;
                if exc {
                    item.is_selected = false;
                }
                model.set_row_data(idx as usize, item);
                let mut sel_cnt = 0;
                let mut exc_cnt = 0;
                for i in 0..model.row_count() {
                    if let Some(it) = model.row_data(i) {
                        if it.is_excluded {
                            exc_cnt += 1;
                        } else if it.is_selected {
                            sel_cnt += 1;
                        }
                    }
                }
                ui.set_dlg_selected_count(sel_cnt);
                ui.set_dlg_excluded_count(exc_cnt);
            }
        }
    });

    // Settings Callbacks
    let ui_weak_settings = ui.as_weak();
    ui.on_open_settings_clicked(move || {
        if let Some(ui) = ui_weak_settings.upgrade() {
            ui.set_settings_dialog_open(true);
        }
    });

    let ui_weak_save_settings = ui.as_weak();
    let config_mgr_settings = config_mgr.clone();
    ui.on_save_settings_clicked(move |always_on_top, scale, cdx_int, rly_int, autostart| {
        if let Some(ui) = ui_weak_save_settings.upgrade() {
            config_mgr_settings.update(|c| {
                c.always_on_top = always_on_top;
                c.scale = scale;
                c.codex_interval_sec = cdx_int as u64;
                c.relay_interval_sec = rly_int as u64;
                c.autostart = autostart;
            });

            set_autostart(autostart);
            ui.set_cfg_always_on_top(always_on_top);
            ui.set_ui_scale(scale);
            if let Some(hwnd) = get_window_hwnd() {
                unsafe {
                    let top_flag = if always_on_top { HWND_TOPMOST } else { HWND_NOTOPMOST };
                    let _ = SetWindowPos(hwnd, top_flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
                }
                resize_window_for_mode(hwnd, ui.get_is_mini(), scale);
            }
            ui.set_settings_dialog_open(false);
        }
    });

    ui.on_exit_app_clicked(move || {
        let _ = slint::quit_event_loop();
    });

    // Square Filter Callbacks
    let ui_weak_sq_open = ui.as_weak();
    let config_mgr_sq = config_mgr.clone();
    let square_client_filter = SquareClient::new();
    let rt_handle_sq = rt_handle.clone();
    ui.on_open_square_filter_clicked(move || {
        if let Some(ui) = ui_weak_sq_open.upgrade() {
            ui.set_square_filter_dialog_open(true);
            let selected_groups = config_mgr_sq.get().square_selected_groups.clone();
            let selected_models = config_mgr_sq.get().square_selected_models.clone();
            let sq_client = square_client_filter.clone();
            let ui_weak_inner = ui.as_weak();

            rt_handle_sq.spawn(async move {
                let all_groups = sq_client.fetch_all_groups().await;
                let all_models = sq_client.fetch_all_models().await;
                let _ = ui_weak_inner.upgrade_in_event_loop(move |ui| {
                    let mut group_items = Vec::new();
                    let mut sel_groups_count = 0;
                    for g in all_groups {
                        let is_sel = selected_groups.contains(&g.name);
                        if is_sel {
                            sel_groups_count += 1;
                        }
                        group_items.push(SquareDialogGroupItem {
                            name: g.name.into(),
                            model: g.model.into(),
                            multiplier: g.multiplier.into(),
                            tps: g.tps.into(),
                            latency: g.latency.into(),
                            success_rate: g.success_rate.into(),
                            is_selected: is_sel,
                        });
                    }

                    let mut model_items = Vec::new();
                    let mut sel_models_count = 0;
                    for m in all_models {
                        let is_sel = selected_models.contains(&m.name);
                        if is_sel {
                            sel_models_count += 1;
                        }
                        model_items.push(SquareDialogModelItem {
                            name: m.name.into(),
                            label: m.label.into(),
                            supported_groups_count: m.supported_groups_count,
                            is_selected: is_sel,
                        });
                    }

                    ui.set_dlg_sq_selected_count(sel_groups_count);
                    ui.set_dlg_sq_total_count(group_items.len() as i32);
                    ui.set_dlg_sq_selected_models_count(sel_models_count);
                    ui.set_dlg_sq_total_models_count(model_items.len() as i32);
                    ui.set_dlg_square_groups(Rc::new(VecModel::from(group_items)).into());
                    ui.set_dlg_square_models(Rc::new(VecModel::from(model_items)).into());
                });
            });
        }
    });

    let ui_weak_sq_tog = ui.as_weak();
    ui.on_toggle_square_group_selected(move |idx, sel| {
        if let Some(ui) = ui_weak_sq_tog.upgrade() {
            let model = ui.get_dlg_square_groups();
            if let Some(mut item) = model.row_data(idx as usize) {
                item.is_selected = sel;
                model.set_row_data(idx as usize, item);
                let mut count = 0;
                for i in 0..model.row_count() {
                    if let Some(it) = model.row_data(i) {
                        if it.is_selected {
                            count += 1;
                        }
                    }
                }
                ui.set_dlg_sq_selected_count(count);
            }
        }
    });

    let ui_weak_sq_tog_m = ui.as_weak();
    ui.on_toggle_square_model_selected(move |idx, sel| {
        if let Some(ui) = ui_weak_sq_tog_m.upgrade() {
            let model = ui.get_dlg_square_models();
            if let Some(mut item) = model.row_data(idx as usize) {
                item.is_selected = sel;
                model.set_row_data(idx as usize, item);
                let mut count = 0;
                for i in 0..model.row_count() {
                    if let Some(it) = model.row_data(i) {
                        if it.is_selected {
                            count += 1;
                        }
                    }
                }
                ui.set_dlg_sq_selected_models_count(count);
            }
        }
    });

    let ui_weak_sq_all_g = ui.as_weak();
    ui.on_select_all_square_groups(move || {
        if let Some(ui) = ui_weak_sq_all_g.upgrade() {
            let model = ui.get_dlg_square_groups();
            let total = model.row_count();
            for i in 0..total {
                if let Some(mut it) = model.row_data(i) {
                    it.is_selected = true;
                    model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_count(total as i32);
        }
    });

    let ui_weak_sq_clr_g = ui.as_weak();
    ui.on_clear_all_square_groups(move || {
        if let Some(ui) = ui_weak_sq_clr_g.upgrade() {
            let model = ui.get_dlg_square_groups();
            for i in 0..model.row_count() {
                if let Some(mut it) = model.row_data(i) {
                    it.is_selected = false;
                    model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_count(0);
        }
    });

    let ui_weak_sq_all_m = ui.as_weak();
    ui.on_select_all_square_models(move || {
        if let Some(ui) = ui_weak_sq_all_m.upgrade() {
            let model = ui.get_dlg_square_models();
            let total = model.row_count();
            for i in 0..total {
                if let Some(mut it) = model.row_data(i) {
                    it.is_selected = true;
                    model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_models_count(total as i32);
        }
    });

    let ui_weak_sq_clr_m = ui.as_weak();
    ui.on_clear_all_square_models(move || {
        if let Some(ui) = ui_weak_sq_clr_m.upgrade() {
            let model = ui.get_dlg_square_models();
            for i in 0..model.row_count() {
                if let Some(mut it) = model.row_data(i) {
                    it.is_selected = false;
                    model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_models_count(0);
        }
    });

    let ui_weak_sq_preset = ui.as_weak();
    ui.on_apply_square_preset(move || {
        if let Some(ui) = ui_weak_sq_preset.upgrade() {
            let g_model = ui.get_dlg_square_groups();
            let mut g_count = 0;
            for i in 0..g_model.row_count() {
                if let Some(mut it) = g_model.row_data(i) {
                    let is_preset = relay::DEFAULT_SELECTED_GROUPS.contains(&it.name.as_str());
                    it.is_selected = is_preset;
                    if is_preset {
                        g_count += 1;
                    }
                    g_model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_count(g_count);

            let m_model = ui.get_dlg_square_models();
            let mut m_count = 0;
            for i in 0..m_model.row_count() {
                if let Some(mut it) = m_model.row_data(i) {
                    let is_preset = relay::DEFAULT_SELECTED_MODELS.contains(&it.name.as_str());
                    it.is_selected = is_preset;
                    if is_preset {
                        m_count += 1;
                    }
                    m_model.set_row_data(i, it);
                }
            }
            ui.set_dlg_sq_selected_models_count(m_count);
        }
    });

    let ui_weak_sq_save = ui.as_weak();
    let config_mgr_sq_save = config_mgr.clone();
    let relay_tx_sq_save = relay_trigger_tx.clone();
    ui.on_save_square_filter_clicked(move || {
        if let Some(ui) = ui_weak_sq_save.upgrade() {
            let g_model = ui.get_dlg_square_groups();
            let mut selected_groups = Vec::new();
            for i in 0..g_model.row_count() {
                if let Some(it) = g_model.row_data(i) {
                    if it.is_selected {
                        selected_groups.push(it.name.to_string());
                    }
                }
            }

            let m_model = ui.get_dlg_square_models();
            let mut selected_models = Vec::new();
            for i in 0..m_model.row_count() {
                if let Some(it) = m_model.row_data(i) {
                    if it.is_selected {
                        selected_models.push(it.name.to_string());
                    }
                }
            }

            config_mgr_sq_save.update(|c| {
                c.square_selected_groups = selected_groups;
                c.square_selected_models = selected_models;
            });
            ui.set_square_filter_dialog_open(false);
            let _ = relay_tx_sq_save.try_send(());
        }
    });

    // Pelican Viewer Callbacks
    let ui_weak_pelican = ui.as_weak();
    let aihub_client_pelican = aihub_client.clone();
    let rt_handle_pelican = rt_handle.clone();
    ui.on_open_pelican_viewer(move |code, group_id| {
        if let Some(ui) = ui_weak_pelican.upgrade() {
            ui.set_pelican_provider_code(code.clone());
            ui.set_pelican_status_text("⏳ 正在实时获取鹈鹕历史实测图...".into());
            ui.set_pelican_cards(Rc::new(VecModel::default()).into());
            ui.set_pelican_dialog_open(true);

            let ui_weak_inner = ui.as_weak();
            let client = aihub_client_pelican.clone();
            let gid = group_id as i64;

            rt_handle_pelican.spawn(async move {
                let images = client.get_provider_history_images(gid, 30).await;
                if images.is_empty() {
                    let _ = ui_weak_inner.upgrade_in_event_loop(|ui| {
                        ui.set_pelican_status_text("暂无实测图记录或未检测到可用历史".into());
                    });
                    return;
                }

                let count_str = format!("共 {} 张实测图 (实时云端同步)", images.len());
                let initial_info: Vec<(String, String, String)> = images
                    .iter()
                    .map(|img| (img.id.clone(), img.published_at_str.clone(), img.url.clone()))
                    .collect();

                let _ = ui_weak_inner.upgrade_in_event_loop(move |ui| {
                    ui.set_pelican_status_text(count_str.into());
                    let cards: Vec<PelicanDialogCardItem> = initial_info
                        .into_iter()
                        .map(|(id, pub_str, url)| PelicanDialogCardItem {
                            id: id.into(),
                            published_at_str: pub_str.into(),
                            url: url.into(),
                            has_image: false,
                            img: slint::Image::default(),
                        })
                        .collect();
                    ui.set_pelican_cards(Rc::new(VecModel::from(cards)).into());
                });

                // Stream in images sequentially with thumbnail pre-scaling (480x300)
                for (idx, img_it) in images.into_iter().enumerate() {
                    let c = client.clone();
                    let ui_w = ui_weak_inner.clone();
                    let item_id = img_it.id;
                    let pub_str = img_it.published_at_str;
                    let url_str = img_it.url;
                    if let Some(buf) = c.fetch_image_as_pixel_buffer(&url_str, 480, 300).await {
                        let _ = ui_w.upgrade_in_event_loop(move |ui| {
                            if ui.get_pelican_dialog_open() {
                                let model = ui.get_pelican_cards();
                                if idx < model.row_count() {
                                    model.set_row_data(
                                        idx,
                                        PelicanDialogCardItem {
                                            id: item_id.into(),
                                            published_at_str: pub_str.into(),
                                            url: url_str.into(),
                                            has_image: true,
                                            img: slint::Image::from_rgba8(buf),
                                        },
                                    );
                                }
                            }
                        });
                    }
                }
            });
        }
    });

    let ui_weak_pel_close = ui.as_weak();
    ui.on_close_pelican_viewer(move || {
        if let Some(ui) = ui_weak_pel_close.upgrade() {
            ui.set_pelican_dialog_open(false);
        }
    });

    ui.on_open_external_url(move |url| {
        use std::os::windows::process::CommandExt;
        let u = url.to_string();
        if !u.is_empty() {
            let _ = std::process::Command::new("explorer")
                .arg(&u)
                .creation_flags(0x08000000)
                .spawn();
        }
    });

    // Auto Collapse on Focus Loss (every 100ms, matching Python collapse_timer)
    let auto_collapse_timer = slint::Timer::default();
    let ui_weak_collapse = ui.as_weak();
    let config_mgr_collapse = config_mgr.clone();
    let last_expand_time_timer = last_expand_time.clone();
    auto_collapse_timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(100),
        move || {
            if let Some(ui) = ui_weak_collapse.upgrade() {
                if !ui.get_is_mini() && !ui.get_filter_dialog_open() && !ui.get_square_filter_dialog_open() && !ui.get_settings_dialog_open() && !ui.get_pelican_dialog_open() {
                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);
                    let exp_ms = last_expand_time_timer.load(std::sync::atomic::Ordering::SeqCst);
                    if now_ms.saturating_sub(exp_ms) < 600 {
                        return; // 0.6s grace period right after clicking expand, matching Python
                    }

                    unsafe {
                        let l_down = GetAsyncKeyState(VK_LBUTTON.0 as i32) < 0;
                        let r_down = GetAsyncKeyState(VK_RBUTTON.0 as i32) < 0;
                        if l_down || r_down {
                            if let Some(hwnd) = get_window_hwnd() {
                                let mut pt = POINT::default();
                                let _ = GetCursorPos(&mut pt);
                                let mut rect = RECT::default();
                                if GetWindowRect(hwnd, &mut rect).is_ok() {
                                    let w = rect.right - rect.left;
                                    let h = rect.bottom - rect.top;
                                    // Guard: only test for outside clicks if window is truly in expanded dimensions
                                    if w > 300 && h > 150 {
                                        let pad = 6;
                                        // If click occurs outside the window rect (with tolerance margin), immediately collapse
                                        if pt.x < (rect.left - pad) || pt.x > (rect.right + pad) || pt.y < (rect.top - pad) || pt.y > (rect.bottom + pad) {
                                            ui.set_is_mini(true);
                                            config_mgr_collapse.update(|c| c.is_mini_mode = true);
                                            resize_window_for_mode(hwnd, true, ui.get_ui_scale());
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    );

    // Fast Codex Activity Monitor (every 1s, matching Python self.activity_timer)
    let activity_timer = slint::Timer::default();
    let ui_weak_activity = ui.as_weak();
    activity_timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(1000),
        move || {
            let tracker = CodexActivityTracker::new();
            let (is_running, _) = tracker.check_is_running();
            if let Some(ui) = ui_weak_activity.upgrade() {
                if ui.get_codex_running() != is_running {
                    ui.set_codex_running(is_running);
                }
            }
        },
    );

    // Live Clock Timer (every 1s)
    let clock_timer = slint::Timer::default();
    let ui_weak_clock = ui.as_weak();
    clock_timer.start(
        slint::TimerMode::Repeated,
        Duration::from_secs(1),
        move || {
            if let Some(ui) = ui_weak_clock.upgrade() {
                let now_time = chrono::Local::now().format("%H:%M:%S").to_string();
                ui.set_time_str(now_time.into());
            }
        },
    );

    // --- Background Tasks ---

    // 1. Bluetooth Worker Loop
    let ui_weak_bt = ui.as_weak();
    let config_mgr_bt = config_mgr.clone();
    rt.spawn(async move {
        let scanner = BluetoothScanner::new();
        loop {
            let only_conn = config_mgr_bt.get().only_connected;
            let devs = scanner.scan_devices(only_conn);

            let mut bt_models = Vec::new();
            let mut top_icon = String::from("🎙️");
            let mut top_batt = String::from("100");

            for d in &devs {
                bt_models.push(BluetoothDeviceInfo {
                    name: d.name.clone().into(),
                    battery: d.battery,
                    icon: d.icon.clone().into(),
                });
            }

            if let Some(first) = devs.first() {
                top_icon = first.icon.clone();
                top_batt = first.battery.to_string();
            }

            let _ = ui_weak_bt.upgrade_in_event_loop(move |ui| {
                ui.set_bt_devices(Rc::new(VecModel::from(bt_models)).into());
                ui.set_bt_icon(top_icon.into());
                ui.set_bt_battery(top_batt.into());
            });

            tokio::time::sleep(Duration::from_secs(10)).await;
        }
    });

    // 2. Codex Worker Loop
    let ui_weak_codex = ui.as_weak();
    let config_mgr_codex = config_mgr.clone();
    rt.spawn(async move {
        let mut client = CodexUsageClient::new(&config_mgr_codex.get().auth_file_path);
        let activity = CodexActivityTracker::new();
        let mut quota_tracker = QuotaTracker::new("data");

        loop {
            let usage = client.fetch_usage().await;
            let (is_running, _) = activity.check_is_running();

            if usage.success {
                quota_tracker.record_snapshot(&usage);
            }
            let analysis = quota_tracker.get_analysis_for_current_cycle(usage.weekly_window.as_ref());
            let sparkline_svg = quota_tracker.generate_sparkline_svg(&analysis, 194.0, 52.0);
            let exhaustion_text = analysis.exhaustion_text.clone();

            let five_h_pct = usage
                .five_hour_window
                .as_ref()
                .map(|w| w.remaining_percent)
                .unwrap_or(100);
            let five_h_countdown = usage
                .five_hour_window
                .as_ref()
                .map(|w| w.reset_countdown.clone())
                .unwrap_or_else(|| "3h 12m".to_string());
            let has_five_h = usage.five_hour_window.is_some();
            let weekly_pct = usage
                .weekly_window
                .as_ref()
                .map(|w| w.remaining_percent)
                .unwrap_or(56);
            let countdown = usage
                .weekly_window
                .as_ref()
                .map(|w| w.reset_countdown.clone())
                .unwrap_or_else(|| "5d 14h".to_string());
            let credits = usage.reset_credits;
            let plan = usage.plan_type.clone();
            let updated = usage.updated_at.clone();

            let now_time = chrono::Local::now().format("%H:%M:%S").to_string();

            let is_error = !usage.success;
            let col_5h = if is_error {
                slint::Color::from_rgb_u8(239, 68, 68)
            } else if five_h_pct > 50 {
                slint::Color::from_rgb_u8(16, 185, 129) // #10B981
            } else if five_h_pct >= 20 {
                slint::Color::from_rgb_u8(245, 158, 11) // #F59E0B
            } else {
                slint::Color::from_rgb_u8(239, 68, 68)  // #EF4444
            };

            let col_wk = if is_error {
                slint::Color::from_rgb_u8(239, 68, 68) // #EF4444
            } else if weekly_pct > 50 {
                slint::Color::from_rgb_u8(16, 185, 129) // #10B981
            } else if weekly_pct >= 20 {
                slint::Color::from_rgb_u8(245, 158, 11) // #F59E0B
            } else {
                slint::Color::from_rgb_u8(239, 68, 68)  // #EF4444
            };

            let err_msg = usage.error.clone().unwrap_or_else(|| "登录凭证失效 (401)".to_string());

            let _ = ui_weak_codex.upgrade_in_event_loop(move |ui| {
                ui.set_codex_running(is_running);
                ui.set_codex_is_error(is_error);

                if is_error {
                    ui.set_codex_5h_val("--".into());
                    ui.set_codex_wk_val("--".into());
                    ui.set_weekly_remaining_pct(0);
                    ui.set_countdown_str("--".into());
                    ui.set_has_five_hour(false);
                    ui.set_plan_type("未登录".into());
                    ui.set_exhaustion_str(format!("提示: {}", err_msg).into());
                } else {
                    ui.set_codex_5h_val(five_h_pct.to_string().into());
                    ui.set_codex_wk_val(weekly_pct.to_string().into());
                    ui.set_weekly_remaining_pct(weekly_pct);
                    ui.set_countdown_str(countdown.into());
                    ui.set_five_hour_remaining_pct(five_h_pct);
                    ui.set_five_hour_countdown_str(five_h_countdown.into());
                    ui.set_has_five_hour(has_five_h);
                    ui.set_plan_type(plan.into());
                    ui.set_exhaustion_str(exhaustion_text.into());
                }
                ui.set_codex_5h_color(col_5h);
                ui.set_codex_wk_color(col_wk);
                ui.set_time_str(now_time.into());
                ui.set_five_hour_color(col_5h);
                ui.set_reset_credits(credits);
                ui.set_updated_time(updated.into());
                if let Ok(sparkline_img) = slint::Image::load_from_svg_data(sparkline_svg.as_bytes()) {
                    ui.set_sparkline_image(sparkline_img);
                }
            });

            let sleep_sec = if usage.success {
                config_mgr_codex.get().codex_interval_sec
            } else {
                5 // fast retry on network or auth error
            };

            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(sleep_sec)) => {},
                _ = codex_trigger_rx.recv() => {},
            }
        }
    });

    // 3. Relay Worker Loop (Square + AIHub)
    let ui_weak_relay = ui.as_weak();
    let config_mgr_relay = config_mgr.clone();
    let aihub_client_relay = aihub_client.clone();
    let thumb_cache_relay = thumb_cache.clone();
    rt.spawn(async move {
        let square_client = SquareClient::new();
        let aihub_client = aihub_client_relay;
        let thumb_cache = thumb_cache_relay;

        loop {
            let cfg = config_mgr_relay.get();
            let square_res = square_client
                .fetch_data(
                    &cfg.square_selected_groups,
                    &cfg.square_selected_models,
                    &cfg.square_group_models,
                )
                .await;
            let aihub_res = aihub_client
                .fetch_data(
                    cfg.aihub_auto_mode,
                    &cfg.aihub_selected_providers,
                    &cfg.aihub_excluded_providers,
                )
                .await;

            let mut sq_models = Vec::new();
            for r in square_res.monitored_rows {
                sq_models.push(SquareRowModel {
                    group_name: r.group_name.into(),
                    short_name: r.short_name.into(),
                    focus_model: r.focus_model.into(),
                    ratio_str: r.ratio_str.into(),
                    output_price: r.output_price.into(),
                    tps: r.tps.into(),
                    ttft: r.ttft.into(),
                    latency: r.latency.into(),
                    success_rate: r.success_rate,
                    color: parse_hex_color(&r.color),
                });
            }

            let mut dlg_items = Vec::new();
            let mut ai_prepared = Vec::new();

            for p in &aihub_res.monitored_providers {
                let mut thumb = None;
                if p.has_image && !p.image_url.is_empty() {
                    let mut cache = thumb_cache.lock().await;
                    if let Some(cached_buf) = cache.get(&p.image_url) {
                        thumb = Some(cached_buf.clone());
                    } else if let Some(decoded_buf) = aihub_client.fetch_image_as_pixel_buffer(&p.image_url, 120, 75).await {
                        cache.insert(p.image_url.clone(), decoded_buf.clone());
                        thumb = Some(decoded_buf);
                    }
                }
                ai_prepared.push((p.clone(), thumb));
            }

            for p in &aihub_res.all_providers {
                let is_sel = cfg.aihub_selected_providers.contains(&p.code);
                let is_exc = cfg.aihub_excluded_providers.contains(&p.code);
                dlg_items.push(DialogProviderItem {
                    code: p.code.clone().into(),
                    multiplier_str: p.multiplier_str.clone().into(),
                    effective_multiplier_str: p.effective_multiplier_str.clone().into(),
                    cache_hit_rate: p.cache_hit_rate.clone().into(),
                    ttft_str: p.ttft_str.clone().into(),
                    success_rate_str: p.success_rate_str.clone().into(),
                    detection_status: p.detection_status.clone().into(),
                    has_image: p.has_image,
                    is_selected: is_sel,
                    is_excluded: is_exc,
                });
            }

            let balance_str = format!(
                "🟢 Square (已用: ${:.2})",
                square_res.balance_used.unwrap_or(12.34)
            );
            let stats_str = format!("1.1s · 99.2% · {}", aihub_res.updated_at);

            let selected_count = cfg.aihub_selected_providers.len() as i32;
            let excluded_count = cfg.aihub_excluded_providers.len() as i32;
            let total_count = dlg_items.len() as i32;

            let _ = ui_weak_relay.upgrade_in_event_loop(move |ui| {
                ui.set_square_balance_str(balance_str.into());
                ui.set_square_rows(Rc::new(VecModel::from(sq_models)).into());

                ui.set_aihub_stats_str(stats_str.into());

                let mut ai_models = Vec::new();
                for (p, thumb_opt) in ai_prepared {
                    let has_thumb = thumb_opt.is_some();
                    let thumb_image = thumb_opt.map(slint::Image::from_rgba8).unwrap_or_default();
                    ai_models.push(AIHubRowModel {
                        code: p.code.into(),
                        multiplier_str: p.multiplier_str.into(),
                        effective_multiplier_str: p.effective_multiplier_str.into(),
                        cache_hit_rate: p.cache_hit_rate.into(),
                        ttft_str: p.ttft_str.into(),
                        tps_str: p.tps_str.into(),
                        success_rate_str: p.success_rate_str.into(),
                        detection_status: p.detection_status.into(),
                        detection_label: p.detection_label.into(),
                        detection_dot: p.detection_dot.into(),
                        has_image: p.has_image,
                        image_url: p.image_url.into(),
                        group_id: p.group_id as i32,
                        has_thumb,
                        thumb_image,
                    });
                }
                ui.set_aihub_rows(Rc::new(VecModel::from(ai_models)).into());

                ui.set_dlg_selected_count(selected_count);
                ui.set_dlg_excluded_count(excluded_count);
                ui.set_dlg_total_count(total_count);
                ui.set_dlg_providers(Rc::new(VecModel::from(dlg_items)).into());
            });

            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(cfg.relay_interval_sec)) => {},
                _ = relay_trigger_rx.recv() => {},
            }
        }
    });

    // 4. Servers Worker Loop (5 GPU cards + 3 Host cards)
    let ui_weak_servers = ui.as_weak();
    rt.spawn(async move {
        let server_mgr = ServerManager::new();

        loop {
            let gpu_cards = server_mgr.query_gpu_cards();
            let host_stats = server_mgr.query_host_stats();

            let mut gpu_models = Vec::new();
            let mut gpu_vals = Vec::new();
            let mut gpu_val_colors = Vec::new();

            for c in &gpu_cards {
                gpu_models.push(GPUCardItem {
                    sid: c.sid.clone().into(),
                    index: c.index.clone().into(),
                    server_name: c.server_name.clone().into(),
                    model: c.model.clone().into(),
                    memory_used_gb: c.memory_used_gb,
                    memory_total_gb: c.memory_total_gb,
                    vram_pct: c.vram_pct,
                    utilization: c.utilization,
                    power_draw: c.power_draw.clone().into(),
                    user: c.user.clone().into(),
                    user_color: parse_hex_color(&c.user_color),
                    is_busy: c.is_busy,
                });

                let val_str = format!("{:.0}", c.vram_pct);
                gpu_vals.push(val_str.into());

                let col = if c.vram_pct >= 30.0 {
                    slint::Color::from_rgb_u8(239, 68, 68) // red
                } else if c.vram_pct >= 10.0 {
                    slint::Color::from_rgb_u8(245, 158, 11) // amber
                } else {
                    slint::Color::from_rgb_u8(16, 185, 129) // emerald #10B981
                };
                gpu_val_colors.push(col);
            }

            let mut host_models = Vec::new();
            for h in &host_stats {
                host_models.push(HostCardItem {
                    id: h.id.clone().into(),
                    name: h.name.clone().into(),
                    cpu_pct: h.cpu_pct,
                    mem_used_gb: h.mem_used_gb,
                    mem_total_gb: h.mem_total_gb,
                    mem_pct: h.mem_pct,
                    disk_free_gb: h.disk_free_gb,
                    disk_str: h.disk_str.clone().into(),
                    is_online: h.is_online,
                });
            }

            // GPU host CPUs (7号, 8号, 4号)
            let mut gpu_srv_cpu_vals: Vec<slint::SharedString> = Vec::new();
            let mut gpu_srv_cpu_colors: Vec<slint::Color> = Vec::new();

            let cpu_gpu7 = host_stats.iter().find(|h| h.id == "gpu7").map(|h| h.cpu_pct).unwrap_or(45.0);
            let cpu_gpu8 = host_stats.iter().find(|h| h.id == "gpu8").map(|h| h.cpu_pct).unwrap_or(46.0);
            let cpu_gpu4 = host_stats.iter().find(|h| h.id == "gpu4").map(|h| h.cpu_pct).unwrap_or(48.0);

            for val in [cpu_gpu7, cpu_gpu8, cpu_gpu4] {
                gpu_srv_cpu_vals.push(format!("{:.0}", val).into());
                let col = if val >= 30.0 {
                    slint::Color::from_rgb_u8(239, 68, 68) // #EF4444
                } else if val >= 10.0 {
                    slint::Color::from_rgb_u8(245, 158, 11) // #F59E0B
                } else {
                    slint::Color::from_rgb_u8(16, 185, 129) // #10B981
                };
                gpu_srv_cpu_colors.push(col);
            }

            // CPU host CPUs (quad, e5, 8375c)
            let mut srv_cpu_vals: Vec<slint::SharedString> = Vec::new();
            let mut srv_cpu_val_colors: Vec<slint::Color> = Vec::new();

            let cpu_quad = host_stats.iter().find(|h| h.id == "quad").map(|h| h.cpu_pct).unwrap_or(96.0);
            let cpu_e5 = host_stats.iter().find(|h| h.id == "e5").map(|h| h.cpu_pct).unwrap_or(96.0);
            let cpu_8375c = host_stats.iter().find(|h| h.id == "8375c").map(|h| h.cpu_pct).unwrap_or(46.0);

            for val in [cpu_quad, cpu_e5, cpu_8375c] {
                srv_cpu_vals.push(format!("{:.0}", val).into());
                let col = if val >= 30.0 {
                    slint::Color::from_rgb_u8(239, 68, 68) // #EF4444
                } else if val >= 10.0 {
                    slint::Color::from_rgb_u8(245, 158, 11) // #F59E0B
                } else {
                    slint::Color::from_rgb_u8(16, 185, 129) // #10B981
                };
                srv_cpu_val_colors.push(col);
            }

            let days = gantt_range_days_loop.load(std::sync::atomic::Ordering::SeqCst);
            let gantt_data = server_mgr.query_gantt_history(days);
            let mut gantt_models = Vec::new();
            for g in gantt_data {
                gantt_models.push(GanttRowModel {
                    task: g.task.into(),
                    has_activity: g.has_activity,
                    start_pct: g.start_pct,
                    width_pct: g.width_pct,
                    user: g.user.into(),
                    user_color: parse_hex_color(&g.user_color),
                });
            }

            let _ = ui_weak_servers.upgrade_in_event_loop(move |ui| {
                ui.set_gpu_cards(Rc::new(VecModel::from(gpu_models)).into());
                ui.set_host_cards(Rc::new(VecModel::from(host_models)).into());
                ui.set_gpu_vals(Rc::new(VecModel::from(gpu_vals)).into());
                ui.set_gpu_val_colors(Rc::new(VecModel::from(gpu_val_colors)).into());
                ui.set_gpu_srv_cpu_vals(Rc::new(VecModel::from(gpu_srv_cpu_vals)).into());
                ui.set_gpu_srv_cpu_colors(Rc::new(VecModel::from(gpu_srv_cpu_colors)).into());
                ui.set_srv_cpu_vals(Rc::new(VecModel::from(srv_cpu_vals)).into());
                ui.set_srv_cpu_val_colors(Rc::new(VecModel::from(srv_cpu_val_colors)).into());
                ui.set_gantt_rows(Rc::new(VecModel::from(gantt_models)).into());
            });

            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(3)) => {},
                _ = servers_trigger_rx.recv() => {},
            }
        }
    });

    // Run the native Slint event loop
    app_log!("[INIT] Entering Slint event loop...");
    let loop_res = slint::run_event_loop();
    app_log!("[INIT] Event loop exited with result: {:?}", loop_res);

    loop_res?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clone_from_slice() {
        let raw = vec![255u8; 100 * 100 * 4];
        let buf = slint::SharedPixelBuffer::<slint::Rgba8Pixel>::clone_from_slice(&raw, 100, 100);
        let _img = slint::Image::from_rgba8(buf);
    }

    #[test]
    fn test_all_dialogs_interaction() {
        let ui = MainWindow::new().unwrap();

        // 1. Pelican dialog test
        ui.set_pelican_provider_code("A018-Plus/K12".into());
        ui.set_pelican_status_text("共 2 张实测图".into());
        let raw = vec![128u8; 480 * 300 * 4];
        let buf = slint::SharedPixelBuffer::<slint::Rgba8Pixel>::clone_from_slice(&raw, 480, 300);
        let img = slint::Image::from_rgba8(buf);

        let cards = vec![
            PelicanDialogCardItem {
                id: "1".into(),
                published_at_str: "2026-10-15 12:00:00".into(),
                url: "https://example.com/1.png".into(),
                has_image: true,
                img,
            },
        ];
        ui.set_pelican_cards(std::rc::Rc::new(slint::VecModel::from(cards)).into());
        ui.set_pelican_dialog_open(true);
        ui.set_pelican_dialog_open(false);

        // 2. AIHub provider filter dialog test
        let items = vec![
            DialogProviderItem {
                code: "prov1".into(),
                multiplier_str: "1.0x".into(),
                effective_multiplier_str: "1.0x".into(),
                cache_hit_rate: "90%".into(),
                ttft_str: "0.5s".into(),
                success_rate_str: "100%".into(),
                detection_status: "passed".into(),
                has_image: false,
                is_selected: true,
                is_excluded: false,
            },
        ];
        ui.set_dlg_providers(std::rc::Rc::new(slint::VecModel::from(items)).into());
        ui.set_filter_dialog_open(true);

        let ui_weak = ui.as_weak();
        ui.on_toggle_dlg_selected(move |idx, sel| {
            if let Some(ui) = ui_weak.upgrade() {
                let model = ui.get_dlg_providers();
                if let Some(mut item) = model.row_data(idx as usize) {
                    item.is_selected = sel;
                    model.set_row_data(idx as usize, item);
                }
            }
        });

        ui.invoke_toggle_dlg_selected(0, false);
        let m = ui.get_dlg_providers();
        let row = m.row_data(0).unwrap();
        assert_eq!(row.is_selected, false);
        ui.set_filter_dialog_open(false);

        // 3. Square groups and models filter dialog test
        let groups = vec![
            SquareDialogGroupItem {
                name: "6-astra".into(),
                model: "GPT-6 Astra".into(),
                multiplier: "0.12x".into(),
                tps: "35.6 t/s".into(),
                latency: "26.39s".into(),
                success_rate: "100.0%".into(),
                is_selected: true,
            },
            SquareDialogGroupItem {
                name: "cc1".into(),
                model: "Claude Opus 5.5".into(),
                multiplier: "0.40x".into(),
                tps: "32.0 t/s".into(),
                latency: "18.00s".into(),
                success_rate: "100.0%".into(),
                is_selected: false,
            },
        ];
        let models = vec![
            SquareDialogModelItem {
                name: "claude-fable-5".into(),
                label: "claude-fable-5 (claude-fable-5)".into(),
                supported_groups_count: 7,
                is_selected: false,
            },
            SquareDialogModelItem {
                name: "gpt-6-astra".into(),
                label: "GPT-6 Astra (gpt-6-astra)".into(),
                supported_groups_count: 12,
                is_selected: true,
            },
        ];
        ui.set_dlg_square_groups(std::rc::Rc::new(slint::VecModel::from(groups)).into());
        ui.set_dlg_square_models(std::rc::Rc::new(slint::VecModel::from(models)).into());
        ui.set_square_filter_dialog_open(true);

        let ui_weak_sq = ui.as_weak();
        ui.on_toggle_square_group_selected(move |idx, sel| {
            if let Some(ui) = ui_weak_sq.upgrade() {
                let model = ui.get_dlg_square_groups();
                if let Some(mut item) = model.row_data(idx as usize) {
                    item.is_selected = sel;
                    model.set_row_data(idx as usize, item);
                }
            }
        });

        let ui_weak_sq_m = ui.as_weak();
        ui.on_toggle_square_model_selected(move |idx, sel| {
            if let Some(ui) = ui_weak_sq_m.upgrade() {
                let model = ui.get_dlg_square_models();
                if let Some(mut item) = model.row_data(idx as usize) {
                    item.is_selected = sel;
                    model.set_row_data(idx as usize, item);
                }
            }
        });

        ui.invoke_toggle_square_group_selected(1, true);
        let m_sq = ui.get_dlg_square_groups();
        let row1 = m_sq.row_data(1).unwrap();
        assert_eq!(row1.is_selected, true);

        ui.invoke_toggle_square_model_selected(0, true);
        let m_sq_models = ui.get_dlg_square_models();
        let m_row0 = m_sq_models.row_data(0).unwrap();
        assert_eq!(m_row0.is_selected, true);
        assert_eq!(m_row0.supported_groups_count, 7);

        ui.set_square_filter_dialog_open(false);
    }
}

