# Universal MCU / Memory Programmer

Professional Windows-based Universal Programmer with Tkinter GUI + Arduino Firmware.

Supports:
- **AVR ISP** (ATmega328P, ATmega168, ATmega8, ATtiny85, ATtiny84, etc)
- **SPI Memory** (W25Q80, W25Q16, W25Q32, W25Q64, W25Q128, etc)
- **I²C Memory** (24C01 to 24C1024)

Modular architecture for future protocols (1-Wire, custom serial).

---

## Features

- **Professional GUI** - Modern Tkinter/ttk interface, resizable, responsive, no freeze during operations
- **Robust Communication** - Framed binary protocol with CRC16, sequence numbers, retries, chunked transfer
- **STK500v1 Compatible** - Preserves original ArduinoISP functionality, works with avrdude
- **Device Database** - JSON-based, easy to add new devices without code changes
- **Critical Workflow**: Read → Store Actual Bytes → Display Hex → Save BIN (real bytes, not simulated)
- **BIN Management** - Save/load with SHA-256, size validation, no silent truncation
- **Hex Viewer** - Address, hex, ASCII, search, goto, copy as hex/C array, diff highlighting
- **Verify & Compare** - Byte-by-byte verification with detailed mismatch info, BIN comparison
- **Safety** - Confirmation dialogs for write/erase, error handling with user-friendly messages
- **Logging** - Professional log console with levels (INFO, SUCCESS, WARNING, ERROR)
- **Cross-Platform** - Primary Windows 10/11, also works on Linux/macOS

---

## Project Structure

```
UniversalProgrammer/
├── app.py                      # Entry point
├── requirements.txt
├── README.md
├── gui/
│   ├── main_window.py          # Main application window
│   ├── hex_viewer.py           # Professional hex viewer
│   ├── device_panel.py         # Device info & protocol selection
│   ├── progress_panel.py       # Progress bar with cancel
│   └── styles.py               # Theming
├── protocols/
│   ├── protocol_base.py        # Abstract base class
│   ├── avr_isp.py              # AVR ISP implementation
│   ├── spi_memory.py           # SPI memory implementation
│   └── i2c_memory.py           # I2C memory implementation
├── hardware/
│   ├── serial_manager.py       # COM port detection & serial I/O
│   └── arduino_interface.py    # Framed protocol, high-level commands
├── memory/
│   ├── dump_manager.py         # In-memory dump storage
│   ├── bin_manager.py          # BIN save/load/compare, hashes
│   └── hex_parser.py           # Intel HEX support
├── devices/
│   ├── avr_devices.json        # AVR device database
│   ├── spi_devices.json        # SPI flash database
│   └── i2c_devices.json        # I2C EEPROM database
├── arduino/
│   └── universal_programmer.ino # Firmware for Arduino/ESP32
└── docs/
    ├── wiring.md               # Wiring diagrams
    ├── protocol.md             # Communication protocol spec
    └── test_plan.md            # Comprehensive test plan
```

---

## Installation

### Requirements

- Python 3.8+
- Arduino IDE (for firmware upload)
- Arduino Uno/Nano/Mega or ESP32 board
- pyserial

### Windows Setup

1. Clone repository:
   ```cmd
   git clone https://github.com/Myhobby2026/Universal-_SPI_Programmer.git
   cd Universal-_SPI_Programmer
   ```

