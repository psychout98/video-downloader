"""Tests for installer/setup.iss — validates the Inno Setup script structure."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SETUP_ISS = PROJECT_ROOT / "installer" / "setup.iss"


@pytest.fixture
def iss_content():
    return SETUP_ISS.read_text(encoding="utf-8")


@pytest.fixture
def iss_sections(iss_content):
    """Parse setup.iss into a dict of section_name -> list of lines."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in iss_content.splitlines():
        stripped = line.strip()
        m = re.match(r"^\[(\w+)\]", stripped)
        if m:
            current = m.group(1)
            sections[current] = []
        elif current and stripped and not stripped.startswith(";"):
            sections[current].append(stripped)
    return sections


# ═══════════════════════════════════════════════════════════════════════════════
#  [Setup] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetupSection:
    def test_has_app_id(self, iss_content):
        assert "AppId=" in iss_content

    def test_requires_admin(self, iss_content):
        assert "PrivilegesRequired=admin" in iss_content

    def test_is_x64_only(self, iss_content):
        assert "x64compatible" in iss_content

    def test_uses_lzma_compression(self, iss_content):
        assert "Compression=lzma2" in iss_content

    def test_modern_wizard_style(self, iss_content):
        assert "WizardStyle=modern" in iss_content

    def test_output_filename(self, iss_content):
        assert "MediaDownloader-Setup" in iss_content

    def test_has_uninstall_icon(self, iss_content):
        assert "UninstallDisplayIcon" in iss_content

    def test_close_applications_enabled(self, iss_content):
        assert "CloseApplications=yes" in iss_content


# ═══════════════════════════════════════════════════════════════════════════════
#  [Files] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestFilesSection:
    def test_copies_wpf_app(self, iss_sections):
        files = iss_sections.get("Files", [])
        sources = [l for l in files if "Source:" in l]
        assert any("build\\publish" in s for s in sources), "WPF app publish files not included"

    def test_copies_server(self, iss_sections):
        files = iss_sections.get("Files", [])
        sources = [l for l in files if "Source:" in l]
        assert any("server" in s for s in sources), "Server files not included"

    def test_copies_requirements(self, iss_sections):
        files = iss_sections.get("Files", [])
        sources = [l for l in files if "Source:" in l]
        assert any("requirements.txt" in s for s in sources), "requirements.txt not included"

    def test_copies_run_server_bat(self, iss_sections):
        files = iss_sections.get("Files", [])
        sources = [l for l in files if "Source:" in l]
        assert any("run_server.bat" in s for s in sources), "run_server.bat not included"

    def test_copies_stop_server_bat(self, iss_sections):
        files = iss_sections.get("Files", [])
        sources = [l for l in files if "Source:" in l]
        assert any("stop_server.bat" in s for s in sources), "stop_server.bat not included"


# ═══════════════════════════════════════════════════════════════════════════════
#  [Tasks] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestTasksSection:
    def test_has_desktop_icon_task(self, iss_sections):
        tasks = iss_sections.get("Tasks", [])
        assert any("desktopicon" in t for t in tasks)

    def test_has_startup_entry_task(self, iss_sections):
        tasks = iss_sections.get("Tasks", [])
        assert any("startupentry" in t for t in tasks)

    def test_desktop_icon_unchecked_by_default(self, iss_content):
        # desktopicon should be unchecked by default
        assert "Flags: unchecked" in iss_content


# ═══════════════════════════════════════════════════════════════════════════════
#  [Dirs] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestDirsSection:
    def test_creates_logs_dir(self, iss_sections):
        dirs = iss_sections.get("Dirs", [])
        assert any("logs" in d for d in dirs)

    def test_creates_data_dir(self, iss_sections):
        dirs = iss_sections.get("Dirs", [])
        assert any(d.endswith('"data"') or "\\data" in d for d in dirs)

    def test_creates_posters_dir(self, iss_sections):
        dirs = iss_sections.get("Dirs", [])
        assert any("posters" in d for d in dirs)


