/*
 * Universal Programmer Firmware
 * Professional Grade - Supports AVR ISP, SPI Memory, I2C Memory
 *
 * Based on ArduinoISP sketch (Copyright 2008-2011 Randall Bohn)
 * Preserves original AVR ISP functionality (STK500v1 compatible)
 * Extends with robust framed binary protocol for GUI
 *
 * Hardware:
 *   Arduino Uno / Nano / Mega / ESP32
 *
 * Pinout (Arduino Uno/Nano):
 *   Pin 10 - RESET for AVR target (active low)
 *   Pin 9  - CS for SPI Memory (active low)
 *   Pin 11 - MOSI (to target MOSI / SPI DI)
 *   Pin 12 - MISO (to target MISO / SPI DO)
 *   Pin 13 - SCK (to target SCK / SPI CLK)
 *   A4/SDA - I2C SDA
 *   A5/SCL - I2C SCL
 *   Pin 7  - Programming LED
 *   Pin 8  - Error LED
 *   Pin 9  - Heartbeat LED (if not used as SPI CS, else use 6)
 *
 * Pinout (ESP32):
 *   GPIO 5  - AVR RESET
 *   GPIO 15 - SPI Memory CS
 *   GPIO 23 - MOSI
 *   GPIO 19 - MISO
 *   GPIO 18 - SCK
 *   GPIO 21 - SDA
 *   GPIO 22 - SCL
 *   GPIO 2  - Built-in LED (heartbeat)
 *
 * Protocol:
 *   Framed binary protocol:
 *     [0xAA][0x55][CMD][SEQ][LEN_L][LEN_H][PAYLOAD...][CRC_L][CRC_H][0x55][0xAA]
 *     CRC16-CCITT over CMD+SEQ+LEN+PAYLOAD
 *     Response: CMD | 0x80, first payload byte = status
 *
 *   STK500v1 compatible (for avrdude):
 *     Detects STK commands (0x30 etc) and handles as ArduinoISP
 *
 * Commands:
 *   0x01 GET_VERSION
 *   0x02 GET_STATUS
 *   0x03 SELECT_PROTOCOL
 *   0x10 AVR_ENTER_PROG
 *   0x11 AVR_EXIT_PROG
 *   0x12 AVR_READ_SIGNATURE
 *   0x13 AVR_READ_FLASH
 *   0x14 AVR_READ_EEPROM
 *   0x15 AVR_WRITE_FLASH
 *   0x16 AVR_WRITE_EEPROM
 *   0x17 AVR_ERASE
 *   0x18 AVR_DETECT
 *   0x20 SPI_DETECT (JEDEC ID)
 *   0x21 SPI_READ
 *   0x22 SPI_WRITE
 *   0x23 SPI_ERASE
 *   0x24 SPI_GET_STATUS
 *   0x25 SPI_WRITE_ENABLE
 *   0x30 I2C_SCAN
 *   0x31 I2C_READ
 *   0x32 I2C_WRITE
 *   0x33 I2C_DETECT
 *   0x40 PING
 *   0x41 RESET_TARGET
 *   0x42 SET_CONFIG
 *
 * Author: Universal Programmer Project
 * Version: 1.0.0
 * License: BSD (compatible with ArduinoISP)
 */

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

// =============================================================================
// Configuration
// =============================================================================

#define FIRMWARE_VERSION "Universal Programmer v1.0.0"
#define FIRMWARE_VERSION_MAJOR 1
#define FIRMWARE_VERSION_MINOR 0
#define FIRMWARE_VERSION_PATCH 0

#define BAUDRATE 115200

// Protocol selection
#define PROTOCOL_NONE 0
#define PROTOCOL_AVR_ISP 1
#define PROTOCOL_SPI_MEM 2
#define PROTOCOL_I2C_MEM 3

// Command definitions
#define CMD_GET_VERSION 0x01
#define CMD_GET_STATUS 0x02
#define CMD_SELECT_PROTOCOL 0x03

#define CMD_AVR_ENTER_PROG 0x10
#define CMD_AVR_EXIT_PROG 0x11
#define CMD_AVR_READ_SIGNATURE 0x12
#define CMD_AVR_READ_FLASH 0x13
#define CMD_AVR_READ_EEPROM 0x14
#define CMD_AVR_WRITE_FLASH 0x15
#define CMD_AVR_WRITE_EEPROM 0x16
#define CMD_AVR_ERASE 0x17
#define CMD_AVR_DETECT 0x18

#define CMD_SPI_DETECT 0x20
#define CMD_SPI_READ 0x21
#define CMD_SPI_WRITE 0x22
#define CMD_SPI_ERASE 0x23
#define CMD_SPI_GET_STATUS 0x24
#define CMD_SPI_WRITE_ENABLE 0x25

#define CMD_I2C_SCAN 0x30
#define CMD_I2C_READ 0x31
#define CMD_I2C_WRITE 0x32
#define CMD_I2C_DETECT 0x33

#define CMD_PING 0x40
#define CMD_RESET_TARGET 0x41
#define CMD_SET_CONFIG 0x42

// Status codes
#define STATUS_OK 0x00
#define STATUS_ERROR_GENERIC 0x01
#define STATUS_ERROR_NO_TARGET 0x02
#define STATUS_ERROR_TIMEOUT 0x03
#define STATUS_ERROR_INVALID_CMD 0x04
#define STATUS_ERROR_INVALID_PARAM 0x05
#define STATUS_ERROR_NOT_SUPPORTED 0x06
#define STATUS_ERROR_VERIFY_FAILED 0x07
#define STATUS_ERROR_BUSY 0x08

