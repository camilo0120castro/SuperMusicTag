# app/ui_unorganized_overlay.py
"""
_SuggestionClearOverlay — floating ✕ button that appears over the
right edge of suggestion cells in the Unorganized tab treeview.
Used by UnorganizedMixin (ui_unorganized.py).
"""
import tkinter as tk
from tkinter import ttk


# ---------------------------------------------------------------------------
# Hover ✕ overlay manager
# ---------------------------------------------------------------------------
class _SuggestionClearOverlay:
    """
    Manages a single floating ✕ button that appears over
    the right edge of whichever suggestion cell the mouse
    is currently hovering over.


    The button is a child of the ROOT WINDOW (app), not
    the treeview or its container. It is positioned using
    absolute screen coordinates so there are no z-order or
    coordinate-conversion issues. This is the only approach
    that reliably receives click events on all platforms.
    """


    _BTN_WIDTH  = 28
    _BTN_HEIGHT = 24


    def __init__(self, tree: ttk.Treeview,
                 root_window,
                 col_ids: tuple,
                 on_clear):
        """
        tree        : the ttk.Treeview widget
        root_window : the top-level app window (ctk.CTk)
        col_ids     : suggestion column ids
        on_clear    : callable(iid, col_id)
        """
        self._tree         = tree
        self._root         = root_window
        self._col_ids      = set(col_ids)
        self._on_clear     = on_clear
        self._current      = None
        self._mouse_on_btn = False
        self._hide_job     = None


        # Button is a child of the ROOT WINDOW.
        # .place() uses absolute x/y within the root window.
        self._btn = tk.Label(
            root_window,
            text="✕",
            bg="#8b2500",
            fg="#ffffff",
            font=("", 11, "bold"),
            cursor="hand2",
            relief="flat",
            padx=0, pady=0,
        )
        self._btn.bind("<Button-1>",  self._on_click)
        self._btn.bind("<Enter>", self._on_btn_enter)
        self._btn.bind("<Leave>", self._on_btn_leave)
        self._btn.place_forget()


    # ------------------------------------------------------------------
    def on_motion(self, event):
        if self._mouse_on_btn:
            return


        iid = self._tree.identify_row(event.y)
        col = self._tree.identify_column(event.x)


        if not iid or not col:
            self.hide()
            return


        try:
            col_id = self._tree.column(col, "id")
        except Exception:
            self.hide()
            return


        if col_id not in self._col_ids:
            self.hide()
            return


        try:
            val = self._tree.set(iid, col_id)
        except Exception:
            self.hide()
            return


        if not val or not val.strip():
            self.hide()
            return


        if self._current == (iid, col_id):
            return


        try:
            bbox = self._tree.bbox(iid, col_id)
        except Exception:
            self.hide()
            return


        if not bbox:
            self.hide()
            return


        bx, by, bw, bh = bbox


        # Convert treeview-local bbox to root-window
        # coordinates using absolute screen position.
        tree_abs_x = self._tree.winfo_rootx()
        tree_abs_y = self._tree.winfo_rooty()
        root_abs_x = self._root.winfo_rootx()
        root_abs_y = self._root.winfo_rooty()


        # Position within root window
        btn_x = (tree_abs_x - root_abs_x
                 + bx + bw - self._BTN_WIDTH)
        btn_y = (tree_abs_y - root_abs_y
                 + by
                 + (bh - self._BTN_HEIGHT) // 2)


        self._current = (iid, col_id)
        self._btn.place(
            x=btn_x, y=btn_y,
            width=self._BTN_WIDTH,
            height=self._BTN_HEIGHT)
        self._btn.lift()


    def on_leave(self, _event=None):
        if not self._mouse_on_btn:
            # Delay the hide slightly so the button's <Enter> can cancel it
            # before it fires (the treeview <Leave> arrives before button <Enter>).
            self._cancel_hide()
            self._hide_job = self._btn.after(80, self.hide)


    def _cancel_hide(self):
        if self._hide_job is not None:
            self._btn.after_cancel(self._hide_job)
            self._hide_job = None


    def hide(self, _event=None):
        self._cancel_hide()
        self._current      = None
        self._mouse_on_btn = False
        self._btn.place_forget()


    def _on_btn_enter(self, _event=None):
        self._cancel_hide()
        self._mouse_on_btn = True


    def _on_btn_leave(self, event):
        self._mouse_on_btn = False
        # Synthesise a check at the current position
        self.on_motion(event)


    def _on_click(self, _event):
        if self._current is None:
            return
        iid, col_id = self._current
        self.hide()
        self._on_clear(iid, col_id)

