"""The console window: control buttons, skin, log and the ACTION status bar."""
import queue
import time
import tkinter as tk
from tkinter import filedialog

import actions
import picker
import screen
import settings
import skin
import theme
from automation import Automation

IDLE, RUNNING, PAUSED = "IDLE", "RUNNING", "PAUSED"


class GameButton(tk.Label):
    """A flat neon button. tk.Button ignores custom colours on Windows, so a Label is used instead."""

    def __init__(self, parent, text, command, color):
        super().__init__(parent, text=text, font=theme.FONT_BTN, fg=color, bg=theme.BG,
                         highlightthickness=2, highlightbackground=color, cursor="hand2")
        self.command, self.color, self.enabled = command, color, True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.color, fg=theme.BG))
        self.bind("<Leave>", lambda e: self._paint())
        self.bind("<Button-1>", lambda e: self.enabled and self.command())

    def _paint(self):
        if self.enabled:
            self.config(bg=theme.BG, fg=self.color, highlightbackground=self.color, cursor="hand2")
        else:
            self.config(bg=theme.BG, fg=theme.MUTED, highlightbackground=theme.MUTED, cursor="arrow")

    def set_enabled(self, value):
        self.enabled = value
        self._paint()

    def set_text(self, text):
        self.config(text=text)


class Console:
    BAR_H = 44  # height of the ACTION status bar at the bottom edge

    def __init__(self):
        self.root = tk.Tk()
        self.state = IDLE
        self.stopping = False
        self.automation = None
        self.settings = settings.load()
        self.ui_queue = queue.Queue()  # messages from the worker thread to the GUI thread

        # The console takes the left quarter of the work area (the screen minus the taskbar).
        left, top, right, bottom = screen.get_work_area()
        self.w = (right - left) // 4
        self.h = bottom - top
        self.top_h = self.h // 2
        self.log_h = self.h - self.top_h - self.BAR_H
        # Everything to the right of the console is reserved for the launcher and the game: (x, y, w, h).
        self.game_area = (left + self.w, top, (right - left) - self.w, self.h)

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{self.w}x{self.h}+{left}+{top}")
        self.root.configure(bg=theme.BG)

        self._build_top()
        self._build_log()
        self._build_action_bar()
        self._refresh_buttons()
        self.root.after(50, self._drain_queue)
        self.log("Console ready. Press START.", "OK")
        self.picker = picker.Picker(self.root, self.log, lambda: self.state != IDLE)
        self.picker.start()

    # ---------- layout ----------
    def _build_top(self):
        self.canvas = tk.Canvas(self.root, width=self.w, height=self.top_h,
                                highlightthickness=0, bd=0, bg=theme.BG)
        self.canvas.place(x=0, y=0)
        self._apply_skin()

        self.canvas.create_text(self.w // 2, 32, text="RONW  AUTOBOSS", fill=theme.CYAN, font=theme.FONT_TITLE)
        self.status_id = self.canvas.create_text(self.w // 2, 64, text="", fill=theme.TEXT, font=theme.FONT_STATUS)

        bw, bh, x = self.w - 60, 44, 30
        self.btn_start = GameButton(self.canvas, "START", self.on_start_stop, theme.GREEN)
        self.btn_pause = GameButton(self.canvas, "PAUSE", self.on_pause, theme.YELLOW)
        self.btn_quit = GameButton(self.canvas, "QUIT", self.on_quit, theme.RED)
        self.btn_skin = GameButton(self.canvas, "CHANGE SKIN", self.on_change_skin, theme.MAGENTA)
        for i, btn in enumerate((self.btn_start, self.btn_pause, self.btn_quit)):
            self.canvas.create_window(x, 100 + i * 56, window=btn, anchor="nw", width=bw, height=bh)
        self.canvas.create_window(x, self.top_h - 56, window=self.btn_skin, anchor="nw", width=bw, height=36)

    def _build_log(self):
        frame = tk.Frame(self.root, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.CYAN)
        frame.place(x=0, y=self.top_h, width=self.w, height=self.log_h)
        scroll = tk.Scrollbar(frame)
        scroll.pack(side="right", fill="y")
        self.log_text = tk.Text(frame, bg=theme.PANEL, fg=theme.TEXT, font=theme.FONT_LOG, wrap="word",
                                bd=0, highlightthickness=0, state="disabled", yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        scroll.config(command=self.log_text.yview)
        for level, color in (("INFO", theme.TEXT), ("OK", theme.GREEN), ("WARN", theme.YELLOW),
                             ("ERROR", theme.RED)):
            self.log_text.tag_config(level, foreground=color)
        self.log_text.tag_config("TIME", foreground=theme.MUTED)

    def _build_action_bar(self):
        """The permanent ACTION bar along the bottom edge of the console."""
        bar = tk.Frame(self.root, bg=theme.BG, highlightthickness=2, highlightbackground=theme.MAGENTA)
        bar.place(x=0, y=self.h - self.BAR_H, width=self.w, height=self.BAR_H)
        tk.Label(bar, text="ACTION", font=theme.FONT_STATUS, fg=theme.MUTED, bg=theme.BG).pack(
            side="left", padx=(10, 8))
        self.action_label = tk.Label(bar, text=actions.IDLE, font=theme.FONT_BTN, fg=theme.CYAN,
                                     bg=theme.BG, anchor="w")
        self.action_label.pack(side="left", fill="x", expand=True)

    def _apply_skin(self):
        # Tk discards an image that has no Python reference, so it is stored on self.
        self.skin_image = skin.load_skin(self.settings["skin"], (self.w, self.top_h))
        if hasattr(self, "skin_item"):
            self.canvas.itemconfig(self.skin_item, image=self.skin_image)
        else:
            self.skin_item = self.canvas.create_image(0, 0, image=self.skin_image, anchor="nw")
            self.canvas.tag_lower(self.skin_item)

    # ---------- messages from any thread ----------
    def log(self, message, level="INFO"):
        """Adds a line to the log. Safe to call from any thread."""
        self.ui_queue.put(("log", time.strftime("%H:%M:%S"), level, message))

    def set_action(self, text):
        """Changes the text of the ACTION bar. Safe to call from any thread."""
        self.ui_queue.put(("action", text))

    def _drain_queue(self):
        """Applies queued updates on the GUI thread. Tk widgets must only be touched from that thread."""
        try:
            while True:
                try:
                    item = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                self._handle(item)
        finally:
            self.root.after(50, self._drain_queue)

    def _handle(self, item):
        kind = item[0]
        if kind == "log":
            _, stamp, level, message = item
            self.log_text.config(state="normal")
            self.log_text.insert("end", f"[{stamp}] ", "TIME")
            self.log_text.insert("end", f"{message}\n", level)
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 1000:  # keep the log bounded during long runs
                self.log_text.delete("1.0", f"{lines - 1000}.0")
            self.log_text.config(state="disabled")
            self.log_text.see("end")
        elif kind == "action":
            self.action_label.config(text=item[1])
        elif kind == "done":  # the worker finished, failed or was stopped
            self.state = IDLE
            self.stopping = False
            self.automation = None
            self._refresh_buttons()

    # ---------- buttons ----------
    def _refresh_buttons(self):
        running = self.state != IDLE
        if self.stopping:
            self.btn_start.set_text("STOPPING...")
        else:
            self.btn_start.set_text("STOP" if running else "START")
        self.btn_start.set_enabled(not self.stopping)
        self.btn_pause.set_text("UNPAUSE" if self.state == PAUSED else "PAUSE")
        self.btn_pause.set_enabled(running and not self.stopping)
        text, color = {IDLE: ("IDLE", theme.MUTED), RUNNING: ("RUNNING", theme.GREEN),
                       PAUSED: ("PAUSED", theme.YELLOW)}[self.state]
        self.canvas.itemconfig(self.status_id, text=f"STATUS: {text}", fill=color)

    def _ensure_launcher_path(self):
        """Returns the saved launcher executable and asks for it on first use. None if the user cancels."""
        path = self.settings.get("launcher_path", "")
        if path:
            return path
        self.log("Select the RONW launcher .exe (first time only)...", "INFO")
        path = filedialog.askopenfilename(
            title="Select the Ragnarok The New World launcher",
            filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
        if not path:
            self.log("No launcher selected. Not started.", "WARN")
            return None
        self.settings["launcher_path"] = path
        settings.save(self.settings)
        return path

    def on_start_stop(self):
        if self.stopping:
            return
        if self.state == IDLE:
            path = self._ensure_launcher_path()
            if not path:
                return
            self.automation = Automation(
                log=self.log, set_action=self.set_action,
                on_done=lambda: self.ui_queue.put(("done",)),
                launcher_path=path, area=self.game_area)
            self.state = RUNNING
            self.log("Automation STARTED.", "OK")
            self.automation.start()
        else:
            self.stopping = True
            self.log("Stopping...", "WARN")
            self.automation.stop()
        self._refresh_buttons()

    def on_pause(self):
        if self.stopping or self.automation is None:
            return
        if self.state == RUNNING:
            self.state = PAUSED
            self.automation.pause()
            self.log("Paused. It stops at the next step.", "WARN")
        elif self.state == PAUSED:
            self.state = RUNNING
            self.automation.resume()
            self.log("Resumed.", "OK")
        self._refresh_buttons()

    def on_quit(self):
        if self.automation:
            self.automation.stop()
        self.root.destroy()

    def on_change_skin(self):
        path = filedialog.askopenfilename(title="Choose a skin image",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        self.settings["skin"] = path
        settings.save(self.settings)
        self._apply_skin()
        self.log(f"Skin changed: {path}", "INFO")

    def run(self):
        self.root.mainloop()