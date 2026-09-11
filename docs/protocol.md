# Universal Programmer - Communication Protocol

## Overview

The Universal Programmer uses a robust framed binary protocol over serial (UART) for communication between the PC GUI and Arduino firmware.

It also preserves STK500v1 compatibility for avrdude.

---

## 1. Framed Binary Protocol

### Frame Structure

Host -> Device and Device -> Host use same framing:

```
Byte:   0    1    2   3   4   5   6..N   N+1 N+2  N+3 N+4
Field: [0xAA][0x55][CMD][SEQ][LEN_L][LEN_H][PAYLOAD][CRC_L][CRC_H][0x55][0xAA]
```

- **HEADER**: 0xAA 0x55 (2 bytes, start of frame)
- **CMD**: Command byte (1 byte)
- **SEQ**: Sequence number (1 byte, increments each command, used to match response)
- **LEN**: Payload length, little-endian uint16 (2 bytes, 0-512)
- **PAYLOAD**: Variable length (LEN bytes)
- **CRC**: CRC16-CCITT (poly 0x1021, init 0xFFFF) over CMD+SEQ+LEN_L+LEN_H+PAYLOAD (2 bytes, little-endian)
- **FOOTER**: 0x55 0xAA (2 bytes, end of frame)

Total frame size: 10 + LEN bytes

### CRC Calculation

```python
def crc16_ccitt(data: bytes):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
```

CRC covers: CMD + SEQ + LEN_L + LEN_H + PAYLOAD

### Response Format

Device response uses CMD | 0x80 (sets MSB) to indicate response.

Payload of response:
- First byte: STATUS code
- Remaining bytes: Response data

```
Response PAYLOAD: [STATUS][DATA...]
```

### Status Codes

| Code | Name | Meaning |
|------|------|---------|
| 0x00 | OK | Success |
| 0x01 | ERROR_GENERIC | Generic error |
| 0x02 | ERROR_NO_TARGET | Target not detected / no response |
| 0x03 | ERROR_TIMEOUT | Timeout communicating with target |
| 0x04 | ERROR_INVALID_CMD | Invalid command |
| 0x05 | ERROR_INVALID_PARAM | Invalid parameter |
| 0x06 | ERROR_NOT_SUPPORTED | Operation not supported |
| 0x07 | ERROR_VERIFY_FAILED | Verification failed |
| 0x08 | ERROR_BUSY | Device busy |

### Sequence Number

- Host increments SEQ for each command (0-255, wraps)
- Device echoes SEQ in response
- Host can use SEQ to match response to request and discard out-of-order packets

---

## 2. Commands

### General Commands

#### 0x01 GET_VERSION

- **Payload**: None
- **Response Data**: ASCII version string, e.g., "Universal Programmer v1.0.0"
- **Description**: Get firmware version

#### 0x02 GET_STATUS

- **Payload**: None
- **Response Data**: 4-byte status flags (uint32 LE)
  - Bit 0: pmode (programming mode active)
  - Bits 8-15: current protocol
  - Bits 16-23: error count
- **Description**: Get firmware status

#### 0x03 SELECT_PROTOCOL

- **Payload**: 1 byte protocol ID
  - 0 = None
  - 1 = AVR ISP
  - 2 = SPI Memory
  - 3 = I2C Memory
- **Response**: None (just status OK)
- **Description**: Select active protocol

#### 0x40 PING

- **Payload**: Optional (e.g., "PING")
- **Response**: "PONG"
- **Description**: Test communication

#### 0x41 RESET_TARGET

- **Payload**: 1 byte (0 = release reset, 1 = assert reset)
- **Response**: None
- **Description**: Control target reset line

### AVR ISP Commands

#### 0x10 AVR_ENTER_PROG

- **Payload**: None
- **Response**: None
- **Description**: Enter AVR programming mode (pulse reset, send 0xAC 0x53)