// STK500 definitions (preserved from ArduinoISP)
#define STK_OK 0x10
#define STK_FAILED 0x11
#define STK_UNKNOWN 0x12
#define STK_INSYNC 0x14
#define STK_NOSYNC 0x15
#define CRC_EOP 0x20

// =============================================================================
// Pin Definitions - Support both AVR Arduino and ESP32
// =============================================================================

#ifdef ARDUINO_ARCH_ESP32
  // ESP32 pinout
  #define PIN_AVR_RESET 5
  #define PIN_SPI_MEM_CS 15
  #define PIN_MOSI 23
  #define PIN_MISO 19
  #define PIN_SCK 18
  #define PIN_SDA 21
  #define PIN_SCL 22
  #define LED_HB 2
  #define LED_ERR 4
  #define LED_PMODE 16
#else
  // Arduino Uno/Nano/Mega
  #define PIN_AVR_RESET 10
  #define PIN_SPI_MEM_CS 9
  #define LED_HB 6
  #define LED_ERR 8
  #define LED_PMODE 7
  #ifndef PIN_MOSI
    #define PIN_MOSI MOSI
  #endif
  #ifndef PIN_MISO
    #define PIN_MISO MISO
  #endif
  #ifndef PIN_SCK
    #define PIN_SCK SCK
  #endif
#endif

// SPI Clock - slow enough for ATtiny85 @ 1MHz
#define SPI_CLOCK (1000000/6)

// =============================================================================
// Global Variables
// =============================================================================

// Protocol state
uint8_t current_protocol = PROTOCOL_NONE;
uint8_t error_count = 0;
uint8_t pmode = 0;
unsigned int here; // address for STK500
uint8_t buff[512]; // buffer for STK and framed protocol

// For framed protocol
uint8_t seq_num = 0;

// SPI settings
SPISettings spi_settings(SPI_CLOCK, MSBFIRST, SPI_MODE0);

// Parameter structure from ArduinoISP
#define beget16(addr) (*addr * 256 + *(addr+1) )
typedef struct param {
  uint8_t devicecode;
  uint8_t revision;
  uint8_t progtype;
  uint8_t parmode;
  uint8_t polling;
  uint8_t selftimed;
  uint8_t lockbytes;
  uint8_t fusebytes;
  uint8_t flashpoll;
  uint16_t eeprompoll;
  uint16_t pagesize;
  uint16_t eepromsize;
  uint32_t flashsize;
} parameter;

parameter param;

// =============================================================================
// Utility Functions
// =============================================================================

uint16_t crc16_ccitt(const uint8_t *data, uint16_t len) {
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t j = 0; j < 8; j++) {
      if (crc & 0x8000) {
        crc = (crc << 1) ^ 0x1021;
      } else {
        crc <<= 1;
      }
    }
  }
  return crc & 0xFFFF;
}

void pulse_led(int pin, int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(50);
    digitalWrite(pin, LOW);
    delay(50);
  }
}

// =============================================================================
// Framed Protocol Implementation
// =============================================================================

#define FRAME_HEADER1 0xAA
#define FRAME_HEADER2 0x55
#define FRAME_FOOTER1 0x55
#define FRAME_FOOTER2 0xAA

#define MAX_PAYLOAD 512
#define RX_BUFFER_SIZE 1024

// Send framed response
void send_response(uint8_t cmd, uint8_t seq, uint8_t status, const uint8_t *payload, uint16_t payload_len) {
  // Build full payload with status byte first
  uint16_t total_len = payload_len + 1;
  if (total_len > MAX_PAYLOAD) total_len = MAX_PAYLOAD;

  uint8_t frame[1024];
  uint16_t idx = 0;

  frame[idx++] = FRAME_HEADER1;
  frame[idx++] = FRAME_HEADER2;
  frame[idx++] = cmd | 0x80; // Response cmd = request | 0x80
  frame[idx++] = seq;
  frame[idx++] = total_len & 0xFF;
  frame[idx++] = (total_len >> 8) & 0xFF;
  frame[idx++] = status;

  if (payload && payload_len > 0) {
    uint16_t copy_len = payload_len;
    if (copy_len > MAX_PAYLOAD - 1) copy_len = MAX_PAYLOAD - 1;
    memcpy(&frame[idx], payload, copy_len);
    idx += copy_len;
  }

  // Calculate CRC over CMD+SEQ+LEN+PAYLOAD (including status)
  uint8_t crc_data[600];
  crc_data[0] = cmd | 0x80;
  crc_data[1] = seq;
  crc_data[2] = total_len & 0xFF;
  crc_data[3] = (total_len >> 8) & 0xFF;
  crc_data[4] = status;
  if (payload && payload_len > 0) {
    uint16_t copy_len = payload_len;
    if (copy_len > MAX_PAYLOAD - 1) copy_len = MAX_PAYLOAD - 1;
    memcpy(&crc_data[5], payload, copy_len);
  }
  uint16_t crc = crc16_ccitt(crc_data, 5 + (payload_len > MAX_PAYLOAD-1 ? MAX_PAYLOAD-1 : payload_len));

  frame[idx++] = crc & 0xFF;
  frame[idx++] = (crc >> 8) & 0xFF;
  frame[idx++] = FRAME_FOOTER1;
  frame[idx++] = FRAME_FOOTER2;

  Serial.write(frame, idx);
  Serial.flush();
}

void send_error(uint8_t cmd, uint8_t seq, uint8_t error_code) {
  send_response(cmd, seq, error_code, NULL, 0);
}

void send_ok(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len) {
  send_response(cmd, seq, STATUS_OK, payload, len);
}

