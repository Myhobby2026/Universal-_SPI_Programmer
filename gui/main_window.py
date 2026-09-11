"""
Main Window - Professional Universal Programmer GUI
Layout:
  - Title bar
  - Connection panel
  - Device panel
  - Operations panel
  - Hex viewer
  - Progress panel
  - Log console
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import sys
from datetime import datetime
import hashlib
import json

# Local imports
from hardware.serial_manager import SerialManager, SerialError
from hardware.arduino_interface import ArduinoInterface, ArduinoInterfaceError
from protocols.avr_isp import AVRISPProtocol
from protocols.spi_memory import SPIMemoryProtocol
from protocols.i2c_memory import I2CMemoryProtocol
from protocols.protocol_base import ProtocolError, DeviceNotDetectedError
from memory.dump_manager import DumpManager
from memory.bin_manager import BinManager, BinManagerError
from .hex_viewer import HexViewer
from .device_panel import DevicePanel
from .progress_panel import ProgressPanel
from .styles import apply_styles


class LogConsole(ttk.LabelFrame):
    """Professional log console with levels"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text=" LOG ", **kwargs)
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Text widget
        text_frame = ttk.Frame(self)
        text_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            wrap='word',
            font=('Consolas', 9),
            height=8,
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='#ffffff',
            state='disabled'
        )
        scroll = ttk.Scrollbar(text_frame, orient='vertical', command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)

        self.text.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')

        # Tags for levels
        self.text.tag_configure('INFO', foreground='#d4d4d4')
        self.text.tag_configure('SUCCESS', foreground='#4ec9b0')
        self.text.tag_configure('WARNING', foreground='#dcdcaa')
        self.text.tag_configure('ERROR', foreground='#f44747')
        self.text.tag_configure('TIME', foreground='#858585')

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=(0, 5))

        ttk.Button(btn_frame, text="Clear Log", width=10, command=self.clear).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Save Log", width=10, command=self.save_log).pack(side='left', padx=2)

        self.rowconfigure(0, weight=1)

    def log(self, message: str, level: str = "INFO"):
        """Add log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text.configure(state='normal')
        self.text.insert('end', f"[{timestamp}] ", 'TIME')
        self.text.insert('end', f"{level:<7} ", level)
        self.text.insert('end', f"{message}\n", level)
        self.text.see('end')
        self.text.configure(state='disabled')
        # Also print to console for debugging
        print(f"[{timestamp}] {level} {message}")

    def clear(self):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.configure(state='disabled')

    def save_log(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            title="Save Log"
        )
        if filepath:
            try:
                content = self.text.get('1.0', 'end')
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log(f"Log saved to {filepath}", "SUCCESS")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save log: {e}")


class ConnectionPanel(ttk.LabelFrame):
    """Connection management panel"""

    def __init__(self, parent, serial_manager, on_connect=None, on_disconnect=None, **kwargs):
        super().__init__(parent, text=" CONNECTION ", **kwargs)
        self.serial_manager = serial_manager
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="115200")
        self.status_var = tk.StringVar(value="● Disconnected")
        self._connected = False

        self._build_ui()
        self.refresh_ports()

    def _build_ui(self):
        self.columnconfigure(1, weight=1)

        # Port
        ttk.Label(self, text="Port:").grid(row=0, column=0, sticky='w', padx=10, pady=5)
        port_frame = ttk.Frame(self)
        port_frame.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        port_frame.columnconfigure(0, weight=1)

        self.port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=20)
        self.port_combo.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        ttk.Button(port_frame, text="↻", width=3, command=self.refresh_ports).grid(row=0, column=1)

        # Baud
        ttk.Label(self, text="Baud:").grid(row=0, column=2, sticky='w', padx=10, pady=5)
        self.baud_combo = ttk.Combobox(
            self,
            textvariable=self.baud_var,
            values=["9600", "19200", "38400", "57600", "115200", "230400"],
            width=8,
            state='readonly'
        )
        self.baud_combo.grid(row=0, column=3, padx=5, pady=5)

        # Connect button
        self.connect_button = ttk.Button(self, text="CONNECT", style='Accent.TButton', command=self.toggle_connect)
        self.connect_button.grid(row=0, column=4, padx=10, pady=5)

        # Status
        status_frame = ttk.Frame(self)
        status_frame.grid(row=1, column=0, columnspan=5, sticky='ew', padx=10, pady=(0, 8))

        ttk.Label(status_frame, text="Status:").pack(side='left')
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=('Segoe UI', 9, 'bold'))
        self.status_label.pack(side='left', padx=5)

        self.version_var = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self.version_var, style='Muted.TLabel').pack(side='left', padx=15)

    def refresh_ports(self):
        ports = self.serial_manager.list_ports()
        values = [f"{p[0]} - {p[1]}" if p[1] != p[0] else p[0] for p in ports]
        # Extract just port names for values, but show description
        port_names = [p[0] for p in ports]

        self.port_combo['values'] = port_names if port_names else ["No ports found"]
        if port_names:
            # Keep current if still available, else select first
            current = self.port_var.get()
            if current not in port_names:
                self.port_var.set(port_names[0])
        else:
            self.port_var.set("")

        return ports

    def toggle_connect(self):
        if self._connected:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get().strip()
        if not port or "No ports" in port:
            messagebox.showwarning("Connection", "No COM port selected. Please select a valid port.")
            return

        # Extract port name if it contains description
        # Our combo now has just names, but handle "COM5 - description" case
        if ' - ' in port:
            port = port.split(' - ')[0].strip()

        baud = int(self.baud_var.get())

        try:
            self.connect_button.config(state='disabled', text="Connecting...")
            self.status_var.set("● Connecting...")
            self.update_idletasks()

            self.serial_manager.connect(port, baud)

            self._connected = True
            self.connect_button.config(state='normal', text="DISCONNECT")
            self.status_var.set("● Connected")
            self.status_label.configure(style='Success.TLabel')

            if self.on_connect:
                self.on_connect(port, baud)

        except SerialError as e:
            self.status_var.set(f"● Error: {e}")
            self.status_label.configure(style='Error.TLabel')
            self.connect_button.config(state='normal', text="CONNECT")
            messagebox.showerror("Connection Failed", str(e))
        except Exception as e:
            self.status_var.set(f"● Error: {e}")
            self.connect_button.config(state='normal', text="CONNECT")
            messagebox.showerror("Connection Failed", str(e))

    def disconnect(self):
        try:
            self.serial_manager.disconnect()
        except Exception:
            pass

        self._connected = False
        self.connect_button.config(state='normal', text="CONNECT")
        self.status_var.set("● Disconnected")
        self.status_label.configure(style='TLabel')
        self.version_var.set("")

        if self.on_disconnect:
            self.on_disconnect()

    def set_connected(self, connected: bool, version: str = ""):
        self._connected = connected
        if connected:
            self.connect_button.config(text="DISCONNECT")
            self.status_var.set("● Connected")
            self.status_label.configure(style='Success.TLabel')
            if version:
                self.version_var.set(f"FW: {version}")
        else:
            self.connect_button.config(text="CONNECT")
            self.status_var.set("● Disconnected")
            self.status_label.configure(style='TLabel')
            self.version_var.set("")

    def is_connected(self) -> bool:
        return self._connected


class OperationsPanel(ttk.LabelFrame):
    """Operations buttons panel"""

    def __init__(self, parent, on_operation=None, **kwargs):
        super().__init__(parent, text=" OPERATIONS ", **kwargs)
        self.on_operation = on_operation
        self._build_ui()

    def _build_ui(self):
        # First row - main operations
        row1 = ttk.Frame(self)
        row1.pack(fill='x', padx=10, pady=5)

        self.read_btn = ttk.Button(row1, text="READ", width=10, command=lambda: self._trigger("read"))
        self.read_btn.pack(side='left', padx=3)

        self.write_btn = ttk.Button(row1, text="WRITE", width=10, command=lambda: self._trigger("write"))
        self.write_btn.pack(side='left', padx=3)

        self.verify_btn = ttk.Button(row1, text="VERIFY", width=10, command=lambda: self._trigger("verify"))
        self.verify_btn.pack(side='left', padx=3)

        self.erase_btn = ttk.Button(row1, text="ERASE", width=10, command=lambda: self._trigger("erase"))
        self.erase_btn.pack(side='left', padx=3)

        # Second row - specific reads
        row2 = ttk.Frame(self)
        row2.pack(fill='x', padx=10, pady=2)

        self.read_flash_btn = ttk.Button(row2, text="READ FLASH", width=12, command=lambda: self._trigger("read_flash"))
        self.read_flash_btn.pack(side='left', padx=3)

        self.read_eeprom_btn = ttk.Button(row2, text="READ EEPROM", width=12, command=lambda: self._trigger("read_eeprom"))
        self.read_eeprom_btn.pack(side='left', padx=3)

        self.read_all_btn = ttk.Button(row2, text="READ ALL", width=12, command=lambda: self._trigger("read_all"))
        self.read_all_btn.pack(side='left', padx=3)

        # Third row - file operations
        row3 = ttk.Frame(self)
        row3.pack(fill='x', padx=10, pady=5)

        ttk.Button(row3, text="Load BIN", width=12, command=lambda: self._trigger("load_bin")).pack(side='left', padx=3)
        ttk.Button(row3, text="Save BIN", width=12, command=lambda: self._trigger("save_bin")).pack(side='left', padx=3)
        ttk.Button(row3, text="Compare BIN", width=12, command=lambda: self._trigger("compare")).pack(side='left', padx=3)
        ttk.Button(row3, text="Detect", width=10, style='Accent.TButton', command=lambda: self._trigger("detect")).pack(side='left', padx=10)

    def _trigger(self, op: str):
        if self.on_operation:
            self.on_operation(op)

    def set_enabled(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        for btn in [self.read_btn, self.write_btn, self.verify_btn, self.erase_btn,
                    self.read_flash_btn, self.read_eeprom_btn, self.read_all_btn]:
            btn.config(state=state)


class MainWindow:
    """Main application window"""

    def __init__(self, root):
        self.root = root
        self.root.title("Universal Programmer - AVR • SPI • I²C")
        self.root.geometry("1000x850")
        self.root.minsize(900, 700)

        # Apply styles
        self.colors = apply_styles(root, use_dark=False)

        # Managers
        self.serial_manager = SerialManager()
        self.arduino_interface = ArduinoInterface(self.serial_manager)
        self.dump_manager = DumpManager()
        self.bin_manager = BinManager()

        # Protocol instances
        self.protocols = {}
        self.current_protocol: str = "AVR ISP"
        self.current_protocol_obj = None
        self.device_info = None

        # Threading
        self.worker_thread: threading.Thread = None
        self.cancel_event = threading.Event()

        # Build UI
        self._build_ui()

        # Initialize protocols after UI (needs interface)
        self._init_protocols()

        # Bind close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Log startup
        self.log_console.log("Universal Programmer started", "INFO")
        self.log_console.log("Select COM port and connect to Arduino", "INFO")

    def _build_ui(self):
        # Main container with scrollbar? Use PanedWindow for resizable sections
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill='x', pady=(0, 5))

        title_label = ttk.Label(title_frame, text="UNIVERSAL PROGRAMMER", font=('Segoe UI', 16, 'bold'))
        title_label.pack(side='left', padx=10)

        subtitle = ttk.Label(title_frame, text="AVR • SPI • I²C  |  Professional Edition", style='Muted.TLabel', font=('Segoe UI', 10))
        subtitle.pack(side='left', padx=15, pady=(5, 0))

        # Top sections in a frame
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill='x', pady=2)

        # Connection panel
        self.connection_panel = ConnectionPanel(
            top_frame,
            self.serial_manager,
            on_connect=self.on_connected,
            on_disconnect=self.on_disconnected
        )
        self.connection_panel.pack(fill='x', pady=2)

        # Middle - split into left (device+operations) and right (progress)
        middle_frame = ttk.Frame(main_frame)
        middle_frame.pack(fill='x', pady=2)
        middle_frame.columnconfigure(0, weight=3)
        middle_frame.columnconfigure(1, weight=2)

        left_frame = ttk.Frame(middle_frame)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 2))

        right_frame = ttk.Frame(middle_frame)
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(2, 0))

        # Device panel
        self.device_panel = DevicePanel(left_frame, on_protocol_change=self.on_protocol_changed)
        self.device_panel.pack(fill='x', pady=2)

        # Operations panel
        self.operations_panel = OperationsPanel(left_frame, on_operation=self.on_operation)
        self.operations_panel.pack(fill='x', pady=2)
        self.operations_panel.set_enabled(False)

        # Progress panel
        self.progress_panel = ProgressPanel(right_frame, on_cancel=self.on_cancel)
        self.progress_panel.pack(fill='both', expand=True, pady=2)

        # Hex viewer and Log in Notebook (tabs)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill='both', expand=True, pady=5)

        # Hex viewer tab
        hex_frame = ttk.Frame(notebook)
        notebook.add(hex_frame, text=" HEX VIEW ")

        self.hex_viewer = HexViewer(hex_frame)
        self.hex_viewer.pack(fill='both', expand=True)

        # Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text=" LOG ")

        self.log_console = LogConsole(log_frame)
        self.log_console.pack(fill='both', expand=True)

        # Also keep log visible at bottom? We'll have it in tab and also as separate?
        # For better UX, keep log console always visible at bottom, and hex viewer on top
        # Let's restructure: Use PanedWindow vertical

        # Status bar
        status_bar = ttk.Frame(main_frame, height=20)
        status_bar.pack(fill='x', side='bottom', pady=(5, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self.status_var, style='Muted.TLabel').pack(side='left', padx=5)

        # Memory type selector
        mem_frame = ttk.Frame(status_bar)
        mem_frame.pack(side='right', padx=5)

        ttk.Label(mem_frame, text="Memory:").pack(side='left', padx=2)
        self.memory_type_var = tk.StringVar(value="flash")
        self.memory_combo = ttk.Combobox(mem_frame, textvariable=self.memory_type_var,
                                         values=["flash", "eeprom", "all"], width=8, state='readonly')
        self.memory_combo.pack(side='left', padx=2)

    def _init_protocols(self):
        """Initialize protocol objects"""
        try:
            self.protocols["AVR ISP"] = AVRISPProtocol(self.arduino_interface)
            self.protocols["SPI Memory"] = SPIMemoryProtocol(self.arduino_interface)
            self.protocols["I²C Memory"] = I2CMemoryProtocol(self.arduino_interface)
            # Alias for straight ASCII
            self.protocols["I2C Memory"] = self.protocols["I²C Memory"]

            self.current_protocol_obj = self.protocols["AVR ISP"]
        except Exception as e:
            self.log_console.log(f"Failed to init protocols: {e}", "ERROR")

    def on_protocol_changed(self, protocol_name: str):
        """Handle protocol selection change"""
        # Normalize name
        if protocol_name == "I²C Memory":
            protocol_name = "I²C Memory"
        self.current_protocol = protocol_name

        # Update memory type options based on protocol
        if protocol_name == "AVR ISP":
            self.memory_combo['values'] = ["flash", "eeprom", "all"]
            self.memory_type_var.set("flash")
        elif protocol_name == "SPI Memory":
            self.memory_combo['values'] = ["flash", "all"]
            self.memory_type_var.set("flash")
        else:  # I2C
            self.memory_combo['values'] = ["eeprom", "all"]
            self.memory_type_var.set("eeprom")

        # Switch protocol object
        if protocol_name in self.protocols:
            self.current_protocol_obj = self.protocols[protocol_name]
            self.log_console.log(f"Protocol selected: {protocol_name}", "INFO")
            self.device_panel.clear()
            self.device_info = None
        else:
            self.log_console.log(f"Protocol {protocol_name} not implemented", "WARNING")

    def on_connected(self, port, baud):
        """Called when serial connected - robust version with retries"""
        self.log_console.log(f"Connected to {port} at {baud} baud", "SUCCESS")
        self.log_console.log("Waiting for Arduino to boot...", "INFO")

        # Try to get firmware version with robust retry
        def get_version_thread():
            try:
                # Give extra time for Arduino to boot after our serial_manager's 2.5s
                time.sleep(1.0)

                # Try ping first with multiple attempts
                self.root.after(0, lambda: self.log_console.log("Testing communication (PING)...", "INFO"))
                ping_ok = False
                for attempt in range(5):
                    try:
                        if self.arduino_interface.ping():
                            ping_ok = True
                            break
                    except Exception as e:
                        self.root.after(0, lambda err=str(e): self.log_console.log(f"PING attempt {attempt+1} failed: {err}", "WARNING"))
                    time.sleep(0.5)

                if not ping_ok:
                    self.root.after(0, lambda: self.log_console.log(
                        "PING failed after 5 attempts. Possible causes:\n"
                        "1) Wrong firmware - upload arduino/universal_programmer.ino (not old ArduinoISP)\n"
                        "2) Wrong baud - use 115200\n"
                        "3) Arduino auto-reset - try 10uF cap between RESET and GND\n"
                        "4) Check wiring and COM port", "ERROR"))
                    self.root.after(0, lambda: self.operations_panel.set_enabled(True))
                    return

                self.root.after(0, lambda: self.log_console.log("Communication test: OK", "SUCCESS"))

                # Now get version
                try:
                    version = self.arduino_interface.get_version()
                    self.root.after(0, lambda: self.connection_panel.set_connected(True, version))
                    self.root.after(0, lambda: self.log_console.log(f"Firmware version: {version}", "INFO"))
                except Exception as e:
                    self.root.after(0, lambda: self.log_console.log(f"Version check failed (but PING OK): {e}", "WARNING"))
                    self.root.after(0, lambda: self.connection_panel.set_connected(True, "Unknown"))

                self.root.after(0, lambda: self.operations_panel.set_enabled(True))

            except Exception as e:
                self.root.after(0, lambda err=str(e): self.log_console.log(f"Connection test failed: {err}", "ERROR"))
                self.root.after(0, lambda: self.operations_panel.set_enabled(True))

        threading.Thread(target=get_version_thread, daemon=True).start()

    def on_disconnected(self):
        self.log_console.log("Disconnected", "INFO")
        self.operations_panel.set_enabled(False)
        self.progress_panel.set_idle()
        self.device_panel.clear()

    def on_cancel(self):
        """Cancel current operation"""
        self.cancel_event.set()
        if self.current_protocol_obj:
            self.current_protocol_obj.cancel()
        self.log_console.log("Cancellation requested...", "WARNING")
        self.progress_panel.set_progress(0, "Cancelling...", "")

    def on_operation(self, operation: str):
        """Handle operation button clicks"""
        if not self.serial_manager.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to Arduino first")
            return

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Busy", "Another operation is already running")
            return

        self.cancel_event.clear()

        # Map operations to methods
        op_map = {
            "detect": self.do_detect,
            "read": self.do_read,
            "read_flash": lambda: self.do_read_specific("flash"),
            "read_eeprom": lambda: self.do_read_specific("eeprom"),
            "read_all": self.do_read_all,
            "write": self.do_write,
            "verify": self.do_verify,
            "erase": self.do_erase,
            "load_bin": self.do_load_bin,
            "save_bin": self.do_save_bin,
            "compare": self.do_compare,
        }

        func = op_map.get(operation)
        if func:
            # Run in thread
            self.worker_thread = threading.Thread(target=self._run_operation, args=(func, operation), daemon=True)
            self.worker_thread.start()
        else:
            self.log_console.log(f"Unknown operation: {operation}", "ERROR")

    def _run_operation(self, func, op_name):
        """Run operation in worker thread with error handling - robust lambda capture"""
        try:
            # Capture op_name safely
            self.root.after(0, lambda n=op_name: self.progress_panel.set_busy(f"{n.upper()}..."))
            self.root.after(0, lambda n=op_name: self.status_var.set(f"Running {n}..."))
            func()
        except Exception as e:
            err_msg = str(e)
            op = op_name
            # Use default args to capture values safely for after() callbacks
            self.root.after(0, lambda m=err_msg, o=op: self.log_console.log(f"{o} failed: {m}", "ERROR"))
            self.root.after(0, lambda m=err_msg: self.progress_panel.set_error(f"Failed: {m[:150]}"))
            self.root.after(0, lambda m=err_msg: self.status_var.set(f"Error: {m[:100]}"))
        finally:
            pass

    def _progress_callback(self, percent: int, message: str):
        """Thread-safe progress update"""
        def update():
            self.progress_panel.set_progress(percent, message)
            self.status_var.set(message)
        self.root.after(0, update)

    def do_detect(self):
        """Detect target device"""
        try:
            self.log_console.log(f"Detecting device with protocol {self.current_protocol}...", "INFO")
            self._progress_callback(0, "Detecting...")

            if not self.current_protocol_obj:
                raise ProtocolError("No protocol selected")

            # For I2C, set address from panel
            if self.current_protocol == "I²C Memory" and hasattr(self.current_protocol_obj, 'set_device_address'):
                try:
                    addr = self.device_panel.get_i2c_address()
                    self.current_protocol_obj.set_device_address(addr)
                    self.log_console.log(f"Using I2C address 0x{addr:02X}", "INFO")
                except Exception:
                    pass

            self.current_protocol_obj.connect()
            info = self.current_protocol_obj.detect()

            self.device_info = info

            # Update UI
            def update_ui():
                self.device_panel.set_device_info(info)
                self.log_console.log(f"Detected: {info.get('name', 'Unknown')}", "SUCCESS")
                if 'signature' in info:
                    self.log_console.log(f"Signature: {info['signature']}", "INFO")
                if 'jedec_id' in info:
                    self.log_console.log(f"JEDEC ID: {info['jedec_id']}", "INFO")
                if 'flash_size' in info:
                    self.log_console.log(f"Flash size: {info['flash_size']} bytes", "INFO")
                if 'eeprom_size' in info:
                    self.log_console.log(f"EEPROM size: {info['eeprom_size']} bytes", "INFO")
                if 'found_str' in info:
                    self.log_console.log(f"I2C devices found: {info['found_str']}", "INFO")
                self.progress_panel.set_success("Detection successful")
                self.status_var.set(f"Detected: {info.get('name')}")

            self.root.after(0, update_ui)

        except DeviceNotDetectedError as e:
            self.root.after(0, lambda err=str(e): self.log_console.log(f"Detection failed: {err}", "ERROR"))
            self.root.after(0, lambda err=str(e): self.progress_panel.set_error(f"Not detected: {err}"))
            self.root.after(0, lambda: self.device_panel.clear())
        except Exception as e:
            err_str = str(e)
            # Provide helpful hint for protocol select timeout
            if "0x03" in err_str or "protocol 1" in err_str.lower() or "Timeout waiting for response header" in err_str:
                self.root.after(0, lambda: self.log_console.log(
                    f"Detection error: {err_str}\n"
                    "HINT: This is usually firmware mismatch. Please:\n"
                    "1) Open Arduino IDE\n"
                    "2) Open arduino/universal_programmer.ino from this project\n"
                    "3) Select your board (Uno/Nano/ESP32) and COM port\n"
                    "4) Upload the firmware\n"
                    "5) Reconnect in GUI (baud 115200)", "ERROR"))
            else:
                self.root.after(0, lambda err=err_str: self.log_console.log(f"Detection error: {err}", "ERROR"))
            self.root.after(0, lambda err=err_str: self.progress_panel.set_error(f"Error: {err[:100]}"))
        finally:
            try:
                if self.current_protocol_obj:
                    self.current_protocol_obj.close()
            except Exception:
                pass

    def do_read_specific(self, mem_type: str):
        """Read specific memory type"""
        self.memory_type_var.set(mem_type)
        self.do_read()

    def do_read(self):
        """Read memory from device"""
        try:
            mem_type = self.memory_type_var.get()
            self.log_console.log(f"Reading {mem_type}...", "INFO")
            self._progress_callback(0, f"Reading {mem_type}...")

            if not self.current_protocol_obj:
                raise ProtocolError("No protocol selected")

            # Ensure device detected
            if not self.device_info:
                self.log_console.log("No device info, attempting auto-detect...", "WARNING")
                self.current_protocol_obj.connect()
                try:
                    self.device_info = self.current_protocol_obj.detect()
                    self.root.after(0, lambda: self.device_panel.set_device_info(self.device_info))
                except Exception as e:
                    self.log_console.log(f"Auto-detect failed: {e}", "WARNING")
                    # Continue anyway if user specified size? For now require detect
                    raise ProtocolError("Please detect device first")

            # Determine length
            length = None
            if self.device_info:
                if mem_type == "flash":
                    length = self.device_info.get('flash_size')
                elif mem_type == "eeprom":
                    length = self.device_info.get('eeprom_size')
                elif mem_type == "all":
                    # For "all", we'll read flash and eeprom separately
                    pass

            if mem_type == "all":
                # Read all supported types
                for mt in ["flash", "eeprom"]:
                    if self.current_protocol_obj.supports_memory_type(mt):
                        # Check if device has this memory
                        has_mem = False
                        if mt == "flash" and self.device_info and self.device_info.get('flash_size'):
                            has_mem = True
                        elif mt == "eeprom" and self.device_info and self.device_info.get('eeprom_size'):
                            has_mem = True
                        elif mt == "flash":  # default for SPI
                            has_mem = True

                        if not has_mem:
                            continue

                        self._progress_callback(0, f"Reading {mt}...")
                        data = self.current_protocol_obj.read(
                            memory_type=mt,
                            address=0,
                            length=None,
                            progress_callback=self._progress_callback
                        )

                        # Store
                        self.dump_manager.set_dump(mt, data, {
                            'device': self.device_info.get('name', 'Unknown'),
                            'signature': self.device_info.get('signature') or self.device_info.get('jedec_id'),
                            'memory_type': mt
                        })

                        self.log_console.log(f"{mt} read: {len(data)} bytes, SHA256: {hashlib.sha256(data).hexdigest()[:16]}...", "SUCCESS")

                        # Update hex viewer with last read
                        self.root.after(0, lambda d=data, m=mt: self.hex_viewer.set_data(d))
            else:
                # Single memory type
                data = self.current_protocol_obj.read(
                    memory_type=mem_type,
                    address=0,
                    length=length,
                    progress_callback=self._progress_callback
                )

                # Critical: Store actual bytes received
                self.dump_manager.set_dump(mem_type, data, {
                    'device': self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown',
                    'signature': self.device_info.get('signature') or self.device_info.get('jedec_id') if self.device_info else '',
                    'memory_type': mem_type
                })

                # Display in hex viewer
                self.root.after(0, lambda: self.hex_viewer.set_data(data))

                # Calculate hashes
                sha256 = hashlib.sha256(data).hexdigest()
                self.log_console.log(f"{mem_type} read complete: {len(data)} bytes", "SUCCESS")
                self.log_console.log(f"SHA-256: {sha256}", "INFO")

                self.root.after(0, lambda: self.progress_panel.set_success(f"{mem_type} read: {len(data)} bytes"))
                self.root.after(0, lambda: self.status_var.set(f"Read {mem_type}: {len(data)} bytes, SHA256: {sha256[:16]}..."))

        except ProtocolError as e:
            if "cancelled" in str(e).lower():
                self.root.after(0, lambda: self.log_console.log("Read cancelled by user", "WARNING"))
                self.root.after(0, lambda: self.progress_panel.set_progress(0, "Cancelled"))
            else:
                self.root.after(0, lambda: self.log_console.log(f"Read failed: {e}", "ERROR"))
                self.root.after(0, lambda: self.progress_panel.set_error(f"Read failed: {e}"))
        except Exception as e:
            self.root.after(0, lambda: self.log_console.log(f"Read error: {e}", "ERROR"))
            self.root.after(0, lambda: self.progress_panel.set_error(f"Error: {e}"))
        finally:
            try:
                if self.current_protocol_obj:
                    self.current_protocol_obj.close()
            except Exception:
                pass

    def do_read_all(self):
        self.memory_type_var.set("all")
        self.do_read()

    def do_write(self):
        """Write memory to device"""
        try:
            mem_type = self.memory_type_var.get()
            if mem_type == "all":
                mem_type = "flash"  # default to flash for write

            # Check if we have data to write
            data = self.dump_manager.get_dump(mem_type)
            if data is None:
                # Try to prompt user to load file
                self.root.after(0, lambda: self.log_console.log(f"No {mem_type} data in buffer. Please load BIN file first.", "WARNING"))
                self.root.after(0, lambda: messagebox.showwarning("No Data", f"No {mem_type} data loaded. Use 'Load BIN' to load a file to program."))
                return

            # Validate size
            if self.device_info:
                max_size = self.device_info.get('flash_size') if mem_type == "flash" else self.device_info.get('eeprom_size', self.device_info.get('flash_size'))
                if max_size and len(data) > max_size:
                    self.root.after(0, lambda: messagebox.showerror("Size Error", f"Data size {len(data)} exceeds device size {max_size}. Will NOT truncate."))
                    return

            # Confirmation dialog
            def confirm_dialog():
                msg = f"Target: {self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown'}\n"
                msg += f"Memory: {mem_type}\n"
                msg += f"Size: {len(data)} bytes\n"
                msg += f"SHA-256: {hashlib.sha256(data).hexdigest()[:16]}...\n\n"
                msg += "Are you sure you want to PROGRAM the device?\nThis will overwrite target memory."

                return messagebox.askokcancel("Confirm PROGRAM", msg, icon='warning')

            confirmed = self.root.after(0, confirm_dialog)
            # Since after() doesn't return, we need to handle differently - use simple blocking for now
            # We'll do confirmation in main thread via queue? For simplicity, ask in worker thread using after wait
            # Actually tkinter messagebox must be called from main thread, but we can use a variable

            # Workaround: Use a thread-safe way
            result = {'confirmed': False}
            event = threading.Event()

            def ask():
                result['confirmed'] = messagebox.askokcancel("Confirm PROGRAM",
                    f"Target: {self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown'}\n"
                    f"Memory: {mem_type}\n"
                    f"Size: {len(data)} bytes\n"
                    f"SHA-256: {hashlib.sha256(data).hexdigest()}\n\n"
                    "Are you sure you want to PROGRAM the device?",
                    icon='warning')
                event.set()

            self.root.after(0, ask)
            event.wait(timeout=60)

            if not result['confirmed']:
                self.root.after(0, lambda: self.log_console.log("Write cancelled by user", "WARNING"))
                self.root.after(0, lambda: self.progress_panel.set_idle())
                return

            self.log_console.log(f"Writing {mem_type}: {len(data)} bytes...", "INFO")
            self._progress_callback(0, f"Writing {mem_type}...")

            if not self.current_protocol_obj:
                raise ProtocolError("No protocol selected")

            self.current_protocol_obj.connect()

            success = self.current_protocol_obj.write(
                data=data,
                memory_type=mem_type,
                address=0,
                progress_callback=self._progress_callback
            )

            if success:
                self.log_console.log(f"{mem_type} write successful", "SUCCESS")
                self.root.after(0, lambda: self.progress_panel.set_success(f"{mem_type} write OK"))

                # Auto-verify?
                self.log_console.log("Auto-verifying...", "INFO")
                self._progress_callback(0, "Verifying...")

                verified, mismatch = self.current_protocol_obj.verify(
                    data=data,
                    memory_type=mem_type,
                    address=0,
                    progress_callback=self._progress_callback
                )

                if verified:
                    self.log_console.log("✓ Verification successful", "SUCCESS")
                    self.root.after(0, lambda: self.progress_panel.set_success("Write + Verify OK"))
                else:
                    self.log_console.log(f"✗ Verification failed at 0x{mismatch['address']:06X}: expected {mismatch['expected']:02X}, read {mismatch['actual']:02X}", "ERROR")
                    self.root.after(0, lambda: self.progress_panel.set_error("Verify failed"))

        except ProtocolError as e:
            if "cancelled" in str(e).lower():
                self.root.after(0, lambda: self.log_console.log("Write cancelled", "WARNING"))
            else:
                self.root.after(0, lambda: self.log_console.log(f"Write failed: {e}", "ERROR"))
                self.root.after(0, lambda: self.progress_panel.set_error(f"Write failed: {e}"))
        except Exception as e:
            self.root.after(0, lambda: self.log_console.log(f"Write error: {e}", "ERROR"))
            self.root.after(0, lambda: self.progress_panel.set_error(f"Error: {e}"))
        finally:
            try:
                if self.current_protocol_obj:
                    self.current_protocol_obj.close()
            except Exception:
                pass

    def do_verify(self):
        """Verify device against buffer"""
        try:
            mem_type = self.memory_type_var.get()
            if mem_type == "all":
                mem_type = "flash"

            data = self.dump_manager.get_dump(mem_type)
            if data is None:
                self.root.after(0, lambda: messagebox.showwarning("No Data", f"No {mem_type} data loaded for verification"))
                return

            self.log_console.log(f"Verifying {mem_type}...", "INFO")
            self._progress_callback(0, f"Verifying {mem_type}...")

            if not self.current_protocol_obj:
                raise ProtocolError("No protocol selected")

            self.current_protocol_obj.connect()

            verified, mismatch = self.current_protocol_obj.verify(
                data=data,
                memory_type=mem_type,
                address=0,
                progress_callback=self._progress_callback
            )

            if verified:
                self.log_console.log("✓ Verification successful", "SUCCESS")
                self.root.after(0, lambda: self.progress_panel.set_success("Verification OK"))
                self.root.after(0, lambda: messagebox.showinfo("Verify", "✓ Verification successful - data matches!"))
            else:
                self.log_console.log(f"✗ Verification failed at 0x{mismatch['address']:06X}: expected {mismatch['expected']:02X}, read {mismatch['actual']:02X}, diff count {mismatch.get('diff_count', '?')}", "ERROR")
                self.root.after(0, lambda: self.progress_panel.set_error(f"Verify failed at 0x{mismatch['address']:06X}"))
                self.root.after(0, lambda: messagebox.showerror("Verify Failed",
                    f"✗ Verification failed\nAddress: 0x{mismatch['address']:06X}\nExpected: {mismatch['expected']:02X}\nRead: {mismatch['actual']:02X}\nDiff count: {mismatch.get('diff_count', '?')}"))

        except Exception as e:
            self.root.after(0, lambda: self.log_console.log(f"Verify error: {e}", "ERROR"))
            self.root.after(0, lambda: self.progress_panel.set_error(f"Error: {e}"))
        finally:
            try:
                if self.current_protocol_obj:
                    self.current_protocol_obj.close()
            except Exception:
                pass

    def do_erase(self):
        """Erase device"""
        try:
            mem_type = self.memory_type_var.get()

            # Confirmation
            result = {'confirmed': False}
            event = threading.Event()

            def ask():
                result['confirmed'] = messagebox.askokcancel("Confirm ERASE",
                    f"WARNING:\nThis will erase the target memory ({mem_type}).\n\n"
                    f"Target: {self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown'}\n\n"
                    "Are you sure?",
                    icon='warning')
                event.set()

            self.root.after(0, ask)
            event.wait(timeout=60)

            if not result['confirmed']:
                self.root.after(0, lambda: self.log_console.log("Erase cancelled", "WARNING"))
                return

            self.log_console.log(f"Erasing {mem_type}...", "WARNING")
            self._progress_callback(0, f"Erasing {mem_type}...")

            if not self.current_protocol_obj:
                raise ProtocolError("No protocol selected")

            self.current_protocol_obj.connect()
            success = self.current_protocol_obj.erase(
                memory_type=mem_type,
                progress_callback=self._progress_callback
            )

            if success:
                self.log_console.log("Erase successful", "SUCCESS")
                self.root.after(0, lambda: self.progress_panel.set_success("Erase OK"))

        except Exception as e:
            self.root.after(0, lambda: self.log_console.log(f"Erase failed: {e}", "ERROR"))
            self.root.after(0, lambda: self.progress_panel.set_error(f"Erase failed: {e}"))
        finally:
            try:
                if self.current_protocol_obj:
                    self.current_protocol_obj.close()
            except Exception:
                pass

    def do_load_bin(self):
        """Load BIN file"""
        try:
            # Use last directory
            initial_dir = self.bin_manager.last_directory

            filepath = filedialog.askopenfilename(
                initialdir=initial_dir,
                filetypes=[
                    ("Binary files", "*.bin"),
                    ("Hex files", "*.hex"),
                    ("All files", "*.*")
                ],
                title="Load BIN/HEX file"
            )

            if not filepath:
                return

            # Check if HEX or BIN
            if filepath.lower().endswith('.hex'):
                from memory.hex_parser import HexParser
                try:
                    data, info = HexParser.parse_intel_hex(filepath)
                    self.log_console.log(f"Loaded HEX file: {filepath} ({len(data)} bytes)", "INFO")
                except Exception as e:
                    self.log_console.log(f"Failed to parse HEX: {e}, trying as binary", "WARNING")
                    data, info = self.bin_manager.load_bin(filepath)
            else:
                data, info = self.bin_manager.load_bin(filepath)

            mem_type = self.memory_type_var.get()
            if mem_type == "all":
                mem_type = "flash"

            # Validate against device size if available
            if self.device_info:
                max_size = self.device_info.get('flash_size') if mem_type == "flash" else self.device_info.get('eeprom_size', self.device_info.get('flash_size'))
                if max_size and len(data) > max_size:
                    # Warn but allow loading
                    self.root.after(0, lambda: messagebox.showwarning("Size Warning",
                        f"File size {len(data)} exceeds target {mem_type} size {max_size}. File loaded but will fail to program unless truncated."))
                    self.log_console.log(f"WARNING: File {len(data)} bytes > target {max_size} bytes", "WARNING")
                else:
                    self.log_console.log(f"File size {len(data)} bytes OK for target {max_size} bytes", "INFO")

            # Store in dump manager
            self.dump_manager.set_dump(mem_type, data, {
                'filepath': filepath,
                'size': len(data),
                'sha256': info.get('sha256'),
                'memory_type': mem_type
            })

            # Update hex viewer
            self.root.after(0, lambda: self.hex_viewer.set_data(data))

            self.log_console.log(f"Loaded {mem_type}: {filepath} ({len(data)} bytes, SHA256: {info.get('sha256', '')[:16]}...)", "SUCCESS")
            self.root.after(0, lambda: self.progress_panel.set_success(f"Loaded {len(data)} bytes"))
            self.root.after(0, lambda: self.status_var.set(f"Loaded: {os.path.basename(filepath)} ({len(data)} bytes)"))

        except BinManagerError as e:
            self.log_console.log(f"Load failed: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Load Error", str(e)))
        except Exception as e:
            self.log_console.log(f"Load error: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Load Error", str(e)))

    def do_save_bin(self):
        """Save current dump to BIN file"""
        try:
            mem_type = self.memory_type_var.get()
            if mem_type == "all":
                # Save all dumps
                types = self.dump_manager.get_all_types()
                if not types:
                    self.root.after(0, lambda: messagebox.showwarning("No Data", "No dumps available to save"))
                    return

                # Ask for directory
                directory = filedialog.askdirectory(
                    initialdir=self.bin_manager.last_directory,
                    title="Select directory to save dumps"
                )
                if not directory:
                    return

                for mt in types:
                    data = self.dump_manager.get_dump(mt)
                    if data:
                        filepath = os.path.join(directory, f"{mt}.bin")
                        # Check if exists
                        if os.path.exists(filepath):
                            # Ask overwrite in main thread
                            result = {'overwrite': False}
                            event = threading.Event()

                            def ask():
                                result['overwrite'] = messagebox.askyesno("File Exists", f"{filepath} exists. Overwrite?")
                                event.set()

                            self.root.after(0, ask)
                            event.wait(timeout=30)
                            if not result['overwrite']:
                                continue

                        info = self.bin_manager.save_bin(filepath, data, {
                            'device': self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown',
                            'memory_type': mt
                        })
                        self.log_console.log(f"Saved {mt}: {filepath} ({info['size']} bytes, SHA256: {info['sha256'][:16]}...)", "SUCCESS")

                self.root.after(0, lambda: self.progress_panel.set_success("Save complete"))
                return

            # Single memory type
            data = self.dump_manager.get_dump(mem_type)
            if data is None:
                self.root.after(0, lambda: messagebox.showwarning("No Data", f"No {mem_type} data available. Read from device or load file first."))
                return

            initial_dir = self.bin_manager.last_directory
            default_name = f"{mem_type}.bin"

            filepath = filedialog.asksaveasfilename(
                initialdir=initial_dir,
                initialfile=default_name,
                defaultextension=".bin",
                filetypes=[
                    ("Binary files", "*.bin"),
                    ("All files", "*.*")
                ],
                title=f"Save {mem_type} dump"
            )

            if not filepath:
                return

            # Show info before saving
            sha256 = hashlib.sha256(data).hexdigest()
            self.log_console.log(f"Saving {mem_type}: {len(data)} bytes, SHA256: {sha256}", "INFO")

            info = self.bin_manager.save_bin(filepath, data, {
                'device': self.device_info.get('name', 'Unknown') if self.device_info else 'Unknown',
                'signature': self.device_info.get('signature') or self.device_info.get('jedec_id') if self.device_info else '',
                'memory_type': mem_type
            })

            self.log_console.log(f"Saved {mem_type} to {filepath} ({info['size']} bytes)", "SUCCESS")
            self.log_console.log(f"File: {filepath}", "INFO")
            self.log_console.log(f"Size: {info['size']} bytes", "INFO")
            self.log_console.log(f"SHA-256: {info['sha256']}", "INFO")

            self.root.after(0, lambda: self.progress_panel.set_success(f"Saved {mem_type}: {info['size']} bytes"))
            self.root.after(0, lambda: self.status_var.set(f"Saved: {filepath}"))

        except BinManagerError as e:
            self.log_console.log(f"Save failed: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Save Error", str(e)))
        except Exception as e:
            self.log_console.log(f"Save error: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Save Error", str(e)))

    def do_compare(self):
        """Compare two BIN files"""
        try:
            # Ask for two files
            file_a = filedialog.askopenfilename(
                initialdir=self.bin_manager.last_directory,
                filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
                title="Select first BIN file (File A)"
            )
            if not file_a:
                return

            file_b = filedialog.askopenfilename(
                initialdir=self.bin_manager.last_directory,
                filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
                title="Select second BIN file (File B)"
            )
            if not file_b:
                return

            data_a, info_a = self.bin_manager.load_bin(file_a)
            data_b, info_b = self.bin_manager.load_bin(file_b)

            result = self.bin_manager.compare_bins(data_a, data_b)

            # Log results
            if result['same']:
                self.log_console.log(f"Compare: Files are identical ({result['len_a']} bytes)", "SUCCESS")
                self.root.after(0, lambda: messagebox.showinfo("Compare", f"Files are IDENTICAL\n\nSize: {result['len_a']} bytes"))
            else:
                self.log_console.log(f"Compare: Files differ - {result['diff_count']} differing bytes", "WARNING")
                self.log_console.log(f"  File A: {file_a} ({result['len_a']} bytes)", "INFO")
                self.log_console.log(f"  File B: {file_b} ({result['len_b']} bytes)", "INFO")
                if result['first_mismatch'] is not None:
                    self.log_console.log(f"  First mismatch at 0x{result['first_mismatch']:06X}", "INFO")
                if result['last_mismatch'] is not None:
                    self.log_console.log(f"  Last mismatch at 0x{result['last_mismatch']:06X}", "INFO")

                # Show detailed dialog
                detail = f"Files differ\n\n"
                detail += f"File A: {os.path.basename(file_a)} ({result['len_a']} bytes)\n"
                detail += f"File B: {os.path.basename(file_b)} ({result['len_b']} bytes)\n\n"
                detail += f"Difference count: {result['diff_count']}\n"
                if result['first_mismatch'] is not None:
                    detail += f"First mismatch: 0x{result['first_mismatch']:06X}\n"
                if result['last_mismatch'] is not None:
                    detail += f"Last mismatch: 0x{result['last_mismatch']:06X}\n\n"

                detail += "First differences:\n"
                detail += f"{'Address':<10} {'File A':<8} {'File B':<8}\n"
                detail += "-"*30 + "\n"
                for addr, b_a, b_b in result['differences'][:20]:
                    detail += f"0x{addr:06X}   {b_a:02X}       {b_b:02X}\n"

                self.root.after(0, lambda: messagebox.showwarning("Compare - Differences Found", detail))

                # Highlight in hex viewer if current data matches one file?
                # For now, show File A in viewer and highlight diffs
                self.root.after(0, lambda: self.hex_viewer.set_data(data_a))
                self.root.after(0, lambda: self.hex_viewer.highlight_differences(result['differences']))

        except Exception as e:
            self.log_console.log(f"Compare failed: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Compare Error", str(e)))

    def on_close(self):
        """Handle window close"""
        if self.worker_thread and self.worker_thread.is_alive():
            if not messagebox.askyesno("Busy", "Operation in progress. Are you sure you want to exit?"):
                return
            self.on_cancel()
            time.sleep(0.5)

        try:
            self.serial_manager.disconnect()
        except Exception:
            pass

        self.root.destroy()
