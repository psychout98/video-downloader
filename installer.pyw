"""
Media Downloader — Windows Installer / Setup Wizard
====================================================
Run with:  python installer.pyw
Compile to .exe with:  build_installer.bat

Wizard pages
------------
1. Welcome
2. API Keys   (TMDB, Real-Debrid, optional webhook secret)
3. Directories (primary NVMe + archive SATA paths)
4. Playback   (MPC-BE exe path, watch threshold)
5. Install    (writes .env, pip install, creates Task Scheduler task)
6. Done
"""
import os
import sys
import subprocess
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Locate project root ───────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Compiled with PyInstaller — EXE lives in the project root
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).parent

ENV_FILE      = ROOT / ".env"
REQUIREMENTS  = ROOT / "requirements.txt"
VBS_LAUNCHER  = ROOT / "silent_launch.vbs"


# ── Defaults (pre-filled in the wizard) ──────────────────────────────────────
DEFAULTS = {
    "TMDB_API_KEY":        "",
    "REAL_DEBRID_API_KEY": "",
    "SECRET_KEY":          "change-me",
    "MOVIES_DIR":          str(Path.home() / "Media" / "Movies"),
    "TV_DIR":              str(Path.home() / "Media" / "TV Shows"),
    "ANIME_DIR":           str(Path.home() / "Media" / "Anime"),
    "DOWNLOADS_DIR":       str(Path.home() / "Media" / "Downloads" / ".staging"),
    "POSTERS_DIR":         str(Path.home() / "Media" / "Posters"),
    "MOVIES_DIR_ARCHIVE":  r"D:\Media\Movies",
    "TV_DIR_ARCHIVE":      r"D:\Media\TV Shows",
    "ANIME_DIR_ARCHIVE":   r"D:\Media\Anime",
    "MPC_BE_EXE":          r"C:\Program Files\MPC-BE x64\mpc-be64.exe",
    "WATCH_THRESHOLD":     "0.85",
    "PORT":                "8000",
    "HOST":                "0.0.0.0",
    "MAX_CONCURRENT_DOWNLOADS": "2",
    "MPC_BE_URL":          "http://127.0.0.1:13579",
}


def _load_existing_env():
    """Read existing .env values so re-running the wizard keeps prior config."""
    d = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                d[k.strip()] = v.strip().strip('"')
    return d


