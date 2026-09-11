"""
Progress Panel - Shows operation progress with cancel support
"""

import tkinter as tk
from tkinter import ttk


class ProgressPanel(ttk.LabelFrame):
    """Progress display with bar and cancel button"""

    def __init__(self, parent, on_cancel=None, **kwargs):
        super().__init__(parent, text=" PROGRESS ", **kwargs)
        self.on_cancel = on_cancel

        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Idle")
        self.percent_var = tk.StringVar(value="0%")

        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)

        # Status and percent
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=(8, 2))
        top_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(top_frame, textvariable=self.status_var, font=('Segoe UI', 9))
        self.status_label.grid(row=0, column=0, sticky='w')

        self.percent_label = ttk.Label(top_frame, textvariable=self.percent_var, font=('Segoe UI', 9, 'bold'))
        self.percent_label.grid(row=0, column=1, sticky='e')

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100,
            mode='determinate',
            length=200
        )
        self.progress_bar.grid(row=1, column=0, sticky='ew', padx=10, pady=5)

        # Cancel button and additional info
        bottom_frame = ttk.Frame(self)
        bottom_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=(2, 8))
        bottom_frame.columnconfigure(0, weight=1)

        self.detail_var = tk.StringVar(value="")
        ttk.Label(bottom_frame, textvariable=self.detail_var, style='Muted.TLabel').grid(row=0, column=0, sticky='w')

        self.cancel_button = ttk.Button(
            bottom_frame,
            text="CANCEL",
            width=10,
            command=self._on_cancel_clicked,
            state='disabled'
        )
        self.cancel_button.grid(row=0, column=1, sticky='e')

    def _on_cancel_clicked(self):
        self.status_var.set("Cancelling...")
        self.cancel_button.config(state='disabled')
        if self.on_cancel:
            self.on_cancel()

    def set_progress(self, percent: int, status: str = None, detail: str = None):
        """Update progress"""
        # Clamp
        percent = max(0, min(100, percent))
        self.progress_var.set(percent)
        self.percent_var.set(f"{percent}%")

        if status:
            self.status_var.set(status)

        if detail is not None:
            self.detail_var.set(detail)

        # Change color based on status - use try/except to handle missing style layouts
        # On some Tk versions, custom Progressbar styles need explicit layout
        try:
            if "error" in (status or "").lower() or "failed" in (status or "").lower():
                self.progress_bar.configure(style='Error.TProgressbar')
            elif "success" in (status or "").lower() or percent == 100:
                self.progress_bar.configure(style='Success.TProgressbar')
            else:
                self.progress_bar.configure(style='TProgressbar')
        except Exception:
            # Fallback: keep default style if custom style layout not found
            try:
                self.progress_bar.configure(style='TProgressbar')
            except Exception:
                pass

    def set_idle(self):
        self.set_progress(0, "Idle", "")
        self.cancel_button.config(state='disabled')

    def set_busy(self, status: str = "Working..."):
        self.set_progress(0, status, "")
        self.cancel_button.config(state='normal')

    def set_success(self, message: str = "Operation successful"):
        self.set_progress(100, message, "")
        self.cancel_button.config(state='disabled')

    def set_error(self, message: str = "Operation failed"):
        self.set_progress(self.progress_var.get(), message, "")
        self.cancel_button.config(state='disabled')

    def enable_cancel(self, enabled: bool = True):
        self.cancel_button.config(state='normal' if enabled else 'disabled')
