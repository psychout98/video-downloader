"""
Integration tests for the WPF desktop application using pywinauto.

Uses the UIA (UI Automation) backend since WPF natively exposes
the Windows UI Automation tree.

Requirements:
    - Windows OS
    - Built MediaDownloader.exe (from dotnet publish or dist/)
    - pywinauto installed

Run:
    pytest tests/integration/test_wpf_app.py -v
"""
from __future__ import annotations

import subprocess
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


@skip_not_windows
@skip_no_pywinauto
class TestAppLaunch:
    """Test the WPF application launches and shows its main window."""

    @pytest.fixture(autouse=True)
    def _launch_app(self, app_exe_path):
        """Launch the app and tear it down after each test."""
        self.app = Application(backend="uia").start(
            app_exe_path,
            timeout=30,
        )
        # Wait for the main window to appear
        try:
            self.main_window = self.app.window(title="Media Downloader", timeout=15)
            self.main_window.wait("visible", timeout=15)
        except Exception:
            # If window didn't appear, still try to clean up
            pass

        yield

        # Teardown: kill the process tree
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_main_window_appears(self):
        """The main window should appear with the correct title."""
        assert self.main_window.exists(), "Main window did not appear"
        assert "Media Downloader" in self.main_window.window_text()

    def test_window_dimensions(self):
        """Window should have reasonable dimensions (min 700x500 per XAML)."""
        rect = self.main_window.rectangle()
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        assert width >= 700, f"Window too narrow: {width}px"
        assert height >= 500, f"Window too short: {height}px"


@skip_not_windows
@skip_no_pywinauto
class TestTabNavigation:
    """Test tab navigation in the WPF main window."""

    @pytest.fixture(autouse=True)
    def _launch_app(self, app_exe_path):
        self.app = Application(backend="uia").start(app_exe_path, timeout=30)
        self.main_window = self.app.window(title="Media Downloader", timeout=15)
        self.main_window.wait("visible", timeout=15)
        yield
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_dashboard_tab_is_default(self):
        """Dashboard tab should be selected by default."""
        tab_control = self.main_window.child_window(control_type="Tab")
        dashboard_tab = tab_control.child_window(title="Dashboard", control_type="TabItem")
        assert dashboard_tab.is_selected()

    def test_switch_to_settings_tab(self):
        """Click the Settings tab and verify it becomes active."""
        tab_control = self.main_window.child_window(control_type="Tab")
        settings_tab = tab_control.child_window(title="Settings", control_type="TabItem")
        settings_tab.click_input()
        time.sleep(0.5)
        assert settings_tab.is_selected()

    def test_switch_to_logs_tab(self):
        """Click the Logs tab and verify it becomes active."""
        tab_control = self.main_window.child_window(control_type="Tab")
        logs_tab = tab_control.child_window(title="Logs", control_type="TabItem")
        logs_tab.click_input()
        time.sleep(0.5)
        assert logs_tab.is_selected()

    def test_switch_to_updates_tab(self):
        """Click the Updates tab and verify it becomes active."""
        tab_control = self.main_window.child_window(control_type="Tab")
        updates_tab = tab_control.child_window(title="Updates", control_type="TabItem")
        updates_tab.click_input()
        time.sleep(0.5)
        assert updates_tab.is_selected()

    def test_cycle_all_tabs(self):
        """Navigate through all tabs sequentially."""
        tab_control = self.main_window.child_window(control_type="Tab")
        tab_names = ["Dashboard", "Settings", "Logs", "Updates"]

        for name in tab_names:
            tab = tab_control.child_window(title=name, control_type="TabItem")
            tab.click_input()
            time.sleep(0.3)
            assert tab.is_selected(), f"{name} tab should be selected"


