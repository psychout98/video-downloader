"""
Integration tests for Windows Installer (Feature 11).

AC Reference:
  11.1  Installer produces MediaDownloader.exe
  11.2  server/ directory exists with main.py, clients/, core/, routers/
  11.3  requirements.txt, run-server.bat, stop-server.bat exist
  11.4  logs/ and data/ directories are created
  11.5  Python venv is created with python and pip

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

    def test_11_2_server_directory_with_modules(self):
        """11.2 — server/ directory exists with main.py, clients/, core/, routers/."""
        server_dir = os.path.join(self.dir, "server")
        assert os.path.isdir(server_dir)
        assert os.path.isfile(os.path.join(server_dir, "main.py"))
        for module in ("clients", "core", "routers"):
            assert os.path.isdir(os.path.join(server_dir, module)), f"Missing: server/{module}/"

    def test_11_3_support_files_exist(self):
        """11.3 — requirements.txt, run-server.bat, stop-server.bat exist."""
        assert os.path.isfile(os.path.join(self.dir, "requirements.txt"))
        assert os.path.isfile(os.path.join(self.dir, "run_server.bat"))
        assert os.path.isfile(os.path.join(self.dir, "stop_server.bat"))

    def test_11_4_logs_and_data_directories_created(self):
        """11.4 — logs/ and data/ directories are created."""
        assert os.path.isdir(os.path.join(self.dir, "logs"))
        assert os.path.isdir(os.path.join(self.dir, "data"))

    def test_11_5_python_venv_created_with_python_and_pip(self):
        """11.5 — Python venv is created with python and pip."""
        venv = os.path.join(self.dir, ".venv")
        assert os.path.isdir(venv), "Python venv was not created"

        python = os.path.join(self.dir, ".venv", "Scripts", "python.exe")
        assert os.path.isfile(python), "venv python.exe not found"

        pip = os.path.join(self.dir, ".venv", "Scripts", "pip.exe")
        assert os.path.isfile(pip), "venv pip.exe not found"


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

    def test_venv_removed(self):
        assert not os.path.isdir(os.path.join(self.dir, ".venv"))

    def test_env_file_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, ".env"))

    def test_database_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "media_downloader.db"))

    def test_main_executable_removed(self):
        assert not os.path.isfile(os.path.join(self.dir, "MediaDownloader.exe"))
