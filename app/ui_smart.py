# app/ui_smart.py
"""
SmartTabMixin — handles the Smart Instructions tab layout and its
placeholder callbacks (NL command execution, staged deletion).
"""
import customtkinter as ctk

from app.constants import (
    WARNING_BG, WARNING_YELLOW,
    DANGER_RED, DANGER_RED_HOVER,
)


class SmartTabMixin:
    # ------------------------------------------------------------------
    # Placeholders
    # ------------------------------------------------------------------
    def _execute_nl_command_placeholder(self):
        # self.nl_input is not available while the
        # Smart Instructions tab is disabled.
        print("TODO: NLP command (Smart tab disabled)")

    def _confirm_delete_placeholder(self):
        print(
            "TODO: confirm deletion with security "
            "checks.")

    # ------------------------------------------------------------------
    # Smart tab
    # ------------------------------------------------------------------
    def _setup_smart_tab(self):
        # Disabled — Smart Instructions tab not yet implemented.
        # All code below is preserved for future use.
        pass

        # self.tab_smart.grid_rowconfigure(0, weight=0)
        # self.tab_smart.grid_rowconfigure(1, weight=0)
        # self.tab_smart.grid_rowconfigure(2, weight=6)
        # self.tab_smart.grid_rowconfigure(3, weight=1)
        # self.tab_smart.grid_columnconfigure(
        #     0, weight=1)

        # banner = ctk.CTkFrame(
        #     self.tab_smart, fg_color=WARNING_BG,
        #     corner_radius=6)
        # banner.grid(
        #     row=0, column=0, sticky="ew",
        #     padx=10, pady=(10, 0))
        # ctk.CTkLabel(
        #     banner,
        #     text=(
        #         "⚠  Smart Instructions are not yet "
        #         "implemented."),
        #     text_color=WARNING_YELLOW, font=("", 12),
        # ).pack(pady=8, padx=12)

        # input_frame = ctk.CTkFrame(self.tab_smart)
        # input_frame.grid(
        #     row=1, column=0, sticky="new",
        #     pady=(8, 0))
        # self.nl_input = ctk.CTkEntry(
        #     input_frame,
        #     placeholder_text=(
        #         "e.g. Find all duplicate files"))
        # self.nl_input.pack(
        #     side="left", fill="x", expand=True,
        #     padx=5, pady=5)
        # ctk.CTkButton(
        #     input_frame, text="Execute", width=80,
        #     command=(
        #         self._execute_nl_command_placeholder),
        # ).pack(side="left", padx=(0, 5), pady=5)

        # staged_wrap = ctk.CTkFrame(
        #     self.tab_smart, fg_color="transparent")
        # staged_wrap.grid(
        #     row=2, column=0, sticky="nsew")
        # ctk.CTkLabel(
        #     staged_wrap,
        #     text="Staged for Deletion",
        #     font=("", 14, "bold"),
        # ).pack(anchor="w", pady=(5, 0))
        # self.staged_delete_scroll = (
        #     ctk.CTkScrollableFrame(staged_wrap))
        # self.staged_delete_scroll.pack(
        #     fill="both", expand=True,
        #     padx=5, pady=5)

        # bottom = ctk.CTkFrame(
        #     self.tab_smart, fg_color="transparent")
        # bottom.grid(row=3, column=0, sticky="sew")
        # ctk.CTkButton(
        #     bottom,
        #     text="Confirm Delete", width=150,
        #     fg_color=DANGER_RED,
        #     hover_color=DANGER_RED_HOVER,
        #     command=self._confirm_delete_placeholder,
        # ).pack(side="right", padx=5, pady=10)

