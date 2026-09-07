/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: telemetry.h
  * Brief: Public interface for 24-byte binary telemetry and serial command parser.
  ******************************************************************************
  */

#ifndef TELEMETRY_H
#define TELEMETRY_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Packet Framing Constants */
#define TELEMETRY_PREAMBLE_0    0xAA
#define TELEMETRY_PREAMBLE_1    0x55

#pragma pack(push, 1)
/**
  * @brief  Packed 24-byte binary telemetry packet structure.
  */
typedef struct {
  uint8_t  preamble[2];     /* 0xAA, 0x55 synchronization bytes */
  uint32_t timestamp_ms;    /* System uptime in milliseconds */
  float    angle_deg;       /* Joint angle in degrees */
  float    velocity_deg_s;  /* Filtered velocity in deg/s */
  float    load_cell;       /* Handle load cell force in lbs */
  float    motor_iq_a;      /* Motor q-axis current in Amps */
  uint16_t crc16;           /* CRC-16-CCITT checksum over bytes 0..21 */
} TelemetryPacket_t;
#pragma pack(pop)

_Static_assert(sizeof(TelemetryPacket_t) == 24, "TelemetryPacket_t must be exactly 24 bytes!");

/**
  * @brief  Host / GUI commands recognized by firmware state machine.
  */
typedef enum {
  CMD_NONE = 0,
  CMD_START,
  CMD_STOP,
  CMD_ZERO,
  CMD_STATUS
} SystemCommand_t;

/* Public Function Prototypes */
void            Telemetry_Init(UART_HandleTypeDef *huart);
SystemCommand_t Telemetry_PollCommand(void);
void            Telemetry_SendPacket(TelemetryPacket_t *pkt);
void            Telemetry_SendAck(const char *msg);
uint16_t        Telemetry_ComputeCRC16(const uint8_t *data, size_t length);

#ifdef __cplusplus
}
#endif

#endif /* TELEMETRY_H */
