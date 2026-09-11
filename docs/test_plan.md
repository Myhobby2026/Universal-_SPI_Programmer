# Test Plan - Universal Programmer

## Overview

This test plan covers all critical functionality from connection to programming.

---

## 1. Arduino Connection Tests

### 1.1 Port Detection

- **Steps**:
  1. Open GUI
  2. Click refresh button (↻) in Connection panel
  3. Check that available COM ports are listed
- **Expected**: List shows COM ports (e.g., COM5) with descriptions
- **Pass Criteria**: Ports detected, no crash if no ports

### 1.2 Connect / Disconnect

- **Steps**:
  1. Select valid COM port (Arduino with firmware)
  2. Select baud 115200
  3. Click CONNECT
  4. Check status changes to "● Connected" and FW version shown
  5. Click DISCONNECT
  6. Check status "● Disconnected"
- **Expected**: Connect succeeds, version displayed, disconnect clean
- **Pass Criteria**: No exceptions, status updates

### 1.3 Invalid Port

- **Steps**:
  1. Select invalid port or disconnect Arduino physically
  2. Click CONNECT
- **Expected**: Error message "Failed to open...", status shows error
- **Pass Criteria**: Graceful error, no crash

### 1.4 Disconnect During Operation

- **Steps**:
  1. Connect
  2. Start READ FLASH (large)
  3. Unplug USB during read
- **Expected**: Operation fails with "Not connected" or timeout, GUI remains responsive
- **Pass Criteria**: No freeze, error logged

---

## 2. AVR ISP Tests

### 2.1 AVR Detection - ATmega328P

- **Setup**: Arduino ISP wired to ATmega328P target (see wiring.md)
- **Steps**:
  1. Connect Arduino
  2. Select Protocol: AVR ISP
  3. Click Detect
- **Expected**: Signature 1E 95 0F, Device ATmega328P, Flash 32KB, EEPROM 1KB
- **Pass Criteria**: Correct signature and device name from database

### 2.2 AVR Detection - ATtiny85

- **Setup**: ATtiny85 target, slow clock
- **Steps**: Same as 2.1
- **Expected**: Signature 1E 93 0B, ATtiny85, 8KB Flash
- **Pass Criteria**: Detection works with slow SPI clock

### 2.3 AVR Detection - No Target

- **Setup**: No target connected, or target without power
- **Steps**: Click Detect
- **Expected**: Error "Target not detected" or invalid signature 00 00 00 / FF FF FF
- **Pass Criteria**: Clear error message, no false detection

### 2.4 AVR Flash Read

- **Setup**: ATmega328P with known firmware
- **Steps**:
  1. Detect
  2. Select Memory: flash
  3. Click READ FLASH or READ
- **Expected**:
  - Progress bar updates 0-100%
  - Log shows "Reading flash..."
  - Hex viewer shows data (not all FF or 00)
  - SHA-256 calculated
  - Status: Read flash: N bytes
- **Pass Criteria**: Data read, progress works, hex viewer updated, actual bytes (not placeholder)

### 2.5 Save BIN

- **Setup**: After successful read
- **Steps**:
  1. Click Save BIN
  2. Choose file location, save as flash.bin
  3. Check file exists, size matches flash size
  4. Open file in hex editor, compare to hex viewer
- **Expected**: File saved, size correct, content matches hex viewer, SHA-256 matches log
- **Pass Criteria**: Actual bytes saved, not simulated

### 2.6 Load BIN

- **Steps**:
  1. Click Load BIN
  2. Select previously saved flash.bin
  3. Check hex viewer shows file content
  4. Check log shows size and SHA-256
- **Expected**: File loaded, hex viewer updated, info displayed
- **Pass Criteria**: Correct loading, no truncation

### 2.7 Flash Write

- **Setup**: ATmega328P target, valid BIN loaded
- **Steps**:
  1. Detect
  2. Load BIN (e.g., blink example, 1KB)
  3. Click WRITE
  4. Confirm dialog shows target, size, SHA-256
  5. Click PROGRAM
- **Expected**:
  - Progress 0-100%
  - Log "Writing flash..."
  - Auto-verify after write
  - Success message "Write + Verify OK"
- **Pass Criteria**: Write succeeds, verify OK

### 2.8 Verify

- **Setup**: After write, or with existing dump
- **Steps**:
  1. Load BIN that was just written
  2. Click VERIFY