#### 0x11 AVR_EXIT_PROG

- **Payload**: None
- **Response**: None
- **Description**: Exit programming mode

#### 0x12 AVR_READ_SIGNATURE

- **Payload**: None
- **Response**: 3-byte signature, e.g., 1E 95 0F for ATmega328P
- **Description**: Read AVR signature bytes

#### 0x18 AVR_DETECT

- **Payload**: None
- **Response**: 7 bytes
  - Bytes 0-2: Signature
  - Bytes 3-4: Flash size in KB (uint16 LE)
  - Bytes 5-6: EEPROM size in KB (uint16 LE)
- **Description**: Detect AVR and return info

#### 0x13 AVR_READ_FLASH

- **Payload**: 6 bytes
  - Bytes 0-3: Address (uint32 LE, byte address)
  - Bytes 4-5: Length (uint16 LE, max 256)
- **Response**: Length bytes of flash data
- **Description**: Read flash memory

#### 0x14 AVR_READ_EEPROM

- **Payload**: 4 bytes
  - Bytes 0-1: Address (uint16 LE)
  - Bytes 2-3: Length (uint16 LE, max 256)
- **Response**: Length bytes of EEPROM data
- **Description**: Read EEPROM

#### 0x15 AVR_WRITE_FLASH

- **Payload**: 4 + N bytes
  - Bytes 0-3: Address (uint32 LE)
  - Bytes 4..: Data to write (page)
- **Response**: None
- **Description**: Write flash page

#### 0x16 AVR_WRITE_EEPROM

- **Payload**: 2 + N bytes
  - Bytes 0-1: Address (uint16 LE)
  - Bytes 2..: Data
- **Response**: None
- **Description**: Write EEPROM

#### 0x17 AVR_ERASE

- **Payload**: None
- **Response**: None
- **Description**: Chip erase

### SPI Memory Commands

#### 0x20 SPI_DETECT

- **Payload**: None
- **Response**: 3-byte JEDEC ID (Manufacturer, Memory Type, Capacity)
- **Description**: Read JEDEC ID (command 0x9F)

#### 0x21 SPI_READ

- **Payload**: 6 bytes
  - Bytes 0-3: Address (uint32 LE)
  - Bytes 4-5: Length (uint16 LE, max 256)
- **Response**: Data
- **Description**: Read SPI flash

#### 0x22 SPI_WRITE

- **Payload**: 4 + N bytes
  - Bytes 0-3: Address
  - Bytes 4..: Data
- **Response**: None
- **Description**: Write SPI flash (handles page boundaries, write enable)

#### 0x23 SPI_ERASE

- **Payload**: 5 bytes
  - Byte 0: Erase type (0xC7=chip, 0x20=sector 4K, 0xD8=block 64K)
  - Bytes 1-4: Address (uint32 LE)
- **Response**: None
- **Description**: Erase SPI flash

#### 0x24 SPI_GET_STATUS

- **Payload**: None
- **Response**: 1-byte status register
- **Description**: Read status register (command 0x05)

### I2C Memory Commands

#### 0x30 I2C_SCAN

- **Payload**: None
- **Response**: List of addresses found (each 1 byte)
- **Description**: Scan I2C bus for devices

#### 0x33 I2C_DETECT

- **Payload**: 1 byte device address
- **Response**: None (OK if device ACKs)
- **Description**: Check if device at address responds

#### 0x31 I2C_READ

- **Payload**: 6 bytes
  - Byte 0: Device address (7-bit)
  - Bytes 1-2: Memory address (uint16 LE)
  - Byte 3: Addr width (1 or 2)
  - Bytes 4-5: Length (uint16 LE, max 128)
- **Response**: Data
- **Description**: Read I2C EEPROM

#### 0x32 I2C_WRITE

- **Payload**: 4 + N bytes
  - Byte 0: Device address
  - Bytes 1-2: Memory address
  - Byte 3: Addr width
  - Bytes 4..: Data
