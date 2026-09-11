"""
Device Panel - Shows protocol selection, device info, signature, memory sizes
"""

import tkinter as tk
from tkinter import ttk


class DevicePanel(ttk.LabelFrame):
    """Panel showing device information and protocol selection"""

    def __init__(self, parent, on_protocol_change=None, **kwargs):
        super().__init__(parent, text=" DEVICE ", **kwargs)
        self.on_protocol_change = on_protocol_change

        self.protocol_var = tk.StringVar(value="AVR ISP")
        self.device_var = tk.StringVar(value="Auto Detect")
        self.signature_var = tk.StringVar(value="-- -- --")
        self.flash_var = tk.StringVar(value="--")
        self.eeprom_var = tk.StringVar(value="--")
        self.name_var = tk.StringVar(value="No device")

        self._build_ui()

    def _build_ui(self):
        # Use grid for clean layout
        self.columnconfigure(1, weight=1)

        # Protocol
        ttk.Label(self, text="Protocol:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        self.protocol_combo = ttk.Combobox(
            self,
            textvariable=self.protocol_var,
            values=["AVR ISP", "SPI Memory", "I²C Memory"],
            state='readonly',
            width=18
        )
        self.protocol_combo.grid(row=0, column=1, sticky='ew', padx=10, pady=5)
        self.protocol_combo.bind('<<ComboboxSelected>>', self._on_protocol_selected)

        # Device
        ttk.Label(self, text="Device:").grid(row=1, column=0, sticky='w', padx=10, pady=2)
        device_frame = ttk.Frame(self)
        device_frame.grid(row=1, column=1, sticky='ew', padx=10, pady=2)
        device_frame.columnconfigure(0, weight=1)

        self.device_label = ttk.Label(device_frame, textvariable=self.name_var, font=('Segoe UI', 9, 'bold'))
        self.device_label.grid(row=0, column=0, sticky='w')

        # Signature
        ttk.Label(self, text="Signature:").grid(row=2, column=0, sticky='w', padx=10, pady=2)
        sig_frame = ttk.Frame(self)
        sig_frame.grid(row=2, column=1, sticky='ew', padx=10, pady=2)
        ttk.Label(sig_frame, textvariable=self.signature_var, font=('Consolas', 9)).pack(side='left')
        self.jedec_label = ttk.Label(sig_frame, text="", style='Muted.TLabel')
        self.jedec_label.pack(side='left', padx=10)

        # Memory sizes
        mem_frame = ttk.Frame(self)
        mem_frame.grid(row=3, column=0, columnspan=2, sticky='ew', padx=10, pady=5)
        mem_frame.columnconfigure((0, 1), weight=1)

        flash_frame = ttk.Frame(mem_frame)
        flash_frame.grid(row=0, column=0, sticky='w')
        ttk.Label(flash_frame, text="Flash:").pack(side='left')
        ttk.Label(flash_frame, textvariable=self.flash_var, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=5)

        eeprom_frame = ttk.Frame(mem_frame)
        eeprom_frame.grid(row=0, column=1, sticky='w')
        ttk.Label(eeprom_frame, text="EEPROM:").pack(side='left')
        ttk.Label(eeprom_frame, textvariable=self.eeprom_var, font=('Segoe UI', 9, 'bold')).pack(side='left', padx=5)

        # Extra info for SPI/I2C
        self.extra_frame = ttk.Frame(self)
        self.extra_frame.grid(row=4, column=0, columnspan=2, sticky='ew', padx=10, pady=2)

        ttk.Label(self.extra_frame, text="I²C Addr:").grid(row=0, column=0, sticky='w')
        self.i2c_addr_var = tk.StringVar(value="0x50")
        self.i2c_addr_entry = ttk.Entry(self.extra_frame, textvariable=self.i2c_addr_var, width=6)
        self.i2c_addr_entry.grid(row=0, column=1, padx=5)

        self.extra_info_var = tk.StringVar(value="")
        ttk.Label(self.extra_frame, textvariable=self.extra_info_var, style='Muted.TLabel').grid(row=0, column=2, padx=10)

        # Hide extra frame by default (only for I2C)
        self.extra_frame.grid_remove()

    def _on_protocol_selected(self, event=None):
        protocol = self.protocol_var.get()
        if protocol == "I²C Memory":
            self.extra_frame.grid()
        else:
            self.extra_frame.grid_remove()

        if self.on_protocol_change:
            self.on_protocol_change(protocol)

    def set_device_info(self, info: dict):
        """Update display with device info dict"""
        if not info:
            self.clear()
            return

        name = info.get('name', 'Unknown')
        self.name_var.set(name)

        sig = info.get('signature') or info.get('jedec_id') or "-- -- --"
        self.signature_var.set(sig)

        flash_size = info.get('flash_size', 0)
        eeprom_size = info.get('eeprom_size', 0)

        # Format sizes nicely
        def format_size(size):
            if size == 0:
                return "--"
            if size >= 1024*1024:
                return f"{size/1024/1024:.1f} MB ({size} bytes)"
            elif size >= 1024:
                return f"{size/1024:.1f} KB ({size} bytes)"
            else:
                return f"{size} bytes"

        # For SPI, flash_size is main
        if 'flash_size' in info:
            self.flash_var.set(format_size(info['flash_size']))
        else:
            self.flash_var.set("--")

        if 'eeprom_size' in info and info['eeprom_size']:
            self.eeprom_var.set(format_size(info['eeprom_size']))
        else:
            # For SPI, show sector size or page size
            if 'sector_size' in info:
                self.eeprom_var.set(f"Sector: {info['sector_size']} bytes")
            elif 'page_size' in info:
                self.eeprom_var.set(f"Page: {info['page_size']} bytes")
            else:
                self.eeprom_var.set("--")

        # Extra info
        extra = []
        if 'i2c_address_str' in info:
            extra.append(f"I2C: {info['i2c_address_str']}")
            self.i2c_addr_var.set(info['i2c_address_str'])
        if 'found_str' in info:
            extra.append(f"Found: {info['found_str']}")
        if 'manufacturer' in info:
            extra.append(f"{info['manufacturer']}")

        self.extra_info_var.set(" | ".join(extra))
        if 'jedec_id' in info:
            self.jedec_label.config(text=f"JEDEC: {info['jedec_id']}")

    def clear(self):
        self.name_var.set("No device")
        self.signature_var.set("-- -- --")
        self.flash_var.set("--")
        self.eeprom_var.set("--")
        self.extra_info_var.set("")
        self.jedec_label.config(text="")

    def get_protocol(self) -> str:
        return self.protocol_var.get()

    def get_i2c_address(self) -> int:
        """Parse I2C address entry"""
        addr_str = self.i2c_addr_var.get().strip()
        try:
            if addr_str.lower().startswith('0x'):
                return int(addr_str, 16)
            return int(addr_str)
        except ValueError:
            return 0x50