// Try to parse a framed packet from serial
// Returns true if packet parsed, false if need more data or invalid
// This is called when we have seen 0xAA 0x55
bool try_parse_framed_packet() {
  // Need at least header(2) + cmd(1) + seq(1) + len(2) + crc(2) + footer(2) = 10
  if (Serial.available() < 8) return false; // we already consumed 2 header bytes

  // Peek next bytes without consuming? We'll read them
  // We have already consumed 0xAA 0x55, now read CMD, SEQ, LEN
  unsigned long timeout = millis() + 1000;
  while (Serial.available() < 4) {
    if (millis() > timeout) return false;
  }

  uint8_t cmd = Serial.read();
  uint8_t seq = Serial.read();
  uint8_t len_l = Serial.read();
  uint8_t len_h = Serial.read();
  uint16_t payload_len = len_l | (len_h << 8);

  if (payload_len > MAX_PAYLOAD) {
    // Invalid length, flush and return
    while (Serial.available()) Serial.read();
    return true; // consumed invalid packet
  }

  // Wait for payload + crc + footer
  uint16_t need = payload_len + 2 + 2;
  timeout = millis() + 2000;
  while (Serial.available() < need) {
    if (millis() > timeout) {
      return false;
    }
  }

  uint8_t payload[MAX_PAYLOAD];
  if (payload_len > 0) {
    Serial.readBytes(payload, payload_len);
  }

  uint8_t crc_l = Serial.read();
  uint8_t crc_h = Serial.read();
  uint16_t received_crc = crc_l | (crc_h << 8);

  uint8_t footer1 = Serial.read();
  uint8_t footer2 = Serial.read();

  if (footer1 != FRAME_FOOTER1 || footer2 != FRAME_FOOTER2) {
    // Bad footer, discard
    return true;
  }

  // Validate CRC
  uint8_t crc_data[600];
  crc_data[0] = cmd;
  crc_data[1] = seq;
  crc_data[2] = len_l;
  crc_data[3] = len_h;
  memcpy(&crc_data[4], payload, payload_len);
  uint16_t calc_crc = crc16_ccitt(crc_data, 4 + payload_len);

  if (calc_crc != received_crc) {
    // CRC mismatch, send error?
    // Don't send error for CRC mismatch to avoid loops, just ignore
    return true;
  }

  // Valid packet! Handle command
  // We'll process in a separate function
  extern void handle_framed_command(uint8_t cmd, uint8_t seq, uint8_t *payload, uint16_t len);
  handle_framed_command(cmd, seq, payload, payload_len);

  return true;
}

// =============================================================================
// AVR ISP Low-Level Functions (Preserved from ArduinoISP)
// =============================================================================

uint8_t spi_transaction(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
  SPI.transfer(a);
  SPI.transfer(b);
  SPI.transfer(c);
  return SPI.transfer(d);
}

void avr_reset_target(bool reset) {
  digitalWrite(PIN_AVR_RESET, reset ? LOW : HIGH); // Active low
}

bool avr_enter_progmode() {
  // Reset target
  digitalWrite(PIN_AVR_RESET, HIGH);
  pinMode(PIN_AVR_RESET, OUTPUT);
  SPI.begin();
  SPI.beginTransaction(spi_settings);

  digitalWrite(PIN_SCK, LOW);
  delay(20);

  avr_reset_target(true);
  delay(20);

  // Send programming enable: 0xAC 0x53 0x00 0x00, expect 0x53 in 3rd byte?
  // Actually we check if response is 0x53 or at least not 0x00/0xFF
  uint8_t resp = spi_transaction(0xAC, 0x53, 0x00, 0x00);
  // Second attempt
  if (resp != 0x53) {
    delay(20);
    resp = spi_transaction(0xAC, 0x53, 0x00, 0x00);
  }

  // If we get 0x00 or 0xFF, target not responding
  if (resp == 0x00 || resp == 0xFF) {
    return false;
  }

  pmode = 1;
  return true;
}

void avr_exit_progmode() {
  SPI.end();
  avr_reset_target(false);
  pinMode(PIN_AVR_RESET, INPUT);
  pmode = 0;
}

uint8_t avr_read_signature_byte(uint8_t addr) {
  return spi_transaction(0x30, 0x00, addr, 0x00);
}

bool avr_read_signature(uint8_t *sig) {
  if (!pmode) return false;
  sig[0] = avr_read_signature_byte(0);
  sig[1] = avr_read_signature_byte(1);
  sig[2] = avr_read_signature_byte(2);
  return true;
}

uint8_t avr_read_flash_byte(uint32_t addr, bool high) {
  uint8_t cmd = high ? 0x28 : 0x20;
  return spi_transaction(cmd, (addr >> 8) & 0xFF, addr & 0xFF, 0x00);
}

bool avr_read_flash(uint32_t addr, uint8_t *buf, uint16_t len) {
  if (!pmode) return false;
  for (uint16_t i = 0; i < len; i++) {
    uint32_t word_addr = (addr + i) >> 1;
    bool high = (addr + i) & 1;
    buf[i] = avr_read_flash_byte(word_addr, high);
  }
  return true;
}

uint8_t avr_read_eeprom_byte(uint16_t addr) {
  return spi_transaction(0xA0, (addr >> 8) & 0xFF, addr & 0xFF, 0x00);
}

bool avr_read_eeprom(uint16_t addr, uint8_t *buf, uint16_t len) {
  if (!pmode) return false;
  for (uint16_t i = 0; i < len; i++) {
    buf[i] = avr_read_eeprom_byte(addr + i);
  }
  return true;
}

