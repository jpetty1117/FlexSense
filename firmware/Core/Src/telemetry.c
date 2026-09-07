/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: telemetry.c
  * Brief: Implementation of binary packet framing, CRC16, and command parser.
  ******************************************************************************
  */

#include "telemetry.h"
#include <string.h>
#include <strings.h>

#define CMD_BUF_SIZE 64

/* Private Module Variables */
static UART_HandleTypeDef *s_huart = NULL;
static char                s_cmd_buf[CMD_BUF_SIZE];
static uint8_t             s_cmd_idx = 0;

/**
  * @brief  Initialize telemetry module with target UART peripheral handle.
  * @param  huart: Pointer to UART_HandleTypeDef (e.g. &huart2).
  * @retval None
  */
void Telemetry_Init(UART_HandleTypeDef *huart)
{
  s_huart = huart;
  s_cmd_idx = 0;
  memset(s_cmd_buf, 0, sizeof(s_cmd_buf));
} /* Telemetry_Init() */

/**
  * @brief  Non-blocking poll for incoming ASCII host commands over UART.
  * @param  None
  * @retval SystemCommand_t: Parsed command code or CMD_NONE.
  */
SystemCommand_t Telemetry_PollCommand(void)
{
  if ( s_huart == NULL )
  {
    return CMD_NONE;
  }

  /* Clear UART overrun flag if active */
  if ( __HAL_UART_GET_FLAG(s_huart, UART_FLAG_ORE) )
  {
    __HAL_UART_CLEAR_OREFLAG(s_huart);
  }

  while ( __HAL_UART_GET_FLAG(s_huart, UART_FLAG_RXNE) )
  {
    char c = (char)(s_huart->Instance->DR & 0xFF);

    if ( (c == '\r') || (c == '\n') )
    {
      if ( s_cmd_idx > 0 )
      {
        s_cmd_buf[s_cmd_idx] = '\0';
        s_cmd_idx = 0;

        if ( (strcasecmp(s_cmd_buf, "START") == 0) || (strcasecmp(s_cmd_buf, "S") == 0) )
        {
          return CMD_START;
        }
        else if ( (strcasecmp(s_cmd_buf, "STOP") == 0) || (strcasecmp(s_cmd_buf, "P") == 0) )
        {
          return CMD_STOP;
        }
        else if ( (strcasecmp(s_cmd_buf, "ZERO") == 0) || (strcasecmp(s_cmd_buf, "Z") == 0) )
        {
          return CMD_ZERO;
        }
        else if ( (strcasecmp(s_cmd_buf, "STATUS") == 0) || (strcasecmp(s_cmd_buf, "?") == 0) )
        {
          return CMD_STATUS;
        }
      }
    }
    else
    {
      if ( s_cmd_idx < (CMD_BUF_SIZE - 1) )
      {
        /* Ignore leading whitespace */
        if ( !( (s_cmd_idx == 0) && ((c == ' ') || (c == '\t')) ) )
        {
          s_cmd_buf[s_cmd_idx++] = c;
        }
      }
      else
      {
        s_cmd_idx = 0; /* Buffer overflow protection */
      }
    }
  } /* while ( RXNE ) */

  return CMD_NONE;
} /* Telemetry_PollCommand() */

/**
  * @brief  Transmits a 24-byte binary telemetry packet with CRC16 over UART.
  * @param  pkt: Pointer to TelemetryPacket_t structure to send.
  * @retval None
  */
void Telemetry_SendPacket(TelemetryPacket_t *pkt)
{
  if ( (s_huart == NULL) || (pkt == NULL) )
  {
    return;
  }

  pkt->preamble[0] = TELEMETRY_PREAMBLE_0;
  pkt->preamble[1] = TELEMETRY_PREAMBLE_1;
  pkt->crc16 = Telemetry_ComputeCRC16((const uint8_t *)pkt, sizeof(TelemetryPacket_t) - sizeof(uint16_t));

  HAL_UART_Transmit(s_huart, (uint8_t *)pkt, sizeof(TelemetryPacket_t), 10);
} /* Telemetry_SendPacket() */

/**
  * @brief  Transmits an ASCII text line (e.g. ACK banner or status response).
  * @param  msg: Null-terminated string.
  * @retval None
  */
void Telemetry_SendAck(const char *msg)
{
  if ( (s_huart != NULL) && (msg != NULL) )
  {
    HAL_UART_Transmit(s_huart, (const uint8_t *)msg, (uint16_t)strlen(msg), 100);
  }
} /* Telemetry_SendAck() */

/**
  * @brief  Compute standard CRC-16-CCITT (poly 0x1021, init 0xFFFF).
  * @param  data: Pointer to data buffer.
  * @param  length: Number of bytes to checksum.
  * @retval uint16_t: Computed 16-bit CRC checksum.
  */
uint16_t Telemetry_ComputeCRC16(const uint8_t *data, size_t length)
{
  uint16_t crc = 0xFFFF;

  for ( size_t i = 0; i < length; i++ )
  {
    crc ^= ( (uint16_t)data[i] << 8 );

    for ( uint8_t bit = 0; bit < 8; bit++ )
    {
      if ( crc & 0x8000 )
      {
        crc = ( (crc << 1) ^ 0x1021 );
      }
      else
      {
        crc = (crc << 1);
      }
    }
  }

  return crc;
} /* Telemetry_ComputeCRC16() */
