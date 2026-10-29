/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: telemetry.c
** --------
** Implementation of binary packet framing, CRC16, and command parser.
*/

#include "telemetry.h"
#include "usbd_cdc_if.h"
#include <string.h>
#include <strings.h>
#include <stdlib.h>

#define CMD_BUF_SIZE        64
#define RX_RING_BUF_SIZE    128

/* Private Module Variables */
static UART_HandleTypeDef *s_huart = (UART_HandleTypeDef *)0;
static char                s_cmd_buf[CMD_BUF_SIZE];
static uint8_t             s_cmd_idx = 0;
static float               s_cmd_param = 0.0f;

static volatile uint8_t s_rx_ring[RX_RING_BUF_SIZE];
static volatile uint8_t s_rx_head = 0;
static volatile uint8_t s_rx_tail = 0;

/* Private Function Prototypes */
static SystemCommand_t ProcessIncomingChar(char c);

/* Read the parameter associated with the latest parsed command
** Parameters:
**   None
** Return:
**   float: Parsed parameter value (e.g. resistance in lbs)
** Notes:
**   None
*/
float Telemetry_GetCommandParam(void)
{
  return s_cmd_param;
} /* Telemetry_GetCommandParam() */

/* Feeds raw data received from USB CDC into the telemetry ring buffer
** Parameters:
**   data - Pointer to incoming byte buffer
**   len - Length in bytes
** Return:
**   None
** Notes:
**   Called from USB CDC receive callback
*/
void Telemetry_FeedUsbData(const uint8_t *data, uint32_t len)
{
  for ( uint32_t i = 0; i < len; i++ )
  {
    uint8_t next;
    next = (uint8_t)((s_rx_head + 1) % RX_RING_BUF_SIZE);
    if ( next != s_rx_tail )
    {
      s_rx_ring[s_rx_head] = data[i];
      __DMB(); /* Ensure data byte is committed before head index advances */
      s_rx_head = next;
    }
  }
} /* Telemetry_FeedUsbData() */

/* Initialize telemetry module with target UART peripheral handle
** Parameters:
**   huart - Pointer to UART_HandleTypeDef (e.g. &huart2)
** Return:
**   None
** Notes:
**   None
*/
void Telemetry_Init(UART_HandleTypeDef *huart)
{
  s_huart = huart;
  s_cmd_idx = 0;
  s_rx_head = 0;
  s_rx_tail = 0;
  memset(s_cmd_buf, 0, sizeof(s_cmd_buf));
} /* Telemetry_Init() */

/* Helper to parse a single incoming character into system commands
** Parameters:
**   c - Incoming character
** Return:
**   SystemCommand_t: Parsed command code or CMD_NONE
** Notes:
**   Handles ASCII delimiter matching and parameter extraction
*/
static SystemCommand_t ProcessIncomingChar(char c)
{
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
      else if ( strcasecmp(s_cmd_buf, "TMC") == 0 )
      {
        return CMD_TMC;
      }
      else if ( strcasecmp(s_cmd_buf, "SPO2") == 0 )
      {
        return CMD_SPO2;
      }
      else if ( (strcasecmp(s_cmd_buf, "HOME") == 0) || (strcasecmp(s_cmd_buf, "H") == 0) )
      {
        return CMD_HOME;
      }
      else if ( (strcasecmp(s_cmd_buf, "TARE") == 0) || (strcasecmp(s_cmd_buf, "T") == 0) )
      {
        return CMD_TARE;
      }
      else if ( (strcasecmp(s_cmd_buf, "DFU") == 0) || (strcasecmp(s_cmd_buf, "BOOTLOADER") == 0) )
      {
        return CMD_DFU;
      }
      else if ( (strncasecmp(s_cmd_buf, "HOMETHR", 7) == 0) || (strncasecmp(s_cmd_buf, "SGTHR", 5) == 0) )
      {
        const char *p = (strncasecmp(s_cmd_buf, "HOMETHR", 7) == 0) ? &s_cmd_buf[7] : &s_cmd_buf[5];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_HOMETHR;
        }
      }
      else if ( (strncasecmp(s_cmd_buf, "HOMESPEED", 9) == 0) || (strncasecmp(s_cmd_buf, "HSPEED", 6) == 0) )
      {
        const char *p = (strncasecmp(s_cmd_buf, "HOMESPEED", 9) == 0) ? &s_cmd_buf[9] : &s_cmd_buf[6];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_HOMESPEED;
        }
      }
      else if ( (strncasecmp(s_cmd_buf, "HOMECURR", 8) == 0) || (strncasecmp(s_cmd_buf, "HCURR", 5) == 0) )
      {
        const char *p = (strncasecmp(s_cmd_buf, "HOMECURR", 8) == 0) ? &s_cmd_buf[8] : &s_cmd_buf[5];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_HOMECURR;
        }
      }
      else if ( (strncasecmp(s_cmd_buf, "RES", 3) == 0) || (strncasecmp(s_cmd_buf, "SET", 3) == 0) )
      {
        /* Support "RES 10.5", "RES:10.5", "RES=10.5", "SET 10.5", etc. */
        const char *p = &s_cmd_buf[3];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_RESISTANCE;
        }
      }
      else if ( strncasecmp(s_cmd_buf, "CURR", 4) == 0 )
      {
        /* Support "CURR 1700", "CURR 1.7", "CURR:1700", etc. */
        const char *p = &s_cmd_buf[4];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          float c = (float)strtod(p, (char **)0);
          /* If given in Amperes (e.g. 1.7), convert to mA (1700) */
          if ( c < 10.0f )
          {
            s_cmd_param = c * 1000.0f;
          }
          else
          {
            s_cmd_param = c;
          }
          return CMD_SET_CURRENT;
        }
      }
    }
  }
  else
  {
    /* Only accept printable ASCII characters (0x20 space through 0x7E ~) */
    if ( (c >= ' ') && (c <= '~') )
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
  }

  return CMD_NONE;
} /* ProcessIncomingChar() */

