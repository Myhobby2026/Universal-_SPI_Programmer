# Architecture - Universal Programmer

## Overview

Clean modular architecture separating GUI, communication, protocol logic, and file handling.

## Layers

```
┌─────────────────────────────────────┐
│           GUI Layer                 │
│  main_window, hex_viewer,           │
│  device_panel, progress_panel       │
├─────────────────────────────────────┤
│        Protocol Layer               │
│  avr_isp, spi_memory, i2c_memory    │
│  protocol_base (interface)          │
├─────────────────────────────────────┤
│        Hardware Layer               │
│  serial_manager, arduino_interface  │
│  (framed protocol, CRC, retries)    │
├─────────────────────────────────────┤
│        Memory Layer                 │
│  dump_manager, bin_manager,         │
│  hex_parser                         │
├─────────────────────────────────────┤
│        Device Database              │
│  JSON files, no code change needed  │
├─────────────────────────────────────┤
│        Firmware Layer               │
│  universal_programmer.ino           │
│  (AVR ISP + SPI + I2C + STK500)     │
└─────────────────────────────────────┘
```

## Data Flow - Critical Requirement

```
Arduino Hardware
      ↓ (SPI/I2C)
Target Device (AVR/SPI Flash/I2C EEPROM)
      ↓ (actual bytes via framed protocol with CRC)
Arduino Firmware (universal_programmer.ino)
      ↓ (binary packet AA 55 CMD SEQ LEN PAYLOAD CRC 55 AA)
Serial Port (pyserial)
      ↓
Arduino Interface (arduino_interface.py)
  - Validates CRC
  - Checks sequence
  - Retries on timeout
  - Returns actual bytes
      ↓
Protocol (avr_isp.py etc)
  - Chunks data (128 bytes)
  - Calls progress_callback
  - Checks cancel flag
  - Returns bytes
      ↓
Dump Manager (dump_manager.py)
  - Stores actual bytes in memory
  - Calculates SHA-256
      ↓
Hex Viewer (hex_viewer.py)
  - Displays actual bytes with address, hex, ASCII
      ↓
Bin Manager (bin_manager.py)
  - Saves actual bytes to .bin file
  - No placeholder, no simulation

Reverse for WRITE:
BIN file -> Load -> Validate size -> Dump Manager -> Protocol -> Arduino Interface -> Firmware -> Target
```

## Threading Model

- **Main Thread**: Tkinter GUI event loop
- **Worker Thread**: Long operations (read, write, verify, erase, detect)
  - Created per operation
  - Uses `threading.Thread(daemon=True)`
  - Communicates via `root.after(0, callback)` for thread-safe UI updates
  - Checks `cancel_event` between chunks
  - No GUI freeze

## Protocol Interface

All protocols implement `ProtocolBase`:

```python
connect() -> bool
detect() -> dict
read(memory_type, address, length, progress_callback) -> bytes
write(data, memory_type, address, progress_callback) -> bool
verify(data, memory_type, address, progress_callback) -> (bool, mismatch_info)
erase(memory_type, progress_callback) -> bool
close()
```

This allows easy addition of new protocols:

1. Create `protocols/new_protocol.py`
2. Inherit from `ProtocolBase`
3. Implement methods
4. Add to `gui/main_window.py` protocol combo
5. Add device database JSON

## Communication Protocol

See `protocol.md` for full spec.

Key features:
- Header 0xAA 0x55, Footer 0x55 0xAA for sync
- CMD, SEQ, LEN, PAYLOAD, CRC16, FOOTER
- CRC16-CCITT validation
- Sequence numbers for matching
- Timeout 2-3s with 3 retries
- Chunked transfer (128-256 bytes)

## Error Handling

- No Python traceback to user
- User-friendly messages: "Target not detected - check wiring"
- Graceful handling of disconnect, timeout, invalid responses
- Log console with levels

## Safety

- Confirmation dialogs for WRITE and ERASE
- Size validation before write (no silent truncation)
- Overwrite protection for files
- Cancel support with safe exit from programming mode

## Device Database

JSON files in `devices/`:

- `avr_devices.json`: signature -> device info
- `spi_devices.json`: JEDEC ID -> device info
- `i2c_devices.json`: name -> device info

Lookup by signature/JEDEC, fallback to generic with size guessing.

No code change needed to add devices.

## GUI Design

- Tkinter/ttk with clam theme
- Professional spacing, typography
- Resizable with PanedWindow
- Notebook tabs for Hex View and Log
- Connection, Device, Operations, Progress panels
- Status bar

## Firmware Design

- Based on ArduinoISP (preserves STK500v1)
- Dual-mode: Framed protocol (0xAA 0x55) and STK500 (ASCII)
- Peek first byte to decide
- Supports Arduino Uno/Nano/Mega and ESP32 (conditional pins)
- Low-level functions for AVR, SPI, I2C
- LEDs for status

## Testing Strategy

See `test_plan.md`.

Critical test: Round-trip integrity (Read -> Save -> Write -> Read -> Compare identical)

## Future Extensions

- 1-Wire: Add CMD 0x50-0x5F, implement in firmware, create `protocols/onewire.py`
- Custom serial: Use 0x60-0x7F range
- The modular architecture makes this straightforward
