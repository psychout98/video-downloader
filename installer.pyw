"""
Media Downloader — Windows Installer
=====================================
Run with:  python installer.pyw          (development)
Compile to .exe with:  build_installer.bat

When compiled with PyInstaller (--add-data flags), the EXE bundles the entire
project inside it.  The user chooses an install location; the installer extracts
the files there, writes .env, runs pip, and registers a Task Scheduler task.

Wizard pages
------------
1. Welcome     (choose install location)
2. API Keys    (TMDB, Real-Debrid, optional webhook secret)
3. Directories (primary NVMe + archive SATA paths)
4. Playback    (MPC-BE exe path, watch threshold)
5. Install     (extract files, write .env, pip install, Task Scheduler)
6. Done
"""
import os
import sys
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

IS_WINDOWS = sys.platform == "win32"
_DETACHED  = subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0

# Default install location
_DEFAULT_INSTALL = Path.home() / "MediaDownloader"


# ── Locate bundled source files ───────────────────────────────────────────────
def _bundled_root() -> Path:
    """
    When frozen (PyInstaller), sys._MEIPASS is the temp folder where --add-data
    files are extracted.  When running as a plain .py/.pyw script, the bundled
    files live beside installer.pyw in the project repo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)          # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


# ── Files/dirs to copy from bundle → install location ────────────────────────
# Each entry: (relative path inside bundle, relative path inside install dir)
_BUNDLE_ITEMS = [
    ("server",           "server"),
    ("run_server.bat",   "run_server.bat"),
    ("stop_server.bat",  "stop_server.bat"),
    ("requirements.txt", "requirements.txt"),
]


def _extract_files(dest: Path, log_fn):
    """Copy bundled project files into the install directory."""
    src_root = _bundled_root()
    dest.mkdir(parents=True, exist_ok=True)

    for rel_src, rel_dst in _BUNDLE_ITEMS:
        src = src_root / rel_src
        dst = dest / rel_dst
        if not src.exists():
            log_fn(f"  WARNING: bundled file not found: {rel_src}\n")
            continue
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                log_fn(f"  Copied folder: {rel_dst}\\\n")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                log_fn(f"  Copied: {rel_dst}\n")
        except Exception as exc:
            log_fn(f"  ERROR copying {rel_src}: {exc}\n")
            raise


# ── Defaults (pre-filled in the wizard) ──────────────────────────────────────
DEFAULTS = {
    "TMDB_API_KEY":             "",
    "REAL_DEBRID_API_KEY":      "",
    "SECRET_KEY":               "change-me",
    "MOVIES_DIR":               str(Path.home() / "Media" / "Movies"),
    "TV_DIR":                   str(Path.home() / "Media" / "TV Shows"),
    "ANIME_DIR":                str(Path.home() / "Media" / "Anime"),
    "DOWNLOADS_DIR":            str(Path.home() / "Media" / "Downloads" / ".staging"),
    "POSTERS_DIR":              str(Path.home() / "Media" / "Posters"),
    "MOVIES_DIR_ARCHIVE":       r"D:\Media\Movies",
    "TV_DIR_ARCHIVE":           r"D:\Media\TV Shows",
    "ANIME_DIR_ARCHIVE":        r"D:\Media\Anime",
    "MPC_BE_EXE":               r"C:\Program Files\MPC-BE x64\mpc-be64.exe",
    "WATCH_THRESHOLD":          "0.85",
    "PORT":                     "8000",
    "HOST":                     "0.0.0.0",
    "MAX_CONCURRENT_DOWNLOADS": "2",
    "MPC_BE_URL":               "http://127.0.0.1:13579",
}


# ── Helper: read existing .env from a given root ──────────────────────────────
def _load_existing_env(root: Path) -> dict:
    d = {}
    env_file = root / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"')
    return d


def _write_env(root: Path, values: dict):
    """Write values to .env inside root, preserving unknown keys."""
    existing = _load_existing_env(root)
    merged   = {**DEFAULTS, **existing, **values}
    lines    = []
    for k, v in merged.items():
        if " " in v or "#" in v:
            v = f'"{v}"'
        lines.append(f"{k}={v}")
    with open(root / ".env", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Find a real Python interpreter ───────────────────────────────────────────
def _find_python(install_root: Path) -> str:
    """
    Return a usable Python executable.
    When frozen, sys.executable is the installer EXE — never use it for pip.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable   # plain .py/.pyw — sys.executable is real Python

    # 1. Project venv created by a previous run of this installer
    venv_py = install_root / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)

    # 2. System Python on PATH
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return found

    raise RuntimeError(
        "Python not found.\n\n"
        "Install Python 3.10+ from python.org, tick 'Add Python to PATH', "
        "then re-run this installer."
    )


