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
#define TX_RING_BUF_SIZE    512U
#define TX_CHUNK_MAX_SIZE   63U  /* Strictly < 64-byte FS MPS avoids extra ZLP frame delay */

extern USBD_HandleTypeDef hUsbDeviceFS;

/* Private Module Variables */
static UART_HandleTypeDef *s_huart = (UART_HandleTypeDef *)0;
static char                s_cmd_buf[CMD_BUF_SIZE];
static uint8_t             s_cmd_idx = 0;
static float               s_cmd_param = 0.0f;

static volatile uint8_t s_rx_ring[RX_RING_BUF_SIZE];
static volatile uint8_t s_rx_head = 0;
static volatile uint8_t s_rx_tail = 0;

static uint8_t           s_tx_ring[TX_RING_BUF_SIZE];
static volatile uint16_t s_tx_head = 0U;
static volatile uint16_t s_tx_tail = 0U;
static uint8_t           s_tx_usb_chunk[TX_CHUNK_MAX_SIZE];

/* Private Function Prototypes */
static SystemCommand_t ProcessIncomingChar(char c);
static void            Telemetry_TxKick(void);
static bool            Telemetry_EnqueueUsb(const uint8_t *data, uint16_t len);

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
  s_tx_head = 0U;
  s_tx_tail = 0U;
  memset(s_cmd_buf, 0, sizeof(s_cmd_buf));
} /* Telemetry_Init() */

