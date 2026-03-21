"""
Media Downloader — System Tray Application.

Provides a Windows system tray icon for managing the FastAPI server:
  - Auto-starts the server on launch
  - Start / Stop / Restart via tray menu
  - Open Web UI in default browser
  - Uninstall (remove Task Scheduler task, firewall rule)
  - Status indicator (green = running, red = stopped)

Usage:
  python tray/tray_app.py

Requires:
  pip install pystray Pillow requests
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing dependencies. Install with: pip install pystray Pillow")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Missing dependency. Install with: pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

# Project root is one level up from tray/
ROOT_DIR = Path(__file__).parent.parent
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
ENV_FILE = ROOT_DIR / ".env"

# Read PORT from .env, default 8000
def _read_port() -> int:
    try:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("PORT="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    return int(val)
    except Exception:
        pass
    return 8000

PORT = _read_port()
BASE_URL = f"http://127.0.0.1:{PORT}"
HEALTH_URL = f"{BASE_URL}/api/status"
POLL_INTERVAL = 10  # seconds between health checks


# ── Icon creation ─────────────────────────────────────────────────────────────

def _create_icon(color: str = "red") -> Image.Image:
    """Create a simple coloured circle icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if color == "green":
        fill = (76, 175, 80, 255)      # green
        outline = (56, 142, 60, 255)
    elif color == "yellow":
        fill = (255, 193, 7, 255)       # yellow (starting)
        outline = (245, 169, 0, 255)
    else:
        fill = (244, 67, 54, 255)       # red
        outline = (211, 47, 47, 255)

    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=fill, outline=outline, width=2,
    )

    # Draw a play triangle or square inside
    cx, cy = size // 2, size // 2
    if color == "green":
        # Draw a small "play" triangle
        tri = [(cx - 6, cy - 10), (cx - 6, cy + 10), (cx + 10, cy)]
        draw.polygon(tri, fill=(255, 255, 255, 220))
    else:
        # Draw a small square (stop)
        sq = 8
        draw.rectangle([cx - sq, cy - sq, cx + sq, cy + sq], fill=(255, 255, 255, 220))

    return img


# ── Server management ─────────────────────────────────────────────────────────

class ServerManager:
    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def check_health(self) -> bool:
        """Check if the server is responding."""
        try:
            r = requests.get(HEALTH_URL, timeout=3)
            alive = r.status_code == 200
            self._running = alive
            return alive
        except Exception:
            self._running = False
            return False

    def start(self) -> bool:
        """Start the server process."""
        with self._lock:
            if self.check_health():
                return True  # already running

            python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
            cmd = [
                python, "-m", "uvicorn",
                "server.main:app",
                "--host", "0.0.0.0",
                "--port", str(PORT),
            ]

            try:
                # Detached process so it outlives the tray app if needed
                kwargs = {
                    "cwd": str(ROOT_DIR),
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                if sys.platform == "win32":
                    DETACHED = 0x00000008
                    NEW_GROUP = 0x00000200
                    kwargs["creationflags"] = DETACHED | NEW_GROUP

                self._process = subprocess.Popen(cmd, **kwargs)
                # Wait a moment then verify
                time.sleep(2)
                for _ in range(10):
                    if self.check_health():
                        return True
                    time.sleep(1)
                return self.check_health()
            except Exception as exc:
                print(f"Failed to start server: {exc}")
                return False

    def stop(self) -> bool:
        """Stop the server process."""
        with self._lock:
            # Try graceful PID-based kill first
            pid_file = ROOT_DIR / "server.pid"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F"],
                            capture_output=True, timeout=10,
                        )
                    else:
                        import signal
                        os.kill(pid, signal.SIGTERM)
                    time.sleep(1)
                except Exception:
                    pass

            # Also kill our child process if we started one
            if self._process and self._process.poll() is None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

            self._process = None
            self._running = False

            # Verify stopped
            time.sleep(1)
            return not self.check_health()

    def restart(self) -> bool:
        """Stop then start the server."""
        self.stop()
        time.sleep(1)
        return self.start()


# ── Tray application ─────────────────────────────────────────────────────────

class TrayApp:
    def __init__(self):
        self.server = ServerManager()
        self._icon: Optional[pystray.Icon] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._running = True

    def _update_icon(self, running: bool):
        """Update the tray icon to reflect server status."""
        if self._icon:
            color = "green" if running else "red"
            self._icon.icon = _create_icon(color)
            status = "Running" if running else "Stopped"
            self._icon.title = f"Media Downloader — {status}"

    def _poll_loop(self):
        """Background thread: poll server health and update icon."""
        while self._running:
            try:
                alive = self.server.check_health()
                self._update_icon(alive)
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    # ── Menu actions ──────────────────────────────────────────────────────

    def _on_start(self, icon, item):
        def _do():
            self._update_icon_starting()
            ok = self.server.start()
            self._update_icon(ok)
            if not ok:
                icon.notify("Failed to start server", "Media Downloader")
        threading.Thread(target=_do, daemon=True).start()

    def _on_stop(self, icon, item):
        def _do():
            self.server.stop()
            self._update_icon(False)
        threading.Thread(target=_do, daemon=True).start()

    def _on_restart(self, icon, item):
        def _do():
            self._update_icon_starting()
            ok = self.server.restart()
            self._update_icon(ok)
            if not ok:
                icon.notify("Restart failed — server did not come back up", "Media Downloader")
        threading.Thread(target=_do, daemon=True).start()

    def _on_open_ui(self, icon, item):
        webbrowser.open(BASE_URL)

    def _on_uninstall(self, icon, item):
        """Run the uninstall script."""
        script = ROOT_DIR / "scripts" / "uninstall_service_windows.bat"
        if script.exists():
            self.server.stop()
            try:
                subprocess.Popen(
                    ["cmd", "/c", str(script)],
                    cwd=str(ROOT_DIR),
                    creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
                )
            except Exception as exc:
                icon.notify(f"Uninstall failed: {exc}", "Media Downloader")
        else:
            icon.notify("Uninstall script not found", "Media Downloader")

    def _on_exit(self, icon, item):
        """Exit the tray app (does NOT stop the server)."""
        self._running = False
        icon.stop()

    def _update_icon_starting(self):
        """Show yellow icon while starting."""
        if self._icon:
            self._icon.icon = _create_icon("yellow")
            self._icon.title = "Media Downloader — Starting…"

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self):
        """Create and run the system tray icon."""
        menu = pystray.Menu(
            pystray.MenuItem("Open Web UI", self._on_open_ui, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Service", self._on_start),
            pystray.MenuItem("Stop Service", self._on_stop),
            pystray.MenuItem("Restart Service", self._on_restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Uninstall", self._on_uninstall),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Tray", self._on_exit),
        )

        self._icon = pystray.Icon(
            name="media-downloader",
            icon=_create_icon("red"),
            title="Media Downloader — Starting…",
            menu=menu,
        )

        # Start health poll thread
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        # Auto-start the server
        def _auto_start():
            time.sleep(1)
            self._update_icon_starting()
            ok = self.server.start()
            self._update_icon(ok)
            if ok:
                print(f"Server started on port {PORT}")
            else:
                print("Server failed to start")
                if self._icon:
                    self._icon.notify("Server failed to start", "Media Downloader")

        threading.Thread(target=_auto_start, daemon=True).start()

        # Run the tray icon (blocks until exit)
        self._icon.run()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = TrayApp()
    app.run()
