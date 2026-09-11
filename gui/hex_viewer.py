"""
Professional Hex Viewer - Displays binary data with address, hex, and ASCII
Features: scroll, search, goto address, copy, highlight differences
"""

import tkinter as tk
from tkinter import ttk, messagebox
import re
import threading
from typing import Optional, List, Tuple


class HexViewer(ttk.Frame):
    """Professional hex viewer widget"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.data: bytes = b''
        self.bytes_per_row: int = 16
        self.start_address: int = 0
        self.highlight_ranges: List[Tuple[int, int, str]] = []  # (start, end, tag)
        self.search_results: List[int] = []
        self.current_search_index: int = -1

        self._build_ui()
        self._setup_tags()

    def _build_ui(self):
        # Top toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', padx=5, pady=(5, 2))

        ttk.Label(toolbar, text="Address:").pack(side='left', padx=(0, 2))
        self.goto_entry = ttk.Entry(toolbar, width=10)
        self.goto_entry.pack(side='left', padx=2)
        self.goto_entry.bind('<Return>', lambda e: self.goto_address_str())
        ttk.Button(toolbar, text="Go", width=4, command=self.goto_address_str).pack(side='left', padx=2)

        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=8, pady=2)

        ttk.Label(toolbar, text="Search (hex):").pack(side='left', padx=(0, 2))
        self.search_entry = ttk.Entry(toolbar, width=20)
        self.search_entry.pack(side='left', padx=2)
        self.search_entry.bind('<Return>', lambda e: self.search_hex())
        ttk.Button(toolbar, text="Find", width=6, command=self.search_hex).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Next", width=6, command=self.search_next).pack(side='left', padx=2)

        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=8, pady=2)

        self.info_label = ttk.Label(toolbar, text="No data", style='Muted.TLabel')
        self.info_label.pack(side='left', padx=10)

        # Text widget with scrollbars
        text_frame = ttk.Frame(self)
        text_frame.pack(fill='both', expand=True, padx=5, pady=5)

        self.text = tk.Text(
            text_frame,
            wrap='none',
            font=('Consolas', 10),
            bg='#1e1e1e' if self._is_dark() else '#ffffff',
            fg='#d4d4d4' if self._is_dark() else '#000000',
            insertbackground='#ffffff',
            selectbackground='#264f78',
            selectforeground='#ffffff',
            padx=8,
            pady=4,
            state='disabled',
            tabs=(80,)
        )

        v_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=self.text.yview)
        h_scroll = ttk.Scrollbar(text_frame, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.text.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')

        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        # Header line
        self.header_text = f"{'Address':<8}  {' '.join(f'{i:02X}' for i in range(16))}  {'ASCII'}"
        # Context menu
        self.context_menu = tk.Menu(self.text, tearoff=0)
        self.context_menu.add_command(label="Copy Selected Bytes", command=self.copy_selected)
        self.context_menu.add_command(label="Copy as Hex String", command=self.copy_as_hex)
        self.context_menu.add_command(label="Copy as C Array", command=self.copy_as_c_array)
        self.text.bind('<Button-3>', self._show_context_menu)

        # Status bar for viewer
        status_frame = ttk.Frame(self)
        status_frame.pack(fill='x', padx=5, pady=(0, 5))
        self.status_label = ttk.Label(status_frame, text="Ready", style='Muted.TLabel')
        self.status_label.pack(side='left')

    def _is_dark(self):
        # Simple heuristic - check if parent bg is dark
        try:
            return False  # default light for compatibility
        except Exception:
            return False

    def _setup_tags(self):
        self.text.tag_configure('address', foreground='#858585')
        self.text.tag_configure('hex', foreground='#d4d4d4' if self._is_dark() else '#000000')
        self.text.tag_configure('ascii', foreground='#ce9178')
        self.text.tag_configure('highlight', background='#ffcc00', foreground='#000000')
        self.text.tag_configure('search', background='#623315', foreground='#ffffff')
        self.text.tag_configure('diff', background='#ff0000', foreground='#ffffff')
        self.text.tag_configure('header', foreground='#569cd6', font=('Consolas', 10, 'bold'))

    def set_data(self, data: bytes, start_address: int = 0):
        """Set binary data to display"""
        self.data = data
        self.start_address = start_address
        self.highlight_ranges.clear()
        self.search_results.clear()
        self.current_search_index = -1

        # Update info
        if data:
            self.info_label.config(text=f"Size: {len(data)} bytes (0x{len(data):X}) | Start: 0x{start_address:08X}")
        else:
            self.info_label.config(text="No data")

        # Render in thread to avoid freezing for large files
        self._render_data()

    def _render_data(self, max_lines: int = None):
        """Render data to text widget"""
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')

        if not self.data:
            self.text.insert('end', "No data loaded. Use READ to capture from device or LOAD BIN to open a file.\n")
            self.text.configure(state='disabled')
            return

        # Header
        header = f"{'Address':<10} {' '.join(f'{i:02X}' for i in range(self.bytes_per_row))}   {'ASCII':<{self.bytes_per_row}}\n"
        separator = f"{'-'*10} {'-'* (self.bytes_per_row*3 -1)}   {'-'*self.bytes_per_row}\n"
        self.text.insert('end', header, 'header')
        self.text.insert('end', separator, 'address')

        # For very large files, limit rendering or paginate
        # We'll render all but in chunks to keep UI responsive
        data_len = len(self.data)
        lines_to_render = data_len // self.bytes_per_row + (1 if data_len % self.bytes_per_row else 0)

        # If file is extremely large (>1MB), warn and maybe limit
        if data_len > 2*1024*1024:
            self.text.insert('end', f"\n[File too large for full hex view: {data_len} bytes. Showing first 1MB]\n", 'diff')
            data_len = 1*1024*1024
            lines_to_render = data_len // self.bytes_per_row

        for row in range(lines_to_render):
            offset = row * self.bytes_per_row
            if offset >= len(self.data):
                break
            chunk = self.data[offset:offset+self.bytes_per_row]

            addr_str = f"{self.start_address + offset:08X}  "
            hex_str = ' '.join(f"{b:02X}" for b in chunk)
            # Pad hex string
            if len(chunk) < self.bytes_per_row:
                hex_str += '   ' * (self.bytes_per_row - len(chunk))

            ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)

            line = f"{addr_str} {hex_str}   {ascii_str}\n"

            # Insert with tags - we need to handle per-part coloring
            # For simplicity, insert whole line then tag parts
            line_start = self.text.index('end-1c')
            self.text.insert('end', line)
            line_end = self.text.index('end-1c')

            # Tag address
            self.text.tag_add('address', f"{line_start}", f"{line_start}+10c")
            # Tag ascii part
            ascii_start_col = 10 + 2 + self.bytes_per_row*3 + 2
            # Roughly calculate ascii start
            # Address(10) + 2 spaces + hex (3*16=48) + 3 spaces = 63
            self.text.tag_add('ascii', f"{line_start}+{10+2+self.bytes_per_row*3+3}c", f"{line_end}")

        self.text.configure(state='disabled')
        self.status_label.config(text=f"Displayed {lines_to_render} lines, {len(self.data)} bytes")

    def clear(self):
        self.set_data(b'')

    def goto_address_str(self):
        """Goto address from entry field"""
        addr_str = self.goto_entry.get().strip()
        if not addr_str:
            return
        try:
            # Support hex with 0x prefix or plain hex/dec
            if addr_str.lower().startswith('0x'):
                addr = int(addr_str, 16)
            else:
                # Try hex first, then decimal
                try:
                    addr = int(addr_str, 16)
                except ValueError:
                    addr = int(addr_str)

            self.goto_address(addr)
        except ValueError:
            messagebox.showwarning("Invalid Address", f"Cannot parse address: {addr_str}")

    def goto_address(self, address: int):
        """Scroll to specific address"""
        if not self.data:
            return

        # Calculate row
        offset = address - self.start_address
        if offset < 0 or offset >= len(self.data):
            messagebox.showwarning("Out of Range", f"Address 0x{address:X} out of range (0x{self.start_address:X} - 0x{self.start_address+len(self.data):X})")
            return

        row = offset // self.bytes_per_row
        # Text widget lines: 2 header lines + row
        line_num = row + 3  # 1-indexed + header
        self.text.see(f"{line_num}.0")

        # Highlight the row briefly
        self.text.configure(state='normal')
        self.text.tag_add('highlight', f"{line_num}.0", f"{line_num}.end")
        self.text.configure(state='disabled')
        # Remove highlight after 2 seconds
        self.after(2000, lambda: self.text.tag_remove('highlight', '1.0', 'end'))

        self.status_label.config(text=f"Address 0x{address:08X} (offset 0x{offset:X})")

    def search_hex(self):
        """Search for hex byte sequence"""
        pattern_str = self.search_entry.get().strip()
        if not pattern_str or not self.data:
            return

        try:
            # Parse hex string like "FF 00 7A" or "FF007A" or "FF,00,7A"
            cleaned = re.sub(r'[^0-9a-fA-F]', ' ', pattern_str)
            bytes_list = []
            for part in cleaned.split():
                if len(part) == 0:
                    continue
                # If part length >2, split into pairs
                if len(part) > 2:
                    # e.g., "FF007A" -> ["FF","00","7A"]
                    for i in range(0, len(part), 2):
                        if i+1 < len(part):
                            bytes_list.append(int(part[i:i+2], 16))
                else:
                    bytes_list.append(int(part, 16))

            if not bytes_list:
                messagebox.showwarning("Invalid Search", "Enter hex bytes like: FF 00 7A or FF007A")
                return

            pattern = bytes(bytes_list)
            self.search_results = []
            start = 0
            while True:
                idx = self.data.find(pattern, start)
                if idx == -1:
                    break
                self.search_results.append(idx)
                start = idx + 1
                if len(self.search_results) > 1000:
                    break  # limit

            if not self.search_results:
                self.status_label.config(text=f"Pattern {pattern.hex().upper()} not found")
                messagebox.showinfo("Search", f"Pattern {pattern.hex().upper()} not found")
                return

            self.current_search_index = 0
            self._highlight_search_results()
            self.goto_address(self.start_address + self.search_results[0])
            self.status_label.config(text=f"Found {len(self.search_results)} occurrences, showing 1/{len(self.search_results)}")

        except ValueError as e:
            messagebox.showwarning("Invalid Hex", f"Invalid hex pattern: {e}")

    def _highlight_search_results(self):
        """Highlight all search results"""
        self.text.configure(state='normal')
        self.text.tag_remove('search', '1.0', 'end')

        for offset in self.search_results:
            row = offset // self.bytes_per_row
            col = offset % self.bytes_per_row
            line_num = row + 3
            # Calculate column position of hex byte
            # Address(10) + 2 spaces + col*3
            start_col = 10 + 2 + col*3
            end_col = start_col + 2
            try:
                self.text.tag_add('search', f"{line_num}.{start_col}", f"{line_num}.{end_col}")
            except Exception:
                pass

        self.text.configure(state='disabled')

    def search_next(self):
        """Go to next search result"""
        if not self.search_results:
            self.search_hex()
            return

        self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
        addr = self.start_address + self.search_results[self.current_search_index]
        self.goto_address(addr)
        self.status_label.config(text=f"Found {len(self.search_results)} occurrences, showing {self.current_search_index+1}/{len(self.search_results)}")

    def highlight_differences(self, diff_list: list):
        """
        Highlight differences from comparison
        diff_list: list of (address, byte_a, byte_b)
        """
        self.text.configure(state='normal')
        self.text.tag_remove('diff', '1.0', 'end')

        for addr, _, _ in diff_list[:500]:  # limit to 500 for performance
            offset = addr - self.start_address
            if offset < 0 or offset >= len(self.data):
                continue
            row = offset // self.bytes_per_row
            col = offset % self.bytes_per_row
            line_num = row + 3
            start_col = 10 + 2 + col*3
            end_col = start_col + 2
            try:
                self.text.tag_add('diff', f"{line_num}.{start_col}", f"{line_num}.{end_col}")
            except Exception:
                pass

        self.text.configure(state='disabled')

    def copy_selected(self):
        """Copy selected bytes - placeholder, copies selected text"""
        try:
            selected = self.text.selection_get()
            self.clipboard_clear()
            self.clipboard_append(selected)
        except Exception:
            pass

    def copy_as_hex(self):
        """Copy data as hex string"""
        if not self.data:
            return
        try:
            # If there's a selection, try to get offset range
            # For simplicity, copy all as hex
            hex_str = self.data.hex().upper()
            # Format as spaced
            spaced = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            self.clipboard_clear()
            self.clipboard_append(spaced)
            self.status_label.config(text="Copied as hex string")
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def copy_as_c_array(self):
        """Copy as C array"""
        if not self.data:
            return
        try:
            lines = []
            lines.append(f"const unsigned char data[{len(self.data)}] = {{")
            for i in range(0, len(self.data), 16):
                chunk = self.data[i:i+16]
                hex_bytes = ', '.join(f"0x{b:02X}" for b in chunk)
                lines.append(f"    {hex_bytes},")
            lines.append("};")
            c_str = '\n'.join(lines)
            self.clipboard_clear()
            self.clipboard_append(c_str)
            self.status_label.config(text="Copied as C array")
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def _show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