def _write_env(values: dict):
    """Write values to .env, preserving any existing keys not in values."""
    existing = _load_existing_env()
    merged   = {**DEFAULTS, **existing, **values}
    lines    = []
    for k, v in merged.items():
        # Quote values that contain spaces or special chars
        if " " in v or "#" in v:
            v = f'"{v}"'
        lines.append(f"{k}={v}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _find_python() -> str:
    """Return the Python executable being used to run this installer."""
    return sys.executable


def _pip_install(log_widget, done_callback):
    """Run pip install -r requirements.txt in a background thread."""
    python = _find_python()
    cmd = [python, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--upgrade"]

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
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


def _append_log(widget, text):
    widget.configure(state="normal")
    widget.insert(tk.END, text)
    widget.see(tk.END)
    widget.configure(state="disabled")


def _create_task_scheduler(port: str, log_widget, done_callback):
    """Create a Windows Task Scheduler task that starts the server at logon."""
    python = _find_python()
    vbs    = str(VBS_LAUNCHER)
    task_name = "MediaDownloader"

    # Build the VBS launcher if it doesn't exist
    if not VBS_LAUNCHER.exists():
        _write_vbs_launcher(port)

    # schtasks /Create command
    xml_path = ROOT / "task_def.xml"
    _write_task_xml(xml_path, vbs)

    cmd = [
        "schtasks", "/Create",
        "/TN", task_name,
        "/XML", str(xml_path),
        "/F",  # overwrite if exists
    ]

    def _run():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            out = result.stdout + result.stderr
            _append_log(log_widget, out + "\n")
            ok = result.returncode == 0
        except Exception as exc:
            _append_log(log_widget, f"Task Scheduler error: {exc}\n")
            ok = False
        finally:
            try: xml_path.unlink()
            except: pass
        done_callback(ok)

    threading.Thread(target=_run, daemon=True).start()


def _write_vbs_launcher(port: str):
    """Write / update silent_launch.vbs with the correct Python path."""
    python  = _find_python()
    run_bat = ROOT / "run_server.bat"
    content = f"""' Silent launcher — runs run_server.bat without a console window
Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c """ + str(run_bat).replace("\\", "\\\\") + """", 0, False
"""
    with open(VBS_LAUNCHER, "w", encoding="utf-8") as f:
        f.write(content)


def _write_task_xml(xml_path: Path, vbs_path: str):
    vbs_escaped = str(vbs_path).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>
  </Triggers>
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
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>wscript.exe</Command>
      <Arguments>//nologo "{vbs_escaped}"</Arguments>
      <WorkingDirectory>{str(ROOT).replace("&", "&amp;")}</WorkingDirectory>
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

FONT_BODY   = ("Segoe UI", 10)
FONT_LABEL  = ("Segoe UI", 9)
FONT_TITLE  = ("Segoe UI", 14, "bold")
FONT_SUB    = ("Segoe UI", 10, "bold")
FONT_MONO   = ("Consolas", 9)


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Downloader — Setup")
        self.configure(bg=BG)
        self.resizable(False, False)

        # Center window
        w, h = 680, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # Load existing env
        existing = _load_existing_env()
        self.vals = {k: tk.StringVar(value=existing.get(k, v)) for k, v in DEFAULTS.items()}

        self._pages: list[tk.Frame] = []
        self._current = 0
        self._install_ok = False

        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=SURFACE, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="▣ Media Downloader", bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=20)
        self._step_label = tk.Label(header, text="Step 1 of 5", bg=SURFACE, fg=MUTED, font=FONT_LABEL)
        self._step_label.pack(side="right", padx=20)

        # ── Separator ───────────────────────────────────────────────────────
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Page container ───────────────────────────────────────────────────
        self._container = tk.Frame(self, bg=BG)
        self._container.pack(fill="both", expand=True, padx=30, pady=20)

        # ── Footer nav ───────────────────────────────────────────────────────
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        footer = tk.Frame(self, bg=SURFACE, height=52)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        self._btn_back = tk.Button(footer, text="← Back", command=self._go_back,
            bg=SURFACE2, fg=MUTED, relief="flat", font=FONT_BODY,
            activebackground=SURFACE, activeforeground=TEXT, cursor="hand2",
            padx=16, pady=6)
        self._btn_back.pack(side="left", padx=16, pady=10)

        self._btn_next = tk.Button(footer, text="Next →", command=self._go_next,
            bg=ACCENT, fg="#111", relief="flat", font=("Segoe UI", 10, "bold"),
            activebackground="#c27b00", activeforeground="#111", cursor="hand2",
            padx=20, pady=6)
        self._btn_next.pack(side="right", padx=16, pady=10)

        # ── Build pages ──────────────────────────────────────────────────────
        self._pages = [
            self._page_welcome(),
            self._page_api_keys(),
            self._page_directories(),
            self._page_playback(),
            self._page_install(),
            self._page_done(),
        ]
        self._show_page(0)

    # ─── Navigation ──────────────────────────────────────────────────────────

    def _show_page(self, idx):
        for p in self._pages:
            p.pack_forget()
        self._pages[idx].pack(fill="both", expand=True)
        self._current = idx
        total = len(self._pages) - 1  # "Done" is not a real step
        self._step_label.configure(text=f"Step {min(idx+1, total)} of {total}")
        self._btn_back.configure(state="normal" if idx > 0 else "disabled")
        if idx == len(self._pages) - 2:  # last real step = Install
            self._btn_next.configure(text="Install ✓", bg=SUCCESS, fg="#fff",
                                     activebackground="#3a9060")
        elif idx == len(self._pages) - 1:  # Done page
            self._btn_next.configure(text="Finish", bg=ACCENT, fg="#111",
                                     activebackground="#c27b00")
            self._btn_back.configure(state="disabled")
        else:
            self._btn_next.configure(text="Next →", bg=ACCENT, fg="#111",
                                     activebackground="#c27b00")

    def _go_next(self):
        if self._current == len(self._pages) - 1:  # Done
            self.destroy()
            return
        if self._current == len(self._pages) - 2:  # Install page
            self._run_install()
            return
        self._show_page(self._current + 1)

    def _go_back(self):
        if self._current > 0:
            self._show_page(self._current - 1)

    # ─── Page builders ───────────────────────────────────────────────────────

    def _make_page(self) -> tk.Frame:
        f = tk.Frame(self._container, bg=BG)
        return f

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
        show = "*" if password else ""
        entry = tk.Entry(row, textvariable=var, show=show,
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

    # ─── Page 0: Welcome ─────────────────────────────────────────────────────

    def _page_welcome(self):
        p = self._make_page()
        tk.Label(p, text="▣", bg=BG, fg=ACCENT, font=("Segoe UI", 48)).pack(pady=(10, 4))
        self._lbl(p, "Welcome to Media Downloader", big=True)
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_BODY, justify="left", wraplength=580,
                 text=(
                     "This wizard will help you configure and install Media Downloader "
                     "on your Windows HTPC.\n\n"
                     "You will need:\n"
                     "  • A TMDB API key  (free at themoviedb.org)\n"
                     "  • A Real-Debrid API key  (paid service, realdebrid.com)\n"
                     "  • MPC-BE installed with its web interface enabled\n\n"
                     "The wizard will write your .env configuration file, install Python "
                     "dependencies, and optionally register a Windows Task Scheduler task "
                     "so the server starts automatically at login."
                 )).pack(anchor="w", pady=(8, 0))

        def _open_tmdb():
            webbrowser.open("https://www.themoviedb.org/settings/api")
        def _open_rd():
            webbrowser.open("https://real-debrid.com/apitoken")

        link_row = tk.Frame(p, bg=BG)
        link_row.pack(anchor="w", pady=(16, 0))
        tk.Label(link_row, text="Get API keys:", bg=BG, fg=MUTED, font=FONT_LABEL).pack(side="left")
        tk.Button(link_row, text="TMDB →", bg=SURFACE2, fg=ACCENT, relief="flat",
                  font=FONT_LABEL, cursor="hand2", command=_open_tmdb,
                  padx=10, pady=3).pack(side="left", padx=(8, 4))
        tk.Button(link_row, text="Real-Debrid →", bg=SURFACE2, fg=ACCENT, relief="flat",
                  font=FONT_LABEL, cursor="hand2", command=_open_rd,
                  padx=10, pady=3).pack(side="left", padx=4)
        return p

    # ─── Page 1: API Keys ────────────────────────────────────────────────────

    def _page_api_keys(self):
        p = self._make_page()
        self._lbl(p, "API Keys", big=True)
        self._lbl(p, "Enter your API credentials below.", muted=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._field(p, "TMDB API Key *",         self.vals["TMDB_API_KEY"],        password=True)
        self._field(p, "Real-Debrid API Key *",   self.vals["REAL_DEBRID_API_KEY"], password=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._lbl(p, "Webhook Security (optional)", muted=False)
        self._field(p, "Secret Key",              self.vals["SECRET_KEY"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL, justify="left",
                 text="Set a strong random string to secure the Siri shortcut webhook. "
                      "Leave as 'change-me' to disable authentication."
                 ).pack(anchor="w", pady=(4, 0))
        return p

    # ─── Page 2: Directories ─────────────────────────────────────────────────

    def _page_directories(self):
        p = self._make_page()
        self._lbl(p, "Media Directories", big=True)

        # Scrollable canvas for the many fields
        canvas = tk.Canvas(p, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_configure)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _section(label):
            tk.Label(inner, text=label, bg=BG, fg=TEXT, font=FONT_SUB,
                     anchor="w").pack(anchor="w", pady=(12, 2))
            tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=(0, 6))

        _section("Primary Drive  (fast NVMe — new downloads land here)")
        self._field(inner, "Movies",    self.vals["MOVIES_DIR"],    browse_dir=True)
        self._field(inner, "TV Shows",  self.vals["TV_DIR"],        browse_dir=True)
        self._field(inner, "Anime",     self.vals["ANIME_DIR"],     browse_dir=True)
        self._field(inner, "Downloads", self.vals["DOWNLOADS_DIR"], browse_dir=True)
        self._field(inner, "Posters",   self.vals["POSTERS_DIR"],   browse_dir=True)

        _section("Archive Drive  (SATA — watched content moved here)")
        self._field(inner, "Movies Archive",   self.vals["MOVIES_DIR_ARCHIVE"],  browse_dir=True)
        self._field(inner, "TV Shows Archive", self.vals["TV_DIR_ARCHIVE"],      browse_dir=True)
        self._field(inner, "Anime Archive",    self.vals["ANIME_DIR_ARCHIVE"],   browse_dir=True)

        # Mouse-wheel scrolling
        def _on_wheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _on_wheel)
        return p

    # ─── Page 3: Playback ────────────────────────────────────────────────────

    def _page_playback(self):
        p = self._make_page()
        self._lbl(p, "Playback Settings", big=True)
        self._lbl(p, "Configure MPC-BE integration and server options.", muted=True)
        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)

        self._field(p, "MPC-BE Executable", self.vals["MPC_BE_EXE"], browse_file=True)
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL, justify="left",
                 text="Full path to mpc-be64.exe. The server will launch MPC-BE automatically "
                      "when you press Play if it's not already running."
                 ).pack(anchor="w", pady=(0, 10))

        self._field(p, "MPC-BE Web URL",    self.vals["MPC_BE_URL"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL,
                 text="Default: http://127.0.0.1:13579  — enable the web interface in "
                      "MPC-BE → Options → Player → Web Interface."
                 ).pack(anchor="w", pady=(0, 10))

        self._field(p, "Watch Threshold",   self.vals["WATCH_THRESHOLD"])
        tk.Label(p, bg=BG, fg=MUTED, font=FONT_LABEL,
                 text="Fraction of a file that must be watched before it is moved to the "
                      "archive drive (default: 0.85 = 85%)."
                 ).pack(anchor="w", pady=(0, 10))

        tk.Frame(p, bg=BORDER, height=1).pack(fill="x", pady=10)
        self._field(p, "Server Port",       self.vals["PORT"])
        self._field(p, "Max Concurrent DL", self.vals["MAX_CONCURRENT_DOWNLOADS"])
        return p

    # ─── Page 4: Install ─────────────────────────────────────────────────────

    def _page_install(self):
        p = self._make_page()
        self._lbl(p, "Install", big=True)

        self._install_task_var = tk.BooleanVar(value=True)
        cb_row = tk.Frame(p, bg=BG)
        cb_row.pack(anchor="w", pady=(0, 12))
        tk.Checkbutton(cb_row, variable=self._install_task_var,
                       text="Register Windows Task Scheduler task (auto-start at login)",
                       bg=BG, fg=TEXT, selectcolor=SURFACE2, activebackground=BG,
                       activeforeground=TEXT, font=FONT_BODY).pack(anchor="w")

        tk.Label(p, text="Installation log:", bg=BG, fg=MUTED, font=FONT_LABEL).pack(anchor="w")
        self._log_text = tk.Text(p, height=14, state="disabled",
                                  bg=SURFACE2, fg=MUTED, font=FONT_MONO,
                                  relief="flat", bd=4,
                                  highlightthickness=1, highlightbackground=BORDER)
        self._log_text.pack(fill="both", expand=True, pady=6)

        self._install_status = tk.Label(p, text="", bg=BG, fg=MUTED, font=FONT_LABEL)
        self._install_status.pack(anchor="w")
        return p

    # ─── Page 5: Done ────────────────────────────────────────────────────────

    def _page_done(self):
        p = self._make_page()
        self._done_icon  = tk.Label(p, text="✓", bg=BG, fg=SUCCESS,
                                    font=("Segoe UI", 56, "bold"))
        self._done_icon.pack(pady=(20, 4))
        tk.Label(p, text="Installation Complete!", bg=BG, fg=TEXT,
                 font=FONT_TITLE).pack()
        self._done_msg = tk.Label(p, bg=BG, fg=MUTED, font=FONT_BODY,
                                  justify="center", wraplength=480,
                                  text="")
        self._done_msg.pack(pady=16)

        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(pady=8)
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
        return p

    def _start_server_now(self):
        run_bat = ROOT / "run_server.bat"
        if run_bat.exists():
            subprocess.Popen(["cmd", "/c", str(run_bat)],
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            messagebox.showwarning("Not found",
                f"run_server.bat not found at:\n{run_bat}\n\nStart the server manually.")

    # ─── Install logic ───────────────────────────────────────────────────────

    def _run_install(self):
        """Called when the user clicks 'Install' on the install page."""
        # Validate required fields
        if not self.vals["TMDB_API_KEY"].get().strip():
            messagebox.showerror("Missing field", "TMDB API Key is required.")
            self._show_page(1); return
        if not self.vals["REAL_DEBRID_API_KEY"].get().strip():
            messagebox.showerror("Missing field", "Real-Debrid API Key is required.")
            self._show_page(1); return

        # Disable navigation during install
        self._btn_next.configure(state="disabled")
        self._btn_back.configure(state="disabled")
        self._show_page(4)  # Install page

        def _step1_write_env():
            _append_log(self._log_text, "Writing .env configuration…\n")
            vals = {k: v.get() for k, v in self.vals.items()}
            try:
                _write_env(vals)
                _append_log(self._log_text, f"  Saved: {ENV_FILE}\n\n")
            except Exception as exc:
                _append_log(self._log_text, f"  ERROR writing .env: {exc}\n")
                self._finish_install(False)
                return
            # Step 2: pip install
            _append_log(self._log_text, "Installing Python dependencies…\n")
            _pip_install(self._log_text, _step2_after_pip)

        def _step2_after_pip(pip_ok: bool):
            if not pip_ok:
                _append_log(self._log_text, "\nDependency install failed — check the log above.\n")
                self._finish_install(False)
                return
            _append_log(self._log_text, "\nDependencies installed successfully.\n\n")
            if self._install_task_var.get():
                _append_log(self._log_text, "Creating Task Scheduler task…\n")
                _create_task_scheduler(
                    self.vals["PORT"].get(), self._log_text, _step3_after_task)
            else:
                _step3_after_task(True)

        def _step3_after_task(task_ok: bool):
            if self._install_task_var.get():
                if task_ok:
                    _append_log(self._log_text, "Task Scheduler task created: MediaDownloader\n\n")
                else:
                    _append_log(self._log_text,
                        "Task Scheduler failed — you can run run_server.bat manually.\n\n")
            self._finish_install(True)

        # Run in thread so UI stays responsive
        threading.Thread(target=_step1_write_env, daemon=True).start()

    def _finish_install(self, ok: bool):
        self._install_ok = ok
        port = self.vals["PORT"].get()
        if ok:
            self._done_msg.configure(
                text=f"Media Downloader is configured and ready.\n\n"
                     f"The server will start automatically at login "
                     f"{'(Task Scheduler task registered)' if self._install_task_var.get() else '(no auto-start — run run_server.bat manually)'}.\n\n"
                     f"Open http://localhost:{port} in your browser to access the UI.",
                fg=MUTED,
            )
            self._done_icon.configure(text="✓", fg=SUCCESS)
        else:
            self._done_msg.configure(
                text="Installation encountered errors. Check the log on the previous screen.\n\n"
                     "You can fix the issues and run the installer again, or configure .env manually.",
                fg=ERROR,
            )
            self._done_icon.configure(text="✗", fg=ERROR)

        self._btn_next.configure(state="normal")
        self._btn_back.configure(state="disabled")
        self._show_page(5)


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
