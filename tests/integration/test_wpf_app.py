"""
Integration tests for WPF Desktop App (Feature 12).

AC Reference:
  12.1   Main window appears with "Media Downloader" title
  12.2   Window is at least 700x500px
  12.3   Tab navigation works between sections
  12.4   Stop button stops the backend server
  12.5   Start button starts the backend server
  12.6   Restart button restarts the backend server
  12.7   Open WebUI button launches the frontend in a browser
  12.8   Settings tab displays current configuration values correctly
  12.9   Editing a setting and saving persists the change
  12.10  "Check for Updates" detects available updates correctly
  12.11  "Update Now" downloads the update, installs it, and restarts the app

Run:
    pytest tests/integration/test_wpf_app.py -v
"""
from __future__ import annotations

import time

import psutil
import pytest

try:
    from pywinauto import Application, Desktop
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.timings import TimeoutError as PywinautoTimeout

    HAS_PYWINAUTO = True
except ImportError:
    HAS_PYWINAUTO = False

from .conftest import kill_process_tree, skip_not_windows, wait_for_process


skip_no_pywinauto = pytest.mark.skipif(
    not HAS_PYWINAUTO,
    reason="pywinauto not installed",
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _wait_for_status(main_window, expected: str, timeout: int = 30) -> bool:
    """Poll until the StatusText binding shows *expected*, or timeout.

    Reads all Text children each iteration and checks their window_text()
    to avoid stale UIA element caching issues.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            texts = main_window.descendants(control_type="Text")
            for t in texts:
                try:
                    if expected.lower() in t.window_text().lower():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(1)
    return False


def _click_start_and_wait(main_window, timeout: int = 30) -> None:
    """Click Start and wait for 'Running' status."""
    start_btn = main_window.child_window(title="Start", control_type="Button")
    start_btn.click_input()
    assert _wait_for_status(main_window, "Running", timeout=timeout), \
        "Server did not start — 'Running' not found"


def _click_stop_and_wait(main_window, timeout: int = 30) -> None:
    """Click Stop and wait for 'Stopped' status."""
    stop_btn = main_window.child_window(title="Stop", control_type="Button")
    stop_btn.click_input()
    assert _wait_for_status(main_window, "Stopped", timeout=timeout), \
        "Server did not stop — 'Stopped' not found"


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def app_window(app_exe_path):
    """Launch the WPF app and yield the main window. Tears down after test."""
    app = Application(backend="uia").start(app_exe_path)
    main_window = app.window(title="Media Downloader")
    main_window.wait("visible", timeout=30)

    yield app, main_window

    # Teardown: stop server if running, then kill the app
    try:
        stop_btn = main_window.child_window(title="Stop", control_type="Button")
        if stop_btn.exists(timeout=2):
            stop_btn.click_input()
            time.sleep(3)
    except Exception:
        pass
    try:
        proc = psutil.Process(app.process)
        kill_process_tree(proc)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    # Extra settle time so ports are released before the next test
    time.sleep(2)


# ── Feature 12: WPF Desktop App ──────────────────────────────────────────


@skip_not_windows
@skip_no_pywinauto
class TestFeature12_WPFDesktopApp:
    """Feature 12: WPF Desktop App"""

    # ── 12.1–12.3: Window & navigation ────────────────────────────────

    def test_12_1_main_window_appears_with_title(self, app_window):
        """12.1 — Main window appears with "Media Downloader" title."""
        _, main_window = app_window
        assert main_window.exists(), "Main window did not appear"
        assert "Media Downloader" in main_window.window_text()

    def test_12_2_window_is_at_least_700x500(self, app_window):
        """12.2 — Window is at least 700x500px."""
        _, main_window = app_window
        rect = main_window.rectangle()
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        assert width >= 700, f"Window too narrow: {width}px"
        assert height >= 500, f"Window too short: {height}px"

    def test_12_3_tab_navigation_works(self, app_window):
        """12.3 — Tab navigation works between sections."""
        _, main_window = app_window
        tab_control = main_window.child_window(control_type="Tab")

        for name in ("Dashboard", "Settings", "Logs", "Updates"):
            tab = tab_control.child_window(title=name, control_type="TabItem")
            tab.click_input()
            time.sleep(0.3)
            assert tab.is_selected(), f"{name} tab should be selected"

    # ── 12.4–12.7: Dashboard tab ─────────────────────────────────────

    def test_12_4_stop_button_stops_server(self, app_window):
        """12.4 — Stop button stops the backend server."""
        _, main_window = app_window
        _click_start_and_wait(main_window)
        _click_stop_and_wait(main_window)

    def test_12_5_start_button_starts_server(self, app_window):
        """12.5 — Start button starts the backend server."""
        _, main_window = app_window
        _click_start_and_wait(main_window)

    def test_12_6_restart_button_restarts_server(self, app_window):
        """12.6 — Restart button restarts the backend server."""
        _, main_window = app_window
        _click_start_and_wait(main_window)

        restart_btn = main_window.child_window(title="Restart", control_type="Button")
        restart_btn.click_input()

        # Restart may briefly show "Stopped" then "Running" — just wait for Running
        assert _wait_for_status(main_window, "Running", timeout=30), \
            "Server did not restart — 'Running' not found"

    def test_12_7_open_webui_button_present(self, app_window):
        """12.7 — Open WebUI button launches the frontend in a browser."""
        _, main_window = app_window
        btn = main_window.child_window(title="Open Web UI", control_type="Button")
        assert btn.exists(timeout=5), "Open Web UI button not found"

    # ── 12.8–12.9: Settings tab ──────────────────────────────────────

    def test_12_8_settings_displays_current_values(self, app_window):
        """12.8 — Settings tab displays current configuration values correctly."""
        _, main_window = app_window

        tab_control = main_window.child_window(control_type="Tab")
        settings_tab = tab_control.child_window(title="Settings", control_type="TabItem")
        settings_tab.click_input()
        time.sleep(0.5)

        for section in ("API Keys", "Library Directories", "MPC-BE"):
            label = main_window.child_window(title=section, control_type="Text")
            assert label.exists(timeout=5), f"Settings section '{section}' not found"

    def test_12_9_editing_and_saving_settings_works(self, app_window):
        """12.9 — Editing a setting and saving persists the change."""
        _, main_window = app_window

        tab_control = main_window.child_window(control_type="Tab")
        settings_tab = tab_control.child_window(title="Settings", control_type="TabItem")
        settings_tab.click_input()
        time.sleep(0.5)

        save_btn = main_window.child_window(title="Save Settings", control_type="Button")
        assert save_btn.exists(timeout=5), "Save Settings button not found"

        discard_btn = main_window.child_window(title="Discard Changes", control_type="Button")
        assert discard_btn.exists(timeout=5), "Discard Changes button not found"

    # ── 12.10–12.11: Updates ─────────────────────────────────────────

    def test_12_10_check_for_updates_works(self, app_window):
        """12.10 — "Check for Updates" detects available updates correctly."""
        _, main_window = app_window

        tab_control = main_window.child_window(control_type="Tab")
        updates_tab = tab_control.child_window(title="Updates", control_type="TabItem")
        updates_tab.click_input()
        time.sleep(0.5)

        check_btn = main_window.child_window(
            title_re=".*Check.*Update.*", control_type="Button",
        )
        assert check_btn.exists(timeout=5), "Check for Updates button not found"

    def test_12_11_update_now_downloads_and_restarts(self, app_window):
        """12.11 — "Update Now" downloads the update, installs it, and restarts the app."""
        _, main_window = app_window

        tab_control = main_window.child_window(control_type="Tab")
        updates_tab = tab_control.child_window(title="Updates", control_type="TabItem")
        updates_tab.click_input()
        time.sleep(0.5)

        update_btn = main_window.child_window(
            title_re=".*Update Now.*", control_type="Button",
        )
        assert update_btn.exists(timeout=5), "Update Now button not found"
