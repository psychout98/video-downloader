"""
Integration tests for the Inno Setup installer and uninstaller.

These tests run MediaDownloader-Setup.exe in silent mode to a temporary
directory and verify the installation artifacts are correct.

Requirements:
    - Windows OS
    - dist/MediaDownloader-Setup.exe exists (from CI build or local build)

Run:
    pytest tests/integration/test_installer.py -v
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import psutil
import pytest

from .conftest import (
    kill_process_tree,
    run_silent_installer,
    run_silent_uninstaller,
    skip_not_windows,
    wait_for_process,
)


@skip_not_windows
class TestInstaller:
    """Test the Inno Setup installer in silent mode."""

    @pytest.fixture(autouse=True, scope="class")
    def _install(self, installer_path, install_dir):
        """Run the installer once for all tests in this class."""
        # Kill any existing MediaDownloader processes to avoid conflicts
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and "MediaDownloader" in proc.info["name"]:
                kill_process_tree(proc)

        exit_code = run_silent_installer(installer_path, install_dir)
        assert exit_code == 0, f"Installer failed with exit code {exit_code}"

        # Wait a moment for post-install tasks (venv creation, pip install)
        time.sleep(5)

        # Store install_dir on class for tests
        self.__class__._install_dir = install_dir
        yield

    @property
    def dir(self) -> str:
        return self.__class__._install_dir

    # ── File structure verification ─────────────────────────────────

    def test_main_executable_exists(self):
        assert os.path.isfile(os.path.join(self.dir, "MediaDownloader.exe"))

    def test_server_directory_exists(self):
        server_dir = os.path.join(self.dir, "server")
        assert os.path.isdir(server_dir)
        assert os.path.isfile(os.path.join(server_dir, "main.py"))

    def test_server_modules_exist(self):
        server_dir = os.path.join(self.dir, "server")
        expected_dirs = ["clients", "core", "routers"]
        for d in expected_dirs:
            assert os.path.isdir(os.path.join(server_dir, d)), f"Missing: server/{d}/"

    def test_requirements_file_exists(self):
        assert os.path.isfile(os.path.join(self.dir, "requirements.txt"))

    def test_run_server_bat_exists(self):
        assert os.path.isfile(os.path.join(self.dir, "run_server.bat"))

    def test_stop_server_bat_exists(self):
        assert os.path.isfile(os.path.join(self.dir, "stop_server.bat"))

    def test_logs_directory_created(self):
        assert os.path.isdir(os.path.join(self.dir, "logs"))

    def test_data_directory_created(self):
        assert os.path.isdir(os.path.join(self.dir, "data"))
        assert os.path.isdir(os.path.join(self.dir, "data", "posters"))

    # ── Python virtual environment ──────────────────────────────────

    def test_venv_created(self):
        venv = os.path.join(self.dir, ".venv")
        assert os.path.isdir(venv), "Python venv was not created"

    def test_venv_has_python(self):
        python = os.path.join(self.dir, ".venv", "Scripts", "python.exe")
        assert os.path.isfile(python), "venv python.exe not found"

    def test_venv_has_pip(self):
        pip = os.path.join(self.dir, ".venv", "Scripts", "pip.exe")
        assert os.path.isfile(pip), "venv pip.exe not found"

    def test_fastapi_installed(self):
        """Verify pip installed the Python dependencies."""
        site_packages = os.path.join(self.dir, ".venv", "Lib", "site-packages")
        # FastAPI creates a fastapi/ package directory
        assert os.path.isdir(os.path.join(site_packages, "fastapi")), (
            "FastAPI not found in site-packages"
        )

    def test_uvicorn_installed(self):
        site_packages = os.path.join(self.dir, ".venv", "Lib", "site-packages")
        assert os.path.isdir(os.path.join(site_packages, "uvicorn")), (
            "uvicorn not found in site-packages"
        )

    # ── Uninstaller ─────────────────────────────────────────────────

    def test_uninstaller_exists(self):
        assert os.path.isfile(os.path.join(self.dir, "unins000.exe"))


@skip_not_windows
class TestUninstaller:
    """Test the uninstaller cleans up properly.

    This runs AFTER TestInstaller since pytest collects in file order.
    """

    @pytest.fixture(autouse=True, scope="class")
    def _uninstall(self, installer_path, install_dir):
        """Ensure installed, then run uninstaller."""
        # If not already installed (e.g. running in isolation), install first
        if not os.path.isfile(os.path.join(install_dir, "unins000.exe")):
            exit_code = run_silent_installer(installer_path, install_dir)
            assert exit_code == 0
            time.sleep(5)

        # Kill app if running
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and "MediaDownloader" in proc.info["name"]:
                kill_process_tree(proc)

        self.__class__._install_dir = install_dir

        exit_code = run_silent_uninstaller(install_dir)
        assert exit_code == 0, f"Uninstaller failed with exit code {exit_code}"

        # Wait for uninstaller to finish cleanup
        time.sleep(5)
        yield

    @property
    def dir(self) -> str:
        return self.__class__._install_dir

    def test_venv_removed(self):
        assert not os.path.isdir(os.path.join(self.dir, ".venv"))

    def test_env_file_removed(self):
        """The .env file should be cleaned up by uninstaller."""
        assert not os.path.isfile(os.path.join(self.dir, ".env"))

    def test_database_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "media_downloader.db"))

    def test_main_executable_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "MediaDownloader.exe"))
