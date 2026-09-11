#!/usr/bin/env python3
"""
CLI test tool for Universal Programmer
Demonstrates critical workflow: READ -> STORE -> DISPLAY -> SAVE
Works without GUI, useful for testing hardware
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hardware.serial_manager import SerialManager
from hardware.arduino_interface import ArduinoInterface
from protocols.avr_isp import AVRISPProtocol
from protocols.spi_memory import SPIMemoryProtocol
from protocols.i2c_memory import I2CMemoryProtocol
from memory.bin_manager import BinManager
import hashlib
import time

def progress_callback(percent, message):
    print(f"[{percent:3d}%] {message}")

def test_avr(port, baud=115200):
    print(f"\n=== Testing AVR ISP on {port} ===")
    sm = SerialManager()
    try:
        sm.connect(port, baud)
        print(f"Connected to {port}")

        iface = ArduinoInterface(sm)
        time.sleep(0.5)

        version = iface.get_version()
        print(f"Firmware version: {version}")

        proto = AVRISPProtocol(iface)
        proto.connect()
        print("Entered programming mode")

        info = proto.detect()
        print(f"Detected: {info}")
        print(f"Signature: {info.get('signature')}")
        print(f"Device: {info.get('name')}")
        print(f"Flash size: {info.get('flash_size')}")

        # Read flash
        print("\nReading flash...")
        data = proto.read("flash", progress_callback=progress_callback)
        print(f"Read {len(data)} bytes")
        print(f"SHA256: {hashlib.sha256(data).hexdigest()}")
        print(f"First 32 bytes: {data[:32].hex()}")

        # Save
        bm = BinManager()
        bm.save_bin("flash_read.bin", data)
        print("Saved to flash_read.bin")

        # Verify actual bytes are from device (not placeholder)
        # Check if data is not all same value
        if len(set(data)) == 1:
            print("WARNING: Data is all same byte, might be placeholder or erased chip")
        else:
            print("Data appears to be actual bytes from device (varied)")

        proto.close()
        sm.disconnect()
        print("AVR test completed successfully")

    except Exception as e:
        print(f"AVR test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            sm.disconnect()
        except:
            pass

def test_spi(port, baud=115200):
    print(f"\n=== Testing SPI Memory on {port} ===")
    sm = SerialManager()
    try:
        sm.connect(port, baud)
        iface = ArduinoInterface(sm)
        time.sleep(0.5)

        proto = SPIMemoryProtocol(iface)
        proto.connect()

        info = proto.detect()
        print(f"Detected: {info}")

        print("\nReading SPI flash...")
        data = proto.read("flash", length=4096, progress_callback=progress_callback)
        print(f"Read {len(data)} bytes")
        print(f"SHA256: {hashlib.sha256(data).hexdigest()}")

        bm = BinManager()
        bm.save_bin("spi_read.bin", data)
        print("Saved to spi_read.bin")

        sm.disconnect()
        print("SPI test completed")

    except Exception as e:
        print(f"SPI test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            sm.disconnect()
        except:
            pass

def test_i2c(port, baud=115200):
    print(f"\n=== Testing I2C Memory on {port} ===")
    sm = SerialManager()
    try:
        sm.connect(port, baud)
        iface = ArduinoInterface(sm)
        time.sleep(0.5)

        proto = I2CMemoryProtocol(iface)
        proto.connect()

        found = proto.scan()
        print(f"I2C scan found: {[hex(a) for a in found]}")

        info = proto.detect()
        print(f"Detected: {info}")

        print("\nReading I2C EEPROM...")
        data = proto.read("eeprom", length=1024, progress_callback=progress_callback)
        print(f"Read {len(data)} bytes")
        print(f"SHA256: {hashlib.sha256(data).hexdigest()}")

        bm = BinManager()
        bm.save_bin("i2c_read.bin", data)
        print("Saved to i2c_read.bin")

        sm.disconnect()
        print("I2C test completed")

    except Exception as e:
        print(f"I2C test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            sm.disconnect()
        except:
            pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Universal Programmer CLI Test")
    parser.add_argument("port", help="COM port (e.g., COM5 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--protocol", choices=["avr", "spi", "i2c", "all"], default="avr", help="Protocol to test")
    args = parser.parse_args()

    if args.protocol == "avr":
        test_avr(args.port, args.baud)
    elif args.protocol == "spi":
        test_spi(args.port, args.baud)
    elif args.protocol == "i2c":
        test_i2c(args.port, args.baud)
    elif args.protocol == "all":
        test_avr(args.port, args.baud)
        test_spi(args.port, args.baud)
        test_i2c(args.port, args.baud)
