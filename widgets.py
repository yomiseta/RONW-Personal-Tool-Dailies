"""Small shared interface widgets."""
import tkinter as tk

import theme


class GameButton(tk.Label):
    """A flat neon button. tk.Button ignores custom colours on Windows, so a Label is used instead."""

    def __init__(self, parent, text, command, color, font=theme.FONT_BTN):
        super().__init__(parent, text=text, font=font, fg=color, bg=theme.BG,
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