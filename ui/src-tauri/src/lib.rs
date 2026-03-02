use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager,
};

#[tauri::command]
fn toggle_chat_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

#[tauri::command]
fn get_backend_port() -> u16 {
    8000
}

/// Pin the window to a screen edge (top, bottom, left, right).
/// Calculates position based on primary monitor dimensions.
#[tauri::command]
fn pin_to_edge(app: tauri::AppHandle, edge: String) {
    if let Some(window) = app.get_webview_window("main") {
        // Get window and screen details
        let win_size = window.outer_size().unwrap_or_default();
        let monitor = window.current_monitor().ok().flatten();

        if let Some(monitor) = monitor {
            let screen = monitor.size();
            let scale = monitor.scale_factor();
            let screen_w = (screen.width as f64 / scale) as i32;
            let screen_h = (screen.height as f64 / scale) as i32;
            let win_w = (win_size.width as f64 / scale) as i32;
            let win_h = (win_size.height as f64 / scale) as i32;

            let (x, y) = match edge.as_str() {
                "right" => (screen_w - win_w - 12, (screen_h - win_h) / 2),
                "left" => (12, (screen_h - win_h) / 2),
                "top" => ((screen_w - win_w) / 2, 12),
                "bottom" => ((screen_w - win_w) / 2, screen_h - win_h - 48), // 48 for taskbar
                _ => return,
            };

            let _ = window.set_position(tauri::Position::Logical(
                tauri::LogicalPosition::new(x as f64, y as f64),
            ));
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--autostart"]),
        ))
        .setup(|app| {
            // Build tray menu
            let show_item = MenuItem::with_id(app, "show", "Open Zora", true, None::<&str>)?;
            let settings_item =
                MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

            let menu = Menu::with_items(app, &[&show_item, &settings_item, &quit_item])?;

            // Build tray icon
            TrayIconBuilder::with_id("zora-tray")
                .menu(&menu)
                .tooltip("Zora AI Desktop Companion")
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "settings" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                            let _ = window.eval("window.__ZORA_OPEN_SETTINGS__()");
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click { .. } = event {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            // Start Python FastAPI sidecar
            let shell = app.shell();
            let sidecar_command = shell
                .sidecar("../sidecar/zora-api")
                .expect("failed to create sidecar command");

            let (mut _rx, _child) = sidecar_command.spawn().unwrap_or_else(|e| {
                eprintln!("Failed to start Zora API sidecar: {}", e);
                panic!("Sidecar failed to start")
            });

            println!("Zora API sidecar started on port 8000");

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            toggle_chat_window,
            get_backend_port,
            pin_to_edge
        ])
        .run(tauri::generate_context!())
        .expect("error while running Zora");
}
