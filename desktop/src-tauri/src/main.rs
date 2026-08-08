// PDC Policy Generator - desktop shell.
//
// The app itself is unchanged: a FastAPI server serving the React SPA. This
// binary only starts that server on a free port, waits for it to answer, and
// points a webview at it. Everything the user sees is still the web UI, so the
// browser and desktop builds cannot drift apart.
//
// Paths are resolved through Tauri's path helpers, never hardcoded - the
// install root is not predictable and the app directory is read-only.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod server;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use tauri::{Manager, State};

use server::{last_server_output, Server};

/// Shared so the window-close handler can stop the server without borrowing
/// from the window - going through `State` there ties the borrow to a
/// temporary, which does not outlive the closure.
type SharedServer = Arc<Mutex<Option<Server>>>;

struct AppState {
    server: SharedServer,
}

/// Strip Windows' verbatim `\\?\` prefix.
///
/// Tauri's `resource_dir()` canonicalises, which on Windows yields an
/// extended-length path like `\\?\C:\Program Files\...`. Those are legal for
/// most file APIs, and the shell's own `is_file()` checks pass happily - which
/// is why the diagnostics reported everything found while nothing worked.
///
/// They are NOT legal as a process WORKING DIRECTORY: `SetCurrentDirectory`
/// rejects the verbatim form, so `boot.py`'s `os.chdir()` raised and the server
/// died before uvicorn ever bound a port.
///
/// Only safe to strip for ordinary drive paths - a genuine UNC (`\\?\UNC\...`)
/// or a >260-char path still needs the prefix, so those are left alone.
fn strip_verbatim(p: &Path) -> PathBuf {
    let s = p.to_string_lossy();
    if let Some(rest) = s.strip_prefix(r"\\?\") {
        // Drive-letter paths only: "C:\..." - never \\?\UNC\server\share.
        let bytes = rest.as_bytes();
        let drive_path = bytes.len() >= 3
            && bytes[0].is_ascii_alphabetic()
            && bytes[1] == b':'
            && bytes[2] == b'\\';
        if drive_path && rest.len() < 250 {
            return PathBuf::from(rest);
        }
    }
    p.to_path_buf()
}