@skip_not_windows
@skip_no_pywinauto
class TestDashboardView:
    """Test the Dashboard view contents."""

    @pytest.fixture(autouse=True)
    def _launch_app(self, app_exe_path):
        self.app = Application(backend="uia").start(app_exe_path, timeout=30)
        self.main_window = self.app.window(title="Media Downloader", timeout=15)
        self.main_window.wait("visible", timeout=15)
        yield
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_header_text_visible(self):
        """Dashboard should show 'Media Downloader' header."""
        header = self.main_window.child_window(
            title="Media Downloader",
            control_type="Text",
        )
        assert header.exists(timeout=5)

    def test_server_status_label(self):
        """Dashboard should show 'Server Status' label."""
        label = self.main_window.child_window(
            title="Server Status",
            control_type="Text",
        )
        assert label.exists(timeout=5)

    def test_start_button_present(self):
        """Dashboard should have a Start button."""
        btn = self.main_window.child_window(title="Start", control_type="Button")
        assert btn.exists(timeout=5)

    def test_stop_button_present(self):
        """Dashboard should have a Stop button."""
        btn = self.main_window.child_window(title="Stop", control_type="Button")
        assert btn.exists(timeout=5)

    def test_restart_button_present(self):
        """Dashboard should have a Restart button."""
        btn = self.main_window.child_window(title="Restart", control_type="Button")
        assert btn.exists(timeout=5)

    def test_open_web_ui_button_present(self):
        """Dashboard should have an 'Open Web UI' button."""
        btn = self.main_window.child_window(title="Open Web UI", control_type="Button")
        assert btn.exists(timeout=5)

    def test_version_label_present(self):
        """Dashboard should show a Version section."""
        label = self.main_window.child_window(title="Version", control_type="Text")
        assert label.exists(timeout=5)


@skip_not_windows
@skip_no_pywinauto
class TestSettingsView:
    """Test the Settings view contents."""

    @pytest.fixture(autouse=True)
    def _launch_and_navigate(self, app_exe_path):
        self.app = Application(backend="uia").start(app_exe_path, timeout=30)
        self.main_window = self.app.window(title="Media Downloader", timeout=15)
        self.main_window.wait("visible", timeout=15)

        # Navigate to Settings tab
        tab_control = self.main_window.child_window(control_type="Tab")
        settings_tab = tab_control.child_window(title="Settings", control_type="TabItem")
        settings_tab.click_input()
        time.sleep(0.5)

        yield
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_settings_header_visible(self):
        """Settings view should show 'Settings' header."""
        header = self.main_window.child_window(title="Settings", control_type="Text")
        assert header.exists(timeout=5)

    def test_api_keys_section(self):
        """Settings should have an 'API Keys' section."""
        section = self.main_window.child_window(title="API Keys", control_type="Text")
        assert section.exists(timeout=5)

    def test_library_directories_section(self):
        """Settings should have a 'Library Directories' section."""
        section = self.main_window.child_window(
            title="Library Directories", control_type="Text"
        )
        assert section.exists(timeout=5)

    def test_mpc_be_section(self):
        """Settings should have an 'MPC-BE' section."""
        section = self.main_window.child_window(title="MPC-BE", control_type="Text")
        assert section.exists(timeout=5)

    def test_save_button_present(self):
        """Settings should have a 'Save Settings' button."""
        btn = self.main_window.child_window(title="Save Settings", control_type="Button")
        assert btn.exists(timeout=5)

    def test_discard_button_present(self):
        """Settings should have a 'Discard Changes' button."""
        btn = self.main_window.child_window(
            title="Discard Changes", control_type="Button"
        )
        assert btn.exists(timeout=5)

    def test_test_rd_key_button_present(self):
        """Settings should have a 'Test' button for RD key."""
        btn = self.main_window.child_window(title="Test", control_type="Button")
        assert btn.exists(timeout=5)

    def test_browse_buttons_present(self):
        """Settings should have multiple Browse buttons for directory selection."""
        browse_buttons = self.main_window.children(
            title="Browse", control_type="Button"
        )
        # Movies, TV, Anime, Movies Archive, TV Archive, Anime Archive,
        # Downloads, Posters, MPC-BE exe = 9 Browse buttons
        assert len(browse_buttons) >= 6, (
            f"Expected at least 6 Browse buttons, found {len(browse_buttons)}"
        )