# ═══════════════════════════════════════════════════════════════════════════════
#  [Icons] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestIconsSection:
    def test_has_start_menu_entry(self, iss_sections):
        icons = iss_sections.get("Icons", [])
        assert any("{group}" in i for i in icons)

    def test_has_desktop_shortcut(self, iss_sections):
        icons = iss_sections.get("Icons", [])
        assert any("autodesktop" in i for i in icons)

    def test_has_uninstall_shortcut(self, iss_sections):
        icons = iss_sections.get("Icons", [])
        assert any("Uninstall" in i for i in icons)


# ═══════════════════════════════════════════════════════════════════════════════
#  [Registry] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistrySection:
    def test_startup_registry_entry(self, iss_sections):
        reg = iss_sections.get("Registry", [])
        assert any("CurrentVersion\\Run" in r for r in reg)

    def test_startup_entry_only_if_task_selected(self, iss_sections):
        reg = iss_sections.get("Registry", [])
        startup_entries = [r for r in reg if "CurrentVersion\\Run" in r]
        assert all("Tasks: startupentry" in r for r in startup_entries)

    def test_registry_deletes_on_uninstall(self, iss_sections):
        reg = iss_sections.get("Registry", [])
        assert any("uninsdeletevalue" in r for r in reg)


# ═══════════════════════════════════════════════════════════════════════════════
#  [Run] Section — Post-install steps
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunSection:
    def test_removes_old_venv(self, iss_content):
        assert "rmdir /s /q" in iss_content
        assert ".venv" in iss_content

    def test_creates_python_venv(self, iss_content):
        assert "python" in iss_content.lower()
        assert "venv" in iss_content

    def test_installs_pip_dependencies(self, iss_content):
        assert "pip" in iss_content.lower()
        assert "requirements.txt" in iss_content

    def test_adds_firewall_rule(self, iss_content):
        assert "netsh" in iss_content
        assert "advfirewall" in iss_content
        assert "MediaDownloader" in iss_content
        assert "8000" in iss_content

    def test_launches_app_after_install(self, iss_sections):
        run = iss_sections.get("Run", [])
        assert any("postinstall" in r for r in run)

    def test_launch_does_not_wait(self, iss_sections):
        run = iss_sections.get("Run", [])
        postinstall = [r for r in run if "postinstall" in r]
        assert all("nowait" in r for r in postinstall)


# ═══════════════════════════════════════════════════════════════════════════════
#  [UninstallRun] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestUninstallRunSection:
    def test_removes_firewall_rule(self, iss_sections):
        uninstall_run = iss_sections.get("UninstallRun", [])
        assert any("firewall" in u and "delete" in u for u in uninstall_run)
        assert any("MediaDownloader" in u for u in uninstall_run)


# ═══════════════════════════════════════════════════════════════════════════════
#  [UninstallDelete] Section
# ═══════════════════════════════════════════════════════════════════════════════

class TestUninstallDeleteSection:
    def test_removes_venv(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any(".venv" in d for d in deletes)

    def test_removes_logs(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any("logs" in d for d in deletes)

    def test_removes_env_file(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any(".env" in d for d in deletes)

    def test_removes_pid_file(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any("server.pid" in d for d in deletes)

    def test_removes_version_file(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any(".version" in d for d in deletes)

    def test_removes_database(self, iss_sections):
        deletes = iss_sections.get("UninstallDelete", [])
        assert any("media_downloader.db" in d for d in deletes)


# ═══════════════════════════════════════════════════════════════════════════════
#  [Code] Section — Pascal Script
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeSection:
    def test_has_old_venv_check_function(self, iss_content):
        assert "OldVenvExists" in iss_content

    def test_old_venv_check_uses_dir_exists(self, iss_content):
        assert "DirExists" in iss_content


# ═══════════════════════════════════════════════════════════════════════════════
#  Required sections present
# ═══════════════════════════════════════════════════════════════════════════════

class TestRequiredSections:
    @pytest.mark.parametrize("section", [
        "Setup", "Languages", "Tasks", "Files", "Dirs", "Icons",
        "Registry", "Run", "UninstallRun", "Code", "UninstallDelete",
    ])
    def test_section_exists(self, iss_sections, section):
        assert section in iss_sections, f"Missing section [{section}]"
