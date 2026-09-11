# Wiring Diagrams - Universal Programmer

## Overview

The Universal Programmer uses an Arduino (Uno/Nano/Mega or ESP32) as the hardware interface.
Three protocols are supported with different wiring.

---

## 1. AVR ISP Wiring (ATmega, ATtiny)

### Arduino Uno / Nano to Target AVR

```
Arduino (Programmer)        Target AVR
--------------------        ------------
Pin 10 (RESET)  --------->  RESET (Pin 1 on ATmega328P)
Pin 11 (MOSI)   --------->  MOSI (Pin 17 on ATmega328P)
Pin 12 (MISO)   <---------  MISO (Pin 18 on ATmega328P)
Pin 13 (SCK)    --------->  SCK  (Pin 19 on ATmega328P)
5V              --------->  VCC
GND             --------->  GND

Optional:
Pin 7  -> Programming LED (with 330R to GND)
Pin 8  -> Error LED
Pin 6  -> Heartbeat LED
```

### ATmega328P Pinout (DIP28)

```
          +---U---+
  RESET - |1    28| - PC5
  PD0   - |2    27| - PC4
  PD1   - |3    26| - PC3
  PD2   - |4    25| - PC2
  PD3   - |5    24| - PC1
  PD4   - |6    23| - PC0
  VCC   - |7    22| - GND
  GND   - |8    21| - AREF
  XTAL1 - |9    20| - AVCC
  XTAL2 - |10   19| - PB5 (SCK)
  PD5   - |11   18| - PB4 (MISO)
  PD6   - |12   17| - PB3 (MOSI)
  PD7   - |13   16| - PB2
  PB0   - |14   15| - PB1
          +-------+
```

### ATtiny85 Wiring

```
Arduino             ATtiny85
-------             --------
Pin 10 (RESET)  ->  Pin 1 (RESET)
Pin 11 (MOSI)   ->  Pin 5 (MOSI / PB0)
Pin 12 (MISO)   <-  Pin 6 (MISO / PB1)
Pin 13 (SCK)    ->  Pin 7 (SCK / PB2)
5V              ->  Pin 8 (VCC)
GND             ->  Pin 4 (GND)

IMPORTANT for ATtiny85:
- Use slow SPI clock (firmware defaults to ~166kHz which is safe for 1MHz internal clock)
- ATtiny85 datasheet: SPI clock must be < 1/6 of CPU clock
- If ATtiny runs at 1MHz, SPI must be <166kHz (we use 166kHz)
- Add 10uF capacitor between Arduino RESET and GND to prevent auto-reset when using Arduino as ISP
  (or use 120R resistor)
```

### ISP Header (6-pin)

Standard 6-pin ISP header on target board:

```
  MISO  1 o--o 2 VCC
  SCK   3 o--o 4 MOSI
  RESET 5 o--o 6 GND
```

Connect to Arduino:

```
ISP Pin 1 (MISO)  -> Arduino Pin 12
ISP Pin 2 (VCC)   -> Arduino 5V
ISP Pin 3 (SCK)   -> Arduino Pin 13
ISP Pin 4 (MOSI)  -> Arduino Pin 11
ISP Pin 5 (RESET) -> Arduino Pin 10
ISP Pin 6 (GND)   -> Arduino GND
```

---

## 2. SPI Memory Wiring (W25Qxx, 25Qxx)

### Arduino Uno to SPI Flash

```
Arduino             SPI Flash (W25Q32 etc, SOIC-8)
-------             ----------------------------
Pin 9  (CS)     ->  Pin 1 (/CS)
Pin 12 (MISO)   <-  Pin 2 (DO / MISO)
Pin 3.3V or 5V* ->  Pin 8 (VCC) + Pin 3 (/WP) + Pin 7 (/HOLD)
Pin 11 (MOSI)   ->  Pin 5 (DI / MOSI)
Pin 13 (SCK)    ->  Pin 6 (CLK)
GND             ->  Pin 4 (GND)

* IMPORTANT: Many SPI flashes are 3.3V only!
  - W25Q series: 2.7V-3.6V, NOT 5V tolerant
  - Use level shifter or 3.3V Arduino (or ESP32)
  - For 5V Arduino, use voltage divider or level shifter for MOSI, SCK, CS
  - MISO from flash to Arduino is 3.3V, which is usually OK for 5V Arduino as HIGH threshold is ~3V
  - Best: Use ESP32 (3.3V) or Arduino with 3.3V output

SOIC-8 Pinout (W25Qxx):

      +---U---+
 /CS -|1    8|- VCC
  DO -|2    7|- /HOLD
 /WP -|3    6|- CLK
 GND -|4    5|- DI
      +-------+
```

### ESP32 to SPI Flash (Recommended for 3.3V)

