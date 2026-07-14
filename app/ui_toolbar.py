# app/ui_toolbar.py
"""
ToolbarMixin — handles the creation and wiring of the application
toolbar (undo/redo, directory buttons, dir label, progress bar).
"""
import customtkinter as ctk

from app.constants import TEXT_ADAPTIVE, TEXT_SECONDARY


class ToolbarMixin:
    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = ctk.CTkFrame(
            self, height=50, corner_radius=0)
        bar.grid(
            row=0, column=0, columnspan=2,
            sticky="ew")

        self.undo_btn = ctk.CTkButton(
            bar, text="↶ Undo", width=70,
            state="disabled", command=self._on_undo)
        self.undo_btn.pack(
            side="left", padx=(10, 5), pady=10)

        self.redo_btn = ctk.CTkButton(
            bar, text="↷ Redo", width=70,
            state="disabled", command=self._on_redo)
        self.redo_btn.pack(
            side="left", padx=(5, 0), pady=10)

        ctk.CTkFrame(
            bar, width=1, height=30,
            fg_color="gray40",
        ).pack(side="left", padx=12, pady=10)

        self.select_dir_btn = ctk.CTkButton(
            bar, text="📁  Select Directory",
            command=self.select_directory)
        self.select_dir_btn.pack(
            side="left", padx=(0, 4), pady=10)

        self.add_dir_btn = ctk.CTkButton(
            bar, text="📁➕  Add Directory",
            height=30,
            fg_color="transparent", border_width=1,
            text_color=TEXT_ADAPTIVE, font=("", 11),
            command=self.add_directory)
        self.add_dir_btn.pack(
            side="left", padx=(0, 12), pady=10)

        self.dir_label = ctk.CTkLabel(
            bar, text="No directory selected.",
            text_color=TEXT_SECONDARY)
        self.dir_label.pack(
            side="left", padx=10, pady=10)

        self.progress_bar = ctk.CTkProgressBar(
            bar, width=200, mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.pack(
            side="right", padx=10, pady=10)
        self.progress_bar.pack_forget()