static inline bool is_stop_command(const char *cmd)
{
  if ( (strcasecmp(cmd, "STOP") == 0) || (strcasecmp(cmd, "ESTOP") == 0) ||
       (strcasecmp(cmd, "HALT") == 0) || (strcasecmp(cmd, "KILL") == 0) ||
       (strcasecmp(cmd, "P") == 0) )
  {
    return true;
  }
  for ( const char *p = cmd; *p != '\0'; p++ )
  {
    if ( ((p[0] == 'S') || (p[0] == 's')) &&
         ((p[1] == 'T') || (p[1] == 't')) &&
         ((p[2] == 'O') || (p[2] == 'o')) &&
         ((p[3] == 'P') || (p[3] == 'p')) )
    {
      return true;
    }
  }
  return false;
}

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
  /* Emergency single-byte aborts: ETX (0x03 / Ctrl-C), ESC (0x1B), '!' */
  if ( (c == 0x03) || (c == 0x1B) || (c == '!') )
  {
    s_cmd_idx = 0;
    return CMD_STOP;
  }

  if ( (c == '\r') || (c == '\n') )
  {
    if ( s_cmd_idx > 0 )
    {
      s_cmd_buf[s_cmd_idx] = '\0';
      s_cmd_idx = 0;

      /* Strip leading whitespace */
      char *cmd = s_cmd_buf;
      while ( (*cmd == ' ') || (*cmd == '\t') )
      {
        cmd++;
      }
      /* Strip trailing whitespace */
      int len = (int)strlen(cmd);
      while ( (len > 0) && ((cmd[len - 1] == ' ') || (cmd[len - 1] == '\t')) )
      {
        cmd[--len] = '\0';
      }

      if ( is_stop_command(cmd) )
      {
        return CMD_STOP;
      }
      else if ( (strcasecmp(cmd, "START") == 0) || (strcasecmp(cmd, "S") == 0) )
      {
        return CMD_START;
      }
      else if ( (strcasecmp(cmd, "ZERO") == 0) || (strcasecmp(cmd, "Z") == 0) )
      {
        return CMD_ZERO;
      }
      else if ( (strcasecmp(cmd, "ZEROPOS") == 0) || (strcasecmp(cmd, "ZEROMOTOR") == 0) ||
                (strcasecmp(cmd, "MOTORZERO") == 0) || (strcasecmp(cmd, "MZ") == 0) ||
                (strcasecmp(cmd, "ZERO_POS") == 0) )
      {
        return CMD_ZERO_MOTOR;
      }
      else if ( (strcasecmp(cmd, "STATUS") == 0) || (strcasecmp(cmd, "?") == 0) )
      {
        return CMD_STATUS;
      }
      else if ( (strcasecmp(cmd, "PINGLC") == 0) || (strcasecmp(cmd, "NAU7802") == 0) ||
                (strcasecmp(cmd, "NAU") == 0) || (strcasecmp(cmd, "LC") == 0) )
      {
        return CMD_PING_LC;
      }
      else if ( strcasecmp(cmd, "HELP") == 0 )
      {
        return CMD_HELP;
      }
      else if ( strcasecmp(cmd, "TMC") == 0 )
      {
        return CMD_TMC;
      }
      else if ( strcasecmp(cmd, "SPO2") == 0 )
      {
        return CMD_SPO2;
      }
      else if ( (strcasecmp(cmd, "RESETARREST") == 0) || (strcasecmp(cmd, "UNARREST") == 0) ||
                (strcasecmp(cmd, "CLEARARREST") == 0) )
      {
        return CMD_RESET_ARREST;
      }
      else if ( (strcasecmp(cmd, "HOME") == 0) || (strcasecmp(cmd, "H") == 0) )
      {
        return CMD_HOME;
      }
      else if ( (strcasecmp(cmd, "TARE") == 0) || (strcasecmp(cmd, "T") == 0) )
      {
        return CMD_TARE;
      }
      else if ( (strcasecmp(cmd, "DFU") == 0) || (strcasecmp(cmd, "BOOTLOADER") == 0) )
      {
        return CMD_DFU;
      }
      else if ( (strncasecmp(cmd, "DIR", 3) == 0) || (strcasecmp(cmd, "INVERT") == 0) )
      {
        const char *p = (strncasecmp(cmd, "DIR", 3) == 0) ? &cmd[3] : &cmd[6];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p == '?' )
        {
          s_cmd_param = -2.0f; /* -2 indicates query without toggle */
        }
        else if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
        }
        else if ( strcasecmp(cmd, "INVERT") == 0 )
        {
          s_cmd_param = -1.0f; /* -1 indicates toggle */
        }
        else
        {
          s_cmd_param = -2.0f; /* plain "DIR" queries current direction */
        }
        return CMD_SET_DIR;
      }
      else if ( (strncasecmp(cmd, "HOMETHR", 7) == 0) || (strncasecmp(cmd, "SGTHR", 5) == 0) )
      {
        const char *p = (strncasecmp(cmd, "HOMETHR", 7) == 0) ? &cmd[7] : &cmd[5];
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
      else if ( (strncasecmp(cmd, "HOMESPEED", 9) == 0) || (strncasecmp(cmd, "HSPEED", 6) == 0) )
      {
        const char *p = (strncasecmp(cmd, "HOMESPEED", 9) == 0) ? &cmd[9] : &cmd[6];
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
      else if ( (strncasecmp(cmd, "HOMECURR", 8) == 0) || (strncasecmp(cmd, "HCURR", 5) == 0) )
      {
        const char *p = (strncasecmp(cmd, "HOMECURR", 8) == 0) ? &cmd[8] : &cmd[5];
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
      else if ( (strncasecmp(cmd, "HOMESLACK", 9) == 0) || (strncasecmp(cmd, "HSLACK", 6) == 0) || (strncasecmp(cmd, "SLACK", 5) == 0) )
      {
        const char *p = (strncasecmp(cmd, "HOMESLACK", 9) == 0) ? &cmd[9] :
                        (strncasecmp(cmd, "HSLACK", 6) == 0) ? &cmd[6] : &cmd[5];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_HOMESLACK;
        }
      }
      else if ( (strncasecmp(cmd, "TORQUE", 6) == 0) || (strncasecmp(cmd, "TORQ", 4) == 0) )
      {
        /* Support "TORQUE 120.0", "TORQ 90.0", "TORQUE:150", etc. (lbf*in) */
        const char *p = (strncasecmp(cmd, "TORQUE", 6) == 0) ? &cmd[6] : &cmd[4];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_TORQUE;
        }
      }
      else if ( (strncasecmp(cmd, "ARM", 3) == 0) || (strncasecmp(cmd, "FOREARM", 7) == 0) )
      {
        /* Support "ARM 12.0", "ARM 9.5", "FOREARM 10.0" (inches) */
        const char *p = (strncasecmp(cmd, "FOREARM", 7) == 0) ? &cmd[7] : &cmd[3];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_ARM;
        }
      }
      else if ( (strncasecmp(cmd, "ARRESTTHR", 9) == 0) || (strncasecmp(cmd, "DROPTHR", 7) == 0) )
      {
        /* Support "ARRESTTHR -160", "DROPTHR 180" (deg/s threshold) */
        const char *p = (strncasecmp(cmd, "ARRESTTHR", 9) == 0) ? &cmd[9] : &cmd[7];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          float v = (float)strtod(p, (char **)0);
          if ( v > 0.0f ) v = -v; /* Ensure negative threshold */
          s_cmd_param = v;
          return CMD_SET_ARREST_THRESH;
        }
      }
      else if ( (strncasecmp(cmd, "RES", 3) == 0) || (strncasecmp(cmd, "SET", 3) == 0) )
      {
        /* Support "RES 10.5", "RES:10.5", "RES=10.5", "SET 10.5", etc. */
        const char *p = &cmd[3];
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
      else if ( (strncasecmp(cmd, "POS", 3) == 0) || (strncasecmp(cmd, "MOVE", 4) == 0) )
      {
        /* Support direct stepper positioning: "POS 6.5", "POS:6.5", "MOVE 12.0", etc. */
        const char *p = (strncasecmp(cmd, "POS", 3) == 0) ? &cmd[3] : &cmd[4];
        while ( (*p == ' ') || (*p == ':') || (*p == '=') || (*p == '\t') )
        {
          p++;
        }
        if ( *p != '\0' )
        {
          s_cmd_param = (float)strtod(p, (char **)0);
          return CMD_SET_POSITION;
        }
      }
      else if ( strncasecmp(cmd, "CURR", 4) == 0 )
      {
        /* Support "CURR 1700", "CURR 1.7", "CURR:1700", etc. */
        const char *p = &cmd[4];
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

  /* 2. Flush any pending USB TX chunks and poll USB CDC RX ring buffer */
  Telemetry_TxKick();
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

/* Return number of queued bytes currently waiting in the USB TX ring */
static inline uint16_t Telemetry_TxUsedBytes(void)
{
  uint16_t head = s_tx_head;
  uint16_t tail = s_tx_tail;
  return (head >= tail) ? (uint16_t)(head - tail)
                        : (uint16_t)(TX_RING_BUF_SIZE - tail + head);
}

/* Drain the next queued USB CDC chunk if the IN endpoint is idle
** Notes:
**   Safe to call from both thread mode (after enqueue/poll) and OTG_FS_IRQHandler
**   (via Telemetry_OnUsbTxComplete). Masks OTG_FS_IRQn briefly in thread mode so
**   s_tx_tail and hcdc->TxState cannot race, preventing torn IN DMA buffers.
*/
static void Telemetry_TxKick(void)
{
  bool in_thread = ((SCB->ICSR & SCB_ICSR_VECTACTIVE_Msk) == 0U);
  uint32_t irq_enabled = in_thread ? NVIC_GetEnableIRQ(OTG_FS_IRQn) : 0U;
  if ( irq_enabled != 0U )
  {
    NVIC_DisableIRQ(OTG_FS_IRQn);
  }

  uint16_t count = Telemetry_TxUsedBytes();
  if ( (hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED) &&
       (hUsbDeviceFS.pClassData != (void *)0) &&
       (count > 0U) )
  {
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
    if ( hcdc->TxState == 0U )
    {
      if ( count > TX_CHUNK_MAX_SIZE )
      {
        count = TX_CHUNK_MAX_SIZE;
      }
      for ( uint16_t i = 0U; i < count; i++ )
      {
        s_tx_usb_chunk[i] = s_tx_ring[(s_tx_tail + i) % TX_RING_BUF_SIZE];
      }
      if ( CDC_Transmit_FS(s_tx_usb_chunk, count) == USBD_OK )
      {
        s_tx_tail = (uint16_t)((s_tx_tail + count) % TX_RING_BUF_SIZE);
      }
    }
  }

  if ( irq_enabled != 0U )
  {
    NVIC_EnableIRQ(OTG_FS_IRQn);
  }
} /* Telemetry_TxKick() */

/* Atomically enqueue a full packet or ASCII line into the USB TX ring buffer */
static bool Telemetry_EnqueueUsb(const uint8_t *data, uint16_t len)
{
  if ( (data == (const uint8_t *)0) || (len == 0U) || (len >= TX_RING_BUF_SIZE) )
  {
    return false;
  }
  if ( hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED )
  {
    return false;
  }

  uint32_t irq_enabled = NVIC_GetEnableIRQ(OTG_FS_IRQn);
  if ( irq_enabled != 0U )
  {
    NVIC_DisableIRQ(OTG_FS_IRQn);
  }

  uint16_t free_bytes = (uint16_t)((TX_RING_BUF_SIZE - 1U) - Telemetry_TxUsedBytes());
  bool fits = (free_bytes >= len);
  if ( fits )
  {
    for ( uint16_t i = 0U; i < len; i++ )
    {
      s_tx_ring[s_tx_head] = data[i];
      s_tx_head = (uint16_t)((s_tx_head + 1U) % TX_RING_BUF_SIZE);
    }
  }

  if ( irq_enabled != 0U )
  {
    NVIC_EnableIRQ(OTG_FS_IRQn);
  }

  if ( fits )
  {
    Telemetry_TxKick();
  }
  return fits;
} /* Telemetry_EnqueueUsb() */

/* USB CDC IN transfer completion hook invoked from CDC_TransmitCplt_FS */
void Telemetry_OnUsbTxComplete(void)
{
  Telemetry_TxKick();
} /* Telemetry_OnUsbTxComplete() */

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

  /* Atomically enqueue whole 28-byte packet so in-flight USB DMA is never torn */
  (void)Telemetry_EnqueueUsb((const uint8_t *)pkt, (uint16_t)sizeof(TelemetryPacket_t));
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

  size_t raw_len = strlen(msg);
  uint16_t len = (raw_len > 256U) ? 256U : (uint16_t)raw_len;

  /* Transmit over hardware UART if initialized */
  if ( s_huart != (UART_HandleTypeDef *)0 )
  {
    HAL_UART_Transmit(s_huart, (const uint8_t *)msg, len, 100);
  }

  /* Atomically enqueue whole ASCII ACK line (up to 256 bytes, avoiding truncation & drops) */
  (void)Telemetry_EnqueueUsb((const uint8_t *)msg, len);
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
