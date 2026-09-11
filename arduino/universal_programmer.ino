/*
 * Universal Programmer Firmware v1.0.1 - Robust Edition
 * Professional Grade - Supports AVR ISP, SPI Memory, I2C Memory
 *
 * Based on ArduinoISP sketch (Copyright 2008-2011 Randall Bohn)
 * Preserves original AVR ISP functionality (STK500v1 compatible)
 * Extends with robust framed binary protocol for GUI
 *
 * Fixes in v1.0.1:
 * - Robust framed protocol parsing with circular buffer (no header loss)
 * - STK500 getch() with timeout to avoid blocking forever
 * - Better auto-reset handling
 * - Improved error recovery
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
 *   Pin 6  - Heartbeat LED
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
 *   STK500v1 compatible (for avrdude)
 *
 * Version: 1.0.1
 */

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

// =============================================================================
// Configuration
// =============================================================================

#define FIRMWARE_VERSION "Universal Programmer v1.0.1"
#define FIRMWARE_VERSION_MAJOR 1
#define FIRMWARE_VERSION_MINOR 0
#define FIRMWARE_VERSION_PATCH 1

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
// Pin Definitions
// =============================================================================

#ifdef ARDUINO_ARCH_ESP32
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

#define SPI_CLOCK (1000000/6)

// =============================================================================
// Global Variables
// =============================================================================

uint8_t current_protocol = PROTOCOL_NONE;
uint8_t error_count = 0;
uint8_t pmode = 0;
unsigned int here;
uint8_t buff[512];

uint8_t seq_num = 0;
SPISettings spi_settings(SPI_CLOCK, MSBFIRST, SPI_MODE0);

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

// RX circular buffer for robust parsing
#define RX_BUF_SIZE 1024
uint8_t rx_buf[RX_BUF_SIZE];
volatile uint16_t rx_head = 0;
volatile uint16_t rx_tail = 0;

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

// RX buffer helpers
inline uint16_t rx_available() {
  if (rx_head >= rx_tail) return rx_head - rx_tail;
  return RX_BUF_SIZE - rx_tail + rx_head;
}

inline bool rx_is_empty() {
  return rx_head == rx_tail;
}

inline void rx_push(uint8_t b) {
  uint16_t next = (rx_head + 1) % RX_BUF_SIZE;
  if (next != rx_tail) {
    rx_buf[rx_head] = b;
    rx_head = next;
  }
}

inline uint8_t rx_peek(uint16_t offset) {
  return rx_buf[(rx_tail + offset) % RX_BUF_SIZE];
}

inline uint8_t rx_pop() {
  if (rx_is_empty()) return 0;
  uint8_t b = rx_buf[rx_tail];
  rx_tail = (rx_tail + 1) % RX_BUF_SIZE;
  return b;
}

inline void rx_clear() {
  rx_head = rx_tail = 0;
}

// Fill RX buffer from Serial
void rx_fill_from_serial() {
  while (Serial.available()) {
    uint8_t b = Serial.read();
    rx_push(b);
    // Avoid overflow - if buffer full, drop oldest
    if ((rx_head + 1) % RX_BUF_SIZE == rx_tail) {
      rx_tail = (rx_tail + 1) % RX_BUF_SIZE;
    }
  }
}

// =============================================================================
// Framed Protocol Implementation - Robust
// =============================================================================

#define FRAME_HEADER1 0xAA
#define FRAME_HEADER2 0x55
#define FRAME_FOOTER1 0x55
#define FRAME_FOOTER2 0xAA
#define MAX_PAYLOAD 512