/* Non-blocking poll for incoming ASCII host commands over UART and USB CDC
** Parameters:
**   None
** Return:
**   SystemCommand_t: Parsed command code or CMD_NONE
** Notes:
**   None
*/
SystemCommand_t Telemetry_PollCommand(void)
{
  /* 1. Poll UART RX if configured */
  if ( s_huart != (UART_HandleTypeDef *)0 )
  {
    if ( __HAL_UART_GET_FLAG(s_huart, UART_FLAG_ORE) ||
         __HAL_UART_GET_FLAG(s_huart, UART_FLAG_FE)  ||
         __HAL_UART_GET_FLAG(s_huart, UART_FLAG_NE) )
    {
      __HAL_UART_CLEAR_OREFLAG(s_huart);
    }

    while ( __HAL_UART_GET_FLAG(s_huart, UART_FLAG_RXNE) )
    {
      char c = (char)(s_huart->Instance->DR & 0xFF);
      SystemCommand_t cmd = ProcessIncomingChar(c);
      if ( cmd != CMD_NONE )
      {
        return cmd;
      }
    }
  }

  /* 2. Poll USB CDC ring buffer */
  while ( s_rx_tail != s_rx_head )
  {
    char c = (char)s_rx_ring[s_rx_tail];
    __DMB(); /* Ensure byte is read before tail advances */
    s_rx_tail = (uint8_t)((s_rx_tail + 1) % RX_RING_BUF_SIZE);
    SystemCommand_t cmd = ProcessIncomingChar(c);
    if ( cmd != CMD_NONE )
    {
      return cmd;
    }
  }

  return CMD_NONE;
} /* Telemetry_PollCommand() */

/* Transmits a 28-byte binary telemetry packet with CRC16 over UART & USB CDC
** Parameters:
**   pkt - Pointer to TelemetryPacket_t structure to send
** Return:
**   None
** Notes:
**   None
*/
void Telemetry_SendPacket(TelemetryPacket_t *pkt)
{
  if ( pkt == (TelemetryPacket_t *)0 )
  {
    return;
  }

  pkt->preamble[0] = TELEMETRY_PREAMBLE_0;
  pkt->preamble[1] = TELEMETRY_PREAMBLE_1;
  pkt->crc16 = Telemetry_ComputeCRC16((const uint8_t *)pkt, sizeof(TelemetryPacket_t) - sizeof(uint16_t));

  /* Transmit over hardware UART if initialized */
  if ( s_huart != (UART_HandleTypeDef *)0 )
  {
    HAL_UART_Transmit(s_huart, (uint8_t *)pkt, sizeof(TelemetryPacket_t), 10);
  }

  /* Transmit over USB CDC Virtual COM port */
  static uint8_t s_usb_pkt_buf[sizeof(TelemetryPacket_t)];
  memcpy(s_usb_pkt_buf, pkt, sizeof(TelemetryPacket_t));
  CDC_Transmit_FS(s_usb_pkt_buf, sizeof(TelemetryPacket_t));
} /* Telemetry_SendPacket() */

/* Transmits an ASCII text line over UART & USB CDC
** Parameters:
**   msg - Null-terminated string
** Return:
**   None
** Notes:
**   None
*/
void Telemetry_SendAck(const char *msg)
{
  if ( msg == (const char *)0 )
  {
    return;
  }

  /* Transmit over hardware UART if initialized */
  if ( s_huart != (UART_HandleTypeDef *)0 )
  {
    HAL_UART_Transmit(s_huart, (const uint8_t *)msg, (uint16_t)strlen(msg), 100);
  }

  /* Transmit over USB CDC Virtual COM port */
  static uint8_t s_ack_buf[128];
  uint16_t len = (uint16_t)strlen(msg);
  if ( len > sizeof(s_ack_buf) )
  {
    len = sizeof(s_ack_buf);
  }
  memcpy(s_ack_buf, msg, len);
  CDC_Transmit_FS(s_ack_buf, len);
} /* Telemetry_SendAck() */

/* Compute standard CRC-16-CCITT (poly 0x1021, init 0xFFFF)
** Parameters:
**   data - Pointer to data buffer
**   length - Number of bytes to checksum
** Return:
**   uint16_t: Computed 16-bit CRC checksum
** Notes:
**   None
*/
uint16_t Telemetry_ComputeCRC16(const uint8_t *data, size_t length)
{
  uint16_t crc = 0xFFFF;

  for ( size_t i = 0; i < length; i++ )
  {
    crc ^= ((uint16_t)data[i] << 8);

    for ( uint8_t bit = 0; bit < 8; bit++ )
    {
      if ( (crc & 0x8000) != 0 )
      {
        crc = ((crc << 1) ^ 0x1021);
      }
      else
      {
        crc = (crc << 1);
      }
    }
  }

  return crc;
} /* Telemetry_ComputeCRC16() */