/// Where the app root (the policy_generator package) lives.
///
/// Packaged: bundle.resources drops the staged tree next to the executable.
/// Dev (`npm run tauri:dev`): walk up to the checkout and use it in place, so
/// there is no build step between editing Python and seeing the change.
fn app_dir(handle: &tauri::AppHandle) -> PathBuf {
    // The staged tree mirrors the repo (policy_generator/ + frontend/dist),
    // because api.py resolves the built UI as REPO_ROOT/frontend/dist - one
    // level up from the package. Flattening it would leave the server up with
    // nothing to serve.
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = strip_verbatim(&res.join("app"));
        if packaged.join("policy_generator").join("api.py").is_file() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

/// boot.py - staged inside the app tree, or taken from the checkout in dev.
/// Mirrors app_dir()'s packaged-then-checkout resolution deliberately: one rule,
/// applied twice, beats two rules that can disagree about which tree is live.
fn boot_py(handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = strip_verbatim(&res.join("app").join("boot.py"));
        if packaged.is_file() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("boot.py")
}

/// Per-user data directory. The app keeps no state of its own here - its one
/// write lands beside the loaded Registry - but the shell's startup report
/// needs a writable home, and Program Files is not one.
fn state_dir(handle: &tauri::AppHandle) -> PathBuf {
    handle
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// The registries folders this machine could hand off from, newest-first -
/// mirroring policy_generator/registry.py's discover_registries() APPDATA
/// candidates. The full discovery (checkout siblings, POLICY_REGISTRY_DIR)
/// belongs to the app; the splash only answers "is there anything to load?".
fn registry_files() -> Vec<String> {
    let Some(appdata) = std::env::var_os("APPDATA") else { return Vec::new() };
    let mut found: Vec<(std::time::SystemTime, String)> = Vec::new();
    for sub in ["com.pentaho.pdc-glossary", "PDC-Glossary"] {
        let dir = PathBuf::from(&appdata).join(sub).join("registries");
        let Ok(entries) = std::fs::read_dir(&dir) else { continue };
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if name.starts_with("registry.") && name.ends_with(".json") {
                let t = e.metadata().and_then(|m| m.modified())
                    .unwrap_or(std::time::SystemTime::UNIX_EPOCH);
                found.push((t, name));
            }
        }
    }
    found.sort_by(|a, b| b.0.cmp(&a.0));
    found.into_iter().map(|(_, n)| n).collect()
}

/// The splash page polls this until the server answers, then navigates to it.
#[tauri::command]
fn server_url(state: State<'_, AppState>) -> Option<String> {
    state.server.lock().ok()?.as_ref().map(|s| s.url())
}

/// The backend's output so far, for the splash to show WHILE it waits.
///
/// Deliberately separate from `diagnostics`: the splash polls this every few
/// hundred ms and `diagnostics` stats several paths, which is wasted work on a
/// hot loop. It also means the startup screen shows what is really happening -
/// uvicorn's own "Started server process" / "Application startup complete" -
/// rather than a bar that moves whether or not anything is working.
#[tauri::command]
fn server_log() -> Vec<String> {
    last_server_output()
}

/// False once the backend process has exited. Lets the splash fail fast on a
/// dead server instead of waiting out a timeout meant for a slow one.
#[tauri::command]
fn server_alive(state: State<'_, AppState>) -> bool {
    let Ok(mut guard) = state.server.lock() else {
        return true; // cannot tell - assume alive rather than cry wolf
    };
    match guard.as_mut() {
        Some(srv) => !srv.exited().unwrap_or(false),
        None => false, // never started
    }
}

/// True once the backend answers /api/version. See server::http_ok for why this
/// cannot be a fetch() from the splash.
#[tauri::command]
fn server_ready(state: State<'_, AppState>) -> bool {
    let Ok(guard) = state.server.lock() else { return false };
    match guard.as_ref() {
        Some(srv) => server::http_ok(srv.port, "/api/version"),
        None => false,
    }
}

/// What this install can see: whether the Glossary app has left a Registry to
/// hand off. First launch is exactly when "will it find my export?" gets
/// asked, and the answer otherwise waits for the app's Load page.
#[tauri::command]
fn env_report(handle: tauri::AppHandle) -> serde_json::Value {
    let regs = registry_files();
    serde_json::json!({
        // Shown in the header at all times. Which build someone is running is
        // the first question on any failure, and it must not depend on the
        // backend answering - the backend is what failed.
        "version": handle.package_info().version.to_string(),
        "state_dir": state_dir(&handle).to_string_lossy(),
        "registries": regs.len(),
        "newest_registry": regs.first().cloned(),
        "ollama": server::port_open("127.0.0.1", 11434),
    })
}

/// Stop the backend and start it again, in place.
///
/// Until now the only recovery from a failed start was closing the window and
/// relaunching - which is what everyone tries first anyway, so the app may as
/// well do it. A port already in use, an antivirus holding a file for a moment,
/// a service starting slowly: all clear on a second attempt, and none of them
/// deserve a reinstall.
///
/// A NEW free port is chosen, deliberately: if the last failure was the port,
/// reusing it would fail the same way.
#[tauri::command]
fn restart_server(handle: tauri::AppHandle, state: State<'_, AppState>) -> bool {
    let resource_dir = strip_verbatim(&handle.path().resource_dir().unwrap_or_default());
    let app_dir = app_dir(&handle);
    let boot_py = boot_py(&handle);
    let state_dir = state_dir(&handle);

    let Ok(mut guard) = state.server.lock() else { return false };
    if let Some(srv) = guard.as_mut() {
        srv.stop();
    }
    *guard = None;

    match Server::start(&resource_dir, &boot_py, &app_dir, &state_dir) {
        Ok(srv) => {
            *guard = Some(srv);
            true
        }
        Err(e) => {
            eprintln!("restart failed: {e}");
            false
        }
    }
}

/// Open the Glossary hand-off folder (or the shell's own data folder when no
/// registries exist yet) in Explorer. It is the answer to "where does my
/// Registry go?", and typing an %APPDATA% path by hand is nobody's idea of a
/// good time.
#[tauri::command]
fn open_state_dir(handle: tauri::AppHandle) -> String {
    if let Some(appdata) = std::env::var_os("APPDATA") {
        let handoff = PathBuf::from(&appdata)
            .join("com.pentaho.pdc-glossary")
            .join("registries");
        if handoff.is_dir() {
            return handoff.to_string_lossy().into_owned();
        }
    }
    let dir = state_dir(&handle);
    std::fs::create_dir_all(&dir).ok();
    dir.to_string_lossy().into_owned()
}

/// Everything a support email needs, as one block of text.
///
/// Built HERE rather than assembled in JavaScript so that the version, the OS
/// and the resolved paths cannot be omitted by a page that failed to load
/// properly - which, on a startup failure, is exactly the situation. Also
/// written to a file, because a 40-line traceback survives a paste badly and an
/// attachment does not.
#[tauri::command]
fn save_report(handle: tauri::AppHandle) -> serde_json::Value {
    let diag = diagnostics(handle.clone());
    let env = env_report(handle.clone());

    let mut out = String::new();
    out.push_str("PDC Policy Generator - startup report\n");
    out.push_str("=====================================\n\n");
    out.push_str(&format!("version   : {}\n", handle.package_info().version));
    out.push_str(&format!("os        : {} {}\n", std::env::consts::OS, std::env::consts::ARCH));
    out.push_str(&format!("exe       : {}\n",
        std::env::current_exe().map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|_| "unknown".into())));
    out.push_str("\n-- what the shell resolved ------------------------\n");
    out.push_str(&serde_json::to_string_pretty(&diag).unwrap_or_default());
    out.push_str("\n\n-- this install ----------------------------------\n");
    out.push_str(&serde_json::to_string_pretty(&env).unwrap_or_default());
    out.push_str("\n\n-- backend output --------------------------------\n");
    let log = last_server_output();
    if log.is_empty() {
        out.push_str("(the backend produced no output at all)\n");
    } else {
        for line in log {
            out.push_str(&line);
            out.push('\n');
        }
    }

    // Into the per-user data directory, which is writable by definition - the
    // install directory is not, and a report that cannot be written is worse
    // than none.
    let path = state_dir(&handle).join("startup-report.txt");
    let written = std::fs::create_dir_all(state_dir(&handle))
        .and_then(|_| std::fs::write(&path, &out))
        .is_ok();

    serde_json::json!({
        "text": out,
        "path": path.to_string_lossy(),
        "written": written,
    })
}