2. Install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```

3. Upload firmware:
   - Open `arduino/universal_programmer.ino` in Arduino IDE
   - Select your board (Uno, Nano, ESP32, etc)
   - Select COM port
   - Click Upload

4. Run GUI:
   ```cmd
   python app.py
   ```

### Linux/macOS

Same steps, but COM port will be `/dev/ttyUSB0` or `/dev/ttyACM0` etc.

---

## Wiring

See `docs/wiring.md` for detailed diagrams.

### Quick Reference

**AVR ISP (ATmega328P)**:
```
Arduino Pin 10 -> Target RESET
Arduino Pin 11 -> Target MOSI
Arduino Pin 12 -> Target MISO
Arduino Pin 13 -> Target SCK
5V -> VCC, GND -> GND
```

**SPI Flash (W25Q32)** - Use 3.3V!
```
Arduino Pin 9  -> Flash /CS (Pin 1)
Arduino Pin 12 -> Flash DO (Pin 2)
Arduino Pin 11 -> Flash DI (Pin 5)
Arduino Pin 13 -> Flash CLK (Pin 6)
3.3V -> VCC (Pin 8) + /WP (Pin 3) + /HOLD (Pin 7)
GND -> GND (Pin 4)
```

**I2C EEPROM (24C256)**:
```
Arduino A4 (SDA) -> EEPROM SDA (Pin 5) + 4.7k pull-up to VCC
Arduino A5 (SCL) -> EEPROM SCL (Pin 6) + 4.7k pull-up to VCC
VCC -> Pin 8, GND -> Pin 4, A0/A1/A2/WP -> GND
```

---

## Usage

### Basic Workflow

1. **Connect**:
   - Select COM port
   - Baud 115200
   - Click CONNECT
   - Check FW version displayed

2. **Detect**:
   - Select Protocol (AVR ISP / SPI Memory / I²C Memory)
   - Click Detect
   - Check signature/JEDEC ID and device name

3. **Read**:
   - Select Memory type (flash/eeprom)
   - Click READ FLASH / READ EEPROM / READ ALL
   - Progress bar updates
   - Hex viewer shows actual bytes
   - Log shows SHA-256

4. **Save**:
   - Click Save BIN
   - Choose location
   - File contains actual bytes read

5. **Load & Write**:
   - Click Load BIN, select file
   - Check size validation
   - Click WRITE
   - Confirm dialog shows target, size, SHA-256
   - Click PROGRAM
   - Auto-verify

6. **Verify**:
   - Click VERIFY to compare device vs loaded BIN
   - Shows success or detailed mismatch (address, expected, actual)

7. **Compare**:
   - Click Compare BIN
   - Select two files
   - Shows diff count, first/last mismatch, list of differences

### Safety

- Write/Erase require confirmation
- No silent truncation - if BIN larger than target, error
- Overwrite protection for existing files

---

## Communication Protocol

See `docs/protocol.md` for full spec.

**Frame**: `AA 55 CMD SEQ LEN_L LEN_H PAYLOAD CRC_L CRC_H 55 AA`

- CRC16-CCITT over CMD+SEQ+LEN+PAYLOAD
- Response: CMD|0x80, first payload byte = status
- Chunked transfer (128-256 bytes) for progress and cancellation
- Retries (3x) on timeout

Also supports STK500v1 for avrdude compatibility.

---

## Device Database

Add new devices by editing JSON files, no code change needed.

**AVR** (`avr_devices.json`):
```json
{
  "name": "ATmega328P",
  "signature": "1E 95 0F",
  "flash_size": 32768,
  "eeprom_size": 1024,
  "page_size": 128
}
```

**SPI** (`spi_devices.json`):
```json
{
  "name": "W25Q32",
  "jedec_id": "EF 40 16",
  "capacity": 4194304,
  "page_size": 256
}
```

**I2C** (`i2c_devices.json`):
```json
{
  "name": "24C256",
  "capacity": 32768,
  "page_size": 64,
  "addr_width": 2
}
```

---

## Testing

See `docs/test_plan.md` for comprehensive test plan covering:

- Connection, detection, read, save, load, write, verify, erase
- SPI, I2C, AVR
- Invalid BIN, disconnect during operation, timeout, cancel
- Compare, hex viewer, logging
- Data integrity round-trip

**Critical Test**: Read → Save → Load → Write → Read → Compare must be identical.

---

## Firmware

`arduino/universal_programmer.ino` is based on ArduinoISP but extended:

- Preserves STK500v1 (avrdude compatible)
- Adds framed binary protocol
- Supports AVR ISP, SPI, I2C
- Works on Arduino Uno/Nano/Mega and ESP32
- Professional error handling, status LEDs

Upload via Arduino IDE.

---

## Extending for New Protocols

1. Add command definitions in firmware (`CMD_...`) and `arduino_interface.py`
2. Implement low-level functions in firmware
3. Create new protocol class in `protocols/` inheriting from `ProtocolBase`
4. Implement `connect()`, `detect()`, `read()`, `write()`, `verify()`, `erase()`
5. Add device database JSON
6. Add protocol to GUI combo box

Example for 1-Wire:
```python
# protocols/onewire.py
class OneWireProtocol(ProtocolBase):
    def get_name(self): return "1-Wire"
    def detect(self): ...
    def read(self): ...
```

---

## Troubleshooting

**No COM ports**:
- Install Arduino drivers
- Check USB cable (data, not charge-only)
- Try different USB port

**Connect fails**:
- Check baud 115200
- Close Arduino IDE Serial Monitor (it locks port)
- Check port not used by other app

**Detect fails - No target**:
- Check wiring (see wiring.md)
- Check target power and GND common
- For AVR: Check target has clock source (crystal or internal)
- For SPI: Check 3.3V, CS pin, wiring
- For I2C: Check pull-ups (4.7k), address, wiring

**Read returns 00 00 00 or FF FF FF**:
- Target not responding, check wiring
- For AVR, try slower SPI clock (firmware default is slow, safe for ATtiny85)
- Check target fuses

**Write fails**:
- Check BIN size vs target size
- For SPI flash: Need erase before write (chip does not auto-erase)
- For I2C: Check WP pin grounded

**GUI freeze**:
- Should not happen (threaded), but if it does, check for large file (>10MB) in hex viewer

---

## License

BSD compatible with ArduinoISP.

Original ArduinoISP: Copyright (c) 2008-2011 Randall Bohn, BSD license.

Universal Programmer extensions: Same BSD license.

---

## Credits

- Based on ArduinoISP by Randall Bohn
- Inspired by professional programmer utilities
- Built for Windows 10/11 with Python/Tkinter

---

## Future Plans

- Phase 1: Arduino comm + GUI (DONE)
- Phase 2: AVR ISP detect/read/write/verify (DONE)
- Phase 3: AVR EEPROM (DONE)
- Phase 4: SPI memory (DONE)
- Phase 5: I2C memory (DONE)
- Phase 6: Hex viewer improvements (DONE)
- Phase 7: BIN comparison (DONE)
- Phase 8: Device database (DONE)
- Phase 9: Packaging for Windows (pyinstaller)

---

## Support

Open issue on GitHub with:
- OS, Python version
- Arduino board type
- Target device
- Log output
- Wiring photo if relevant