bool avr_write_flash_page(uint32_t addr, uint8_t *data, uint16_t len) {
  if (!pmode) return false;
  // addr is byte address, but page is word address
  // Load page buffer
  for (uint16_t i = 0; i < len; i++) {
    uint32_t word_addr = (addr + i) >> 1;
    bool high = (addr + i) & 1;
    uint8_t cmd = high ? 0x48 : 0x40;
    spi_transaction(cmd, (word_addr >> 8) & 0xFF, word_addr & 0xFF, data[i]);
    delayMicroseconds(100);
  }
  // Write page
  uint32_t page_addr = addr >> 1;
  spi_transaction(0x4C, (page_addr >> 8) & 0xFF, page_addr & 0xFF, 0x00);
  delay(10); // Wait for page write
  return true;
}

bool avr_write_eeprom_byte(uint16_t addr, uint8_t data) {
  if (!pmode) return false;
  spi_transaction(0xC0, (addr >> 8) & 0xFF, addr & 0xFF, data);
  delay(10);
  return true;
}

bool avr_write_eeprom(uint16_t addr, uint8_t *data, uint16_t len) {
  for (uint16_t i = 0; i < len; i++) {
    if (!avr_write_eeprom_byte(addr + i, data[i])) return false;
  }
  return true;
}

bool avr_chip_erase() {
  if (!pmode) return false;
  spi_transaction(0xAC, 0x80, 0x00, 0x00);
  delay(100);
  return true;
}

// =============================================================================
// SPI Memory Functions
// =============================================================================

void spi_mem_select(bool select) {
  digitalWrite(PIN_SPI_MEM_CS, select ? LOW : HIGH);
}

uint8_t spi_mem_transfer(uint8_t data) {
  return SPI.transfer(data);
}

void spi_mem_init() {
  pinMode(PIN_SPI_MEM_CS, OUTPUT);
  spi_mem_select(false);
  if (current_protocol != PROTOCOL_AVR_ISP || !pmode) {
    SPI.begin();
  }
  SPI.beginTransaction(spi_settings);
}

uint8_t spi_mem_read_status() {
  spi_mem_select(true);
  spi_mem_transfer(0x05);
  uint8_t status = spi_mem_transfer(0x00);
  spi_mem_select(false);
  return status;
}

void spi_mem_write_enable() {
  spi_mem_select(true);
  spi_mem_transfer(0x06);
  spi_mem_select(false);
  delayMicroseconds(10);
}

bool spi_mem_wait_ready(uint16_t timeout_ms = 5000) {
  unsigned long start = millis();
  while (millis() - start < timeout_ms) {
    if ((spi_mem_read_status() & 0x01) == 0) return true;
    delay(1);
  }
  return false;
}

bool spi_mem_read_jedec(uint8_t *buf) {
  spi_mem_init();
  spi_mem_select(true);
  spi_mem_transfer(0x9F);
  buf[0] = spi_mem_transfer(0x00);
  buf[1] = spi_mem_transfer(0x00);
  buf[2] = spi_mem_transfer(0x00);
  spi_mem_select(false);
  // Some devices return 0x00 0x00 0x00 if not connected
  if (buf[0] == 0x00 && buf[1] == 0x00 && buf[2] == 0x00) return false;
  if (buf[0] == 0xFF && buf[1] == 0xFF && buf[2] == 0xFF) return false;
  return true;
}

bool spi_mem_read(uint32_t addr, uint8_t *buf, uint16_t len) {
  spi_mem_init();
  spi_mem_select(true);
  spi_mem_transfer(0x03);
  spi_mem_transfer((addr >> 16) & 0xFF);
  spi_mem_transfer((addr >> 8) & 0xFF);
  spi_mem_transfer(addr & 0xFF);
  for (uint16_t i = 0; i < len; i++) {
    buf[i] = spi_mem_transfer(0x00);
  }
  spi_mem_select(false);
  return true;
}

bool spi_mem_write(uint32_t addr, uint8_t *data, uint16_t len) {
  spi_mem_init();
  uint16_t offset = 0;
  while (offset < len) {
    uint16_t chunk = len - offset;
    // Don't cross page boundary (256 bytes)
    uint16_t page_offset = (addr + offset) % 256;
    uint16_t space_in_page = 256 - page_offset;
    if (chunk > space_in_page) chunk = space_in_page;

    spi_mem_write_enable();
    spi_mem_select(true);
    spi_mem_transfer(0x02);
    spi_mem_transfer(((addr + offset) >> 16) & 0xFF);
    spi_mem_transfer(((addr + offset) >> 8) & 0xFF);
    spi_mem_transfer((addr + offset) & 0xFF);
    for (uint16_t i = 0; i < chunk; i++) {
      spi_mem_transfer(data[offset + i]);
    }
    spi_mem_select(false);

    if (!spi_mem_wait_ready()) return false;
    offset += chunk;
  }
  return true;
}

bool spi_mem_erase(uint8_t type, uint32_t addr) {
  spi_mem_init();
  spi_mem_write_enable();
  spi_mem_select(true);
  if (type == 0xC7) {
    // Chip erase
    spi_mem_transfer(0xC7);
  } else if (type == 0x20) {
    // Sector erase 4KB
    spi_mem_transfer(0x20);
    spi_mem_transfer((addr >> 16) & 0xFF);
    spi_mem_transfer((addr >> 8) & 0xFF);
    spi_mem_transfer(addr & 0xFF);
  } else if (type == 0xD8) {
    // Block erase 64KB
    spi_mem_transfer(0xD8);
    spi_mem_transfer((addr >> 16) & 0xFF);
    spi_mem_transfer((addr >> 8) & 0xFF);
    spi_mem_transfer(addr & 0xFF);
  } else {
    spi_mem_select(false);
    return false;
  }
  spi_mem_select(false);

  // Wait for erase - chip erase can take several seconds
  uint16_t timeout = (type == 0xC7) ? 10000 : 3000;
  return spi_mem_wait_ready(timeout);
}