```
ESP32               SPI Flash
-----               ---------
GPIO 15 (CS)    ->  /CS (Pin 1)
GPIO 19 (MISO)  <-  DO  (Pin 2)
3.3V            ->  VCC (Pin 8), /WP (Pin 3), /HOLD (Pin 7)
GPIO 23 (MOSI)  ->  DI  (Pin 5)
GPIO 18 (SCK)   ->  CLK (Pin 6)
GND             ->  GND (Pin 4)
```

---

## 3. I2C Memory Wiring (24Cxx EEPROM)

### Arduino Uno to 24Cxx

```
Arduino             24Cxx (SOIC-8 / DIP-8)
-------             -----------------------
A4 (SDA)        ->  Pin 5 (SDA) + 4.7k pull-up to VCC
A5 (SCL)        ->  Pin 6 (SCL) + 4.7k pull-up to VCC
5V or 3.3V*     ->  Pin 8 (VCC)
GND             ->  Pin 4 (GND)
                    Pin 1,2,3 (A0,A1,A2) -> GND (sets address 0x50)
                    Pin 7 (WP) -> GND (write enable)

* 24Cxx can be 5V or 3.3V depending on part, check datasheet
  Most are 1.8V-5.5V wide range, so 5V Arduino OK

SOIC-8 / DIP-8 Pinout (24Cxx):

      +---U---+
  A0 -|1    8|- VCC
  A1 -|2    7|- WP
  A2 -|3    6|- SCL
 GND -|4    5|- SDA
      +-------+
```

### ESP32 to 24Cxx

```
ESP32               24Cxx
-----               -----
GPIO 21 (SDA)   ->  SDA (Pin 5) + 4.7k pull-up to 3.3V
GPIO 22 (SCL)   ->  SCL (Pin 6) + 4.7k pull-up to 3.3V
3.3V            ->  VCC (Pin 8)
GND             ->  GND (Pin 4), A0,A1,A2 (Pins 1,2,3), WP (Pin 7)
```

### I2C Address

24Cxx address is 0x50-0x57 depending on A0,A1,A2 pins:

```
A2 A1 A0 | Address
---------+--------
 0  0  0 | 0x50 (most common)
 0  0  1 | 0x51
 0  1  0 | 0x52
 ...
 1  1  1 | 0x57
```

All grounded = 0x50 (default in software).

---

## 4. Power Supply Notes

- **AVR Target**: Can be powered from Arduino 5V (if target is 5V) or external 3.3V/5V. Ensure common GND.
- **SPI Flash**: Usually 3.3V. Use ESP32 or 3.3V Arduino, or level shifter.
- **I2C EEPROM**: Usually wide voltage (1.8-5.5V), check datasheet.

### Decoupling

Add 100nF ceramic capacitor close to target VCC/GND for stability.

---

## 5. ESP32 Specific Wiring

ESP32 is recommended for SPI flash because it's 3.3V native.

```
ESP32 DevKit:

  GPIO 5  -> AVR RESET
  GPIO 15 -> SPI Flash CS
  GPIO 23 -> MOSI
  GPIO 19 -> MISO
  GPIO 18 -> SCK
  GPIO 21 -> SDA (I2C)
  GPIO 22 -> SCL (I2C)
  GPIO 2  -> Heartbeat LED (built-in)
  3.3V    -> VCC for SPI flash and I2C
  GND     -> Common GND

Note: ESP32 is 3.3V only, do NOT connect 5V to its pins!
If target AVR is 5V, use level shifter or resistor divider.
```

---

## 6. Safety

- Always connect GND first
- Double-check VCC voltage (3.3V vs 5V)
- For SPI flash, never apply 5V if chip is 3.3V only
- Use current-limited supply if possible
- Add pull-up resistors for I2C (4.7k to VCC)
- For AVR ISP, ensure target has clock source (crystal or internal RC)

---

## 7. Example Breadboard Layout

```
[Arduino Uno]                 [Target ATmega328P on breadboard]
                                                             +---+
Pin 10 ---[1k]--- RESET  ----- Pin 1 (RESET)  --------------|   |
Pin 11 --------- MOSI   ----- Pin 17 (MOSI)  --------------|   |
Pin 12 --------- MISO   ----- Pin 18 (MISO)  --------------|   |
Pin 13 --------- SCK    ----- Pin 19 (SCK)   --------------|   |
5V     --------- VCC    ----- Pin 7 (VCC) + 100nF to GND --|   |
GND    --------- GND    ----- Pin 8 (GND)  ----------------|   |
                                                             +---+
```

---

## 8. Testing Wiring

1. Power on Arduino, upload universal_programmer.ino
2. Connect target with power OFF
3. Power on, open Universal Programmer GUI
4. Select COM port, CONNECT
5. Select protocol, click DETECT
6. If detection fails:
   - Check wiring continuity with multimeter
   - Check VCC voltage
   - Check GND common
   - For AVR, check if target has clock (fuses)
   - For SPI, check CS is correct and chip is 3.3V powered
   - For I2C, check pull-ups and address