void send_response(uint8_t cmd, uint8_t seq, uint8_t status, const uint8_t *payload, uint16_t payload_len) {
  uint16_t total_len = payload_len + 1;
  if (total_len > MAX_PAYLOAD) total_len = MAX_PAYLOAD;

  uint8_t frame[1024];
  uint16_t idx = 0;

  frame[idx++] = FRAME_HEADER1;
  frame[idx++] = FRAME_HEADER2;
  frame[idx++] = cmd | 0x80;
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

// Try to parse one framed packet from rx_buf
// Returns true if packet handled, false otherwise
bool try_parse_framed_from_buffer() {
  // Need at least minimal packet
  if (rx_available() < 10) return false;

  // Search for header AA 55
  uint16_t search_offset = 0;
  uint16_t avail = rx_available();
  
  for (uint16_t i = 0; i < avail - 1; i++) {
    uint8_t b1 = rx_peek(i);
    uint8_t b2 = rx_peek(i+1);
    
    if (b1 == FRAME_HEADER1 && b2 == FRAME_HEADER2) {
      // Found header at offset i
      // Check if we have enough for minimal header
      if (avail - i < 10) return false; // need more data

      uint8_t cmd = rx_peek(i+2);
      uint8_t seq = rx_peek(i+3);
      uint8_t len_l = rx_peek(i+4);
      uint8_t len_h = rx_peek(i+5);
      uint16_t payload_len = len_l | (len_h << 8);

      if (payload_len > MAX_PAYLOAD) {
        // Invalid length, skip this header
        // Remove bytes up to i+2
        for (uint16_t j = 0; j < i+2; j++) rx_pop();
        return false;
      }

      uint16_t total_len = 2 + 1 + 1 + 2 + payload_len + 2 + 2;
      
      if (avail - i < total_len) {
        // Need more data
        return false;
      }

      // Check footer
      uint8_t foot1 = rx_peek(i + total_len - 2);
      uint8_t foot2 = rx_peek(i + total_len - 1);
      
      if (foot1 != FRAME_FOOTER1 || foot2 != FRAME_FOOTER2) {
        // Bad footer, skip header
        for (uint16_t j = 0; j < i+2; j++) rx_pop();
        return false;
      }

      // Extract payload for CRC check
      uint8_t payload[MAX_PAYLOAD];
      for (uint16_t p = 0; p < payload_len; p++) {
        payload[p] = rx_peek(i + 6 + p);
      }

      // Check CRC
      uint8_t crc_data[600];
      crc_data[0] = cmd;
      crc_data[1] = seq;
      crc_data[2] = len_l;
      crc_data[3] = len_h;
      memcpy(&crc_data[4], payload, payload_len);
      uint16_t calc_crc = crc16_ccitt(crc_data, 4 + payload_len);
      
      uint8_t crc_l = rx_peek(i + 6 + payload_len);
      uint8_t crc_h = rx_peek(i + 6 + payload_len + 1);
      uint16_t recv_crc = crc_l | (crc_h << 8);

      if (calc_crc != recv_crc) {
        // CRC mismatch, skip header
        for (uint16_t j = 0; j < i+2; j++) rx_pop();
        return false;
      }

      // Valid packet! Remove preceding garbage and packet from buffer
      for (uint16_t j = 0; j < i; j++) rx_pop(); // remove garbage before header
      for (uint16_t j = 0; j < total_len; j++) rx_pop(); // remove packet

      // Handle command
      extern void handle_framed_command(uint8_t cmd, uint8_t seq, uint8_t *payload, uint16_t len);
      handle_framed_command(cmd, seq, payload, payload_len);
      return true;
    }
  }

  // No header found - if buffer is large and contains no header, 
  // it might be STK500 data, so don't clear, let STK handler deal with it
  // But if buffer is very large (>500) and no header, clear some to avoid overflow
  if (avail > 500) {
    // Keep last 100 bytes
    while (rx_available() > 100) rx_pop();
  }
  
  return false;
}

// =============================================================================
// AVR ISP Low-Level Functions
// =============================================================================

uint8_t spi_transaction(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
  SPI.transfer(a);
  SPI.transfer(b);
  SPI.transfer(c);
  return SPI.transfer(d);
}

void avr_reset_target(bool reset) {
  digitalWrite(PIN_AVR_RESET, reset ? LOW : HIGH);
}

bool avr_enter_progmode() {
  digitalWrite(PIN_AVR_RESET, HIGH);
  pinMode(PIN_AVR_RESET, OUTPUT);
  SPI.begin();
  SPI.beginTransaction(spi_settings);

  digitalWrite(PIN_SCK, LOW);
  delay(20);

  avr_reset_target(true);
  delay(20);

  uint8_t resp = spi_transaction(0xAC, 0x53, 0x00, 0x00);
  if (resp != 0x53) {
    delay(20);
    resp = spi_transaction(0xAC, 0x53, 0x00, 0x00);
  }

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
  for (uint16_t i = 0; i < len; i++) {
    uint32_t word_addr = (addr + i) >> 1;
    bool high = (addr + i) & 1;
    uint8_t cmd = high ? 0x48 : 0x40;
    spi_transaction(cmd, (word_addr >> 8) & 0xFF, word_addr & 0xFF, data[i]);
    delayMicroseconds(100);
  }
  uint32_t page_addr = addr >> 1;
  spi_transaction(0x4C, (page_addr >> 8) & 0xFF, page_addr & 0xFF, 0x00);
  delay(10);
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
    spi_mem_transfer(0xC7);
  } else if (type == 0x20) {
    spi_mem_transfer(0x20);
    spi_mem_transfer((addr >> 16) & 0xFF);
    spi_mem_transfer((addr >> 8) & 0xFF);
    spi_mem_transfer(addr & 0xFF);
  } else if (type == 0xD8) {
    spi_mem_transfer(0xD8);
    spi_mem_transfer((addr >> 16) & 0xFF);
    spi_mem_transfer((addr >> 8) & 0xFF);
    spi_mem_transfer(addr & 0xFF);
  } else {
    spi_mem_select(false);
    return false;
  }
  spi_mem_select(false);

  uint16_t timeout = (type == 0xC7) ? 10000 : 3000;
  return spi_mem_wait_ready(timeout);
}