# ── venv creation ─────────────────────────────────────────────────────────────
def _create_venv(root: Path, system_python: str, log_widget, done_callback):
    """Create a .venv inside root using the system Python."""
    venv_dir = root / ".venv"
    cmd = [system_python, "-m", "venv", str(venv_dir)]

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
            for line in proc.stdout:
                _append_log(log_widget, line)
            proc.wait()
            ok = proc.returncode == 0
            if ok:
                _append_log(log_widget, f"  Created: {venv_dir}\n")
        except Exception as exc:
            _append_log(log_widget, f"\nERROR creating venv: {exc}\n")
            ok = False
        done_callback(ok)

    threading.Thread(target=_run, daemon=True).start()


def _venv_python(root: Path) -> str:
    """Return the Python executable inside the project's .venv."""
    if IS_WINDOWS:
        return str(root / ".venv" / "Scripts" / "python.exe")
    return str(root / ".venv" / "bin" / "python")


# ── pip install ───────────────────────────────────────────────────────────────
def _pip_install(root: Path, log_widget, done_callback):
    """Install requirements into the project's .venv."""
    python = _venv_python(root)
    requirements = root / "requirements.txt"
    cmd = [python, "-m", "pip", "install", "-r", str(requirements), "--upgrade"]

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
            for line in proc.stdout:
                _append_log(log_widget, line)
            proc.wait()
            ok = proc.returncode == 0
        except Exception as exc:
            _append_log(log_widget, f"\nERROR: {exc}\n")
            ok = False
        done_callback(ok)

    threading.Thread(target=_run, daemon=True).start()


# ── Post-install validation ───────────────────────────────────────────────────
def _validate_install(root: Path, log_widget, done_callback):
    """Verify the install worked: check key packages can be imported."""
    python = _venv_python(root)
    check_script = (
        "import uvicorn, fastapi, dotenv, aiofiles, aiosqlite, httpx; "
        "print('All packages OK')"
    )
    cmd = [python, "-c", check_script]

    def _run():
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
            if result.returncode == 0:
                _append_log(log_widget, f"  {result.stdout.strip()}\n")
                ok = True
            else:
                _append_log(log_widget, f"  Import check failed:\n{result.stderr}\n")
                ok = False
        except Exception as exc:
            _append_log(log_widget, f"  Validation error: {exc}\n")
            ok = False
        done_callback(ok)

    threading.Thread(target=_run, daemon=True).start()


def _append_log(widget, text):
    widget.configure(state="normal")
    widget.insert(tk.END, text)
    widget.see(tk.END)
    widget.configure(state="disabled")


# ── Task Scheduler ────────────────────────────────────────────────────────────
def _create_task_scheduler(root: Path, port: str, log_widget, done_callback):
    vbs_path = root / "silent_launch.vbs"
    _write_vbs_launcher(root)   # always regenerate with correct paths

    xml_path = root / "task_def.xml"
    _write_task_xml(root, xml_path, str(vbs_path))

    cmd = ["schtasks", "/Create", "/TN", "MediaDownloader", "/XML", str(xml_path), "/F"]

    def _run():
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
            )
            _append_log(log_widget, result.stdout + result.stderr + "\n")
            ok = result.returncode == 0
        except Exception as exc:
            _append_log(log_widget, f"Task Scheduler error: {exc}\n")
            ok = False
        finally:
            try: xml_path.unlink()
            except: pass
        done_callback(ok)

    threading.Thread(target=_run, daemon=True).start()


def _write_vbs_launcher(root: Path):
    run_bat = root / "run_server.bat"
    content = (
        "' Silent launcher — runs run_server.bat without a console window\n"
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        f"sh.Run \"cmd /c \\\"{run_bat}\\\"\", 0, False\n"
    )
    with open(root / "silent_launch.vbs", "w", encoding="utf-8") as f:
        f.write(content)