- **Response**: None
- **Description**: Write I2C EEPROM

---

## 3. Communication Flow Examples

### Example: Read AVR Signature

Host -> Device:
```
AA 55 12 01 00 00 [CRC] 55 AA
(CMD=0x12 READ_SIG, SEQ=1, LEN=0)
```

Device -> Host:
```
AA 55 92 01 04 00 00 1E 95 0F [CRC] 55 AA
(CMD=0x92 = 0x12|0x80, SEQ=1, LEN=4, STATUS=0x00, DATA=1E 95 0F)
```

### Example: Read Flash Chunk

Host -> Device:
```
AA 55 13 02 06 00 00 00 00 00 80 00 [CRC] 55 AA
(CMD=0x13 READ_FLASH, SEQ=2, LEN=6, PAYLOAD=addr 0x00000000, len 0x0080=128)
```

Device -> Host:
```
AA 55 93 02 81 00 00 [128 bytes data] [CRC] 55 AA
(LEN=0x81=129 = 1 status + 128 data)
```

### Example: Error - No Target

Host -> Device: READ_SIG

Device -> Host:
```
AA 55 92 01 01 00 02 [CRC] 55 AA
(STATUS=0x02 ERROR_NO_TARGET)
```

---

## 4. Data Integrity Features

- **CRC16**: Every packet validated with CRC16-CCITT
- **Header/Footer**: Double-byte markers for sync
- **Length Validation**: Payload length checked against max
- **Sequence Number**: Detect out-of-order or duplicate packets
- **Timeout**: Host uses 2-3 second timeout per command, with retries (3x)
- **Chunked Transfer**: Large reads/writes split into 128-256 byte chunks to avoid buffer overflow and allow progress reporting and cancellation

---

## 5. STK500v1 Compatibility

Firmware also implements STK500v1 protocol for avrdude compatibility.

- If first byte is not 0xAA, it's treated as STK500 command
- Commands: '0' (signon), '1' (get sync), 'A'/'@' (get version), 'B' (set params), 'P' (enter progmode), 'Q' (leave), 'U' (set address), 0x60/0x61 (prog flash/eeprom), 0x64 (prog page), 0x74 (read sign), 0x75 (read page), 'V' (universal)
- This allows using Arduino as standard AVR ISP with avrdude:
  ```
  avrdude -c stk500v1 -P COM5 -b 19200 -p m328p -U flash:r:dump.bin:r
  ```
- Note: Our firmware uses 115200 baud, while classic ArduinoISP uses 19200. We support both? Our firmware uses 115200, but STK500 should still work at that baud.

---

## 6. Implementation Notes for PC Side

- Use `serial_manager.py` for port handling
- Use `arduino_interface.py` for packet building/parsing
- Implement retry logic (3 retries) on timeout or CRC error
- Flush buffers before sending command
- Use separate thread for long operations to avoid GUI freeze
- Support cancellation via flag checked between chunks

---

## 7. Future Extensions

- 1-Wire protocol: Add CMD 0x50-0x5F range
- Custom protocols: Use 0x60-0x7F range
- For new protocols, follow same pattern: DETECT, READ, WRITE, ERASE, SCAN

---

## 8. Error Handling

- If CRC mismatch: Discard packet, wait for next (don't send error to avoid loop)
- If invalid footer: Discard and resync by searching for next 0xAA 0x55
- If timeout: Host retries
- If target not responding: Firmware returns ERROR_NO_TARGET quickly (after 2 attempts)
- If host disconnects: Firmware exits progmode and resets state

---

## 9. Baud Rate

- Default: 115200 baud
- 8N1
- No flow control
- DTR/RTS not used (but Arduino may reset on connect, so wait 1.5s after opening port)

---

## 10. Version History

- v1.0.0: Initial release with AVR ISP, SPI, I2C support, framed protocol + STK500
