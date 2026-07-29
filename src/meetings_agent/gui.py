"""Desktop GUI so a meeting can be run by clicking buttons instead of typing
terminal commands.

Thin wrapper around the same record/transcribe/correct/summarize/sync
functions the CLI uses. Long-running stages run on a background thread so
the window stays responsive; recording is stopped via the same `.stop`
sentinel file record() already supports for non-interactive stopping.

The look is a deliberate single (light) theme: a neutral canvas, white
cards, a teal accent, and a dark log console.
"""

import os
import queue
import sys
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

from .config import KNOWLEDGE_FILE, MEETING_TYPE, RAW_DIR, TRANSCRIBE_BACKEND
from .profiles import PROFILES

# --- palette -------------------------------------------------------------
APP_BG = "#e9ecee"
CARD = "#ffffff"
INK = "#1b2124"
MUTED = "#6b7378"
BORDER = "#d8dcde"
ACCENT = "#2f8f83"
ACCENT_HOVER = "#26746a"
DANGER = "#c24a30"
DANGER_HOVER = "#a33c26"
NEUTRAL = "#eef1f2"
NEUTRAL_HOVER = "#e0e4e6"
AMBER = "#c98a1e"
LOG_BG = "#12181b"
LOG_FG = "#cdd6d3"

FONT = "Segoe UI"
FONT_MONO = "Cascadia Mono"


def _raw_dir(meeting_type: str) -> str:
    return str(RAW_DIR / meeting_type / date.today().isoformat())


class _QueueWriter:
    """Redirects print() output into a thread-safe queue the UI polls."""

    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def write(self, text: str) -> None:
        if text:
            self.q.put(text)

    def flush(self) -> None:
        pass


