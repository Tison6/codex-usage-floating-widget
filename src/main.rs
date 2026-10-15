#![windows_subsystem = "windows"]

mod bluetooth;
mod codex;
mod config;
mod relay;
mod servers;

use bluetooth::BluetoothScanner;
use codex::{CodexActivityTracker, CodexUsageClient};
use config::ConfigManager;
use relay::{AIHubClient, SquareClient};
use servers::ServerManager;
use slint::{ComponentHandle, Model, VecModel};
use std::rc::Rc;
use std::sync::Arc;
use std::time::Duration;
use windows::core::w;
use windows::Win32::Foundation::{HWND, LPARAM, RECT, WPARAM};
use windows::Win32::UI::Input::KeyboardAndMouse::ReleaseCapture;
use windows::Win32::UI::WindowsAndMessaging::{
    FindWindowW, GetForegroundWindow, GetWindowRect, SendMessageW,
    HTCAPTION, WM_NCLBUTTONDOWN,
};
use tray_icon::{
    menu::{Menu, MenuItem, MenuEvent},
    TrayIconBuilder, Icon, TrayIconEvent,
};

slint::include_modules!();

fn get_window_hwnd() -> Option<HWND> {
    unsafe {
        if let Ok(hwnd) = FindWindowW(None, w!("状态小组件")) {
            if !hwnd.0.is_null() {
                return Some(hwnd);
            }
        }
        None
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
    println!("[INIT] Starting desktop floating widget...");
    let rt = tokio::runtime::Runtime::new()?;
    println!("[INIT] Tokio runtime initialized");
    let config_mgr = Arc::new(ConfigManager::new("config.json"));
    let cfg = config_mgr.get();
    println!("[INIT] Config loaded. Mini mode: {}", cfg.is_mini_mode);

    let ui = MainWindow::new()?;
    println!("[INIT] MainWindow instantiated");

    // Initial properties from config
    ui.set_is_mini(cfg.is_mini_mode);
    ui.set_ui_scale(cfg.scale);
    ui.set_cfg_always_on_top(cfg.always_on_top);
    ui.set_aihub_auto_mode(cfg.aihub_auto_mode);
    ui.set_cfg_codex_interval(cfg.codex_interval_sec as i32);
    ui.set_cfg_relay_interval(cfg.relay_interval_sec as i32);
    ui.set_cfg_autostart(cfg.autostart);

    ui.show()?;
    println!("[INIT] MainWindow shown");

    // Initial Window Position
    ui.window().set_position(slint::PhysicalPosition::new(
        cfg.window_pos[0],
        cfg.window_pos[1],
    ));
    println!("[INIT] Window position set to [{}, {}]", cfg.window_pos[0], cfg.window_pos[1]);

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
                        ui.set_is_mini(!cur);
                        config_mgr_tray.update(|c| c.is_mini_mode = !cur);
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
                            ui.set_is_mini(!cur);
                            config_mgr_tray.update(|c| c.is_mini_mode = !cur);
                        }
                    }
                    _ => {}
                }
            }
        },
    );

    // --- UI Callbacks ---

    // Window Dragging Callback
    let config_mgr_drag = config_mgr.clone();
    ui.on_drag_window(move || {
        unsafe {
            if let Some(hwnd) = get_window_hwnd() {
                let _ = ReleaseCapture();
                let _ = SendMessageW(
                    hwnd,
                    WM_NCLBUTTONDOWN,
                    WPARAM(HTCAPTION as usize),
                    LPARAM(0),
                );

                // Update saved position after drag
                let mut rect = RECT::default();
                if GetWindowRect(hwnd, &mut rect).is_ok() {
                    config_mgr_drag.update(|c| {
                        c.window_pos = [rect.left, rect.top];
                    });
                }
            }
        }
    });

    // Expand / Collapse Callbacks
    let last_expand_time = Arc::new(std::sync::atomic::AtomicU64::new(0));
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

            unsafe {
                if let Some(hwnd) = get_window_hwnd() {
                    let _ = windows::Win32::UI::WindowsAndMessaging::SetForegroundWindow(hwnd);
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
            ui.set_settings_dialog_open(false);
        }
    });

    ui.on_exit_app_clicked(move || {
        let _ = slint::quit_event_loop();
    });

    let relay_tx_sq = relay_trigger_tx.clone();
    ui.on_open_square_filter_clicked(move || {
        let _ = relay_tx_sq.try_send(());
    });

    // Auto Collapse on Focus Loss (every 250ms)
    let auto_collapse_timer = slint::Timer::default();
    let ui_weak_collapse = ui.as_weak();
    let last_expand_time_timer = last_expand_time.clone();
    auto_collapse_timer.start(
        slint::TimerMode::Repeated,
        Duration::from_millis(250),
        move || {
            if let Some(ui) = ui_weak_collapse.upgrade() {
                if !ui.get_is_mini() && !ui.get_filter_dialog_open() && !ui.get_settings_dialog_open() {
                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);
                    let exp_ms = last_expand_time_timer.load(std::sync::atomic::Ordering::SeqCst);
                    if now_ms.saturating_sub(exp_ms) < 1000 {
                        return; // 1-second grace period right after clicking expand
                    }

                    unsafe {
                        let fg = GetForegroundWindow();
                        if !fg.0.is_null() {
                            if let Some(hwnd) = get_window_hwnd() {
                                if fg != hwnd {
                                    ui.set_is_mini(true);
                                }
                            }
                        }
                    }
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

            tokio::time::sleep(Duration::from_secs(60)).await;
        }
    });

    // 2. Codex Worker Loop
    let ui_weak_codex = ui.as_weak();
    let config_mgr_codex = config_mgr.clone();
    rt.spawn(async move {
        let mut client = CodexUsageClient::new(&config_mgr_codex.get().auth_file_path);
        let activity = CodexActivityTracker::new();

        loop {
            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(config_mgr_codex.get().codex_interval_sec)) => {},
                _ = codex_trigger_rx.recv() => {},
            }

            let usage = client.fetch_usage().await;
            let (is_running, _) = activity.check_is_running();

            let five_h_pct = usage
                .five_hour_window
                .as_ref()
                .map(|w| w.remaining_percent)
                .unwrap_or(100);
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

            let _ = ui_weak_codex.upgrade_in_event_loop(move |ui| {
                ui.set_codex_running(is_running);
                ui.set_codex_5h_val(five_h_pct.to_string().into());
                ui.set_codex_wk_val(weekly_pct.to_string().into());
                ui.set_time_str(now_time.into());

                ui.set_plan_type(plan.into());
                ui.set_weekly_remaining_pct(weekly_pct);
                ui.set_countdown_str(countdown.into());
                ui.set_reset_credits(credits);
                ui.set_updated_time(updated.into());
            });
        }
    });

    // 3. Relay Worker Loop (Square + AIHub)
    let ui_weak_relay = ui.as_weak();
    let config_mgr_relay = config_mgr.clone();
    rt.spawn(async move {
        let square_client = SquareClient::new();
        let aihub_client = AIHubClient::new();

        loop {
            let cfg = config_mgr_relay.get();
            let square_res = square_client
                .fetch_data(&cfg.square_selected_groups, &cfg.square_group_models)
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
                    color: r.color.into(),
                });
            }

            let mut ai_models = Vec::new();
            let mut dlg_items = Vec::new();

            for p in &aihub_res.monitored_providers {
                ai_models.push(AIHubRowModel {
                    code: p.code.clone().into(),
                    multiplier_str: p.multiplier_str.clone().into(),
                    effective_multiplier_str: p.effective_multiplier_str.clone().into(),
                    cache_hit_rate: p.cache_hit_rate.clone().into(),
                    ttft_str: p.ttft_str.clone().into(),
                    tps_str: p.tps_str.clone().into(),
                    success_rate_str: p.success_rate_str.clone().into(),
                    detection_status: p.detection_status.clone().into(),
                    detection_label: p.detection_label.clone().into(),
                    detection_dot: p.detection_dot.clone().into(),
                    has_image: p.has_image,
                    image_url: p.image_url.clone().into(),
                });
            }

            for p in &aihub_res.monitored_providers {
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
                    is_busy: c.is_busy,
                });

                let val_str = format!("{:.0}", c.vram_pct);
                gpu_vals.push(val_str.into());

                let col = if c.is_busy || c.vram_pct > 30.0 {
                    slint::Color::from_rgb_u8(239, 68, 68) // red
                } else if c.vram_pct > 10.0 {
                    slint::Color::from_rgb_u8(245, 158, 11) // amber
                } else {
                    slint::Color::from_rgb_u8(0, 230, 118) // #00e676
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
                    is_online: h.is_online,
                });
            }

            // GPU host CPUs (7号, 8号, 4号)
            let gpu_srv_cpu_vals: Vec<slint::SharedString> = vec!["3".into(), "4".into(), "1".into()];
            let gpu_srv_cpu_colors: Vec<slint::Color> = vec![
                slint::Color::from_rgb_u8(0, 230, 118),
                slint::Color::from_rgb_u8(0, 230, 118),
                slint::Color::from_rgb_u8(0, 230, 118),
            ];

            // CPU host CPUs (quad, e5, 8375c)
            let srv_cpu_vals: Vec<slint::SharedString> = vec!["93".into(), "92".into(), "49".into()];
            let srv_cpu_val_colors: Vec<slint::Color> = vec![
                slint::Color::from_rgb_u8(239, 68, 68),
                slint::Color::from_rgb_u8(239, 68, 68),
                slint::Color::from_rgb_u8(245, 158, 11),
            ];

            let _ = ui_weak_servers.upgrade_in_event_loop(move |ui| {
                ui.set_gpu_cards(Rc::new(VecModel::from(gpu_models)).into());
                ui.set_host_cards(Rc::new(VecModel::from(host_models)).into());
                ui.set_gpu_vals(Rc::new(VecModel::from(gpu_vals)).into());
                ui.set_gpu_val_colors(Rc::new(VecModel::from(gpu_val_colors)).into());
                ui.set_gpu_srv_cpu_vals(Rc::new(VecModel::from(gpu_srv_cpu_vals)).into());
                ui.set_gpu_srv_cpu_colors(Rc::new(VecModel::from(gpu_srv_cpu_colors)).into());
                ui.set_srv_cpu_vals(Rc::new(VecModel::from(srv_cpu_vals)).into());
                ui.set_srv_cpu_val_colors(Rc::new(VecModel::from(srv_cpu_val_colors)).into());
            });

            tokio::select! {
                _ = tokio::time::sleep(Duration::from_secs(10)) => {},
                _ = servers_trigger_rx.recv() => {},
            }
        }
    });

    // Run the native Slint event loop
    println!("[INIT] Entering Slint event loop...");
    slint::run_event_loop()?;
    println!("[INIT] Event loop exited");

    Ok(())
}
