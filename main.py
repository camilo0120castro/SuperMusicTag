# main.py
"""
SuperMusicTag — entry point.
"""
from dotenv import load_dotenv

load_dotenv()

import tkinter as _tk
import customtkinter as ctk

# Workaround for CTkToplevel iconbitmap bug on
# Python 3.14. wm_iconbitmap raises a TclError on
# that version when called on a Toplevel window.
# Patching Wm.wm_iconbitmap to swallow the error
# silently — icon is cosmetic and not functional.
_original_iconbitmap = _tk.Wm.wm_iconbitmap

def _safe_iconbitmap(self, bitmap=None, default=None):
    try:
        return _original_iconbitmap(
            self, bitmap=bitmap, default=default)
    except Exception:
        pass

_tk.Wm.wm_iconbitmap = _safe_iconbitmap
_tk.Wm.iconbitmap    = _safe_iconbitmap

from app.app import SuperMusicTagApp


if __name__ == "__main__":
    app = SuperMusicTagApp()
    app.mainloop()