- **Expected**: "Verification successful" if matches, or detailed mismatch if not
- **Pass Criteria**: Correct verification, mismatch info shows address, expected, actual

### 2.9 Verify Fail Case

- **Steps**:
  1. Load BIN A, write to device
  2. Load BIN B (different)
  3. Click VERIFY
- **Expected**: Verification fails, shows first mismatch address and bytes
- **Pass Criteria**: Useful error info

### 2.10 EEPROM Read/Write

- **Steps**:
  1. Read EEPROM
  2. Save eeprom.bin
  3. Load different eeprom.bin
  4. Write EEPROM
  5. Read back and compare
- **Expected**: EEPROM operations work independently from flash
- **Pass Criteria**: Data integrity

### 2.11 Erase

- **Steps**:
  1. Click ERASE
  2. Confirm warning dialog
- **Expected**: Chip erased, flash reads as FF
- **Pass Criteria**: Erase completes, verification after shows all FF

### 2.12 Invalid BIN Size

- **Steps**:
  1. Create file larger than target (e.g., 64KB file for 32KB device)
  2. Load it
  3. Try to write
- **Expected**: Warning "File size exceeds target size, will NOT truncate", write blocked
- **Pass Criteria**: No silent truncation, clear warning

---

## 3. SPI Memory Tests

### 3.1 SPI Detection - W25Q32

- **Setup**: W25Q32 flash wired to Arduino (see wiring.md), 3.3V!
- **Steps**:
  1. Select Protocol: SPI Memory
  2. Click Detect
- **Expected**: JEDEC ID EF 40 16, Device W25Q32, 4MB
- **Pass Criteria**: Correct JEDEC and device lookup

### 3.2 SPI Read

- **Steps**: After detect, READ FLASH
- **Expected**: Progress, hex viewer shows data, SHA-256
- **Pass Criteria**: Actual bytes from chip

### 3.3 SPI Write/Verify

- **Steps**:
  1. Load BIN (e.g., 4KB)
  2. Write
  3. Verify
- **Expected**: Write and verify OK
- **Pass Criteria**: Data integrity, page boundary handling

### 3.4 SPI Erase

- **Steps**: Erase, then read, should be FF
- **Expected**: Chip erased
- **Pass Criteria**: All FF after erase

### 3.5 SPI No Target

- **Setup**: No SPI flash connected
- **Steps**: Detect
- **Expected**: Error "No target" or JEDEC 00 00 00 / FF FF FF
- **Pass Criteria**: Graceful error

---

## 4. I2C Memory Tests

### 4.1 I2C Scan

- **Setup**: 24C256 EEPROM wired with pull-ups
- **Steps**:
  1. Select Protocol: I2C Memory
  2. Click Detect (which does scan internally)
- **Expected**: Found devices list shows 0x50, device 24C256, 32KB
- **Pass Criteria**: Scan works

### 4.2 I2C Scan - No Device

- **Setup**: No I2C device
- **Steps**: Detect
- **Expected**: "No I2C devices found"
- **Pass Criteria**: Clear message

### 4.3 I2C Read

- **Steps**: READ
- **Expected**: Progress, data, hex viewer
- **Pass Criteria**: Actual bytes

### 4.4 I2C Write/Verify

- **Steps**: Load BIN, write, verify
- **Expected**: Write OK, verify OK, respects page boundaries
- **Pass Criteria**: Data integrity

### 4.5 I2C Address Configuration

- **Steps**:
  1. Change I2C address in device panel to 0x51
  2. Detect
- **Expected**: Tries 0x51, if not found uses 0x50 or reports not found
- **Pass Criteria**: Address setting works

---

## 5. File Operation Tests

### 5.1 Save As...

- **Steps**: After read, Save BIN, choose custom name
- **Expected**: File saved with custom name
- **Pass Criteria**: Works, remembers last directory

### 5.2 Overwrite Protection

- **Steps**:
  1. Save flash.bin
  2. Save again to same file
- **Expected**: Confirmation dialog "File exists, overwrite?"
- **Pass Criteria**: No silent overwrite

### 5.3 Compare BIN - Identical

- **Steps**:
  1. Save flash.bin
  2. Compare BIN, select same file twice
- **Expected**: "Files are IDENTICAL"
- **Pass Criteria**: Correct comparison

