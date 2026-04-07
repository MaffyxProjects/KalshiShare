from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import webbrowser


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
REQUIRED_RUNTIME_MODULES = ("requests", "flask")
OPTIONAL_RUNTIME_MODULES = ("praw", "google.generativeai")

PALETTE = {
    "bg": "#f4efe6",
    "panel": "#fffdf8",
    "panel_alt": "#f2ead9",
    "hero": "#184c43",
    "hero_soft": "#dbece7",
    "text": "#211b16",
    "muted": "#6f655a",
    "border": "#d8cab4",
    "primary": "#1f6a58",
    "primary_hover": "#185645",
    "primary_pressed": "#14463a",
    "secondary": "#efe4d1",
    "secondary_hover": "#e5d7c0",
    "secondary_pressed": "#d8c9ae",
    "danger": "#9d4338",
    "danger_hover": "#85372d",
    "danger_pressed": "#6d2d25",
    "success_bg": "#dcefe7",
    "success_fg": "#1d5a4b",
    "warning_bg": "#f4e8c9",
    "warning_fg": "#785c12",
    "error_bg": "#f1ddd8",
    "error_fg": "#6f261e",
    "idle_bg": "#ebe2d3",
    "idle_fg": "#5d5247",
    "log_bg": "#1c211f",
    "log_fg": "#d7e2dc",
    "log_border": "#2a322f",
}


def build_pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SRC_DIR}{os.pathsep}{existing}" if existing else str(SRC_DIR)
    )
    return env


def subprocess_windowless_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}

    kwargs: dict[str, object] = {}
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startupinfo_type = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_type is not None:
        startupinfo = startupinfo_type()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

    return kwargs


def iter_python_commands() -> list[list[str]]:
    candidates: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    for candidate in (
        [str(ROOT_DIR / ".venv" / "Scripts" / "python.exe")],
        [sys.executable],
        ["py", "-3.13"],
        ["py", "-3.12"],
        ["py", "-3.11"],
        ["py", "-3.10"],
        ["python"],
    ):
        key = tuple(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)

    return candidates