def _write_task_xml(root: Path, xml_path: Path, vbs_path: str):
    def _esc(s):
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>wscript.exe</Command>
      <Arguments>//nologo "{_esc(vbs_path)}"</Arguments>
      <WorkingDirectory>{_esc(str(root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
    with open(xml_path, "w", encoding="utf-16") as f:
        f.write(xml)


# ═══════════════════════════════════════════════════════════════════════════════
#  Wizard UI
# ═══════════════════════════════════════════════════════════════════════════════

BG       = "#0c0c10"
SURFACE  = "#16161e"
SURFACE2 = "#1e1e28"
BORDER   = "#2a2a38"
ACCENT   = "#e5a00d"
TEXT     = "#e8e8f0"
MUTED    = "#7878a0"
SUCCESS  = "#4caf7d"
ERROR    = "#e05555"

FONT_BODY  = ("Segoe UI", 10)
FONT_LABEL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_SUB   = ("Segoe UI", 10, "bold")
FONT_MONO  = ("Consolas", 9)


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Downloader — Setup")
        self.configure(bg=BG)
        self.resizable(False, False)

        w, h = 680, 620
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # ── Install location — the single source of truth ─────────────────
        # Default: ~/MediaDownloader.  User can change it on the Welcome page.
        self.install_var = tk.StringVar(value=str(_DEFAULT_INSTALL))

        # Pre-fill form fields from defaults (overridden by existing .env if
        # the user happens to point at a folder with one)
        self.vals = {k: tk.StringVar(value=v) for k, v in DEFAULTS.items()}

        self._pages: list[tk.Frame] = []
        self._current = 0

        # ── Header ────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=SURFACE, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="▣ Media Downloader", bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=20)
        self._step_label = tk.Label(header, text="Step 1 of 5", bg=SURFACE,
                                    fg=MUTED, font=FONT_LABEL)
        self._step_label.pack(side="right", padx=20)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        self._container = tk.Frame(self, bg=BG)
        self._container.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = tk.Frame(self, bg=SURFACE, height=52)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        self._btn_back = tk.Button(
            footer, text="← Back", command=self._go_back,
            bg=SURFACE2, fg=MUTED, relief="flat", font=FONT_BODY,
            activebackground=SURFACE, activeforeground=TEXT,
            cursor="hand2", padx=16, pady=6)
        self._btn_back.pack(side="left", padx=16, pady=10)

        self._btn_next = tk.Button(
            footer, text="Next →", command=self._go_next,
            bg=ACCENT, fg="#111", relief="flat",
            font=("Segoe UI", 10, "bold"),
            activebackground="#c27b00", activeforeground="#111",
            cursor="hand2", padx=20, pady=6)
        self._btn_next.pack(side="right", padx=16, pady=10)

        self._pages = [
            self._page_welcome(),
            self._page_api_keys(),
            self._page_directories(),
            self._page_playback(),
            self._page_install(),
            self._page_done(),
        ]
        self._show_page(0)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _show_page(self, idx):
        for p in self._pages:
            p.pack_forget()
        self._pages[idx].pack(fill="both", expand=True)
        self._current = idx
        total = len(self._pages) - 1
        self._step_label.configure(text=f"Step {min(idx+1, total)} of {total}")
        self._btn_back.configure(state="normal" if idx > 0 else "disabled")
        if idx == len(self._pages) - 2:
            self._btn_next.configure(text="Install ✓", bg=SUCCESS, fg="#fff",
                                     activebackground="#3a9060")
        elif idx == len(self._pages) - 1:
            self._btn_next.configure(text="Finish", bg=ACCENT, fg="#111",
                                     activebackground="#c27b00")
            self._btn_back.configure(state="disabled")
        else:
            self._btn_next.configure(text="Next →", bg=ACCENT, fg="#111",
                                     activebackground="#c27b00")

    def _go_next(self):
        if self._current == 0:
            if not self._validate_install_dir():
                return
        if self._current == len(self._pages) - 1:
            self.destroy()
            return
        # Page 4 is the install/log page — both "Install ✓" and "Retry ↺" run install
        if self._current == len(self._pages) - 2:
            self._reset_log()
            self._run_install()
            return
        self._show_page(self._current + 1)

    def _go_back(self):
        if self._current > 0:
            self._show_page(self._current - 1)

    def _validate_install_dir(self) -> bool:
        """Make sure the chosen install path is usable."""
        dest = Path(self.install_var.get().strip())
        if not dest.name:
            messagebox.showerror("Invalid path", "Please enter a valid install folder path.")
            return False

        # Check the parent exists (or can be created) and is writable
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror(
                "Cannot create folder",
                f"Could not create the install folder:\n{dest}\n\n{exc}"
            )
            return False

        # If a previous install exists there, offer to upgrade
        if (dest / "run_server.bat").exists():
            existing_env = _load_existing_env(dest)
            for k, v in existing_env.items():
                if k in self.vals:
                    self.vals[k].set(v)

        return True

    # ── Field helpers ─────────────────────────────────────────────────────────

    def _make_page(self) -> tk.Frame:
        return tk.Frame(self._container, bg=BG)

    def _lbl(self, parent, text, big=False, muted=False):
        font = FONT_TITLE if big else (FONT_SUB if not muted else FONT_LABEL)
        fg   = TEXT if not muted else MUTED
        tk.Label(parent, text=text, bg=BG, fg=fg, font=font,
                 justify="left", wraplength=580).pack(anchor="w", pady=(0, 4))

    def _field(self, parent, label: str, var: tk.StringVar,
               password=False, browse_dir=False, browse_file=False) -> tk.Frame:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=MUTED, font=FONT_LABEL,
                 anchor="w", width=24).pack(side="left")
        entry = tk.Entry(row, textvariable=var, show="*" if password else "",
                         bg=SURFACE2, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=FONT_BODY, bd=4,
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
        entry.pack(side="left", fill="x", expand=True)
        if browse_dir:
            tk.Button(row, text="📁", bg=SURFACE2, fg=MUTED, relief="flat",
                      cursor="hand2", font=FONT_LABEL,
                      command=lambda v=var: self._browse_dir(v)
                      ).pack(side="left", padx=(4, 0))
        if browse_file:
            tk.Button(row, text="📄", bg=SURFACE2, fg=MUTED, relief="flat",
                      cursor="hand2", font=FONT_LABEL,
                      command=lambda v=var: self._browse_file(v)
                      ).pack(side="left", padx=(4, 0))
        return row

    def _browse_dir(self, var: tk.StringVar):
        d = filedialog.askdirectory(initialdir=var.get() or str(Path.home()))
        if d:
            var.set(d)

    def _browse_file(self, var: tk.StringVar):
        p = filedialog.askopenfilename(
            initialdir=str(Path(var.get()).parent) if var.get() else str(Path.home()),
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
        )
        if p:
            var.set(p)

    # ── Page 0: Welcome ───────────────────────────────────────────────────────

    def _page_welcome(self):
        p = self._make_page()
        tk.Label(p, text="▣", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 40)).pack(pady=(4, 2))
        self._lbl(p, "Welcome to Media Downloader", big=True)
        self._lbl(p,
                  "This wizard will install Media Downloader and configure it "
                  "for your system.", muted=True)

        # ── Uninstall section (shown when an existing install is detected) ──
        # A zero-height placeholder always occupies this position in the layout.
        # The visible card is packed/forgotten inside it so repacking never
        # moves it to the bottom of the page.
        _uninstall_slot = tk.Frame(p, bg=BG)
        _uninstall_slot.pack(fill="x", pady=(8, 0))

        self._uninstall_frame = tk.Frame(_uninstall_slot, bg=SURFACE2,
                                         highlightthickness=1,
                                         highlightbackground=BORDER)
        # (not packed yet — shown by _refresh_uninstall_section)

        uninstall_left = tk.Frame(self._uninstall_frame, bg=SURFACE2)
        uninstall_left.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        tk.Label(uninstall_left, bg=SURFACE2, fg=SUCCESS, font=FONT_LABEL,
                 text="✓ Existing installation detected at this location."
                 ).pack(anchor="w")
        tk.Label(uninstall_left, bg=SURFACE2, fg=MUTED, font=FONT_LABEL,
                 text="Stops the server, removes the task, and deletes the install folder. "
                      "Media files are not touched."
                 ).pack(anchor="w", pady=(2, 0))

        self._uninstall_btn = tk.Button(
            self._uninstall_frame, text="🗑 Uninstall",
            bg=ERROR, fg="#fff", relief="flat",
            font=("Segoe UI", 10, "bold"),
            activebackground="#b84444", activeforeground="#fff",
            cursor="hand2", padx=14, pady=6,
            command=self._do_uninstall)
        self._uninstall_btn.pack(side="right", padx=12, pady=8)

        # Re-check whenever the install path changes
        self.install_var.trace_add("write", lambda *_: self._refresh_uninstall_section())
        self._refresh_uninstall_section()

        # ── Install location ──────────────────────────────────────────────
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=8)
        tk.Label(p, bg=BG, fg=TEXT, font=FONT_SUB,
                 text="Install Location").pack(anchor="w")
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL, wraplength=580,
                 text="Choose where Media Downloader will be installed. "
                      "The folder will be created if it doesn't exist."
                 ).pack(anchor="w", pady=(2, 6))

        folder_row = tk.Frame(p, bg=BG)
        folder_row.pack(fill="x")
        folder_entry = tk.Entry(
            folder_row, textvariable=self.install_var,
            bg=SURFACE2, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=FONT_BODY, bd=4,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT)
        folder_entry.pack(side="left", fill="x", expand=True)
        tk.Button(folder_row, text="Browse…", bg=ACCENT, fg="#111",
                  relief="flat", font=FONT_LABEL, cursor="hand2",
                  padx=10, pady=4,
                  command=self._browse_install_dir
                  ).pack(side="left", padx=(6, 0))

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=8)

        tk.Label(p, bg=BG, fg=MUTED, font=FONT_BODY, justify="left", wraplength=580,
                 text="You will also need:\n"
                      "  • Python 3.10+ installed and on your PATH\n"
                      "  • A TMDB API key  (free — themoviedb.org)\n"
                      "  • A Real-Debrid API key  (paid — realdebrid.com)\n"
                      "  • MPC-BE with its web interface enabled on port 13579"
                 ).pack(anchor="w")

        link_row = tk.Frame(p, bg=BG)
        link_row.pack(anchor="w", pady=(10, 0))
        tk.Label(link_row, text="Get API keys:", bg=BG, fg=MUTED,
                 font=FONT_LABEL).pack(side="left")
        tk.Button(link_row, text="TMDB →", bg=SURFACE2, fg=ACCENT, relief="flat",
                  font=FONT_LABEL, cursor="hand2", padx=10, pady=3,
                  command=lambda: webbrowser.open(
                      "https://www.themoviedb.org/settings/api")
                  ).pack(side="left", padx=(8, 4))
        tk.Button(link_row, text="Real-Debrid →", bg=SURFACE2, fg=ACCENT,
                  relief="flat", font=FONT_LABEL, cursor="hand2", padx=10, pady=3,
                  command=lambda: webbrowser.open(
                      "https://real-debrid.com/apitoken")
                  ).pack(side="left", padx=4)

        return p

    def _is_installed(self) -> bool:
        """Return True if an existing install is detected at the chosen path."""
        dest = Path(self.install_var.get().strip())
        return (dest / "run_server.bat").exists() and (dest / ".venv").exists()

    def _refresh_uninstall_section(self):
        """Show or hide the uninstall card inside its placeholder slot."""
        try:
            if self._is_installed():
                self._uninstall_frame.pack(fill="x")
            else:
                self._uninstall_frame.pack_forget()
        except Exception:
            pass

    def _do_uninstall(self):
        dest = Path(self.install_var.get().strip())
        if not messagebox.askyesno(
            "Confirm Uninstall",
            f"This will permanently:\n\n"
            f"  \u2022 Stop the running server\n"
            f"  \u2022 Remove the Task Scheduler task\n"
            f"  \u2022 Remove the firewall rule\n"
            f"  \u2022 Delete the install folder:\n    {dest}\n\n"
            f"Your media files will NOT be deleted.\n\n"
            f"Continue?",
            icon="warning",
        ):
            return

        # ── Progress window ────────────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title("Uninstalling Media Downloader")
        win.configure(bg=BG)
        win.resizable(False, False)
        w, h = 560, 360
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.grab_set()

        tk.Label(win, text="Uninstalling Media Downloader…",
                 bg=BG, fg=TEXT, font=FONT_SUB).pack(anchor="w", padx=20, pady=(16, 4))

        log = tk.Text(win, height=12, state="disabled",
                      bg=SURFACE2, fg=MUTED, font=FONT_MONO,
                      relief="flat", bd=4,
                      highlightthickness=1, highlightbackground=BORDER)
        log.pack(fill="both", expand=True, padx=20, pady=6)

        status_lbl = tk.Label(win, text="", bg=BG, fg=MUTED, font=FONT_LABEL)
        status_lbl.pack(anchor="w", padx=20)

        close_btn = tk.Button(
            win, text="Close", state="disabled",
            bg=ACCENT, fg="#111", relief="flat",
            font=("Segoe UI", 10, "bold"), cursor="hand2",
            activebackground="#c27b00", padx=16, pady=6,
            command=win.destroy)
        close_btn.pack(side="right", padx=20, pady=12)

        def _run():
            import time
            cf = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0

            def run_cmd(args):
                try:
                    r = subprocess.run(args, capture_output=True, text=True,
                                       creationflags=cf, timeout=10)
                    return (r.stdout + r.stderr).strip()
                except Exception as exc:
                    return str(exc)

            _append_log(log, "Stopping server (Task Scheduler)…\n")
            run_cmd(["schtasks", "/end", "/tn", "MediaDownloader"])
            _append_log(log, "  Done\n")

            # Kill any python/wscript processes launched from this install dir
            _append_log(log, "Terminating server process…\n")
            venv_py = str(dest / ".venv" / "Scripts" / "python.exe")
            vbs     = str(dest / "silent_launch.vbs")
            for path_fragment in [venv_py, vbs]:
                try:
                    subprocess.run(
                        ["taskkill", "/f", "/fi",
                         f"IMAGENAME eq python.exe",
                         "/fi", f"MODULES eq {Path(path_fragment).name}"],
                        capture_output=True, creationflags=cf)
                except Exception:
                    pass
            # Fallback: wmic to kill by executable path
            try:
                subprocess.run(
                    ["wmic", "process", "where",
                     f"ExecutablePath like '%{dest.name}%'", "delete"],
                    capture_output=True, creationflags=cf, timeout=8)
            except Exception:
                pass
            time.sleep(1)
            _append_log(log, "  Done\n")

            _append_log(log, "\nRemoving Task Scheduler task…\n")
            out = run_cmd(["schtasks", "/delete", "/tn", "MediaDownloader", "/f"])
            _append_log(log, f"  {out or 'Done'}\n")

            _append_log(log, "\nRemoving firewall rule…\n")
            run_cmd(["netsh", "advfirewall", "firewall",
                     "delete", "rule", "name=MediaDownloader"])
            _append_log(log, "  Done\n")

            _append_log(log, f"\nDeleting install folder:\n  {dest}\n")
            try:
                shutil.rmtree(dest)
                _append_log(log, "  Deleted.\n")
                ok = True
            except Exception as exc:
                _append_log(log, f"  ERROR: {exc}\n")
                _append_log(log, "  Some files may be locked. Close any open windows "
                                 "from this folder and try again.\n")
                ok = False

            if ok:
                status_lbl.configure(text="✓ Uninstall complete. You can close this window.", fg=SUCCESS)
            else:
                status_lbl.configure(
                    text="⚠ Finished with errors — check the log above.", fg=ACCENT)
            close_btn.configure(state="normal")
            # Hide the uninstall section on the welcome page
            self._uninstall_frame.pack_forget()

        threading.Thread(target=_run, daemon=True).start()

    def _browse_install_dir(self):
        d = filedialog.askdirectory(
            title="Choose install location",
            initialdir=self.install_var.get() or str(Path.home()),
        )
        if d:
            self.install_var.set(d)

    # ── Page 1: API Keys ──────────────────────────────────────────────────────

    def _page_api_keys(self):
        p = self._make_page()
        self._lbl(p, "API Keys", big=True)
        self._lbl(p, "Enter your API credentials below.", muted=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._field(p, "TMDB API Key *",       self.vals["TMDB_API_KEY"],        password=True)
        self._field(p, "Real-Debrid Key *",    self.vals["REAL_DEBRID_API_KEY"], password=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._lbl(p, "Webhook Security (optional)")
        self._field(p, "Secret Key",            self.vals["SECRET_KEY"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL, justify="left",
                 text="Set a strong random string to secure the Siri shortcut endpoint. "
                      "Leave as 'change-me' to disable auth."
                 ).pack(anchor="w", pady=(4, 0))
        return p

    # ── Page 2: Directories ───────────────────────────────────────────────────

    def _page_directories(self):
        p = self._make_page()
        self._lbl(p, "Media Directories", big=True)

        canvas = tk.Canvas(p, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _section(label):
            tk.Label(inner, text=label, bg=BG, fg=TEXT, font=FONT_SUB,
                     anchor="w").pack(anchor="w", pady=(12, 2))
            tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))

        _section("Primary Drive  (NVMe — new downloads land here)")
        self._field(inner, "Movies",    self.vals["MOVIES_DIR"],    browse_dir=True)
        self._field(inner, "TV Shows",  self.vals["TV_DIR"],        browse_dir=True)
        self._field(inner, "Anime",     self.vals["ANIME_DIR"],     browse_dir=True)
        self._field(inner, "Downloads", self.vals["DOWNLOADS_DIR"], browse_dir=True)
        self._field(inner, "Posters",   self.vals["POSTERS_DIR"],   browse_dir=True)

        _section("Archive Drive  (SATA — watched content moved here)")
        self._field(inner, "Movies Archive",   self.vals["MOVIES_DIR_ARCHIVE"],  browse_dir=True)
        self._field(inner, "TV Archive",       self.vals["TV_DIR_ARCHIVE"],      browse_dir=True)
        self._field(inner, "Anime Archive",    self.vals["ANIME_DIR_ARCHIVE"],   browse_dir=True)

        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))
        return p

    # ── Page 3: Playback ──────────────────────────────────────────────────────

    def _page_playback(self):
        p = self._make_page()
        self._lbl(p, "Playback Settings", big=True)
        self._lbl(p, "Configure MPC-BE integration and server options.", muted=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)

        self._field(p, "MPC-BE Executable", self.vals["MPC_BE_EXE"], browse_file=True)
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL,
                 text="Full path to mpc-be64.exe."
                 ).pack(anchor="w", pady=(0, 10))

        self._field(p, "MPC-BE Web URL",    self.vals["MPC_BE_URL"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL,
                 text="Enable in MPC-BE → Options → Player → Web Interface (port 13579)."
                 ).pack(anchor="w", pady=(0, 10))

        self._field(p, "Watch Threshold",   self.vals["WATCH_THRESHOLD"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL,
                 text="Fraction watched before archiving (default 0.85 = 85%)."
                 ).pack(anchor="w", pady=(0, 10))

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._field(p, "Server Port",       self.vals["PORT"])
        self._field(p, "Max Concurrent DL", self.vals["MAX_CONCURRENT_DOWNLOADS"])
        return p

    # ── Page 4: Install ───────────────────────────────────────────────────────

    def _page_install(self):
        p = self._make_page()
        self._lbl(p, "Install", big=True)

        self._install_task_var = tk.BooleanVar(value=IS_WINDOWS)
        cb_row = tk.Frame(p, bg=BG)
        cb_row.pack(anchor="w", pady=(0, 12))
        cb = tk.Checkbutton(
            cb_row, variable=self._install_task_var,
            text="Register Windows Task Scheduler task (auto-start at login)",
            bg=BG, fg=TEXT, selectcolor=SURFACE2,
            activebackground=BG, activeforeground=TEXT, font=FONT_BODY)
        cb.pack(anchor="w")
        if not IS_WINDOWS:
            cb.configure(state="disabled")
            tk.Label(cb_row, text="  (Windows only)",
                     bg=BG, fg=MUTED, font=FONT_LABEL).pack(anchor="w")

        tk.Label(p, text="Installation log:", bg=BG, fg=MUTED,
                 font=FONT_LABEL).pack(anchor="w")
        self._log_text = tk.Text(
            p, height=14, state="disabled",
            bg=SURFACE2, fg=MUTED, font=FONT_MONO,
            relief="flat", bd=4,
            highlightthickness=1, highlightbackground=BORDER)
        self._log_text.pack(fill="both", expand=True, pady=6)

        self._install_status = tk.Label(p, text="", bg=BG, fg=MUTED, font=FONT_LABEL)
        self._install_status.pack(anchor="w")
        return p

    # ── Page 5: Done ──────────────────────────────────────────────────────────

    def _page_done(self):
        p = self._make_page()
        self._done_icon = tk.Label(p, text="✓", bg=BG, fg=SUCCESS,
                                   font=("Segoe UI", 56, "bold"))
        self._done_icon.pack(pady=(20, 4))
        tk.Label(p, text="Installation Complete!", bg=BG, fg=TEXT,
                 font=FONT_TITLE).pack()
        self._done_msg = tk.Label(p, bg=BG, fg=MUTED, font=FONT_BODY,
                                  justify="center", wraplength=480, text="")
        self._done_msg.pack(pady=16)

        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(pady=8)
        if IS_WINDOWS:
            tk.Button(btn_row, text="▶ Start Server Now", bg=SUCCESS, fg="#fff",
                      relief="flat", font=("Segoe UI", 10, "bold"),
                      activebackground="#3a9060", cursor="hand2",
                      padx=16, pady=6,
                      command=self._start_server_now).pack(side="left", padx=8)
            tk.Button(btn_row, text="Open Browser", bg=SURFACE2, fg=TEXT,
                      relief="flat", font=FONT_BODY, cursor="hand2",
                      padx=12, pady=6,
                      command=lambda: webbrowser.open(
                          f"http://localhost:{self.vals['PORT'].get()}")
                      ).pack(side="left", padx=8)
        else:
            tk.Label(btn_row,
                     text="Transfer the install folder to your Windows PC "
                          "and run run_server.bat there.",
                     bg=BG, fg=MUTED, font=FONT_LABEL).pack()
        return p

    def _start_server_now(self):
        root = Path(self.install_var.get())
        run_bat = root / "run_server.bat"
        if run_bat.exists():
            subprocess.Popen(["cmd", "/c", str(run_bat)], creationflags=_DETACHED)
        else:
            messagebox.showwarning("Not found", f"run_server.bat not found in:\n{root}")

    # ── Install logic ─────────────────────────────────────────────────────────

    def _reset_log(self):
        """Clear the log and status label before a fresh install attempt."""
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state="disabled")
        self._install_status.configure(text="", fg=MUTED)
        self._btn_next.configure(
            text="Install ✓", state="disabled",
            bg=SUCCESS, fg="#fff", activebackground="#3a9060")
        self._btn_back.configure(state="disabled")

    def _run_install(self):
        if not self.vals["TMDB_API_KEY"].get().strip():
            messagebox.showerror("Missing field", "TMDB API Key is required.")
            self._show_page(1); return
        if not self.vals["REAL_DEBRID_API_KEY"].get().strip():
            messagebox.showerror("Missing field", "Real-Debrid API Key is required.")
            self._show_page(1); return

        dest = Path(self.install_var.get())

        self._btn_next.configure(state="disabled")
        self._btn_back.configure(state="disabled")
        self._show_page(4)

        def _step0_extract():
            _append_log(self._log_text, f"Installing to: {dest}\n\n")
            _append_log(self._log_text, "Copying program files…\n")
            try:
                _extract_files(dest, lambda msg: _append_log(self._log_text, msg))
                _append_log(self._log_text, "Files installed.\n\n")
            except Exception as exc:
                _append_log(self._log_text, f"\nERROR during file extraction: {exc}\n")
                self._finish_install(False); return
            _step1_write_env()

        def _step1_write_env():
            _append_log(self._log_text, "Writing .env configuration…\n")
            vals = {k: v.get() for k, v in self.vals.items()}
            try:
                _write_env(dest, vals)
                _append_log(self._log_text, f"  Saved: {dest / '.env'}\n\n")
            except Exception as exc:
                _append_log(self._log_text, f"  ERROR: {exc}\n")
                self._finish_install(False); return

            _append_log(self._log_text, "Locating Python interpreter…\n")
            try:
                system_python = _find_python(dest)
                _append_log(self._log_text, f"  Using: {system_python}\n\n")
            except RuntimeError as exc:
                _append_log(self._log_text, f"  ERROR: {exc}\n")
                self._finish_install(False); return

            _append_log(self._log_text, "Creating virtual environment (.venv)…\n")
            _create_venv(dest, system_python, self._log_text, _step2_after_venv)

        def _step2_after_venv(ok: bool):
            if not ok:
                _append_log(self._log_text, "\nFailed to create virtual environment.\n")
                self._finish_install(False); return
            _append_log(self._log_text, "\nInstalling Python dependencies…\n")
            _pip_install(dest, self._log_text, _step3_after_pip)

        def _step3_after_pip(ok: bool):
            if not ok:
                _append_log(self._log_text, "\nDependency install failed.\n")
                self._finish_install(False); return
            _append_log(self._log_text, "\nDependencies installed.\n\n")
            _append_log(self._log_text, "Validating installation…\n")
            _validate_install(dest, self._log_text, _step4_after_validation)

        def _step4_after_validation(ok: bool):
            if not ok:
                _append_log(self._log_text,
                    "\nValidation failed — the server may not start correctly.\n"
                    "Try re-running the installer.\n")
                self._finish_install(False); return
            _append_log(self._log_text, "\n")
            if self._install_task_var.get():
                _append_log(self._log_text, "Creating Task Scheduler task…\n")
                _create_task_scheduler(
                    dest, self.vals["PORT"].get(),
                    self._log_text, _step5_after_task)
            else:
                _step5_after_task(True)

        def _step5_after_task(ok: bool):
            if self._install_task_var.get():
                msg = "Task registered: MediaDownloader\n\n" if ok \
                      else "Task Scheduler failed — start manually with run_server.bat.\n\n"
                _append_log(self._log_text, msg)
            self._finish_install(True)

        threading.Thread(target=_step0_extract, daemon=True).start()

    def _finish_install(self, ok: bool):
        port = self.vals["PORT"].get()
        dest = Path(self.install_var.get())
        if ok:
            if IS_WINDOWS:
                auto = ("auto-starts at login (Task Scheduler task registered)."
                        if self._install_task_var.get()
                        else "run run_server.bat to start the server.")
            else:
                auto = "run run_server.bat on Windows to start the server."
            self._done_msg.configure(
                text=f"Installed to:\n{dest}\n\n"
                     f"Server {auto}\n\n"
                     f"Then open http://localhost:{port} in a browser.",
                fg=MUTED)
            self._done_icon.configure(text="✓", fg=SUCCESS)
            # Success — advance to Done page, no going back needed
            self._btn_next.configure(state="normal")
            self._btn_back.configure(state="disabled")
            self._show_page(5)
        else:
            # Failure — stay on the log page so the user can read the output
            _append_log(self._log_text, "\n── Installation failed ──────────────────\n")
            self._install_status.configure(
                text="✗  Installation failed — review the log above.",
                fg=ERROR)
            # Re-enable Back so they can correct settings and retry
            self._btn_back.configure(state="normal")
            self._btn_next.configure(
                text="Retry ↺", state="normal",
                bg=ACCENT, fg="#111", activebackground="#c27b00")


if __name__ == "__main__":
    InstallerApp().mainloop()
