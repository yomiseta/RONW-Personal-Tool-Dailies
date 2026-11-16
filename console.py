import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog

import screen
import settings
import skin
import theme
import winutil
import launcher

IDLE, RUNNING, PAUSED = "IDLE", "RUNNING", "PAUSED"


class GameButton(tk.Label):
    """A flat neon button (tk.Button ignores colours on Windows, so we use a Label)."""

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
    def __init__(self):
        self.root = tk.Tk()
        self.state = IDLE
        self.settings = settings.load()
        self.log_queue = queue.Queue()

        # Left quarter of the work area (the screen minus the taskbar).
        left, top, right, bottom = screen.get_work_area()
        self.w = (right - left) // 4
        self.h = bottom - top
        self.top_h = self.h // 2
        self.log_h = self.h - self.top_h
        # The space to the right of the console (x, y, width, height) for the game windows.
        self.game_area = (left + self.w, top, (right - left) - self.w, self.h)

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{self.w}x{self.h}+{left}+{top}")
        self.root.configure(bg=theme.BG)

        self._build_top()
        self._build_log()
        self._refresh_buttons()
        self.root.after(50, self._drain_log)
        self.log("Console ready. Press START.", "OK")

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

    def _apply_skin(self):
        self.skin_image = skin.load_skin(self.settings["skin"], (self.w, self.top_h))  # keep a reference!
        if hasattr(self, "skin_item"):
            self.canvas.itemconfig(self.skin_item, image=self.skin_image)
        else:
            self.skin_item = self.canvas.create_image(0, 0, image=self.skin_image, anchor="nw")
            self.canvas.tag_lower(self.skin_item)

    # ---------- logging (safe to call from any thread) ----------
    def log(self, message, level="INFO"):
        self.log_queue.put((time.strftime("%H:%M:%S"), level, message))

    def _drain_log(self):
        try:
            while True:
                stamp, level, message = self.log_queue.get_nowait()
                self.log_text.config(state="normal")
                self.log_text.insert("end", f"[{stamp}] ", "TIME")
                self.log_text.insert("end", f"{message}\n", level)
                lines = int(self.log_text.index("end-1c").split(".")[0])
                if lines > 1000:
                    self.log_text.delete("1.0", f"{lines - 1000}.0")
                self.log_text.config(state="disabled")
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.root.after(50, self._drain_log)

    # ---------- buttons ----------
    def _refresh_buttons(self):
        running = self.state != IDLE
        self.btn_start.set_text("STOP" if running else "START")
        self.btn_pause.set_text("UNPAUSE" if self.state == PAUSED else "PAUSE")
        self.btn_pause.set_enabled(running)
        text, color = {IDLE: ("IDLE", theme.MUTED), RUNNING: ("RUNNING", theme.GREEN),
                       PAUSED: ("PAUSED", theme.YELLOW)}[self.state]
        self.canvas.itemconfig(self.status_id, text=f"STATUS: {text}", fill=color)

    def on_start_stop(self):
        if self.state == IDLE:
            count = winutil.minimize_all(skip_pid=os.getpid())
            self.log(f"Minimized {count} window(s).", "INFO")
            if not self.open_launcher():
                return  # could not open it, stay IDLE
            self.state = RUNNING
            self.log("Automation STARTED.", "OK")
            threading.Thread(target=self._arrange_launcher, daemon=True).start()
        else:
            self.state = IDLE
            self.log("Automation STOPPED.", "WARN")
            # Later: tell the bot to stop here.
        self._refresh_buttons()

    def open_launcher(self):
        """Opens the RONW launcher. Returns True if it is running or was started."""
        if launcher.is_running():
            self.log("RONW is already running. Not opening a second one.", "INFO")
            return True

        path = self.settings.get("launcher_path", "")
        if not path:
            self.log("Select the RONW launcher .exe (first time only)...", "INFO")
            path = filedialog.askopenfilename(
                title="Select the Ragnarok The New World launcher",
                filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
            if not path:
                self.log("No launcher selected. Not started.", "WARN")
                return False
            self.settings["launcher_path"] = path
            settings.save(self.settings)

        try:
            launcher.start(path)
        except OSError as err:
            self.log(f"Could not open the launcher: {err}", "ERROR")
            self.settings["launcher_path"] = ""  # ask again next time
            settings.save(self.settings)
            return False

        self.log("Launcher opened. Waiting for it to appear...", "OK")
        return True
    
    def _arrange_launcher(self):
        """Runs in a background thread: waits for the launcher window, then fits it to the right area."""
        x, y, w, h = self.game_area
        self.log("Waiting for the launcher window...", "INFO")
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.state == IDLE:  # user pressed STOP
                return
            hwnd = winutil.find_window(launcher.PROCESS_NAME, "Chrome_WidgetWin_0", "ragnarok")
            if hwnd:
                time.sleep(1.0)  # let the window finish drawing
                fx, fy, fw, fh = winutil.fit_window(hwnd, x, y, w, h)
                self.log(f"Launcher placed at x={fx} y={fy} size={fw}x{fh}.", "OK")
                return
            time.sleep(0.5)
        self.log("The launcher window did not appear within 60 seconds.", "ERROR")    

    def on_pause(self):
        if self.state == RUNNING:
            self.state = PAUSED
            self.log("Paused.", "WARN")
        elif self.state == PAUSED:
            self.state = RUNNING
            self.log("Resumed.", "OK")
        self._refresh_buttons()

    def on_quit(self):
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