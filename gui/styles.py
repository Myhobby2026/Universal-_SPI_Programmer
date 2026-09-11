"""
Professional styling for Universal Programmer GUI
"""

import tkinter as tk
from tkinter import ttk


# Color scheme - professional dark/light hybrid
COLORS = {
    'bg_primary': '#1e1e2e',      # Dark background
    'bg_secondary': '#252536',    # Slightly lighter
    'bg_tertiary': '#2d2d44',     # Cards/frames
    'bg_input': '#31314d',
    'accent': '#4a9eff',          # Blue accent
    'accent_hover': '#6bb0ff',
    'success': '#2ecc71',
    'warning': '#f1c40f',
    'error': '#e74c3c',
    'text_primary': '#e0e0e0',
    'text_secondary': '#a0a0b0',
    'text_muted': '#707080',
    'border': '#3a3a5a',
    'progress_bg': '#2d2d44',
    'progress_fg': '#4a9eff',
}

# Alternative light theme for Windows native look
COLORS_LIGHT = {
    'bg_primary': '#f0f0f0',
    'bg_secondary': '#ffffff',
    'bg_tertiary': '#ffffff',
    'bg_input': '#ffffff',
    'accent': '#0078d4',
    'accent_hover': '#106ebe',
    'success': '#107c10',
    'warning': '#d83b01',
    'error': '#a4262c',
    'text_primary': '#000000',
    'text_secondary': '#505050',
    'text_muted': '#808080',
    'border': '#cccccc',
    'progress_bg': '#e0e0e0',
    'progress_fg': '#0078d4',
}


def apply_styles(root, use_dark=False):
    """Apply ttk styles"""

    style = ttk.Style()

    # Use clam as base for more customization
    try:
        style.theme_use('clam')
    except Exception:
        pass

    # Choose colors
    colors = COLORS if use_dark else COLORS_LIGHT

    # Configure root background
    root.configure(bg=colors['bg_primary'] if use_dark else '#f5f5f5')

    # General
    style.configure('.', background=colors['bg_secondary'],
                    foreground=colors['text_primary'],
                    font=('Segoe UI', 9))

    # Frame
    style.configure('TFrame', background=colors['bg_secondary'])
    style.configure('Card.TFrame', background=colors['bg_tertiary'],
                    relief='flat', borderwidth=1)
    style.configure('Dark.TFrame', background=colors['bg_primary'])

    # Label
    style.configure('TLabel', background=colors['bg_secondary'],
                    foreground=colors['text_primary'],
                    font=('Segoe UI', 9))
    style.configure('Title.TLabel', font=('Segoe UI', 12, 'bold'),
                    foreground=colors['text_primary'])
    style.configure('Heading.TLabel', font=('Segoe UI', 10, 'bold'),
                    foreground=colors['text_primary'])
    style.configure('Muted.TLabel', foreground=colors['text_muted'],
                    font=('Segoe UI', 8))
    style.configure('Success.TLabel', foreground=colors['success'])
    style.configure('Error.TLabel', foreground=colors['error'])
    style.configure('Status.TLabel', font=('Consolas', 9))

    # Button
    style.configure('TButton', font=('Segoe UI', 9),
                    padding=(12, 6),
                    background=colors['bg_tertiary'])
    style.map('TButton',
              background=[('active', colors['accent_hover']), ('pressed', colors['accent'])],
              foreground=[('active', '#ffffff')])

    style.configure('Accent.TButton', background=colors['accent'],
                    foreground='white',
                    font=('Segoe UI', 9, 'bold'),
                    padding=(14, 7))
    style.map('Accent.TButton',
              background=[('active', colors['accent_hover']), ('pressed', colors['accent'])],
              foreground=[('active', 'white')])

    style.configure('Danger.TButton', background=colors['error'],
                    foreground='white')

    # Combobox
    style.configure('TCombobox', fieldbackground=colors['bg_input'],
                    background=colors['bg_input'],
                    foreground=colors['text_primary'],
                    arrowcolor=colors['text_primary'])

    # Entry
    style.configure('TEntry', fieldbackground=colors['bg_input'],
                    foreground=colors['text_primary'],
                    insertcolor=colors['text_primary'])

    # Progressbar - define base and ensure custom styles inherit layout
    style.configure('TProgressbar', background=colors['progress_fg'],
                    troughcolor=colors['progress_bg'],
                    bordercolor=colors['border'],
                    lightcolor=colors['progress_fg'],
                    darkcolor=colors['progress_fg'])

    # For custom progressbar styles, copy layout from TProgressbar to avoid TclError
    # Layout "Horizontal.Error.TProgressbar" not found happens when style has no layout
    try:
        base_layout = style.layout('TProgressbar')
        style.layout('Success.TProgressbar', base_layout)
        style.layout('Error.TProgressbar', base_layout)
    except Exception:
        # Fallback: try Horizontal layout name (some themes use Horizontal.TProgressbar)
        try:
            base_layout = style.layout('Horizontal.TProgressbar')
            style.layout('Horizontal.Success.TProgressbar', base_layout)
            style.layout('Horizontal.Error.TProgressbar', base_layout)
            # Also try without Horizontal prefix for safety
            style.layout('Success.TProgressbar', base_layout)
            style.layout('Error.TProgressbar', base_layout)
        except Exception:
            pass

    style.configure('Success.TProgressbar', background=colors['success'],
                    troughcolor=colors['progress_bg'])
    style.configure('Error.TProgressbar', background=colors['error'],
                    troughcolor=colors['progress_bg'])
    # Also configure Horizontal variants
    try:
        style.configure('Horizontal.Success.TProgressbar', background=colors['success'],
                        troughcolor=colors['progress_bg'])
        style.configure('Horizontal.Error.TProgressbar', background=colors['error'],
                        troughcolor=colors['progress_bg'])
    except Exception:
        pass

    # Labelframe
    style.configure('TLabelframe', background=colors['bg_secondary'],
                    bordercolor=colors['border'])
    style.configure('TLabelframe.Label', background=colors['bg_secondary'],
                    foreground=colors['text_primary'],
                    font=('Segoe UI', 9, 'bold'))

    # Notebook (tabs)
    style.configure('TNotebook', background=colors['bg_primary'],
                    borderwidth=0)
    style.configure('TNotebook.Tab', background=colors['bg_tertiary'],
                    foreground=colors['text_secondary'],
                    padding=(12, 6),
                    font=('Segoe UI', 9))
    style.map('TNotebook.Tab',
              background=[('selected', colors['accent']), ('active', colors['bg_tertiary'])],
              foreground=[('selected', 'white'), ('active', colors['text_primary'])])

    # Scrollbar
    style.configure('TScrollbar', background=colors['bg_tertiary'],
                    troughcolor=colors['bg_secondary'],
                    bordercolor=colors['border'])

    # Separator
    style.configure('TSeparator', background=colors['border'])

    return colors


def get_font(family='Segoe UI', size=9, weight='normal'):
    return (family, size, weight)