### 5.4 Compare BIN - Different

- **Steps**:
  1. Compare two different BIN files
- **Expected**: Shows diff count, first/last mismatch, list of differences with address, File A byte, File B byte
- **Pass Criteria**: Useful diff info, highlight in hex viewer

### 5.5 Load Large File

- **Steps**: Load 16MB BIN file
- **Expected**: Hex viewer handles it (maybe shows first 1MB with warning), GUI remains responsive
- **Pass Criteria**: No freeze

---

## 6. Hex Viewer Tests

### 6.1 Display

- **Steps**: Read flash, check hex viewer shows address, hex bytes, ASCII
- **Expected**: Professional layout, scrollable
- **Pass Criteria**: Correct display

### 6.2 Go To Address

- **Steps**:
  1. Enter 0x100 in Address field
  2. Click Go
- **Expected**: Scrolls to 0x100, highlights row
- **Pass Criteria**: Navigation works

### 6.3 Search

- **Steps**:
  1. Enter "FF 00" in search
  2. Click Find
- **Expected**: Finds occurrences, highlights, shows count
- **Pass Criteria**: Search works, Next cycles through results

### 6.4 Copy

- **Steps**: Right-click, Copy as Hex String, paste elsewhere
- **Expected**: Hex string copied
- **Pass Criteria**: Copy works

---

## 7. Progress and Cancellation Tests

### 7.1 Progress Updates

- **Steps**: Read large flash (32KB)
- **Expected**: Progress bar 0-100%, status text updates with address
- **Pass Criteria**: Smooth progress, no freeze

### 7.2 Cancel During Read

- **Steps**:
  1. Start READ (large)
  2. Click CANCEL
- **Expected**: Operation stops, log "Cancelled", progress reset, target exits programming mode safely
- **Pass Criteria**: Safe cancellation

### 7.3 Cancel During Write

- **Steps**: Similar to 7.2 but during write
- **Expected**: Stops safely, reports cancelled
- **Pass Criteria**: Safe

---

## 8. Error Handling Tests

### 8.1 Communication Timeout

- **Steps**: Simulate timeout (e.g., use wrong baud, or disconnect target SCK)
- **Expected**: Error "Target timeout" or "No target", not Python traceback
- **Pass Criteria**: User-friendly error

### 8.2 Invalid Signature

- **Steps**: Connect target with invalid signature (e.g., short MISO to GND)
- **Expected**: Signature 00 00 00, error "Invalid signature - check wiring"
- **Pass Criteria**: Helpful message

### 8.3 Wrong Protocol

- **Steps**: Select SPI protocol but AVR target connected, click Detect
- **Expected**: Detect fails with no target or invalid JEDEC, clear message
- **Pass Criteria**: No crash

---

## 9. Device Database Tests

### 9.1 AVR Database

- **Steps**: Check devices/avr_devices.json loaded, detection uses it
- **Expected**: Known signatures map to names and sizes
- **Pass Criteria**: Database works, easy to add new devices without code change

### 9.2 SPI Database

- **Steps**: Similar for SPI
- **Expected**: JEDEC IDs map to devices
- **Pass Criteria**: Works

### 9.3 I2C Database

- **Steps**: Similar
- **Expected**: Works
- **Pass Criteria**: Works

---

## 10. Data Integrity Tests

### 10.1 Read -> Save -> Load -> Write -> Read -> Compare

- **Steps**:
  1. Read flash from device A
  2. Save as original.bin
  3. Write original.bin to device B
  4. Read from device B as copy.bin
  5. Compare original.bin and copy.bin
- **Expected**: Identical
- **Pass Criteria**: Full round-trip integrity - critical requirement

### 10.2 Checksum Verification

- **Steps**: After read, note SHA-256, save, load, check SHA-256 matches
- **Expected**: SHA-256 consistent
- **Pass Criteria**: No corruption

### 10.3 Packet CRC

- **Steps**: Check firmware and GUI implement CRC16, corrupted packets discarded
- **Expected**: No silent corruption
- **Pass Criteria**: CRC validation works

---

## 11. GUI Responsiveness

### 11.1 No Freeze During Operations

- **Steps**: Start long read, try to interact with GUI (e.g., scroll log, click tabs)
- **Expected**: GUI remains responsive, progress updates
- **Pass Criteria**: Worker threads used, no freeze

### 11.2 Keyboard Shortcuts