def _flat_button(parent, text, command, *, fg, bg, hover, width=None, bold=False, big=False):
    """A flat, hover-lit button — full color control across platforms."""
    btn = tk.Button(
        parent, text=text, command=command,
        relief="flat", bd=0, cursor="hand2",
        fg=fg, bg=bg, activebackground=hover, activeforeground=fg,
        disabledforeground="#a7adb0",
        font=(FONT, 11 if big else 10, "bold" if bold else "normal"),
        padx=16, pady=10 if big else 7,
    )
    if width:
        btn.configure(width=width)
    btn._base_bg = bg
    btn._hover_bg = hover

    def on_enter(_):
        if str(btn["state"]) != "disabled":
            btn.configure(bg=btn._hover_bg)

    def on_leave(_):
        btn.configure(bg=btn._base_bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Meetings Agent")
        root.geometry("900x680")
        root.minsize(760, 560)
        root.configure(bg=APP_BG)

        self.log_queue: queue.Queue = queue.Queue()
        self.busy = False
        self.recording = False
        self.paused = False
        self.last_summary: Path | None = None

        self._type_choices = ["auto", *PROFILES.keys()]
        default_type = MEETING_TYPE if MEETING_TYPE in self._type_choices else "auto"

        self._init_styles()
        self._build_header()
        self._build_config_card(default_type)
        self._build_actions_card()
        self._build_log()

        self._auto_dir = _raw_dir(default_type)
        self.type_var.trace_add("write", self._on_type_change)
        self._refresh_status()
        self._poll_log()

    # ---- styling ----
    def _init_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Modern.TCombobox",
            fieldbackground=CARD, background=CARD, foreground=INK,
            bordercolor=BORDER, arrowcolor=INK, relief="flat", padding=5,
        )
        style.map("Modern.TCombobox", fieldbackground=[("readonly", CARD)])

    def _card(self, title: str) -> tk.Frame:
        wrap = tk.Frame(self.root, bg=APP_BG)
        wrap.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(wrap, text=title.upper(), bg=APP_BG, fg=MUTED,
                 font=(FONT, 8, "bold")).pack(anchor="w", pady=(0, 4))
        card = tk.Frame(wrap, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)
        return inner

    # ---- header ----
    def _build_header(self) -> None:
        head = tk.Frame(self.root, bg=APP_BG)
        head.pack(fill="x", padx=18, pady=(16, 12))
        tk.Label(head, text="Meetings Agent", bg=APP_BG, fg=INK,
                 font=(FONT, 17, "bold")).pack(side="left")
        self.status = tk.Label(head, text="●  Sẵn sàng", bg=APP_BG, fg=ACCENT,
                               font=(FONT, 10, "bold"))
        self.status.pack(side="right")

    # ---- config card ----
    def _build_config_card(self, default_type: str) -> None:
        c = self._card("Cấu hình")

        row1 = tk.Frame(c, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="Transcribe", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left")
        tk.Label(row1, text=f" {TRANSCRIBE_BACKEND} ", bg=NEUTRAL, fg=INK,
                 font=(FONT, 9, "bold"), padx=4, pady=1).pack(side="left", padx=(4, 18))

        tk.Label(row1, text="Loại họp", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(0, 4))
        self.type_var = tk.StringVar(value=default_type)
        combo = ttk.Combobox(row1, textvariable=self.type_var, values=self._type_choices,
                             state="readonly", width=10, style="Modern.TCombobox")
        combo.pack(side="left", padx=(0, 18))

        tk.Label(row1, text="Sprint #", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(0, 4))
        self.sprint_var = tk.StringVar(value="")
        tk.Entry(row1, textvariable=self.sprint_var, width=7, relief="flat",
                 bg=NEUTRAL, fg=INK, font=(FONT, 10),
                 highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left")

        row2 = tk.Frame(c, bg=CARD)
        row2.pack(fill="x", pady=(12, 0))
        tk.Label(row2, text="Thư mục", bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(0, 6))
        self.dir_var = tk.StringVar(value=_raw_dir(default_type))
        tk.Entry(row2, textvariable=self.dir_var, relief="flat", bg=NEUTRAL, fg=INK,
                 font=(FONT_MONO, 9), highlightthickness=1, highlightbackground=BORDER,
                 highlightcolor=ACCENT).pack(side="left", fill="x", expand=True, ipady=3)
        _flat_button(row2, "Chọn…", self._browse, fg=INK, bg=NEUTRAL,
                     hover=NEUTRAL_HOVER).pack(side="left", padx=(8, 0))

    # ---- actions card ----
    def _build_actions_card(self) -> None:
        c = self._card("Thao tác")

        rec_row = tk.Frame(c, bg=CARD)
        rec_row.pack(fill="x")
        self.record_btn = _flat_button(rec_row, "●  Bắt đầu ghi âm", self._start_record,
                                       fg="white", bg=ACCENT, hover=ACCENT_HOVER, bold=True)
        self.record_btn.pack(side="left")
        self.pause_btn = _flat_button(rec_row, "⏸  Tạm dừng", self._toggle_pause,
                                      fg=INK, bg=NEUTRAL, hover=NEUTRAL_HOVER, bold=True)
        self.pause_btn.configure(state="disabled")
        self.pause_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = _flat_button(rec_row, "■  Dừng ghi âm", self._stop_record,
                                     fg="white", bg=DANGER, hover=DANGER_HOVER, bold=True)
        self.stop_btn.configure(state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        self.run_all_btn = _flat_button(
            c, "▶  Chạy tự động   ·   Transcribe → Correct → Summarize",
            self._run_pipeline, fg="white", bg=ACCENT, hover=ACCENT_HOVER, bold=True, big=True)
        self.run_all_btn.pack(fill="x", pady=(12, 10))

        steps = tk.Frame(c, bg=CARD)
        steps.pack(fill="x")
        tk.Label(steps, text="Hoặc từng bước:", bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(0, 8))
        self.stage_buttons: list[tk.Button] = []
        for label, fn in [
            ("Transcribe", self._run_transcribe),
            ("Correct", self._run_correct),
            ("Summarize", self._run_summarize),
            ("Sync Knowledge", self._run_sync),
        ]:
            b = _flat_button(steps, label, fn, fg=INK, bg=NEUTRAL, hover=NEUTRAL_HOVER)
            b.pack(side="left", padx=(0, 6))
            self.stage_buttons.append(b)

        self.open_btn = _flat_button(steps, "📄 Mở summary", self._open_last_summary,
                                     fg=ACCENT, bg=NEUTRAL, hover=NEUTRAL_HOVER)
        self.open_btn.configure(state="disabled")
        self.open_btn.pack(side="left", padx=(0, 6))

    # ---- log ----
    def _build_log(self) -> None:
        wrap = tk.Frame(self.root, bg=APP_BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        tk.Label(wrap, text="NHẬT KÝ", bg=APP_BG, fg=MUTED,
                 font=(FONT, 8, "bold")).pack(anchor="w", pady=(0, 4))
        frame = tk.Frame(wrap, bg=LOG_BG, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(frame, state="disabled", wrap="word", relief="flat",
                           bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG,
                           font=(FONT_MONO, 9), padx=12, pady=10, bd=0)
        scroll = tk.Scrollbar(frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

    # ---- status ----
    def _refresh_status(self) -> None:
        if self.recording and self.paused:
            self.status.configure(text="⏸  Tạm dừng", fg=AMBER)
        elif self.recording:
            self.status.configure(text="●  Đang ghi âm", fg=DANGER)
        elif self.busy:
            self.status.configure(text="●  Đang xử lý", fg=AMBER)
        else:
            self.status.configure(text="●  Sẵn sàng", fg=ACCENT)

    # ---- behavior (unchanged logic) ----
    def _on_type_change(self, *_) -> None:
        # Only auto-update the folder if the user hasn't picked a custom one.
        if self.dir_var.get() == self._auto_dir:
            self._auto_dir = _raw_dir(self.type_var.get())
            self.dir_var.set(self._auto_dir)

    def _browse(self) -> None:
        d = filedialog.askdirectory(initialdir=str(RAW_DIR))
        if d:
            self.dir_var.set(d)

    def _meeting_dir(self) -> Path:
        return Path(self.dir_var.get())

    def _poll_log(self) -> None:
        try:
            while True:
                text = self.log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", text)
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in self.stage_buttons:
            b.configure(state=state)
        self.run_all_btn.configure(state=state)
        self.record_btn.configure(state=state)
        self._refresh_status()

    def _run_in_thread(self, fn, *args, on_success=None) -> None:
        if self.busy or self.recording:
            return
        self._set_busy(True)
        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self.log_queue)

        def target():
            result, ok = None, False
            try:
                result = fn(*args)
                ok = True
            except Exception as e:
                self.log_queue.put(f"\nLỖI: {e}\n")
            finally:
                sys.stdout = old_stdout
                self.root.after(0, lambda: self._set_busy(False))
                if ok and on_success is not None:
                    self.root.after(0, lambda: on_success(result))

        threading.Thread(target=target, daemon=True).start()

    def _open_file(self, path) -> None:
        """Open a file with the OS default handler (called on the main thread)."""
        if not path:
            return
        path = Path(path)
        if not path.exists():
            self.log_queue.put(f"\nKhông tìm thấy file để mở: {path}\n")
            return
        try:
            os.startfile(str(path))  # Windows
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", str(path)])

    def _on_summary_done(self, published) -> None:
        self.last_summary = Path(published) if published else None
        if self.last_summary:
            self.open_btn.configure(state="normal")
            self._open_file(self.last_summary)

    def _open_last_summary(self) -> None:
        if self.last_summary:
            self._open_file(self.last_summary)

    def _start_record(self) -> None:
        if self.busy or self.recording:
            return
        from .audio import record

        meeting_dir = self._meeting_dir()
        self.recording = True
        self.paused = False
        self._set_busy(True)
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal", text="⏸  Tạm dừng")

        old_stdout = sys.stdout
        sys.stdout = _QueueWriter(self.log_queue)

        def target():
            try:
                record(meeting_dir)
            except Exception as e:
                self.log_queue.put(f"\nLỖI: {e}\n")
            finally:
                sys.stdout = old_stdout
                self.recording = False
                self.paused = False
                self.root.after(0, self._on_record_end)

        threading.Thread(target=target, daemon=True).start()

    def _on_record_end(self) -> None:
        self._set_busy(False)
        self.stop_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled", text="⏸  Tạm dừng")

    def _toggle_pause(self) -> None:
        if not self.recording:
            return
        self.paused = not self.paused
        pf = self._meeting_dir() / ".pause"
        if self.paused:
            pf.touch()
            self.pause_btn.configure(text="▶  Tiếp tục")
        else:
            pf.unlink(missing_ok=True)
            self.pause_btn.configure(text="⏸  Tạm dừng")
        self._refresh_status()

    def _stop_record(self) -> None:
        (self._meeting_dir() / ".stop").touch()

    def _run_transcribe(self) -> None:
        from .cli import _transcribe
        self._run_in_thread(_transcribe, self._meeting_dir())

    def _run_correct(self) -> None:
        from .correct import correct
        self._run_in_thread(correct, self._meeting_dir())

    def _run_summarize(self) -> None:
        from .summarize import summarize
        self._run_in_thread(summarize, self._meeting_dir(), self.type_var.get(),
                            self.sprint_var.get().strip() or None,
                            on_success=self._on_summary_done)

    def _run_sync(self) -> None:
        from .knowledge import sync
        if not KNOWLEDGE_FILE:
            self.log_queue.put("\nChưa cấu hình KNOWLEDGE_FILE trong .env\n")
            return
        self._run_in_thread(sync, self._meeting_dir(), Path(KNOWLEDGE_FILE))

    def _run_pipeline(self) -> None:
        meeting_type = self.type_var.get()
        sprint_number = self.sprint_var.get().strip() or None

        def pipeline(meeting_dir: Path):
            from .cli import _transcribe
            from .correct import correct
            from .summarize import summarize

            _transcribe(meeting_dir)
            try:
                correct(meeting_dir)
            except Exception as e:
                print(f"\nWARNING: correct thất bại ({e}) — summarize sẽ dùng transcript thô.")
            published = summarize(meeting_dir, meeting_type, sprint_number)
            print("\nXong. Mở file summary — bấm 'Sync Knowledge' nếu cần.")
            return published

        self._run_in_thread(pipeline, self._meeting_dir(), on_success=self._on_summary_done)


def launch_gui() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
