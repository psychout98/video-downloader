"""
Integration tests for Windows Installer (Feature 11).

AC Reference:
  11.1  Installer produces MediaDownloader.exe
  11.2  server/static/ directory exists with frontend assets
  11.3  logs/ and data/ directories are created

Run:
    pytest tests/integration/test_installer.py -v
"""
from __future__ import annotations

import os
import time

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
class TestFeature11_WindowsInstaller:
    """Feature 11: Windows Installer"""

    @pytest.fixture(autouse=True, scope="class")
    def _install(self, installer_path, install_dir):
        """Run the installer once for all tests in this class."""
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and "MediaDownloader" in proc.info["name"]:
                kill_process_tree(proc)

        exit_code = run_silent_installer(installer_path, install_dir)
        assert exit_code == 0, f"Installer failed with exit code {exit_code}"
        time.sleep(5)

        self.__class__._install_dir = install_dir
        yield

    @property
    def dir(self) -> str:
        return self.__class__._install_dir

    def test_11_1_installer_produces_main_executable(self):
        """11.1 — Installer produces MediaDownloader.exe."""
        assert os.path.isfile(os.path.join(self.dir, "MediaDownloader.exe"))

    def test_11_2_server_static_directory_exists(self):
        """11.2 — server/static/ directory exists with frontend assets."""
        static_dir = os.path.join(self.dir, "server", "static")
        assert os.path.isdir(static_dir), "server/static/ directory not found"

    def test_11_3_logs_and_data_directories_created(self):
        """11.3 — logs/ and data/ directories are created."""
        assert os.path.isdir(os.path.join(self.dir, "logs"))
        assert os.path.isdir(os.path.join(self.dir, "data"))


@skip_not_windows
class TestUninstaller:
    """Verify the uninstaller cleans up properly."""

    @pytest.fixture(autouse=True, scope="class")
    def _uninstall(self, installer_path, install_dir):
        if not os.path.isfile(os.path.join(install_dir, "unins000.exe")):
            exit_code = run_silent_installer(installer_path, install_dir)
            assert exit_code == 0
            time.sleep(5)

        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and "MediaDownloader" in proc.info["name"]:
                kill_process_tree(proc)

        self.__class__._install_dir = install_dir
        exit_code = run_silent_uninstaller(install_dir)
        assert exit_code == 0, f"Uninstaller failed with exit code {exit_code}"
        time.sleep(5)
        yield

    @property
    def dir(self) -> str:
        return self.__class__._install_dir

    def test_env_file_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, ".env"))

    def test_database_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "media_downloader.db"))

    def test_main_executable_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "MediaDownloader.exe"))
