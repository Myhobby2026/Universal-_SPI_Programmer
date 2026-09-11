# ATtiny85 Support - Guide

Yes, ATtiny85 is fully supported!

## Device Definition

In `devices/avr_devices.json`:

```json
{
  "name": "ATtiny85",
  "part_number": "ATtiny85",
  "manufacturer": "Microchip",
  "signature": "1E 93 0B",
  "flash_size": 8192,
  "eeprom_size": 512,
  "page_size": 64,
  "protocol": "AVR ISP",
  "description": "8KB Flash, 512B EEPROM, 512B SRAM - Requires slow SPI clock"
}
```

- Signature `1E 93 0B` is auto-detected
- Flash 8KB (8192 bytes)
- EEPROM 512 bytes
- Page size 64 bytes (vs 128 for ATmega328P) - handled automatically

## Why ATtiny85 Needs Special Handling

ATtiny85 often runs at 1MHz internal oscillator (default fuse).

Datasheet requirement:
> SPI clock must be less than 1/6 of CPU clock

For 1MHz CPU:
- Max SPI = 1MHz / 6 = 166.6 kHz

Our firmware uses:

```c
#define SPI_CLOCK (1000000/6)  // ~166kHz - safe for ATtiny85 @ 1MHz
```

This is defined in `arduino/universal_programmer.ino` line 110.

If ATtiny85 runs at 8MHz (fuse changed), you could use faster clock, but 166kHz works for both 1MHz and 8MHz, just slower.

## Wiring ATtiny85

```
Arduino (Programmer)    ATtiny85 (Target)
--------------------    ------------------
Pin 10 (RESET)    --->  Pin 1 (RESET / PB5)
Pin 11 (MOSI)     --->  Pin 5 (MOSI / PB0)
Pin 12 (MISO)     <---  Pin 6 (MISO / PB1)
Pin 13 (SCK)      --->  Pin 7 (SCK / PB2)
5V                --->  Pin 8 (VCC)
GND               --->  Pin 4 (GND)

ATtiny85 Pinout (DIP-8):

      +---U---+
RESET-|1    8|- VCC
 PB3 -|2    7|- PB2 (SCK)
 PB4 -|3    6|- PB1 (MISO)
 GND -|4    5|- PB0 (MOSI)
      +-------+
```

**Important:**

1. **Disable Auto-Reset on Arduino**: Put 10uF capacitor between Arduino RESET and GND (negative to GND) after uploading firmware. This prevents Arduino from resetting when GUI opens serial port. Alternative: 120 ohm resistor between RESET and 5V.

2. **Decoupling**: 100nF capacitor between ATtiny85 VCC and GND close to chip.

3. **No Crystal Needed**: ATtiny85 uses internal oscillator by default.

## Using in GUI

1. Wire ATtiny85 as above
2. Connect Arduino, upload `universal_programmer.ino`
3. Open GUI `python app.py`
4. Select COM port, CONNECT (115200 baud)
5. Protocol: AVR ISP (default)
6. Click DETECT
   - Expected: Signature `1E 93 0B`, Device `ATtiny85`, Flash `8.0 KB (8192 bytes)`, EEPROM `512 bytes`
7. Operations:
   - READ FLASH -> Reads 8192 bytes, shows in hex viewer, SHA-256
   - Save BIN -> Saves actual bytes
   - Load BIN -> Load firmware (e.g., 1KB blink)
   - WRITE -> Programs flash (handles 64-byte pages automatically)
   - VERIFY -> Checks

## Page Size Handling

Our `protocols/avr_isp.py` uses device-specific page size:

```python
page_size = self.device_info.get('page_size', 128) if memory_type == "flash" else 32
```

For ATtiny85, `page_size = 64`, so writes are chunked into 64-byte pages.

Firmware `avr_write_flash_page()` loads page buffer then commits:

```c
for (uint16_t i = 0; i < len; i++) {
  uint32_t word_addr = (addr + i) >> 1;
  bool high = (addr + i) & 1;
  uint8_t cmd = high ? 0x48 : 0x40;
  spi_transaction(cmd, ...);
}
spi_transaction(0x4C, ...); // commit page
```

Works for ATtiny85's 64-byte pages.

## Fuse Considerations

ATtiny85 fuses control clock source. Default:

- Low fuse 0x62: Internal 8MHz divided by 8 = 1MHz
- High fuse 0xDF
- Extended 0xFF

If you change fuses to 8MHz (no divide), SPI can be faster, but our 166kHz still works.

**Warning**: If you set RSTDISBL fuse (PB5 as I/O), you lose ISP programming and need high-voltage programmer. Our tool does NOT support HVSP - only ISP. So avoid setting RSTDISBL.

## Testing ATtiny85

Tested workflow:

1. Detect -> Should show ATtiny85
2. Read Flash -> Should show actual bytes (not all FF if chip has bootloader or previous code, or all FF if erased)
3. Save BIN -> Check file size 8192
4. Load `examples/blink_example.bin` (32 bytes) or your own
5. Write -> Progress 0-100%, auto-verify
6. Read back -> Compare with original BIN using Compare BIN feature -> Should be identical

## Example: Blink for ATtiny85

Simple blink compiled for ATtiny85 (PB0):

```c
// ATtiny85 blink PB0
void setup() { pinMode(0, OUTPUT); }
void loop() { digitalWrite(0, HIGH); delay(500); digitalWrite(0, LOW); delay(500); }
```

Compile with Arduino IDE: Board = ATtiny25/45/85, Chip = ATtiny85, Clock = 1MHz internal, then Export compiled binary. Use that BIN for WRITE.

## Troubleshooting ATtiny85

- **Signature 00 00 00 or FF FF FF**: Check wiring, power, GND, and auto-reset capacitor. Also check if chip is getting clock.
- **Detection fails**: Try slower? Our clock is already slowest safe. Check connections with multimeter.
- **Write fails**: Ensure BIN size <= 8192. For ATtiny85, flash is 8KB, but bootloader area? ATtiny85 usually no bootloader, so full 8KB usable.
- **Verify fails after write**: Might be fuse for BOD or lock bits. Try chip erase first (ERASE button).
- **ATtiny85 not responding after fuse change**: If you set wrong clock fuse (e.g., external crystal but no crystal), chip appears dead. Need to provide external clock to recover. Avoid changing clock fuses unless you know.

## Conclusion

ATtiny85 is first-class citizen in this programmer, not an afterthought. It was explicitly required in the spec ("with Support ATtiny85 also") and is fully implemented in:

- Firmware SPI clock
- Device database
- Protocol page handling
- GUI auto-detection
- Wiring docs
- Test plan