def command_has_modules(command: list[str], modules: tuple[str, ...]) -> bool:
    probe = (
        "import importlib.util, sys; "
        "missing=[name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]; "
        "raise SystemExit(1 if missing else 0)"
    )
    try:
        result = subprocess.run(
            command + ["-c", probe, *modules],
            capture_output=True,
            text=True,
            timeout=8,
            **subprocess_windowless_kwargs(),
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0


def missing_modules(command: list[str], modules: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for module in modules:
        if not command_has_modules(command, (module,)):
            missing.append(module)
    return missing


def resolve_runtime_command(
    required_modules: tuple[str, ...] = REQUIRED_RUNTIME_MODULES,
) -> list[str] | None:
    for command in iter_python_commands():
        if command_has_modules(command, required_modules):
            return command
    return None


def build_dashboard_command(
    host: str,
    port: int,
    python_command: list[str] | None = None,
) -> list[str]:
    base = list(python_command or [sys.executable])
    return base + [
        "-m",
        "referral_assistant.ui.dashboard",
        "--host",
        host,
        "--port",
        str(port),
    ]


def build_cli_command(
    command: str,
    python_command: list[str] | None = None,
) -> list[str]:
    base = list(python_command or [sys.executable])
    return base + ["-m", "referral_assistant.cli", command]


@dataclass
class LauncherState:
    dashboard_process: subprocess.Popen[str] | None = None
    runtime_command: list[str] | None = None


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Referral Assistant Launcher")
        self.root.geometry("960x720")
        self.root.minsize(860, 620)
        self.root.configure(bg=PALETTE["bg"])
        self.state = LauncherState()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.ui_queue: queue.Queue[tuple[str, object | None]] = queue.Queue()

        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="8501")
        self.url_var = tk.StringVar(value=self.current_dashboard_url)
        self.runtime_var = tk.StringVar(value="Detecting a compatible Python runtime...")
        self.status_var = tk.StringVar(value="")
        self.status_detail_var = tk.StringVar(value="")

        self._configure_styles()
        self._build_ui()
        self._set_status(
            "Offline",
            "idle",
            "Click Launch Everything to initialize the database, start the dashboard, and open it in your browser.",
        )
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(150, self._pump_log_queue)
        self.root.after(400, self._refresh_dashboard_state)
        self.root.after(250, self._detect_runtime)

    @property
    def current_dashboard_url(self) -> str:
        host = self.host_var.get().strip() or "127.0.0.1"
        port = self.port_var.get().strip() or "8501"
        return f"http://{host}:{port}"

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Launcher.TEntry",
            padding=(10, 8),
            fieldbackground=PALETTE["panel"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["border"],
            lightcolor=PALETTE["border"],
            darkcolor=PALETTE["border"],
            relief="flat",
        )
        style.map(
            "Launcher.TEntry",
            fieldbackground=[("readonly", PALETTE["panel_alt"])],
            foreground=[("readonly", PALETTE["text"])],
        )

        style.configure(
            "Primary.Launcher.TButton",
            font=("Segoe UI Semibold", 11),
            padding=(18, 12),
            background=PALETTE["primary"],
            foreground="#ffffff",
            borderwidth=0,
            focuscolor=PALETTE["primary"],
        )
        style.map(
            "Primary.Launcher.TButton",
            background=[
                ("pressed", PALETTE["primary_pressed"]),
                ("active", PALETTE["primary_hover"]),
            ],
            foreground=[("disabled", "#f5f8f7")],
        )

        style.configure(
            "Secondary.Launcher.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 10),
            background=PALETTE["secondary"],
            foreground=PALETTE["text"],
            borderwidth=0,
            focuscolor=PALETTE["secondary"],
        )
        style.map(
            "Secondary.Launcher.TButton",
            background=[
                ("pressed", PALETTE["secondary_pressed"]),
                ("active", PALETTE["secondary_hover"]),
            ],
        )

        style.configure(
            "Danger.Launcher.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(14, 10),
            background=PALETTE["danger"],
            foreground="#ffffff",
            borderwidth=0,
            focuscolor=PALETTE["danger"],
        )
        style.map(
            "Danger.Launcher.TButton",
            background=[
                ("pressed", PALETTE["danger_pressed"]),
                ("active", PALETTE["danger_hover"]),
            ],
        )

    def _build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=PALETTE["bg"])
        shell.pack(fill=tk.BOTH, expand=True)
        shell.grid_rowconfigure(0, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(
            shell,
            bg=PALETTE["bg"],
            highlightthickness=0,
            bd=0,
        )
        canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        main = tk.Frame(canvas, bg=PALETTE["bg"], padx=24, pady=24)
        self.main_window_id = canvas.create_window((0, 0), window=main, anchor="nw")
        self.canvas = canvas
        self.main_frame = main

        def _sync_scroll_region(event: tk.Event[tk.Misc]) -> None:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def _sync_width(event: tk.Event[tk.Misc]) -> None:
            self.canvas.itemconfigure(self.main_window_id, width=event.width)

        main.bind("<Configure>", _sync_scroll_region)
        canvas.bind("<Configure>", _sync_width)

        def _on_mousewheel(event: tk.Event[tk.Misc]) -> None:
            if event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.root.bind_all("<MouseWheel>", _on_mousewheel)

        main.grid_columnconfigure(0, weight=1)

        hero = self._create_card(
            main,
            bg=PALETTE["hero"],
            border=PALETTE["hero"],
            padx=24,
            pady=20,
        )
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)

        tk.Label(
            hero,
            text="LOCAL CONTROL CENTER",
            bg=PALETTE["hero"],
            fg=PALETTE["hero_soft"],
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            hero,
            text="Referral Draft Assistant",
            bg=PALETTE["hero"],
            fg="#ffffff",
            font=("Georgia", 24, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Label(
            hero,
            text="A calmer front door for the app: one-click startup, quick control buttons, and a live activity console.",
            bg=PALETTE["hero"],
            fg=PALETTE["hero_soft"],
            font=("Segoe UI", 10),
            justify="left",
            wraplength=520,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        status_card = tk.Frame(
            hero,
            bg=PALETTE["panel"],
            padx=16,
            pady=14,
            highlightbackground=PALETTE["hero_soft"],
            highlightcolor=PALETTE["hero_soft"],
            highlightthickness=1,
            bd=0,
        )
        status_card.grid(row=0, column=1, rowspan=3, sticky="ne", padx=(20, 0))
        tk.Label(
            status_card,
            text="Dashboard Status",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 9),
            anchor="w",
        ).pack(anchor="w")
        self.status_chip = tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=PALETTE["idle_bg"],
            fg=PALETTE["idle_fg"],
            font=("Segoe UI Semibold", 10),
            padx=10,
            pady=6,
        )
        self.status_chip.pack(anchor="w", pady=(8, 8))
        tk.Label(
            status_card,
            textvariable=self.status_detail_var,
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=190,
            anchor="w",
        ).pack(anchor="w")

        settings = self._create_card(main)
        settings.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        settings.grid_columnconfigure(0, weight=1)

        tk.Label(
            settings,
            text="Connection",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            settings,
            text="Pick where the local dashboard should listen. The launcher will keep the URL in sync.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        fields = tk.Frame(settings, bg=PALETTE["panel"])
        fields.grid(row=2, column=0, sticky="ew")
        fields.grid_columnconfigure(0, weight=3)
        fields.grid_columnconfigure(1, weight=2)

        host_block = tk.Frame(fields, bg=PALETTE["panel"])
        host_block.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        tk.Label(
            host_block,
            text="Host",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        ttk.Entry(
            host_block,
            textvariable=self.host_var,
            style="Launcher.TEntry",
        ).pack(fill=tk.X, pady=(6, 0))

        port_block = tk.Frame(fields, bg=PALETTE["panel"])
        port_block.grid(row=0, column=1, sticky="ew")
        tk.Label(
            port_block,
            text="Port",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        ttk.Entry(
            port_block,
            textvariable=self.port_var,
            style="Launcher.TEntry",
        ).pack(fill=tk.X, pady=(6, 0))

        url_block = tk.Frame(fields, bg=PALETTE["panel"])
        url_block.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        tk.Label(
            url_block,
            text="Dashboard URL",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        ttk.Entry(
            url_block,
            textvariable=self.url_var,
            style="Launcher.TEntry",
            state="readonly",
        ).pack(fill=tk.X, pady=(6, 0))

        runtime_strip = tk.Frame(
            settings,
            bg=PALETTE["panel_alt"],
            padx=12,
            pady=10,
            highlightbackground=PALETTE["border"],
            highlightthickness=1,
            bd=0,
        )
        runtime_strip.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        tk.Label(
            runtime_strip,
            text="Runtime",
            bg=PALETTE["panel_alt"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        tk.Label(
            runtime_strip,
            textvariable=self.runtime_var,
            bg=PALETTE["panel_alt"],
            fg=PALETTE["text"],
            font=("Consolas", 9),
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(4, 0))

        actions = self._create_card(main)
        actions.grid(row=2, column=0, sticky="ew", pady=(16, 0))
        actions.grid_columnconfigure(0, weight=1)

        tk.Label(
            actions,
            text="Quick Actions",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            actions,
            text="Use the one-click path for normal startup, then dip into the smaller controls only when you need them.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        buttons = tk.Frame(actions, bg=PALETTE["panel"])
        buttons.grid(row=2, column=0, sticky="ew")
        for column in range(2):
            buttons.grid_columnconfigure(column, weight=1)

        ttk.Button(
            buttons,
            text="Launch Everything",
            command=self.launch_everything,
            style="Primary.Launcher.TButton",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(
            buttons,
            text="Initialize Database",
            command=self.initialize_database,
            style="Secondary.Launcher.TButton",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        ttk.Button(
            buttons,
            text="Run Scheduler Once",
            command=self.run_scheduler_once,
            style="Secondary.Launcher.TButton",
        ).grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(
            buttons,
            text="Start Dashboard",
            command=self.start_dashboard,
            style="Secondary.Launcher.TButton",
        ).grid(row=2, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        ttk.Button(
            buttons,
            text="Stop Dashboard",
            command=self.stop_dashboard,
            style="Danger.Launcher.TButton",
        ).grid(row=2, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(
            buttons,
            text="Open Dashboard",
            command=self.open_dashboard,
            style="Secondary.Launcher.TButton",
        ).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(
            buttons,
            text="Copy URL",
            command=self.copy_url,
            style="Secondary.Launcher.TButton",
        ).grid(row=3, column=1, sticky="ew")

        tk.Label(
            actions,
            text="Tip: Launch Everything handles the first-time startup path automatically.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))

        log_card = self._create_card(main)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(2, weight=1)

        tk.Label(
            log_card,
            text="Activity Console",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            log_card,
            text="Startup messages, subprocess output, and quick diagnostics show up here in real time.",
            bg=PALETTE["panel"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 12))

        log_shell = tk.Frame(
            log_card,
            bg=PALETTE["log_bg"],
            highlightbackground=PALETTE["log_border"],
            highlightcolor=PALETTE["log_border"],
            highlightthickness=1,
            bd=0,
        )
        log_shell.grid(row=2, column=0, sticky="nsew")
        log_shell.grid_rowconfigure(0, weight=1)
        log_shell.grid_columnconfigure(0, weight=1)

        self.log_widget = ScrolledText(
            log_shell,
            wrap=tk.WORD,
            height=14,
            bg=PALETTE["log_bg"],
            fg=PALETTE["log_fg"],
            insertbackground=PALETTE["log_fg"],
            selectbackground=PALETTE["primary"],
            selectforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=14,
            font=("Consolas", 10),
        )
        self.log_widget.grid(row=0, column=0, sticky="nsew")
        self.log_widget.configure(state=tk.DISABLED)
        self._append_log(
            "Launcher ready. Click Launch Everything to initialize the database, start the dashboard, and open it in your browser."
        )

    def _create_card(
        self,
        parent: tk.Widget,
        *,
        bg: str | None = None,
        border: str | None = None,
        padx: int = 18,
        pady: int = 18,
    ) -> tk.Frame:
        fill = bg or PALETTE["panel"]
        outline = border or PALETTE["border"]
        return tk.Frame(
            parent,
            bg=fill,
            padx=padx,
            pady=pady,
            highlightbackground=outline,
            highlightcolor=outline,
            highlightthickness=1,
            bd=0,
        )

    def initialize_database(self) -> None:
        runtime_command = self._ensure_runtime_command()
        if runtime_command is None:
            return
        self._run_command_async(
            "Initialize Database",
            build_cli_command("init-db", runtime_command),
        )

    def run_scheduler_once(self) -> None:
        runtime_command = self._ensure_runtime_command()
        if runtime_command is None:
            return
        self._run_command_async(
            "Run Scheduler Once",
            build_cli_command("run-once", runtime_command),
        )

    def launch_everything(self) -> None:
        runtime_command = self._ensure_runtime_command()
        if runtime_command is None:
            return
        self._set_status(
            "Preparing",
            "warning",
            "Initializing the database and bringing the dashboard online.",
        )
        thread = threading.Thread(
            target=self._launch_everything,
            args=(list(runtime_command),),
            daemon=True,
        )
        thread.start()

    def start_dashboard(self, runtime_command: list[str] | None = None) -> None:
        resolved_runtime = runtime_command or self._ensure_runtime_command()
        if resolved_runtime is None:
            return

        host = self.host_var.get().strip() or "127.0.0.1"
        try:
            port = int(self.port_var.get().strip() or "8501")
        except ValueError:
            self._set_status("Port Error", "error", "Use a numeric port value like 8501.")
            messagebox.showerror("Invalid Port", "Port must be a whole number.")
            return

        self.url_var.set(f"http://{host}:{port}")
        existing = self.state.dashboard_process
        if existing is not None and existing.poll() is None:
            self._set_status("Running", "running", f"Dashboard live at {self.url_var.get()}")
            self._append_log("Dashboard is already running.")
            return

        command = build_dashboard_command(host, port, resolved_runtime)
        self._append_log(f"Starting dashboard: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            env=build_pythonpath_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **subprocess_windowless_kwargs(),
        )
        self.state.dashboard_process = process
        self._set_status("Running", "running", f"Dashboard live at {self.url_var.get()}")
        thread = threading.Thread(
            target=self._stream_process_output,
            args=(process, "dashboard"),
            daemon=True,
        )
        thread.start()

    def stop_dashboard(self) -> None:
        process = self.state.dashboard_process
        if process is None or process.poll() is not None:
            self._set_status("Offline", "idle", "Dashboard is not currently running.")
            self._append_log("Dashboard is not currently running.")
            return

        self._append_log("Stopping dashboard process.")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._append_log("Dashboard did not exit in time; killing process.")
            process.kill()
        self.state.dashboard_process = None
        self._set_status("Offline", "idle", "Dashboard stopped cleanly.")

    def open_dashboard(self) -> None:
        self.url_var.set(self.current_dashboard_url)
        webbrowser.open(self.url_var.get())
        self._append_log(f"Opened dashboard in browser: {self.url_var.get()}")

    def copy_url(self) -> None:
        self.url_var.set(self.current_dashboard_url)
        self.root.clipboard_clear()
        self.root.clipboard_append(self.url_var.get())
        self._append_log(f"Copied dashboard URL: {self.url_var.get()}")

    def on_close(self) -> None:
        self.stop_dashboard()
        self.root.destroy()

    def _detect_runtime(self) -> None:
        self._ensure_runtime_command(log_result=False)

    def _ensure_runtime_command(
        self,
        *,
        log_result: bool = True,
    ) -> list[str] | None:
        if self.state.runtime_command is not None:
            self.runtime_var.set(" ".join(self.state.runtime_command))
            return list(self.state.runtime_command)

        runtime_command = resolve_runtime_command()
        if runtime_command is None:
            self.runtime_var.set("No compatible Python runtime found.")
            self._set_status(
                "Setup Required",
                "error",
                "Install the app dependencies into a Python environment, then reopen the launcher.",
            )
            if log_result:
                self._append_log(
                    "No compatible Python runtime was found with the required modules: requests, flask."
                )
                self._append_log(
                    "Suggested fix: py -3.10 -m pip install -e ."
                )
            return None

        self.state.runtime_command = list(runtime_command)
        optional_missing = missing_modules(runtime_command, OPTIONAL_RUNTIME_MODULES)
        if optional_missing:
            self.runtime_var.set(
                f"{' '.join(runtime_command)}  |  optional modules missing: {', '.join(optional_missing)}"
            )
        else:
            self.runtime_var.set(" ".join(runtime_command))
        if log_result:
            self._append_log(f"Using runtime: {' '.join(runtime_command)}")
            if optional_missing:
                self._append_log(
                    "This runtime can launch the dashboard, but scheduler features may need extra packages: "
                    + ", ".join(optional_missing)
                )
        return list(runtime_command)

    def _run_command_async(self, label: str, command: list[str]) -> None:
        thread = threading.Thread(
            target=self._run_command,
            args=(label, command),
            daemon=True,
        )
        thread.start()

    def _run_command(self, label: str, command: list[str]) -> None:
        result = self._run_command_capture(label, command)
        if label == "Initialize Database" and result.returncode == 0:
            self._append_log("Database initialization completed successfully.")

    def _launch_everything(self, runtime_command: list[str]) -> None:
        self.log_queue.put("Launch Everything started.")
        init_result = self._run_command_capture(
            "Initialize Database",
            build_cli_command("init-db", runtime_command),
        )
        if init_result.returncode != 0:
            self.log_queue.put(
                "Launch Everything stopped because database initialization failed."
            )
            self.ui_queue.put(
                (
                    "set_status",
                    (
                        "Attention",
                        "error",
                        "Database initialization failed. Check the activity console for details.",
                    ),
                )
            )
            return

        self.log_queue.put("Database ready. Starting dashboard.")
        self.ui_queue.put(("launch_everything_continue", runtime_command))

    def _run_command_capture(
        self,
        label: str,
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        self.log_queue.put(f"{label}: {' '.join(command)}")
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            env=build_pythonpath_env(),
            capture_output=True,
            text=True,
            **subprocess_windowless_kwargs(),
        )
        if result.stdout.strip():
            self.log_queue.put(result.stdout.strip())
        if result.stderr.strip():
            self.log_queue.put(result.stderr.strip())
        self.log_queue.put(f"{label} exited with code {result.returncode}.")
        return result

    def _stream_process_output(
        self,
        process: subprocess.Popen[str],
        label: str,
    ) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            cleaned = line.rstrip()
            if cleaned:
                self.log_queue.put(f"[{label}] {cleaned}")
        return_code = process.wait()
        self.log_queue.put(f"[{label}] process exited with code {return_code}.")

    def _pump_log_queue(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)

        while True:
            try:
                action, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if action == "launch_everything_continue":
                self.start_dashboard(runtime_command=payload if isinstance(payload, list) else None)
                self.root.after(1100, self.open_dashboard)
            elif action == "set_status" and isinstance(payload, tuple):
                text, kind, detail = payload
                self._set_status(str(text), str(kind), str(detail))

        self.root.after(150, self._pump_log_queue)

    def _refresh_dashboard_state(self) -> None:
        process = self.state.dashboard_process
        self.url_var.set(self.current_dashboard_url)
        if process is None or process.poll() is not None:
            if process is not None and process.poll() is not None:
                self.state.dashboard_process = None
            if self.status_var.get() == "Running":
                self._set_status("Offline", "idle", "Dashboard process ended.")
        self.root.after(400, self._refresh_dashboard_state)

    def _set_status(self, text: str, kind: str, detail: str) -> None:
        self.status_var.set(text)
        self.status_detail_var.set(detail)

        color_map = {
            "running": (PALETTE["success_bg"], PALETTE["success_fg"]),
            "warning": (PALETTE["warning_bg"], PALETTE["warning_fg"]),
            "error": (PALETTE["error_bg"], PALETTE["error_fg"]),
            "idle": (PALETTE["idle_bg"], PALETTE["idle_fg"]),
        }
        bg_color, fg_color = color_map.get(kind, color_map["idle"])
        self.status_chip.configure(bg=bg_color, fg=fg_color)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)


def main() -> None:
    root = tk.Tk()
    launcher = LauncherApp(root)
    launcher.url_var.set(launcher.current_dashboard_url)
    root.mainloop()


if __name__ == "__main__":
    main()
