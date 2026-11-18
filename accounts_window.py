"""The Accounts window: tick which accounts are automated, reorder, edit, delete and add them."""
import tkinter as tk
from tkinter import messagebox

import accounts
import settings
import theme
from widgets import GameButton

WIDTH, HEIGHT = 560, 540
ROW_H = 46                 # height of one account row
ROW_GAP = 2                # vertical padding above and below a row
EDGE_SCROLL = 24           # pixels from the list edge where dragging starts to scroll it
FONT_SMALL = ("Consolas", -13, "bold")
FONT_NAME = ("Consolas", -16)


class AccountsWindow:
    def __init__(self, root, settings, log, position):
        self.root = root
        self.settings = settings          # the same dict the console uses, so the choices are saved
        self.log = log
        self.position = position          # (x, y) where the window opens
        self.win = None
        self.rows = []
        self._drag = None

    # ----- opening and closing -----
    def open(self):
        if self.win is not None:
            self.win.lift()
            self.win.focus_force()
            return
        try:
            self.accounts = accounts.load_all()
        except accounts.AccountsError as err:
            self.log(str(err), "ERROR")
            return

        win = self.win = tk.Toplevel(self.root)
        win.title("Accounts")
        win.configure(bg=theme.BG)
        win.attributes("-topmost", True)
        win.geometry(f"{WIDTH}x{HEIGHT}+{self.position[0]}+{self.position[1]}")
        win.minsize(WIDTH, 300)
        win.protocol("WM_DELETE_WINDOW", self.close)

        tk.Label(win, text="ACCOUNTS", font=theme.FONT_TITLE, fg=theme.CYAN, bg=theme.BG).pack(pady=(12, 0))
        tk.Label(win, text="Checked accounts are automated in this order. Drag a row to change the order.",
                 font=theme.FONT_LOG, fg=theme.MUTED, bg=theme.BG).pack(pady=(2, 8))

        # The buttons are packed first so they always stay visible below a long list.
        bar = tk.Frame(win, bg=theme.BG)
        bar.pack(side="bottom", fill="x", padx=12, pady=12)
        GameButton(bar, "ADD ACCOUNT", self._add, theme.GREEN).pack(side="left", expand=True, fill="x",
                                                                    padx=(0, 6), ipady=4)
        GameButton(bar, "CLOSE", self.close, theme.RED).pack(side="left", expand=True, fill="x",
                                                             padx=(6, 0), ipady=4)

        body = tk.Frame(win, bg=theme.PANEL, highlightthickness=2, highlightbackground=theme.CYAN)
        body.pack(fill="both", expand=True, padx=12)
        self.canvas = tk.Canvas(body, bg=theme.PANEL, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(body, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=theme.PANEL)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.inner.bind("<Configure>", lambda e: self._update_scroll_region())
        win.bind("<MouseWheel>", lambda e: self._scroll(-1 if e.delta > 0 else 1))

        self._rebuild()

    def close(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None

    def _on_canvas_resize(self, event):
        self.canvas.itemconfigure(self._inner_id, width=event.width)
        self._update_scroll_region()

    def _update_scroll_region(self):
        """The scrollable height is never smaller than the visible list, so a short list stays put."""
        height = max(self.inner.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))
        if self.inner.winfo_reqheight() <= self.canvas.winfo_height():
            self.canvas.yview_moveto(0)

    def _scroll(self, units):
        """Scrolls only when there are more rows than fit, and never past the first or last row."""
        if self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(units, "units")

    # ----- the list -----
    def _rebuild(self):
        for child in self.inner.winfo_children():
            child.destroy()
        self.rows = []
        if not self.accounts:
            tk.Label(self.inner, text="No accounts yet. Use ADD ACCOUNT.", font=theme.FONT_LOG,
                     fg=theme.MUTED, bg=theme.PANEL).pack(pady=30)
            return
        for acc in self.accounts:
            self.rows.append(self._make_row(acc))
        self._renumber()

    def _make_row(self, acc):
        frame = tk.Frame(self.inner, bg=theme.BG, height=ROW_H, highlightthickness=1,
                         highlightbackground=theme.MUTED)
        frame.pack(fill="x", padx=6, pady=ROW_GAP)
        frame.pack_propagate(False)
        row = {"account": acc, "frame": frame}

        grip = tk.Label(frame, text="≡", font=theme.FONT_BTN, fg=theme.MUTED, bg=theme.BG, cursor="fleur")
        grip.pack(side="left", padx=(8, 4))
        number = tk.Label(frame, text="", font=FONT_SMALL, fg=theme.CYAN, bg=theme.BG, width=3, anchor="e",
                          cursor="fleur")
        number.pack(side="left")
        row["number"] = number

        var = tk.BooleanVar(value=acc.name not in accounts.disabled_names(self.settings))
        check = tk.Checkbutton(frame, variable=var, bg=theme.BG, activebackground=theme.BG,
                               selectcolor=theme.BG, fg=theme.GREEN, activeforeground=theme.GREEN,
                               highlightthickness=0, bd=0, cursor="hand2",
                               command=lambda: self._toggle(acc, var))
        check.pack(side="left", padx=(6, 2))

        GameButton(frame, "DELETE", lambda: self._delete(acc), theme.RED, FONT_SMALL).pack(
            side="right", padx=(4, 8), ipadx=4)
        GameButton(frame, "EDIT", lambda: self._edit(acc), theme.YELLOW, FONT_SMALL).pack(
            side="right", padx=4, ipadx=4)
        name = tk.Label(frame, text=acc.name, font=FONT_NAME, fg=theme.TEXT, bg=theme.BG, anchor="w",
                        cursor="fleur")
        name.pack(side="left", fill="x", expand=True, padx=6)

        # Everything except the checkbox and the buttons works as a drag handle.
        for handle in (frame, grip, number, name):
            handle.bind("<ButtonPress-1>", lambda e, r=row: self._drag_start(r))
            handle.bind("<B1-Motion>", self._drag_move)
            handle.bind("<ButtonRelease-1>", self._drag_end)
        return row

    def _renumber(self):
        for index, row in enumerate(self.rows, 1):
            row["number"].config(text=f"{index}.")

    def _toggle(self, acc, var):
        accounts.set_enabled(self.settings, acc.name, var.get())
        self._save_settings()

    def _save_settings(self):
        settings.save(self.settings)

    # ----- drag to reorder -----
    def _drag_start(self, row):
        self._drag = {"row": row, "order": [r["account"].name for r in self.rows]}
        row["frame"].config(highlightbackground=theme.MAGENTA)

    def _drag_move(self, event):
        if not self._drag:
            return
        row = self._drag["row"]
        # Where the pointer is inside the list decides which slot the row belongs in.
        y = event.y_root - self.inner.winfo_rooty()
        target = max(0, min(len(self.rows) - 1, int(y // (ROW_H + 2 * ROW_GAP))))
        current = self.rows.index(row)
        if target != current:
            other = self.rows[target]["frame"]
            # The row is moved by re-packing it next to its new neighbour. It is never hidden,
            # so the mouse drag carries on without interruption.
            if target < current:
                row["frame"].pack_configure(before=other)
            else:
                row["frame"].pack_configure(after=other)
            self.rows.insert(target, self.rows.pop(current))
            self._renumber()
        # Scroll when the pointer is dragged against the top or bottom edge of the list.
        top = self.canvas.winfo_rooty()
        if event.y_root < top + EDGE_SCROLL:
            self._scroll(-1)
        elif event.y_root > top + self.canvas.winfo_height() - EDGE_SCROLL:
            self._scroll(1)

    def _drag_end(self, event):
        if not self._drag:
            return
        self._drag["row"]["frame"].config(highlightbackground=theme.MUTED)
        before = self._drag["order"]
        self._drag = None
        self.accounts = [r["account"] for r in self.rows]
        if [a.name for a in self.accounts] != before:
            accounts.save_all(self.accounts)
            self.log("Account order saved.", "OK")

    @staticmethod
    def _key(name):
        """A name reduced to what matters for comparing: no spaces, no difference in capitals."""
        return "".join(name.split()).casefold()

    def _name_taken(self, name, ignore=None):
        """True when another account already has this name."""
        key = self._key(name)
        return any(a is not ignore and self._key(a.name) == key for a in self.accounts)

    # ----- edit, delete, add -----
    def _edit(self, acc):
        def save(name, password):
            if self._name_taken(name, ignore=acc):
                return "Another account already uses that name."
            old = acc.name
            acc.name, acc.password = name, password
            accounts.rename_in_settings(self.settings, old, name)
            self._save_settings()
            accounts.save_all(self.accounts)
            self._rebuild()
            self.log(f"Account updated: {name}", "OK")
            return None
        self._ask("Edit account", acc.name, acc.password, save)

    def _delete(self, acc):
        if not messagebox.askyesno("Delete account", f"Delete {acc.name} from Accounts.ini?", parent=self.win):
            return
        self.accounts.remove(acc)
        accounts.set_enabled(self.settings, acc.name, True)   # forget its unchecked mark
        self._save_settings()
        accounts.save_all(self.accounts)
        self._rebuild()
        self.log(f"Account deleted: {acc.name}", "OK")

    def _add(self):
        def save(name, password):
            if self._name_taken(name):
                return "That account already exists."
            self.accounts.append(accounts.Account(name, password))
            accounts.save_all(self.accounts)
            self._rebuild()
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(1.0)
            self.log(f"Account added: {name}", "OK")
            return None
        self._ask("Add account", "", "", save)

    def _ask(self, title, name, password, on_save):
        """Small window with a username and a password. on_save(name, password) returns an error
        text to show, or None when the account was stored."""
        dlg = tk.Toplevel(self.win)
        dlg.title(title)
        dlg.configure(bg=theme.BG)
        dlg.transient(self.win)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        x, y = self.win.winfo_rootx() + 60, self.win.winfo_rooty() + 110
        dlg.geometry(f"440x270+{x}+{y}")

        def field(label, value, hidden=False):
            tk.Label(dlg, text=label, font=theme.FONT_STATUS, fg=theme.MUTED, bg=theme.BG,
                     anchor="w").pack(fill="x", padx=20, pady=(12, 2))
            entry = tk.Entry(dlg, font=FONT_NAME, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
                             relief="flat", highlightthickness=1, highlightbackground=theme.MUTED,
                             highlightcolor=theme.CYAN, show="•" if hidden else "")
            entry.insert(0, value)
            entry.pack(fill="x", padx=20, ipady=4)
            return entry

        user_entry = field("Username", name)
        pass_entry = field("Password", password, hidden=True)
        show = tk.BooleanVar(value=False)
        tk.Checkbutton(dlg, text="Show password", variable=show, font=theme.FONT_LOG, fg=theme.TEXT,
                       bg=theme.BG, activebackground=theme.BG, activeforeground=theme.TEXT,
                       selectcolor=theme.BG, highlightthickness=0, bd=0,
                       command=lambda: pass_entry.config(show="" if show.get() else "•")
                       ).pack(anchor="w", padx=16, pady=(6, 0))
        message = tk.Label(dlg, text="", font=theme.FONT_LOG, fg=theme.RED, bg=theme.BG)
        message.pack(pady=(4, 0))

        def submit(event=None):
            user, secret = user_entry.get().strip(), pass_entry.get()
            if not user or not secret:
                message.config(text="Enter both a username and a password.")
                return
            error = on_save(user, secret)
            if error:
                message.config(text=error)
            else:
                dlg.destroy()

        bar = tk.Frame(dlg, bg=theme.BG)
        bar.pack(fill="x", padx=20, pady=10)
        GameButton(bar, "SAVE", submit, theme.GREEN).pack(side="left", expand=True, fill="x",
                                                          padx=(0, 6), ipady=2)
        GameButton(bar, "CANCEL", dlg.destroy, theme.RED).pack(side="left", expand=True, fill="x",
                                                               padx=(6, 0), ipady=2)
        dlg.bind("<Return>", submit)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.grab_set()
        user_entry.focus_set()