// =============================================================================
// I2C Memory Functions
// =============================================================================

void i2c_init() {
  Wire.begin();
  Wire.setClock(100000);
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
      if (*count >= 32) break;
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
    if (chunk > 32) chunk = 32;

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
    uint16_t chunk = len - offset;
    if (chunk > 30) chunk = 30;

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
    delay(10);
  }
  return true;
}

// =============================================================================
// Framed Command Handler
// =============================================================================

void handle_framed_command(uint8_t cmd, uint8_t seq, uint8_t *payload, uint16_t len) {
  uint8_t resp_buf[512];

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
      if (proto <= PROTOCOL_I2C_MEM) {
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
      if ((sig[0] == 0x00 && sig[1] == 0x00 && sig[2] == 0x00) ||
          (sig[0] == 0xFF && sig[1] == 0xFF && sig[2] == 0xFF)) {
        send_error(cmd, seq, STATUS_ERROR_NO_TARGET);
        break;
      }
      resp_buf[0] = sig[0];
      resp_buf[1] = sig[1];
      resp_buf[2] = sig[2];
      resp_buf[3] = 32; resp_buf[4] = 0;
      resp_buf[5] = 1; resp_buf[6] = 0;
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
// STK500v1 Compatibility - Non-blocking version
// =============================================================================

// getch with timeout - returns 0xFF on timeout
uint8_t getch_timeout(uint16_t timeout_ms = 1000) {
  unsigned long start = millis();
  while (millis() - start < timeout_ms) {
    rx_fill_from_serial();
    if (!rx_is_empty()) {
      return rx_pop();
    }
    // Also check direct Serial for STK500 compatibility
    if (Serial.available()) {
      return Serial.read();
    }
  }
  return 0xFF; // timeout
}

uint8_t getch() {
  // Blocking version for STK500 - but with longer timeout
  unsigned long start = millis();
  while (millis() - start < 2000) {
    rx_fill_from_serial();
    if (!rx_is_empty()) {
      return rx_pop();
    }
    if (Serial.available()) {
      return Serial.read();
    }
  }
  return 0xFF;
}

void fill_buff(int n) {
  for (int i = 0; i < n; i++) {
    buff[i] = getch();
  }
}

void empty_reply() {
  uint8_t eop = getch();
  if (CRC_EOP == eop) {
    Serial.print((char)STK_INSYNC);
    Serial.print((char)STK_OK);
  } else {
    error_count++;
    Serial.print((char)STK_NOSYNC);
  }
}

void breply(uint8_t b) {
  uint8_t eop = getch();
  if (CRC_EOP == eop) {
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
    case 0x80: breply(2); break;
    case 0x81: breply(1); break;
    case 0x82: breply(18); break;
    case 0x93: breply('S'); break;
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

void universal() {
  fill_buff(4);
  uint8_t ch = spi_transaction(buff[0], buff[1], buff[2], buff[3]);
  breply(ch);
}

void flash(uint8_t hilo, unsigned int addr, uint8_t data) {
  spi_transaction(0x40 + 8 * hilo, addr >> 8 & 0xFF, addr & 0xFF, data);
}

void commit(unsigned int addr) {
  spi_transaction(0x4C, (addr >> 8) & 0xFF, addr & 0xFF, 0);
}

unsigned int current_page() {
  if (param.pagesize == 32) return here & 0xFFFFFFF0;
  if (param.pagesize == 64) return here & 0xFFFFFFE0;
  if (param.pagesize == 128) return here & 0xFFFFFFC0;
  if (param.pagesize == 256) return here & 0xFFFFFF80;
  return here;
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

uint8_t write_eeprom_chunk(unsigned int start, unsigned int length) {
  fill_buff(length);
  for (unsigned int x = 0; x < length; x++) {
    unsigned int addr = start + x;
    spi_transaction(0xC0, (addr >> 8) & 0xFF, addr & 0xFF, buff[x]);
    delay(45);
  }
  return STK_OK;
}

void prog_lamp(int state) {
  digitalWrite(LED_PMODE, state);
}

void avrisp() {
  // Check if we have data in rx_buf first
  uint8_t ch;
  if (!rx_is_empty()) {
    ch = rx_pop();
  } else {
    if (!Serial.available()) return;
    ch = Serial.read();
  }

  switch (ch) {
    case '0':
      error_count = 0;
      empty_reply();
      break;
    case '1':
      {
        uint8_t eop = getch();
        if (eop == CRC_EOP) {
          Serial.print((char)STK_INSYNC);
          Serial.print("AVR ISP");
          Serial.print((char)STK_OK);
        } else {
          error_count++;
          Serial.print((char)STK_NOSYNC);
        }
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
      uint8_t eop = getch();
      if (eop == CRC_EOP) {
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
    case 'U': {
      here = getch();
      here += 256 * getch();
      empty_reply();
      break;
    }
    case 0x60:
    case 0x61: {
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      if (ch == 0x60) {
        fill_buff(l);
        uint8_t eop = getch();
        if (eop == CRC_EOP) {
          Serial.print((char)STK_INSYNC);
          Serial.print((char)write_flash_pages(l));
        } else {
          error_count++;
          Serial.print((char)STK_NOSYNC);
        }
      } else {
        uint8_t memtype = getch();
        (void)memtype;
        fill_buff(l);
        uint8_t eop = getch();
        if (eop == CRC_EOP) {
          Serial.print((char)STK_INSYNC);
          Serial.print((char)write_eeprom_chunk(0, l));
        } else {
          error_count++;
          Serial.print((char)STK_NOSYNC);
        }
      }
      break;
    }
    case 0x64: {
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      uint8_t memtype = getch();
      fill_buff(l);
      uint8_t eop = getch();
      if (eop == CRC_EOP) {
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
    case 'V':
      universal();
      break;
    case 'Q':
      error_count = 0;
      end_pmode();
      empty_reply();
      break;
    case 0x75: {
      uint8_t low = getch();
      uint8_t high = getch();
      unsigned int l = low + 256 * high;
      uint8_t memtype = getch();
      uint8_t eop = getch();
      if (eop != CRC_EOP) {
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
    case 0x74: {
      uint8_t eop = getch();
      if (eop != CRC_EOP) {
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
      {
        uint8_t eop = getch();
        if (eop == CRC_EOP) {
          Serial.print((char)STK_UNKNOWN);
        } else {
          Serial.print((char)STK_NOSYNC);
        }
      }
  }
}

// =============================================================================
// Setup and Loop - Robust
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
  digitalWrite(PIN_AVR_RESET, HIGH);

  pinMode(PIN_SPI_MEM_CS, OUTPUT);
  digitalWrite(PIN_SPI_MEM_CS, HIGH);

  Wire.begin();
  rx_clear();

  delay(100);
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
  analogWrite(LED_HB, hbval);
}

void loop() {
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

  // Fill RX buffer from serial
  rx_fill_from_serial();

  // First, try to handle framed protocol (priority)
  // Try multiple times to handle burst
  for (uint8_t i = 0; i < 3; i++) {
    if (try_parse_framed_from_buffer()) {
      continue;
    } else {
      break;
    }
  }

  // If no framed packet handled, try STK500 if we have data
  if (!rx_is_empty()) {
    // Peek first byte - if it's AA, it might be partial framed packet, wait for more
    uint8_t first = rx_peek(0);
    if (first == 0xAA) {
      // Might be start of framed, but not enough data yet - wait
      if (rx_available() < 10) {
        // Not enough for framed, but also check if second byte is 55
        // If we have at least 2 bytes and second is not 55, it's not framed
        if (rx_available() >= 2) {
          uint8_t second = rx_peek(1);
          if (second != 0x55) {
            // Not framed, treat as STK
            avrisp();
          }
          // Else wait for more data
        }
      } else {
        // We have enough for minimal, but try_parse failed - might be corrupted
        // Try STK as fallback if first byte looks like STK command
        // STK commands are ASCII '0','1','A','B', etc (0x30-0x5A) or 0x60,0x61,0x64,0x74,0x75
        // AA (0xAA) is not valid STK, so don't handle as STK
      }
    } else {
      // Not AA, likely STK500 command
      avrisp();
    }
  }
}
