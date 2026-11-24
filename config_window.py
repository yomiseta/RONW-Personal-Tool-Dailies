"""The Config window: shows the settings of config.ini and saves changes to it."""
import tkinter as tk
from tkinter import messagebox

import config
import theme
from widgets import GameButton

WIDTH = 560
ROW_H = 190                # height reserved for one setting
FONT_SMALL = ("Consolas", -13, "bold")
FONT_NOTE = ("Consolas", -12)


class ConfigWindow:
    def __init__(self, root, log, position):
        self.root = root
        self.log = log                    # callable: log(message, level)
        self.position = position          # (x, y) where the window opens
        self.win = None
        self.fields = {}                  # setting name -> (typed text, message label)
        self.saved = {}                   # setting name -> the number saved in config.ini
        self.dirty = False

    # ----- opening and closing -----
    def open(self):
        if self.win is not None:
            self.win.lift()
            self.win.focus_force()
            return
        self.saved = config.all_values()

        win = self.win = tk.Toplevel(self.root)
        win.title("Config")
        win.configure(bg=theme.BG)
        win.attributes("-topmost", True)
        height = 140 + ROW_H * len(config.SETTINGS)
        win.geometry(f"{WIDTH}x{height}+{self.position[0]}+{self.position[1]}")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close)

        tk.Label(win, text="CONFIG", font=theme.FONT_TITLE, fg=theme.CYAN, bg=theme.BG).pack(pady=(12, 0))
        tk.Label(win, text="The settings of config.ini. SAVE turns on when something changed.",
                 font=theme.FONT_LOG, fg=theme.MUTED, bg=theme.BG).pack(pady=(2, 8))

        bar = tk.Frame(win, bg=theme.BG)
        bar.pack(side="bottom", fill="x", padx=12, pady=12)
        self.btn_save = GameButton(bar, "SAVE", self._save, theme.GREEN)
        self.btn_save.pack(side="left", expand=True, fill="x", padx=(0, 6), ipady=4)
        GameButton(bar, "CLOSE", self.close, theme.RED).pack(side="left", expand=True, fill="x",
                                                             padx=(6, 0), ipady=4)

        body = tk.Frame(win, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.CYAN)
        body.pack(fill="both", expand=True, padx=12)

        self.fields = {}
        for setting in config.SETTINGS:
            self._make_row(body, setting)
        self._update()

    def close(self, force=False):
        """Closes the window. With unsaved changes it asks first, unless `force` is set."""
        if self.win is None:
            return
        if self.dirty:
            if not force and not messagebox.askyesno("Config", "Discard the unsaved changes?", parent=self.win):
                return
            self.log("Unsaved config changes were discarded.", "WARN")
        self.win.destroy()
        self.win = None
        self.dirty = False

    # ----- one setting -----
    def _make_row(self, parent, setting):
        frame = tk.Frame(parent, bg=theme.BG, highlightthickness=1, highlightbackground=theme.MUTED)
        frame.pack(fill="x", padx=8, pady=8)
        tk.Label(frame, text=setting.label, font=theme.FONT_BTN, fg=theme.TEXT, bg=theme.BG,
                 anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(frame, text=setting.help, font=FONT_NOTE, fg=theme.MUTED, bg=theme.BG, anchor="w",
                 justify="left", wraplength=WIDTH - 70).pack(fill="x", padx=10)

        line = tk.Frame(frame, bg=theme.BG)
        line.pack(fill="x", padx=10, pady=(8, 0))
        var = tk.StringVar(value=str(self.saved[setting.name]))
        only_digits = (self.win.register(lambda text: text == "" or (text.isdigit() and len(text) <= 6)), "%P")
        entry = tk.Entry(line, textvariable=var, width=10, font=theme.FONT_BTN, bg=theme.PANEL, fg=theme.TEXT,
                         insertbackground=theme.CYAN, relief="flat", highlightthickness=1,
                         highlightbackground=theme.CYAN, highlightcolor=theme.GREEN,
                         validate="key", validatecommand=only_digits)
        entry.pack(side="left", ipady=3)
        tk.Label(line, text=f"allowed {setting.minimum} to {setting.maximum}, default {setting.default}",
                 font=FONT_NOTE, fg=theme.MUTED, bg=theme.BG).pack(side="left", padx=10)

        message = tk.Label(frame, text="", font=FONT_NOTE, fg=theme.RED, bg=theme.BG, anchor="w")
        message.pack(fill="x", padx=10, pady=(2, 8))
        var.trace_add("write", lambda *_: self._update())
        self.fields[setting.name] = (var, message)

    # ----- changes -----
    def _texts(self):
        return {name: var.get() for name, (var, _) in self.fields.items()}

    def _update(self):
        """SAVE is clickable only while something differs from what is saved, and every field is valid.
        Typing the saved value again turns it off."""
        changed, valid, problems = config.evaluate(self._texts(), self.saved)
        for name, (_, message) in self.fields.items():
            message.config(text=problems.get(name, ""))
        self.dirty = changed
        self.btn_save.set_enabled(changed and valid)

    def _save(self):
        if not self.dirty:
            return
        values = {}
        for setting in config.SETTINGS:
            value = config.parse(setting, self.fields[setting.name][0].get())
            if value is None:
                return
            values[setting.name] = value
        try:
            config.save(values)
        except OSError as err:
            self.log(f"config.ini could not be saved: {err}", "ERROR")
            return
        self.saved = values
        for name, value in values.items():
            self.log(f"Config saved: {name} = {value}", "OK")
        self._update()