// =============================================================================
// I2C Memory Functions
// =============================================================================

void i2c_init() {
  Wire.begin();
  Wire.setClock(100000); // 100kHz
}

bool i2c_scan(uint8_t *found, uint8_t *count) {
  i2c_init();
  *count = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      found[*count] = addr;
      (*count)++;
      if (*count >= 32) break; // limit
    }
  }
  return *count > 0;
}

bool i2c_detect(uint8_t dev_addr) {
  i2c_init();
  Wire.beginTransmission(dev_addr);
  return Wire.endTransmission() == 0;
}

bool i2c_read(uint8_t dev_addr, uint16_t mem_addr, uint8_t addr_width, uint8_t *buf, uint16_t len) {
  i2c_init();
  Wire.beginTransmission(dev_addr);
  if (addr_width == 2) {
    Wire.write((mem_addr >> 8) & 0xFF);
  }
  Wire.write(mem_addr & 0xFF);
  if (Wire.endTransmission(false) != 0) return false;

  uint16_t offset = 0;
  while (offset < len) {
    uint16_t chunk = len - offset;
    if (chunk > 32) chunk = 32; // Wire buffer limit

    uint8_t requested = Wire.requestFrom(dev_addr, chunk);
    if (requested == 0) return false;

    for (uint8_t i = 0; i < requested && offset < len; i++) {
      buf[offset++] = Wire.read();
    }
  }
  return true;
}

bool i2c_write(uint8_t dev_addr, uint16_t mem_addr, uint8_t addr_width, uint8_t *data, uint16_t len) {
  i2c_init();
  uint16_t offset = 0;
  while (offset < len) {
    // Page write handling - don't cross page boundary
    // For simplicity, assume 32-byte pages for now, but caller handles paging
    uint16_t chunk = len - offset;
    if (chunk > 30) chunk = 30; // Leave room for addr bytes

    Wire.beginTransmission(dev_addr);
    if (addr_width == 2) {
      Wire.write((mem_addr + offset) >> 8 & 0xFF);
    }
    Wire.write((mem_addr + offset) & 0xFF);
    for (uint16_t i = 0; i < chunk; i++) {
      Wire.write(data[offset + i]);
    }
    if (Wire.endTransmission() != 0) return false;

    offset += chunk;
    delay(10); // Write cycle time
  }
  return true;
}

// =============================================================================
// Framed Command Handler
// =============================================================================

