"""
Shared fixtures for Windows integration tests.

These tests are designed to run on a Windows machine (or VM) where
the MediaDownloader installer, WPF app, and MPC-BE may be available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil
import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default paths — override with env vars if needed
INSTALLER_PATH = os.environ.get(
    "MD_INSTALLER_PATH",
    str(Path(__file__).resolve().parents[2] / "dist" / "MediaDownloader-Setup.exe"),
)

APP_EXE_PATH = os.environ.get(
    "MD_APP_EXE_PATH",
    str(Path(__file__).resolve().parents[2] / "build" / "publish" / "MediaDownloader.exe"),
)

MPC_BE_EXE = os.environ.get(
    "MPC_BE_EXE",
    r"C:\Program Files\MPC-BE x64\mpc-be64.exe",
)

BACKEND_URL = os.environ.get("MD_BACKEND_URL", "http://127.0.0.1:8000")

# Test media file for MPC-BE playback tests
TEST_MEDIA_FILE = os.environ.get("TEST_MEDIA_FILE", "")


# ---------------------------------------------------------------------------
# Platform guard
# ---------------------------------------------------------------------------

skip_not_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows integration tests — skipped on non-Windows platform",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def install_dir():
    """Provide a temporary directory for silent-install tests."""
    tmpdir = tempfile.mkdtemp(prefix="md_install_test_")
    yield tmpdir
    # Best-effort cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def installer_path():
    """Return the path to MediaDownloader-Setup.exe, skipping if absent."""
    if not os.path.isfile(INSTALLER_PATH):
        pytest.skip(f"Installer not found at {INSTALLER_PATH}")
    return INSTALLER_PATH


@pytest.fixture(scope="session")
def app_exe_path():
    """Return the path to the built MediaDownloader.exe, skipping if absent."""
    if not os.path.isfile(APP_EXE_PATH):
        pytest.skip(f"App exe not found at {APP_EXE_PATH}")
    return APP_EXE_PATH


@pytest.fixture(scope="session")
def mpc_be_available():
    """Skip the test if MPC-BE is not installed."""
    if not os.path.isfile(MPC_BE_EXE):
        pytest.skip(f"MPC-BE not found at {MPC_BE_EXE}")
    return MPC_BE_EXE


@pytest.fixture(scope="session")
def test_media_file():
    """Provide a path to a test media file for playback tests."""
    if not TEST_MEDIA_FILE or not os.path.isfile(TEST_MEDIA_FILE):
        pytest.skip("TEST_MEDIA_FILE env var not set or file not found")
    return TEST_MEDIA_FILE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def wait_for_process(name: str, timeout: float = 30) -> psutil.Process | None:
    """Wait until a process with the given name appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"] and name.lower() in proc.info["name"].lower():
                return proc
        time.sleep(0.5)
    return None


def kill_process_tree(proc: psutil.Process) -> None:
    """Kill a process and all its children."""
    try:
        children = proc.children(recursive=True)
        for child in children:
            child.kill()
        proc.kill()
        psutil.wait_procs(children + [proc], timeout=10)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def run_silent_installer(installer: str, target_dir: str, timeout: float = 120) -> int:
    """Run the Inno Setup installer in silent mode and return the exit code."""
    result = subprocess.run(
        [installer, f"/SILENT", f"/DIR={target_dir}", "/SUPPRESSMSGBOXES", "/NORESTART"],
        timeout=timeout,
        capture_output=True,
    )
    return result.returncode


def run_silent_uninstaller(install_dir: str, timeout: float = 60) -> int:
    """Run the uninstaller from the install directory in silent mode."""
    uninstaller = os.path.join(install_dir, "unins000.exe")
    if not os.path.isfile(uninstaller):
        raise FileNotFoundError(f"Uninstaller not found: {uninstaller}")
    result = subprocess.run(
        [uninstaller, "/SILENT", "/SUPPRESSMSGBOXES"],
        timeout=timeout,
        capture_output=True,
    )
    return result.returncode