/// Ask the LOCAL model what to try before emailing anyone.
///
/// The app itself uses no LLM - it is deterministic by design - but if the
/// machine happens to run Ollama (the Glossary or Insights install put it
/// there), a startup failure is a fine moment to use it. Local only: the
/// report carries file paths and a traceback.
///
/// Returns a `status` the panel can act on rather than a bare string, because
/// "Ollama is not running" and "Ollama is running but has no model" need
/// different words in front of a stuck user.
#[tauri::command]
async fn llm_suggest(handle: tauri::AppHandle) -> serde_json::Value {
    // Off the UI thread: generation takes seconds to a minute, and blocking here
    // would freeze the very panel that is supposed to be helping.
    tauri::async_runtime::spawn_blocking(move || {
        if !server::port_open("127.0.0.1", 11434) {
            return serde_json::json!({ "status": "no_ollama" });
        }
        let Some(model) = server::ollama::first_model() else {
            return serde_json::json!({ "status": "no_model" });
        };
        let report = save_report(handle);
        let text = report.get("text").and_then(|t| t.as_str()).unwrap_or("");

        let prompt = format!(
            "You are helping a Windows user whose desktop application failed to start.

             The application is a local FastAPI server launched by a Tauri shell. It ships              its own Python runtime. Below is its startup report.

             Give AT MOST three concrete things to try, most likely first. Each one line,              starting with a dash. Prefer checks the user can actually perform on Windows.              If the report shows a specific Python error, address THAT rather than giving              generic advice. Do not apologise, do not restate the problem, do not suggest              contacting support - they already have that option.

             --- report ---
{text}"
        );

        match server::ollama::suggest(&model, &prompt) {
            Some(s) if !s.is_empty() => {
                serde_json::json!({ "status": "ok", "model": model, "text": s })
            }
            _ => serde_json::json!({ "status": "failed", "model": model }),
        }
    })
    .await
    .unwrap_or_else(|_| serde_json::json!({ "status": "failed" }))
}

/// Surfaced on the splash when startup fails, so a dead backend reads as an
/// error message rather than a permanently blank window.
#[tauri::command]
fn diagnostics(handle: tauri::AppHandle) -> serde_json::Value {
    let dir = app_dir(&handle);
    serde_json::json!({
        "app_dir": dir.to_string_lossy(),
        "api_py_found": dir.join("policy_generator").join("api.py").is_file(),
        "boot_py": boot_py(&handle).to_string_lossy(),
        "boot_py_found": boot_py(&handle).is_file(),
        "state_dir": state_dir(&handle).to_string_lossy(),
        "vendored_python": handle
            .path()
            .resource_dir()
            .map(|r| strip_verbatim(&r).join("python").join("python.exe").is_file())
            .unwrap_or(false),
        // The last thing the backend said before dying. Without this a failed
        // start is a blank window and a shrug: every path check passes, because
        // the paths were never the problem.
        "server_log": last_server_output(),
    })
}

fn main() {
    let shared: SharedServer = Arc::new(Mutex::new(None));
    let for_close = shared.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            server: shared.clone(),
        })
        .invoke_handler(tauri::generate_handler![server_url, server_log, server_alive, server_ready, env_report, diagnostics, save_report, llm_suggest, restart_server, open_state_dir])
        .setup(move |app| {
            let handle = app.handle().clone();
            let resource_dir = strip_verbatim(&handle.path().resource_dir().unwrap_or_default());
            let app_dir = app_dir(&handle);
            let boot_py = boot_py(&handle);
            let state_dir = state_dir(&handle);
            std::fs::create_dir_all(&state_dir).ok();

            match Server::start(&resource_dir, &boot_py, &app_dir, &state_dir) {
                Ok(srv) => {
                    *shared.lock().unwrap() = Some(srv);
                }
                Err(e) => {
                    // Do not abort: the splash reports this, with the
                    // diagnostics above, which is far more useful than a window
                    // that never appears.
                    eprintln!("failed to start the backend: {e}");
                }
            }
            Ok(())
        })
        .on_window_event(move |_window, event| {
            // Stop the server on close rather than waiting for process exit, so
            // the port is free immediately if the user relaunches.
            if let tauri::WindowEvent::Destroyed = event {
                if let Ok(mut guard) = for_close.lock() {
                    if let Some(srv) = guard.as_mut() {
                        srv.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running the PDC Policy Generator shell");
}
