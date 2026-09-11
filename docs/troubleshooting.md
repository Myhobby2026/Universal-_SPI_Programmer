# Troubleshooting Guide

## Error: "Command 0x03 failed after 3 retries: Timeout waiting for response header"

This is the most common initial setup error. It means the GUI cannot communicate with the Arduino firmware using the framed protocol.

### Root Cause

The GUI sends a framed binary packet `AA 55 03 ...` (SELECT_PROTOCOL) but receives no response.

### Solutions - Check in Order

#### 1. Firmware Not Uploaded (Most Common - 90% of cases)

**Symptom**: Timeout on first command, no FW version shown, PING fails

**Cause**: You have old `ArduinoISP` example uploaded, not `universal_programmer.ino`

**Old ArduinoISP** only understands STK500 commands like `0x30` and `0x20`, not our framed `AA 55` protocol. When it receives `AA 55`, it treats `AA` as unknown STK command and waits for `20` (EOP), causing timeout.

**Fix**:

1. Open Arduino IDE
2. File -> Open -> `arduino/universal_programmer.ino` from THIS project (not Examples->ArduinoISP)
3. Tools -> Board -> Select your board (Arduino Uno, Nano, etc)
4. Tools -> Port -> Select your COM port
5. Tools -> Baud Rate is not in IDE, but firmware uses 115200 - this is set in code
6. Click Upload (right arrow)
7. Wait for "Done uploading"
8. Close Arduino IDE Serial Monitor if open (it locks the port)
9. Reopen GUI, select same COM port, baud 115200, CONNECT
10. Check log: Should show "Firmware version: Universal Programmer v1.0.1" and "Communication test: OK"

**How to verify firmware is correct**:

- After upload, open Arduino IDE Serial Monitor at 115200 baud
- Type nothing, but if you send `AA 55 40 00 04 00 50 49 4E 47` (hex) you should get response
- Easier: Our GUI's PING should work. If PING fails, firmware is wrong.

#### 2. Wrong Baud Rate

**Symptom**: Timeout, no data received

**Fix**: Select **115200** in GUI baud dropdown. Our firmware uses 115200, while classic ArduinoISP uses 19200. If you use 19200 with our firmware, it won't work.

#### 3. Arduino Auto-Reset

**Symptom**: First connect works but then timeout, or intermittent

**Cause**: Arduino Uno/Nano resets when serial port is opened (DTR line). Bootloader waits 1-2 seconds, during which it doesn't respond to our protocol.

**Fix in code**: We already wait 2.5 seconds after opening port (`serial_manager.py`). But some boards need more.

**Additional hardware fix**: Put **10uF capacitor** between Arduino RESET pin and GND (negative to GND) AFTER uploading firmware. This disables auto-reset. Or use 120 ohm resistor between RESET and 5V.

**Alternative**: In `serial_manager.py`, increase delay to 3.0 seconds.

#### 4. COM Port Locked

**Symptom**: "Failed to open COMx: Access denied"

**Fix**: Close Arduino IDE, close any other serial terminal, close previous instance of GUI. Only one app can use COM port at a time.

#### 5. Wrong COM Port

**Symptom**: Timeout, no data

**Fix**: Click refresh button (↻) in GUI, select correct port. On Windows, check Device Manager -> Ports (COM & LPT) -> Arduino Uno (COMx). On Linux, `/dev/ttyUSB0` or `/dev/ttyACM0`.

#### 6. USB Cable

**Symptom**: Port appears but no communication

**Fix**: Use data cable, not charge-only cable. Try different USB port, try different cable.

#### 7. ESP32 vs Uno

**Symptom**: Timeout on ESP32

**Fix**: ESP32 doesn't auto-reset same way, but needs correct pins. Ensure you selected ESP32 board when uploading. Also ESP32 boot time is longer - our code waits 2.5s, should be enough.

### Debugging Steps

1. **Enable verbose logging**: In GUI, LOG tab shows all attempts. If you see "PING attempt 1 failed", firmware not responding.

2. **Test with CLI tool**: Run `python tools/read_test.py COM5 --protocol avr` from command line. It gives more detailed error including bytes received.

3. **Check raw bytes**: In `arduino_interface.py`, we now show preview of received bytes on timeout: `Received X bytes: ...`. If you see text like `41 56 52 20 49 53 50` which is ASCII "AVR ISP", you have old firmware.

4. **Loopback test**: Disconnect target, short Arduino Pin 11 to Pin 12 (MOSI to MISO) and test SPI detect - should still get PING OK even without target. If PING fails even without target, it's firmware/connection issue, not target wiring.

### Error: "Layout Horizontal.Error.TProgressbar not found"

**Fixed in v1.0.1**: This was a Tkinter style bug on some Windows Python versions (3.13). Custom progressbar styles need explicit layout.

**Fix**: Update to latest code - we now handle this with try/except and proper layout copying in `gui/styles.py` and `gui/progress_panel.py`.

If you still see it, edit `gui/progress_panel.py` and comment out style changing lines, or ensure `styles.py` defines `Horizontal.Error.TProgressbar`.

### Error: "Target not detected / no response"

**Symptom**: PING OK, version OK, but DETECT fails with no target

**Cause**: Wiring issue between Arduino and target, or target not powered

**Fix**:

- Check wiring per `docs/wiring.md`
- Check target VCC and GND with multimeter
- For AVR: Check target has clock (crystal or internal). If fuses set to external crystal but no crystal, chip appears dead.
- For SPI flash: Check 3.3V power (not 5V!), CS pin, and that chip is not write-protected (WP pin high)
- For I2C: Check 4.7k pull-ups to VCC on SDA/SCL, check address (0x50), check WP grounded

### Error: "Invalid signature 00 00 00 or FF FF FF"

**Cause**: MISO line stuck low or high, or target not in programming mode

**Fix**:

- Check MISO, MOSI, SCK, RESET wiring
- Check RESET is controlled by Arduino Pin 10 (should be LOW during programming)
- Try slower SPI? Our clock is already 166kHz safe for ATtiny85
- Try chip erase first (ERASE button) if chip has lock bits

### General Tips

- **Always** upload `universal_programmer.ino` from this project, not the old ArduinoISP example
- **Always** use 115200 baud
- **Always** close Serial Monitor before using GUI
- **For ATtiny85**: Use slow clock (we do), and add 10uF cap to disable auto-reset
- **For SPI flash**: Use 3.3V! ESP32 is better than Uno for SPI flash
- **For I2C**: Need pull-ups

### Still Not Working?

1. Open issue on GitHub with:
   - OS and Python version
   - Arduino board type
   - Full log from LOG tab (copy/paste)
   - What you see in Device Manager / `ls /dev/tty*`
   - Photo of wiring

2. Try the CLI tool: `python tools/read_test.py COM5 --protocol avr` and paste output

3. Try Arduino IDE Serial Monitor at 115200 baud, send PING command manually? Our firmware should respond PONG to framed PING, but Serial Monitor sends ASCII, not binary, so not easy. Better to use CLI tool.