void handle_framed_command(uint8_t cmd, uint8_t seq, uint8_t *payload, uint16_t len) {
  uint8_t resp_buf[512];
  uint16_t resp_len = 0;

  switch (cmd) {
    case CMD_GET_VERSION: {
      const char *ver = FIRMWARE_VERSION;
      send_ok(cmd, seq, (uint8_t*)ver, strlen(ver));
      break;
    }

    case CMD_GET_STATUS: {
      uint32_t status = 0;
      if (pmode) status |= 0x01;
      status |= (current_protocol << 8);
      status |= (error_count << 16);
      resp_buf[0] = status & 0xFF;
      resp_buf[1] = (status >> 8) & 0xFF;
      resp_buf[2] = (status >> 16) & 0xFF;
      resp_buf[3] = (status >> 24) & 0xFF;
      send_ok(cmd, seq, resp_buf, 4);
      break;
    }

    case CMD_SELECT_PROTOCOL: {
      if (len < 1) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint8_t proto = payload[0];
      if (proto >= PROTOCOL_NONE && proto <= PROTOCOL_I2C_MEM) {
        // Exit previous protocol
        if (current_protocol == PROTOCOL_AVR_ISP && pmode) {
          avr_exit_progmode();
        }
        current_protocol = proto;
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
      }
      break;
    }

    case CMD_AVR_ENTER_PROG: {
      if (avr_enter_progmode()) {
        digitalWrite(LED_PMODE, HIGH);
        send_ok(cmd, seq, NULL, 0);
      } else {
        digitalWrite(LED_ERR, HIGH);
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
        delay(200);
        digitalWrite(LED_ERR, LOW);
      }
      break;
    }

    case CMD_AVR_EXIT_PROG: {
      avr_exit_progmode();
      digitalWrite(LED_PMODE, LOW);
      send_ok(cmd, seq, NULL, 0);
      break;
    }

    case CMD_AVR_READ_SIGNATURE: {
      uint8_t sig[3];
      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }
      if (avr_read_signature(sig)) {
        send_ok(cmd, seq, sig, 3);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_AVR_DETECT: {
      uint8_t sig[3];
      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }
      if (!avr_read_signature(sig)) {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
        break;
      }
      // Check for invalid signature
      if ((sig[0] == 0x00 && sig[1] == 0x00 && sig[2] == 0x00) ||
          (sig[0] == 0xFF && sig[1] == 0xFF && sig[2] == 0xFF)) {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
        break;
      }
      // Return signature + dummy flash/eeprom sizes (will be looked up on PC side)
      resp_buf[0] = sig[0];
      resp_buf[1] = sig[1];
      resp_buf[2] = sig[2];
      // For compatibility, add flash size as 32KB and eeprom 1KB if unknown
      resp_buf[3] = 32; resp_buf[4] = 0; // flash KB
      resp_buf[5] = 1; resp_buf[6] = 0;  // eeprom KB
      send_ok(cmd, seq, resp_buf, 7);
      break;
    }

    case CMD_AVR_READ_FLASH: {
      if (len < 6) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint32_t addr = payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24);
      uint16_t read_len = payload[4] | (payload[5] << 8);

      if (read_len > 256) read_len = 256;
      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }

      if (avr_read_flash(addr, resp_buf, read_len)) {
        send_ok(cmd, seq, resp_buf, read_len);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_AVR_READ_EEPROM: {
      if (len < 4) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint16_t addr = payload[0] | (payload[1] << 8);
      uint16_t read_len = payload[2] | (payload[3] << 8);
      if (read_len > 256) read_len = 256;

      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }

      if (avr_read_eeprom(addr, resp_buf, read_len)) {
        send_ok(cmd, seq, resp_buf, read_len);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_AVR_WRITE_FLASH: {
      if (len < 5) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint32_t addr = payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24);
      uint16_t data_len = len - 4;

      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }

      if (avr_write_flash_page(addr, &payload[4], data_len)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_AVR_WRITE_EEPROM: {
      if (len < 3) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint16_t addr = payload[0] | (payload[1] << 8);
      uint16_t data_len = len - 2;

      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }

      if (avr_write_eeprom(addr, &payload[2], data_len)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_AVR_ERASE: {
      if (!pmode) {
        if (!avr_enter_progmode()) {
          send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
          break;
        }
      }
      if (avr_chip_erase()) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_SPI_DETECT: {
      uint8_t jedec[3];
      if (spi_mem_read_jedec(jedec)) {
        send_ok(cmd, seq, jedec, 3);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_SPI_READ: {
      if (len < 6) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint32_t addr = payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24);
      uint16_t read_len = payload[4] | (payload[5] << 8);
      if (read_len > 256) read_len = 256;

      if (spi_mem_read(addr, resp_buf, read_len)) {
        send_ok(cmd, seq, resp_buf, read_len);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_SPI_WRITE: {
      if (len < 5) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint32_t addr = payload[0] | (payload[1] << 8) | (payload[2] << 16) | (payload[3] << 24);
      uint16_t data_len = len - 4;

      if (spi_mem_write(addr, &payload[4], data_len)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_SPI_ERASE: {
      if (len < 5) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint8_t type = payload[0];
      uint32_t addr = payload[1] | (payload[2] << 8) | (payload[3] << 16) | (payload[4] << 24);

      if (spi_mem_erase(type, addr)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_SPI_GET_STATUS: {
      uint8_t status = spi_mem_read_status();
      send_ok(cmd, seq, &status, 1);
      break;
    }

    case CMD_I2C_SCAN: {
      uint8_t found[32];
      uint8_t count = 0;
      i2c_scan(found, &count);
      send_ok(cmd, seq, found, count);
      break;
    }

    case CMD_I2C_DETECT: {
      if (len < 1) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint8_t dev_addr = payload[0];
      if (i2c_detect(dev_addr)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_I2C_READ: {
      if (len < 6) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint8_t dev_addr = payload[0];
      uint16_t mem_addr = payload[1] | (payload[2] << 8);
      uint8_t addr_width = payload[3];
      uint16_t read_len = payload[4] | (payload[5] << 8);
      if (read_len > 128) read_len = 128;

      if (i2c_read(dev_addr, mem_addr, addr_width, resp_buf, read_len)) {
        send_ok(cmd, seq, resp_buf, read_len);
      } else {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
      }
      break;
    }

    case CMD_I2C_WRITE: {
      if (len < 4) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      uint8_t dev_addr = payload[0];
      uint16_t mem_addr = payload[1] | (payload[2] << 8);
      uint8_t addr_width = payload[3];
      uint16_t data_len = len - 4;

      if (i2c_write(dev_addr, mem_addr, addr_width, &payload[4], data_len)) {
        send_ok(cmd, seq, NULL, 0);
      } else {
        send_error(cmd, seq, STATUS_ERROR_GENERIC);
      }
      break;
    }

    case CMD_PING: {
      const char *pong = "PONG";
      send_ok(cmd, seq, (uint8_t*)pong, 4);
      break;
    }

    case CMD_RESET_TARGET: {
      if (len < 1) {
        send_error(cmd, seq, STATUS_ERROR_INVALID_PARAM);
        break;
      }
      bool reset = payload[0] != 0;
      if (current_protocol == PROTOCOL_AVR_ISP) {
        avr_reset_target(reset);
      }
      send_ok(cmd, seq, NULL, 0);
      break;
    }

    default: {
      send_error(cmd, seq, STATUS_ERROR_INVALID_CMD);
      break;
    }
  }
}

// =============================================================================
// STK500v1 Compatibility (Preserved from ArduinoISP)
// =============================================================================

uint8_t getch() {
  while (!Serial.available());
  return Serial.read();
}

void fill_buff(int n) {
  for (int i = 0; i < n; i++) {
    buff[i] = getch();
  }
}

void empty_reply() {
  if (CRC_EOP == getch()) {
    Serial.print((char)STK_INSYNC);
    Serial.print((char)STK_OK);
  } else {
    error_count++;
    Serial.print((char)STK_NOSYNC);
  }
}

void breply(uint8_t b) {
  if (CRC_EOP == getch()) {
    Serial.print((char)STK_INSYNC);
    Serial.print((char)b);
    Serial.print((char)STK_OK);
  } else {
    error_count++;
    Serial.print((char)STK_NOSYNC);
  }
}

void get_version(uint8_t c) {
  switch (c) {
    case 0x80: breply(2); break; // HW version
    case 0x81: breply(1); break; // SW major
    case 0x82: breply(18); break; // SW minor
    case 0x93: breply('S'); break; // serial programmer
    default: breply(0);
  }
}

void set_parameters() {
  param.devicecode = buff[0];
  param.revision = buff[1];
  param.progtype = buff[2];
  param.parmode = buff[3];
  param.polling = buff[4];
  param.selftimed = buff[5];
  param.lockbytes = buff[6];
  param.fusebytes = buff[7];
  param.flashpoll = buff[8];
  param.eeprompoll = beget16(&buff[10]);
  param.pagesize = beget16(&buff[12]);
  param.eepromsize = beget16(&buff[14]);
  param.flashsize = buff[16] * 0x01000000 + buff[17] * 0x00010000 + buff[18] * 0x00000100 + buff[19];
}

void start_pmode() {
  SPI.begin();
  SPI.beginTransaction(spi_settings);
  pinMode(PIN_AVR_RESET, OUTPUT);
  digitalWrite(PIN_SCK, LOW);
  delay(20);
  avr_reset_target(true);
  delay(20);
  spi_transaction(0xAC, 0x53, 0x00, 0x00);
  pmode = 1;
}

void end_pmode() {
  SPI.end();
  avr_reset_target(false);
  pinMode(PIN_AVR_RESET, INPUT);
  pmode = 0;
}

bool avr_op_check() {
  if (!pmode) {
    error_count++;
    return false;
  }
  return true;
}

void universal() {
  uint8_t ch;
  fill_buff(4);
  ch = spi_transaction(buff[0], buff[1], buff[2], buff[3]);
  breply(ch);
}

void flash(uint8_t hilo, unsigned int addr, uint8_t data) {
  spi_transaction(0x40 + 8 * hilo, addr >> 8 & 0xFF, addr & 0xFF, data);
}

void commit(unsigned int addr) {
  if (param.devicecode >= 0xe0) {
    // AT89S
    spi_transaction(0x4C, addr >> 8 & 0xFF, addr & 0xFF, 0);
  } else {
    spi_transaction(0x4C, (addr >> 8) & 0xFF, addr & 0xFF, 0);
  }
}

unsigned int current_page() {
  if (param.pagesize == 32) return here & 0xFFFFFFF0;
  if (param.pagesize == 64) return here & 0xFFFFFFE0;
  if (param.pagesize == 128) return here & 0xFFFFFFC0;
  if (param.pagesize == 256) return here & 0xFFFFFF80;
  return here;
}

void write_flash(unsigned int l) {
  fill_buff(l);
  if (CRC_EOP == getch()) {
    Serial.print((char)STK_INSYNC);
    Serial.print((char)write_flash_pages(l));
  } else {
    error_count++;
    Serial.print((char)STK_NOSYNC);
  }
}

uint8_t write_flash_pages(int length) {
  int x = 0;
  unsigned int page = current_page();
  while (x < length) {
    if (page != current_page()) {
      commit(page);
      page = current_page();
    }
    flash(0, here, buff[x++]);
    flash(1, here, buff[x++]);
    here++;
  }
  commit(page);
  return STK_OK;
}

#define EECHUNK 32
uint8_t write_eeprom(unsigned int length) {
  fill_buff(length);
  if (CRC_EOP == getch()) {
    Serial.print((char)STK_INSYNC);
    Serial.print((char)write_eeprom_chunk(0, length));
  } else {
    error_count++;
    Serial.print((char)STK_NOSYNC);
  }
  return STK_OK;
}

uint8_t write_eeprom_chunk(unsigned int start, unsigned int length) {
  fill_buff(length);
  prog_lamp(LOW);
  for (unsigned int x = 0; x < length; x++) {
    unsigned int addr = start + x;
    spi_transaction(0xC0, (addr >> 8) & 0xFF, addr & 0xFF, buff[x]);
    delay(45);
  }
  prog_lamp(HIGH);
  return STK_OK;
}

void prog_lamp(int state) {
  digitalWrite(LED_PMODE, state);
}

void avrisp() {
  uint8_t ch = getch();
  switch (ch) {
    case '0': // signon
      error_count = 0;
      empty_reply();
      break;
    case '1':
      if (getch() == CRC_EOP) {
        Serial.print((char)STK_INSYNC);
        Serial.print("AVR ISP");
        Serial.print((char)STK_OK);
      } else {
        error_count++;
        Serial.print((char)STK_NOSYNC);
      }
      break;
    case '@': {
      uint8_t c = getch();
      get_version(c);
      break;
    }
    case 'A': {
      uint8_t c = getch();
      switch (c) {
        case 0x80: breply(2); break;
        case 0x81: breply(1); break;
        case 0x82: breply(18); break;
        case 0x93: breply('S'); break;
        default: breply(0);
      }
      break;
    }
    case 'B': {
      fill_buff(20);
      set_parameters();
      empty_reply();
      break;
    }
    case 'E': {
      fill_buff(5);
      if (CRC_EOP == getch()) {
        Serial.print((char)STK_INSYNC);
        Serial.print((char)STK_OK);
      } else {
        error_count++;
        Serial.print((char)STK_NOSYNC);
      }
      break;
    }
    case 'P': {
      if (pmode) end_pmode();
      start_pmode();
      empty_reply();
      break;
    }
    case 'R': {
      // Read flash low/high handled via U command in newer
      break;
    }
    case 'U': {
      // Set address
      here = getch();
      here += 256 * getch();
      empty_reply();
      break;
    }
    case 0x60: // STK_PROG_FLASH
    case 0x61: { // STK_PROG_DATA
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      if (ch == 0x60) write_flash(l);
      else {
        // eeprom
        uint8_t memtype = getch();
        (void)memtype;
        write_eeprom(l);
      }
      break;
    }
    case 0x64: // STK_PROG_PAGE
    {
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      uint8_t memtype = getch();
      fill_buff(l);
      if (CRC_EOP == getch()) {
        Serial.print((char)STK_INSYNC);
        uint8_t ok = STK_FAILED;
        if (memtype == 'F') {
          ok = write_flash_pages(l);
        } else if (memtype == 'E') {
          ok = write_eeprom_chunk(here, l);
          here += l;
        }
        Serial.print((char)ok);
      } else {
        error_count++;
        Serial.print((char)STK_NOSYNC);
      }
      break;
    }
    case 'V': // STK_UNIVERSAL
      universal();
      break;
    case 'Q': // STK_LEAVE_PROGMODE
      error_count = 0;
      end_pmode();
      empty_reply();
      break;
    case 0x75: // STK_READ_PAGE
    {
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      uint8_t memtype = getch();
      if (CRC_EOP != getch()) {
        error_count++;
        Serial.print((char)STK_NOSYNC);
        break;
      }
      Serial.print((char)STK_INSYNC);
      bool ok = false;
      if (memtype == 'F') {
        for (unsigned int i = 0; i < l; i += 2) {
          uint8_t low_b = spi_transaction(0x20, here >> 8 & 0xFF, here & 0xFF, 0);
          uint8_t high_b = spi_transaction(0x28, here >> 8 & 0xFF, here & 0xFF, 0);
          Serial.print((char)low_b);
          Serial.print((char)high_b);
          here++;
        }
        ok = true;
      } else if (memtype == 'E') {
        for (unsigned int i = 0; i < l; i++) {
          uint8_t b = spi_transaction(0xA0, here >> 8 & 0xFF, here & 0xFF, 0);
          Serial.print((char)b);
          here++;
        }
        ok = true;
      }
      Serial.print((char)(ok ? STK_OK : STK_FAILED));
      break;
    }
    case 0x74: // STK_READ_SIGN
    {
      if (CRC_EOP != getch()) {
        error_count++;
        Serial.print((char)STK_NOSYNC);
        break;
      }
      Serial.print((char)STK_INSYNC);
      if (pmode) {
        uint8_t sig[3];
        avr_read_signature(sig);
        Serial.print((char)sig[0]);
        Serial.print((char)sig[1]);
        Serial.print((char)sig[2]);
      } else {
        Serial.print((char)0);
        Serial.print((char)0);
        Serial.print((char)0);
      }
      Serial.print((char)STK_OK);
      break;
    }
    default:
      error_count++;
      if (CRC_EOP == getch()) {
        Serial.print((char)STK_UNKNOWN);
      } else {
        Serial.print((char)STK_NOSYNC);
      }
  }
}

// =============================================================================
// Setup and Loop
// =============================================================================

void setup() {
  Serial.begin(BAUDRATE);

  pinMode(LED_PMODE, OUTPUT);
  pulse_led(LED_PMODE, 2);
  pinMode(LED_ERR, OUTPUT);
  pulse_led(LED_ERR, 2);
  pinMode(LED_HB, OUTPUT);
  pulse_led(LED_HB, 2);

  pinMode(PIN_AVR_RESET, OUTPUT);
  digitalWrite(PIN_AVR_RESET, HIGH); // Not in reset (active low, so HIGH = not reset)

  pinMode(PIN_SPI_MEM_CS, OUTPUT);
  digitalWrite(PIN_SPI_MEM_CS, HIGH);

  // Initialize I2C
  Wire.begin();

  // Heartbeat init
  digitalWrite(LED_HB, LOW);

  // Send boot message for debugging (optional)
  delay(100);
  // Don't send boot message in STK mode to avoid confusing avrdude
  // Instead, wait for commands
}

uint8_t hbval = 128;
int8_t hbdelta = 8;

void heartbeat() {
  static unsigned long last_time = 0;
  unsigned long now = millis();
  if ((now - last_time) < 40) return;
  last_time = now;
  if (hbval > 192) hbdelta = -hbdelta;
  if (hbval < 32) hbdelta = -hbdelta;
  hbval += hbdelta;
#ifdef ARDUINO_ARCH_ESP32
  analogWrite(LED_HB, hbval);
#else
  analogWrite(LED_HB, hbval);
#endif
}

void loop() {
  // Handle LEDs
  if (pmode) {
    digitalWrite(LED_PMODE, HIGH);
  } else {
    digitalWrite(LED_PMODE, LOW);
  }

  if (error_count) {
    digitalWrite(LED_ERR, HIGH);
  } else {
    digitalWrite(LED_ERR, LOW);
  }

  heartbeat();

  if (!Serial.available()) return;

  // Peek first byte to decide protocol
  // If it's 0xAA, it's framed protocol, else STK500
  int first = Serial.peek();

  if (first == 0xAA) {
    // Framed protocol - check for full header
    if (Serial.available() >= 2) {
      uint8_t b1 = Serial.read();
      uint8_t b2 = Serial.read();
      if (b1 == FRAME_HEADER1 && b2 == FRAME_HEADER2) {
        // Valid framed header, parse rest
        try_parse_framed_packet();
      } else {
        // Not a valid header, treat as STK? Put back? We already consumed, so ignore
        // For safety, flush
      }
    }
  } else {
    // STK500 protocol
    avrisp();
  }
}
