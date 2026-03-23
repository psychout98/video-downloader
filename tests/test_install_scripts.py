"""Tests for install/uninstall scripts and run_server.sh — validates structure and logic."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
INSTALL_SCRIPT = PROJECT_ROOT / "scripts" / "install_service_windows.bat"
UNINSTALL_SCRIPT = PROJECT_ROOT / "scripts" / "uninstall_service_windows.bat"
RUN_SERVER_SH = PROJECT_ROOT / "run_server.sh"


# ═══════════════════════════════════════════════════════════════════════════════
#  install_service_windows.bat
# ═══════════════════════════════════════════════════════════════════════════════

class TestInstallScript:
    @pytest.fixture(autouse=True)
    def load_script(self):
        self.content = INSTALL_SCRIPT.read_text(encoding="utf-8")

    # ── Admin check ──────────────────────────────────────────────────────

    def test_checks_for_admin_privileges(self):
        assert "net session" in self.content

    def test_shows_admin_error_message(self):
        assert "Run as administrator" in self.content

    # ── .env validation ──────────────────────────────────────────────────

    def test_checks_env_file_exists(self):
        assert ".env" in self.content
        # Should reference .env.example for guidance
        assert ".env.example" in self.content

    # ── Python check ─────────────────────────────────────────────────────

    def test_checks_python_is_available(self):
        assert "where python" in self.content

    def test_shows_python_install_url(self):
        assert "python.org" in self.content

    # ── Virtual environment ──────────────────────────────────────────────

    def test_creates_virtual_environment(self):
        assert "venv" in self.content

    def test_checks_for_existing_venv(self):
        assert ".venv\\Scripts\\python.exe" in self.content

    # ── Pip install ──────────────────────────────────────────────────────

    def test_installs_requirements(self):
        assert "requirements.txt" in self.content
        assert "pip install" in self.content

    def test_upgrades_pip(self):
        assert "pip install --upgrade pip" in self.content

    # ── Task Scheduler ───────────────────────────────────────────────────

    def test_registers_scheduled_task(self):
        assert "Register-ScheduledTask" in self.content
        assert "MediaDownloader" in self.content

    def test_task_triggers_at_logon(self):
        assert "AtLogOn" in self.content

    # ── Firewall ─────────────────────────────────────────────────────────

    def test_adds_firewall_rule(self):
        assert "advfirewall firewall add rule" in self.content

    def test_firewall_for_port_8000(self):
        assert "localport=8000" in self.content

    def test_removes_old_firewall_rule_before_adding(self):
        # Script should delete the old rule before adding a new one
        assert "firewall delete rule" in self.content

    # ── Post-install start ───────────────────────────────────────────────

    def test_starts_task_after_install(self):
        assert "schtasks /run" in self.content

    # ── Step numbering ───────────────────────────────────────────────────

    def test_has_four_steps(self):
        assert "[1/4]" in self.content
        assert "[2/4]" in self.content
        assert "[3/4]" in self.content
        assert "[4/4]" in self.content

    # ── Error handling ───────────────────────────────────────────────────

    def test_exits_on_admin_failure(self):
        # Should exit with non-zero on admin failure
        assert "exit /b 1" in self.content

    def test_handles_pip_failure(self):
        lines = self.content.splitlines()
        pip_section = False
        has_error_check = False
        for line in lines:
            if "pip install" in line and "requirements" in line:
                pip_section = True
            if pip_section and "errorlevel" in line:
                has_error_check = True
                break
        assert has_error_check, "No error check after pip install"

    # ── Output ───────────────────────────────────────────────────────────

    def test_shows_web_ui_url(self):
        assert "http://localhost:8000" in self.content

    def test_shows_done_message(self):
        assert "Done!" in self.content


# ═══════════════════════════════════════════════════════════════════════════════
#  uninstall_service_windows.bat
# ═══════════════════════════════════════════════════════════════════════════════

class TestUninstallScript:
    @pytest.fixture(autouse=True)
    def load_script(self):
        self.content = UNINSTALL_SCRIPT.read_text(encoding="utf-8")

    def test_stops_scheduled_task(self):
        assert "schtasks /end" in self.content
        assert "MediaDownloader" in self.content

    def test_deletes_scheduled_task(self):
        assert "schtasks /delete" in self.content

    def test_removes_firewall_rule(self):
        assert "firewall delete rule" in self.content
        assert "MediaDownloader" in self.content

    def test_preserves_user_data(self):
        assert ".env" in self.content or "not touched" in self.content
        assert "media library" in self.content.lower() or "not touched" in self.content


# ═══════════════════════════════════════════════════════════════════════════════
#  run_server.sh
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunServerSh:
    @pytest.fixture(autouse=True)
    def load_script(self):
        self.content = RUN_SERVER_SH.read_text(encoding="utf-8")

    def test_has_shebang(self):
        assert self.content.startswith("#!/bin/bash")

    def test_creates_venv_if_missing(self):
        assert "python3 -m venv" in self.content

    def test_installs_requirements_on_venv_creation(self):
        assert "requirements.txt" in self.content

    def test_creates_logs_directory(self):
        assert "mkdir -p logs" in self.content

    def test_reads_port_from_env(self):
        assert "PORT" in self.content
        assert ".env" in self.content

    def test_default_port_is_8000(self):
        assert "PORT=8000" in self.content

    def test_uses_uvicorn(self):
        assert "uvicorn" in self.content
        assert "server.main:app" in self.content

    def test_binds_to_all_interfaces(self):
        assert "--host 0.0.0.0" in self.content

    def test_uses_venv_python(self):
        assert ".venv/bin/python" in self.content

    def test_script_is_executable_friendly(self):
        # Should cd to script directory
        assert 'cd "$(dirname "$0")"' in self.content