- **Steps**: Test Ctrl+O (load), Ctrl+S (save), etc if implemented
- **Expected**: Shortcuts work
- **Pass Criteria**: UX

---

## 12. Logging Tests

### 12.1 Log Levels

- **Steps**: Perform operations, check log shows INFO, SUCCESS, WARNING, ERROR with colors
- **Expected**: Professional log
- **Pass Criteria**: Levels work

### 12.2 Clear and Save Log

- **Steps**: Click Clear Log, then Save Log
- **Expected**: Log cleared, saved to file
- **Pass Criteria**: Works

---

## 13. Safety Tests

### 13.1 Write Confirmation

- **Steps**: Click WRITE without confirmation should not write
- **Expected**: Dialog "Are you sure you want to PROGRAM?" with CANCEL and PROGRAM
- **Pass Criteria**: Confirmation required

### 13.2 Erase Confirmation

- **Steps**: Click ERASE
- **Expected**: Warning dialog
- **Pass Criteria**: Confirmation required

---

## 14. Packaging Test (Windows)

### 14.1 Requirements

- **Steps**: pip install -r requirements.txt on fresh Windows
- **Expected**: Only pyserial needed
- **Pass Criteria**: Minimal dependencies

### 14.2 Run on Windows 10/11

- **Steps**: Run python app.py on Windows
- **Expected**: GUI opens, COM ports detected
- **Pass Criteria**: Works on target OS

---

## Test Summary Checklist

- [ ] 1.1 Port Detection
- [ ] 1.2 Connect/Disconnect
- [ ] 1.3 Invalid Port
- [ ] 1.4 Disconnect During Operation
- [ ] 2.1 AVR Detect ATmega328P
- [ ] 2.2 AVR Detect ATtiny85
- [ ] 2.3 AVR No Target
- [ ] 2.4 AVR Flash Read
- [ ] 2.5 Save BIN
- [ ] 2.6 Load BIN
- [ ] 2.7 Flash Write
- [ ] 2.8 Verify
- [ ] 2.9 Verify Fail
- [ ] 2.10 EEPROM Read/Write
- [ ] 2.11 Erase
- [ ] 2.12 Invalid BIN Size
- [ ] 3.1 SPI Detect W25Q32
- [ ] 3.2 SPI Read
- [ ] 3.3 SPI Write/Verify
- [ ] 3.4 SPI Erase
- [ ] 3.5 SPI No Target
- [ ] 4.1 I2C Scan
- [ ] 4.2 I2C No Device
- [ ] 4.3 I2C Read
- [ ] 4.4 I2C Write/Verify
- [ ] 4.5 I2C Address Config
- [ ] 5.1 Save As
- [ ] 5.2 Overwrite Protection
- [ ] 5.3 Compare Identical
- [ ] 5.4 Compare Different
- [ ] 5.5 Large File
- [ ] 6.1 Hex Display
- [ ] 6.2 Goto Address
- [ ] 6.3 Search
- [ ] 6.4 Copy
- [ ] 7.1 Progress Updates
- [ ] 7.2 Cancel Read
- [ ] 7.3 Cancel Write
- [ ] 8.1 Timeout
- [ ] 8.2 Invalid Signature
- [ ] 8.3 Wrong Protocol
- [ ] 9.1 AVR DB
- [ ] 9.2 SPI DB
- [ ] 9.3 I2C DB
- [ ] 10.1 Round-trip Integrity
- [ ] 10.2 Checksum
- [ ] 10.3 CRC
- [ ] 11.1 No Freeze
- [ ] 12.1 Log Levels
- [ ] 12.2 Clear/Save Log
- [ ] 13.1 Write Confirmation
- [ ] 13.2 Erase Confirmation
- [ ] 14.1 Requirements
- [ ] 14.2 Windows Run

---

## Critical Requirement Verification

**MOST IMPORTANT**: READ FROM TARGET → STORE ACTUAL BYTES → DISPLAY DUMP → SAVE ACTUAL DUMP AS .BIN

Test this explicitly:

1. Read from real target (not simulated)
2. Check hex viewer shows actual data (not placeholder like all FF if device has code)
3. Save to .BIN
4. Open .BIN in external hex editor, verify bytes match what was read
5. Write .BIN to another device
6. Read back and compare - must be identical

This must be demonstrated for each protocol.