@skip_not_windows
@skip_no_pywinauto
class TestServerLifecycle:
    """Test starting and stopping the server from the Dashboard."""

    @pytest.fixture(autouse=True)
    def _launch_app(self, app_exe_path):
        self.app = Application(backend="uia").start(app_exe_path, timeout=30)
        self.main_window = self.app.window(title="Media Downloader", timeout=15)
        self.main_window.wait("visible", timeout=15)
        yield
        # Stop server if running, then kill app
        try:
            stop_btn = self.main_window.child_window(title="Stop", control_type="Button")
            if stop_btn.exists(timeout=2):
                stop_btn.click_input()
                time.sleep(3)
        except Exception:
            pass
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_start_server(self):
        """Click Start and verify status text changes."""
        start_btn = self.main_window.child_window(title="Start", control_type="Button")
        start_btn.click_input()

        # Wait for status to update — look for "Running" text
        time.sleep(5)
        # The StatusText binding should update to "Running"
        running_text = self.main_window.child_window(
            title_re=".*Running.*",
            control_type="Text",
        )
        assert running_text.exists(timeout=15), "Server did not start — 'Running' not found"

    def test_stop_server(self):
        """Start the server, then stop it."""
        # Start first
        start_btn = self.main_window.child_window(title="Start", control_type="Button")
        start_btn.click_input()
        time.sleep(5)

        # Stop
        stop_btn = self.main_window.child_window(title="Stop", control_type="Button")
        stop_btn.click_input()
        time.sleep(3)

        stopped_text = self.main_window.child_window(
            title_re=".*Stopped.*",
            control_type="Text",
        )
        assert stopped_text.exists(timeout=15), "Server did not stop — 'Stopped' not found"


@skip_not_windows
@skip_no_pywinauto
class TestSystemTray:
    """Test system tray behavior (minimize to tray, restore)."""

    @pytest.fixture(autouse=True)
    def _launch_app(self, app_exe_path):
        self.app = Application(backend="uia").start(app_exe_path, timeout=30)
        self.main_window = self.app.window(title="Media Downloader", timeout=15)
        self.main_window.wait("visible", timeout=15)
        yield
        try:
            proc = psutil.Process(self.app.process)
            kill_process_tree(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    def test_minimize_hides_window(self):
        """Minimizing should hide the window (to system tray)."""
        self.main_window.minimize()
        time.sleep(1)
        # WPF app hides on minimize (to tray), window may not be visible
        assert not self.main_window.is_visible() or self.main_window.is_minimized()

    def test_restore_from_tray(self):
        """After minimizing, the tray icon double-click should restore."""
        self.main_window.minimize()
        time.sleep(1)

        # Access the tray via Desktop — look for the notification area
        try:
            desktop = Desktop(backend="uia")
            # The system tray area
            tray_area = desktop.window(
                class_name="Shell_TrayWnd"
            ).child_window(
                title="Notification Chevron", control_type="Button"
            )
            tray_area.click_input()
            time.sleep(0.5)

            # Find our tray icon in the overflow area
            overflow = desktop.window(class_name="NotifyIconOverflowWindow")
            md_icon = overflow.child_window(title_re=".*Media Downloader.*")
            md_icon.double_click_input()
            time.sleep(1)

            assert self.main_window.is_visible(), "Window was not restored from tray"
        except (ElementNotFoundError, PywinautoTimeout):
            pytest.skip("Could not locate system tray icon — may vary by Windows version")


@skip_not_windows
@skip_no_pywinauto
class TestCleanExit:
    """Test that closing the window terminates the process."""

    def test_close_terminates_process(self, app_exe_path):
        app = Application(backend="uia").start(app_exe_path, timeout=30)
        main_window = app.window(title="Media Downloader", timeout=15)
        main_window.wait("visible", timeout=15)

        pid = app.process
        assert psutil.pid_exists(pid)

        main_window.close()
        time.sleep(3)

        # Process should have exited
        assert not psutil.pid_exists(pid), "App process still running after close"
