/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: tmc2209.c
** --------
** Complete single-wire UART driver implementation for TMC2209.
** Provides digital current scaling, StealthChop2, CoolStep,
** StallGuard4 load sensing, 256 microstepping, VACTUAL velocity
** control, and comprehensive hardware fault diagnostics.
*/

#include "tmc2209.h"
#include <string.h>
#include <stdio.h>
#include <math.h>

#define TMC2209_UART_TX_PIN         GPIO_PIN_2
#define TMC2209_UART_TX_PORT        GPIOA
#define TMC2209_UART_RX_PIN         GPIO_PIN_3
#define TMC2209_UART_RX_PORT        GPIOA

/* Private Module Variables */
static UART_HandleTypeDef s_tmc_uart;
static uint8_t             s_slave_addr      = 0;          /* Dynamic slave address (0..3) */
static bool                s_is_initialized  = false;
static uint32_t            s_gconf_shadow    = 0;
static uint32_t            s_chopconf_shadow = 0x10000053; /* Default chopper */

static uint8_t             s_diag_tx_status  = 0xFF;
static uint8_t             s_diag_rx_status  = 0xFF;
static uint8_t             s_diag_rx[8]      = {0};
static uint8_t             s_diag_rx_count   = 0;
static uint32_t            s_diag_sr         = 0;

/* Private Function Prototypes */
static uint8_t TMC2209_CalcCRC(const uint8_t *datagram, uint8_t datagram_len);

/* Calculate Trinamic 8-bit CRC using CRC-8-ATM polynomial (0x07)
** Parameters:
**   datagram - Pointer to buffer to checksum
**   datagram_len - Length of datagram including CRC byte
** Return:
**   uint8_t: Computed CRC-8 checksum
** Notes:
**   Private helper function
*/
static uint8_t TMC2209_CalcCRC(const uint8_t *datagram, uint8_t datagram_len)
{
  uint8_t crc = 0;
  for ( uint8_t i = 0; i < (datagram_len - 1); i++ )
  {
    uint8_t current_byte = datagram[i];
    for ( uint8_t j = 0; j < 8; j++ )
    {
      if ( ((crc >> 7) ^ (current_byte & 0x01)) != 0 )
      {
        crc = (uint8_t)((crc << 1) ^ 0x07);
      }
      else
      {
        crc = (uint8_t)(crc << 1);
      }
      current_byte >>= 1;
    }
  }
  return crc;
} /* TMC2209_CalcCRC() */

/* Write a 32-bit register to the TMC2209 over single-wire UART
** Parameters:
**   reg - Register address (0x00 to 0x7F)
**   data - 32-bit value to write
** Return:
**   bool: True if transmitted successfully
** Notes:
**   Appends Trinamic 8-bit CRC checksum
*/
bool TMC2209_WriteRegister(uint8_t reg, uint32_t data)
{
  uint8_t tx[8];
  tx[0] = 0x05;                        /* Sync nibble */
  tx[1] = s_slave_addr;                /* Slave address (0..3) */
  tx[2] = (uint8_t)(reg | 0x80);       /* Register address with write bit */
  tx[3] = (uint8_t)((data >> 24) & 0xFF);
  tx[4] = (uint8_t)((data >> 16) & 0xFF);
  tx[5] = (uint8_t)((data >> 8)  & 0xFF);
  tx[6] = (uint8_t)(data & 0xFF);
  tx[7] = TMC2209_CalcCRC(tx, 8);

  HAL_HalfDuplex_EnableTransmitter(&s_tmc_uart);
  HAL_StatusTypeDef status = HAL_UART_Transmit(&s_tmc_uart, tx, 8, 20);
  HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);

  /* Small inter-datagram gap (min 8 bit times = ~70 us) */
  for ( volatile int i = 0; i < 200; i++ )
  {
    __NOP();
  }

  return (status == HAL_OK);
} /* TMC2209_WriteRegister() */

/* Read a 32-bit register from the TMC2209 over single-wire UART
** Parameters:
**   reg - Register address (0x00 to 0x7F)
**   data - Pointer to store received 32-bit value
** Return:
**   bool: True if valid reply received with correct CRC
** Notes:
**   Validates master address and CRC
*/
bool TMC2209_ReadRegister(uint8_t reg, uint32_t *data)
{
  if ( data == (uint32_t *)0 )
  {
    return false;
  }

  uint8_t req[4];
  req[0] = 0x05;                       /* Sync nibble */
  req[1] = s_slave_addr;               /* Slave address (0..3) */
  req[2] = (uint8_t)(reg & 0x7F);      /* Register address with read bit (0) */
  req[3] = TMC2209_CalcCRC(req, 4);

  /* Clear any prior errors before transmitting */
  __HAL_UART_CLEAR_OREFLAG(&s_tmc_uart);
  __HAL_UART_CLEAR_NEFLAG(&s_tmc_uart);
  __HAL_UART_CLEAR_FEFLAG(&s_tmc_uart);

  HAL_HalfDuplex_EnableTransmitter(&s_tmc_uart);
  HAL_StatusTypeDef tx_status = HAL_UART_Transmit(&s_tmc_uart, req, 4, 15);
  HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);

  s_diag_tx_status = (uint8_t)tx_status;
  if ( tx_status != HAL_OK )
  {
    return false;
  }

  /* Receive 8-byte response datagram directly on PA2 from TMC2209 */
  uint8_t rx[8];
  memset(rx, 0, sizeof(rx));
  HAL_StatusTypeDef rx_status = HAL_UART_Receive(&s_tmc_uart, rx, 8, 30);

  s_diag_rx_status = (uint8_t)rx_status;
  s_diag_sr        = s_tmc_uart.Instance->SR;
  s_diag_rx_count  = (uint8_t)(8 - s_tmc_uart.RxXferCount);
  memcpy(s_diag_rx, rx, 8);

  if ( rx_status != HAL_OK )
  {
    return false;
  }

  /* Validate sync byte, master address (0xFF), register match, and CRC-8 */
  if ( (rx[0] != 0x05) || (rx[1] != 0xFF) || (rx[2] != (reg & 0x7F)) )
  {
    return false;
  }

  if ( TMC2209_CalcCRC(rx, 8) != rx[7] )
  {
    return false; /* CRC-8 mismatch */
  }

  *data = ((uint32_t)rx[3] << 24) |
          ((uint32_t)rx[4] << 16) |
          ((uint32_t)rx[5] << 8)  |
          ((uint32_t)rx[6]);

  return true;
} /* TMC2209_ReadRegister() */

/* Format diagnostic telemetry into buffer when driver is offline
** Parameters:
**   buf - Destination string buffer
**   max_len - Maximum buffer capacity
*/
void TMC2209_GetDiagnostic(char *buf, size_t max_len)
{
  uint8_t pa2   = (uint8_t)HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_2);
  uint8_t diag  = (uint8_t)HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_1);
  uint8_t index = (uint8_t)HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_3);
  uint8_t ms1   = (uint8_t)HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_7);
  uint8_t ms2   = (uint8_t)HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_0);

  snprintf(buf, max_len,
           "ACK:TMC:ONLINE=0,BAUD=%lu,ADDR=%u,TX=%u,RX=%u,CNT=%u,RAW=%02X%02X%02X%02X%02X%02X%02X%02X,PA2=%u,DIAG=%u,INDEX=%u,MS1=%u,MS2=%u,SR=0x%02lX\r\n",
           (unsigned long)s_tmc_uart.Init.BaudRate, s_slave_addr, s_diag_tx_status, s_diag_rx_status, s_diag_rx_count,
           s_diag_rx[0], s_diag_rx[1], s_diag_rx[2], s_diag_rx[3],
           s_diag_rx[4], s_diag_rx[5], s_diag_rx[6], s_diag_rx[7],
           pa2, diag, index, ms1, ms2, (unsigned long)s_diag_sr);
} /* TMC2209_GetDiagnostic() */

/* Verify active UART communications with TMC2209 by reading IFCNT
** Automatically probes all 4 possible slave addresses (0..3) if needed
** Parameters:
**   None
** Return:
**   bool: True if responding
** Notes:
**   None
*/
bool TMC2209_Ping(void)
{
  uint32_t ifcnt = 0;
  if ( TMC2209_ReadRegister(TMC2209_REG_IFCNT, &ifcnt) )
  {
    return true;
  }

  /* Probe other slave addresses in case MS1/MS2 bootstrapped to 1, 2, or 3 */
  uint8_t saved_addr = s_slave_addr;
  for ( uint8_t addr = 0; addr < 4; addr++ )
  {
    if ( addr == saved_addr )
    {
      continue;
    }
    s_slave_addr = addr;
    if ( TMC2209_ReadRegister(TMC2209_REG_IFCNT, &ifcnt) )
    {
      return true;
    }
  }

  s_slave_addr = saved_addr;
  return false;
} /* TMC2209_Ping() */

/* Initialize hardware UART peripheral and configure TMC2209 with optimal defaults
** Parameters:
**   None
** Return:
**   bool: True if TMC2209 is detected and initialized over UART
** Notes:
**   Configures USART2 on PA2 (TX / Half-Duplex Single-Wire)
*/
bool TMC2209_Init(void)
{
  /* 1. Enable Clocks for USART2 and GPIOA */
  __HAL_RCC_USART2_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* 2. Configure GPIO Pin for USART2 (PA2 TX/Single-Wire Push-Pull with internal Pull-up) */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin       = TMC2209_UART_TX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull      = GPIO_PULLUP;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART2;
  HAL_GPIO_Init(TMC2209_UART_TX_PORT, &GPIO_InitStruct);

  /* 3. Configure USART2 Peripheral Handle in Single-Wire Half-Duplex mode */
  s_tmc_uart.Instance          = USART2;
  s_tmc_uart.Init.WordLength   = UART_WORDLENGTH_8B;
  s_tmc_uart.Init.StopBits     = UART_STOPBITS_1;
  s_tmc_uart.Init.Parity       = UART_PARITY_NONE;
  s_tmc_uart.Init.Mode         = UART_MODE_TX_RX;
  s_tmc_uart.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
  s_tmc_uart.Init.OverSampling = UART_OVERSAMPLING_16;

  /* Standard baud rates to probe (115200 standard, fallback to 57600, 19200) */
  const uint32_t bauds[] = { 115200, 57600, 19200 };
  const size_t num_bauds = sizeof(bauds) / sizeof(bauds[0]);

  s_gconf_shadow = TMC2209_GCONF_MSTEP_REG_SELECT |
                   TMC2209_GCONF_PDN_DISABLE      |
                   TMC2209_GCONF_MULTISTEP_FILT;

  bool link_ok = false;

  for ( size_t b = 0; b < num_bauds && !link_ok; b++ )
  {
    s_tmc_uart.Init.BaudRate = bauds[b];
    HAL_HalfDuplex_Init(&s_tmc_uart);
    HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);
    HAL_Delay(10);

    /* Write GCONF with pdn_disable=1 across addresses 0..3 to unlock bidirectional UART mode */
    for ( uint8_t addr = 0; addr < 4; addr++ )
    {
      s_slave_addr = addr;
      TMC2209_WriteRegister(TMC2209_REG_GCONF, s_gconf_shadow);
      HAL_Delay(2);
    }

    /* Probe IFCNT to detect response */
    for ( int attempt = 0; attempt < 4; attempt++ )
    {
      if ( TMC2209_Ping() )
      {
        link_ok = true;
        break;
      }
      HAL_Delay(5);
    }
  }

  if ( !link_ok )
  {
    s_is_initialized = false;
    return false;
  }

  /* 6. Commit final Base Global Configuration */
  TMC2209_WriteRegister(TMC2209_REG_GCONF, s_gconf_shadow);

  /* 7. Set Standard Running Current (1.3 A / 1300 mA RMS limit over UART, 50% hold current) */
  TMC2209_SetCurrent(1300, 50);

  /* 8. Configure 1/16 Microstepping with 256-Microstep Interpolation */
  TMC2209_SetMicrostepping(16, true);

  /* 9. Enable StealthChop2 (Whisper-Quiet Operation) */
  TMC2209_EnableStealthChop(true);

  /* 10. Enable CoolStep (Automatic load-adaptive current reduction) */
  TMC2209_ConfigureCoolStep(2, 5);

  /* 11. Configure StallGuard4 load sensitivity */
  TMC2209_ConfigureStallGuard(64);

  s_is_initialized = true;
  return true;
} /* TMC2209_Init() */

/* Program digital RMS coil current in milliamps and standstill hold percentage
** Parameters:
**   run_current_mA - Commanded running current (e.g. 800 to 1700 mA RMS)
**   hold_percent - Standstill current as percentage of run current (0 to 100%)
** Return:
**   bool: True if successfully written
** Notes:
**   Eliminates the need for screwdriver adjustment of VREF
*/
bool TMC2209_SetCurrent(uint16_t run_current_mA, uint8_t hold_percent)
{
  if ( run_current_mA > 2000 )
  {
    run_current_mA = 2000;
  }
  if ( hold_percent > 100 )
  {
    hold_percent = 100;
  }

  /* Maximum RMS current for Rsense = 0.11 ohms at CS = 31 is ~1770 mA */
  float max_rms_mA = 1770.0f;
  int cs = (int)lroundf(((float)run_current_mA / max_rms_mA) * 32.0f) - 1;
  if ( cs < 0 )
  {
    cs = 0;
  }
  else if ( cs > 31 )
  {
    cs = 31;
  }

  uint8_t irun  = (uint8_t)cs;
  uint8_t ihold = (uint8_t)((irun * hold_percent) / 100);
  uint8_t iholddelay = 4; /* Standard ~130 ms power-down delay */

  uint32_t val = ((uint32_t)iholddelay << 16) |
                 ((uint32_t)irun       << 8)  |
                 ((uint32_t)ihold);

  return TMC2209_WriteRegister(TMC2209_REG_IHOLD_IRUN, val);
} /* TMC2209_SetCurrent() */

/* Configure microstepping resolution and 256-microstep interpolation
** Parameters:
**   microsteps - 1, 2, 4, 8, 16, 32, 64, 128, or 256
**   interpolate_256 - True to enable internal 256-step interpolation
** Return:
**   bool: True if successfully programmed
** Notes:
**   None
*/
bool TMC2209_SetMicrostepping(uint16_t microsteps, bool interpolate_256)
{
  uint8_t mres;

  switch ( microsteps )
  {
    case 256:
      mres = 0;
      break;
    case 128:
      mres = 1;
      break;
    case 64:
      mres = 2;
      break;
    case 32:
      mres = 3;
      break;
    case 16:
      mres = 4;
      break;
    case 8:
      mres = 5;
      break;
    case 4:
      mres = 6;
      break;
    case 2:
      mres = 7;
      break;
    case 1:
      mres = 8;
      break;
    default:
      mres = 4;
      break;
  } /* switch ( microsteps ) */

  /* Read-modify-write CHOPCONF */
  uint32_t chopconf = s_chopconf_shadow;
  chopconf &= ~((0x0FU << 24) | (1U << 28)); /* Clear MRES and INTPOL bits */
  chopconf |= ((uint32_t)mres << 24);

  if ( interpolate_256 )
  {
    chopconf |= (1U << 28); /* Set intpol = 1 */
  }

  s_chopconf_shadow = chopconf;
  return TMC2209_WriteRegister(TMC2209_REG_CHOPCONF, s_chopconf_shadow);
} /* TMC2209_SetMicrostepping() */

/* Toggle between StealthChop2 and SpreadCycle
** Parameters:
**   enable - True for StealthChop2, False for SpreadCycle
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool TMC2209_EnableStealthChop(bool enable)
{
  if ( enable )
  {
    s_gconf_shadow &= ~TMC2209_GCONF_EN_SPREADCYCLE;
  }
  else
  {
    s_gconf_shadow |= TMC2209_GCONF_EN_SPREADCYCLE;
  }

  return TMC2209_WriteRegister(TMC2209_REG_GCONF, s_gconf_shadow);
} /* TMC2209_EnableStealthChop() */

/* Set velocity threshold where driver automatically switches to SpreadCycle
** Parameters:
**   speed_tstep - Measured step period threshold
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool TMC2209_SetSpreadCycleThreshold(uint32_t speed_tstep)
{
  return TMC2209_WriteRegister(TMC2209_REG_TPWMTHRS, speed_tstep);
} /* TMC2209_SetSpreadCycleThreshold() */

/* Configure CoolStep load-dependent current reduction
** Parameters:
**   semin - Lower StallGuard threshold to increase current
**   semax - Upper StallGuard threshold to decrease current
** Return:
**   bool: True if programmed
** Notes:
**   Saves up to 75% power during static rehabilitation holds
*/
bool TMC2209_ConfigureCoolStep(uint8_t semin, uint8_t semax)
{
  if ( semin == 0 )
  {
    /* Disable CoolStep */
    return TMC2209_WriteRegister(TMC2209_REG_COOLCONF, 0);
  }

  uint32_t coolconf = ((uint32_t)(semin & 0x0F))       |
                      (1U << 5)                         |
                      ((uint32_t)(semax & 0x0F) << 8)   |
                      (1U << 13);

  /* Enable CoolStep threshold speed */
  TMC2209_WriteRegister(TMC2209_REG_TCOOLTHRS, 0x000FFFFF);
  return TMC2209_WriteRegister(TMC2209_REG_COOLCONF, coolconf);
} /* TMC2209_ConfigureCoolStep() */

/* Configure StallGuard4 detection threshold (0..255)
** Parameters:
**   threshold - Sensitivity value (higher = triggers on lighter load)
** Return:
**   bool: True if programmed
** Notes:
**   None
*/
bool TMC2209_ConfigureStallGuard(uint8_t threshold)
{
  return TMC2209_WriteRegister(TMC2209_REG_SGTHRS, (uint32_t)threshold);
} /* TMC2209_ConfigureStallGuard() */

/* Read live mechanical load measurement from motor coils (0..1023)
** Parameters:
**   None
** Return:
**   uint16_t: StallGuard load indicator
** Notes:
**   Higher values indicate light load; lower values indicate heavy load
*/
uint16_t TMC2209_ReadStallGuard(void)
{
  uint32_t val = 0;
  if ( TMC2209_ReadRegister(TMC2209_REG_SG_RESULT, &val) )
  {
    return (uint16_t)(val & 0x3FF);
  }
  return 0;
} /* TMC2209_ReadStallGuard() */

/* Invert motor direction directly in software
** Parameters:
**   invert - True to reverse shaft direction
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool TMC2209_SetShaftInvert(bool invert)
{
  if ( invert )
  {
    s_gconf_shadow |= TMC2209_GCONF_SHAFT;
  }
  else
  {
    s_gconf_shadow &= ~TMC2209_GCONF_SHAFT;
  }
  return TMC2209_WriteRegister(TMC2209_REG_GCONF, s_gconf_shadow);
} /* TMC2209_SetShaftInvert() */

/* Command motor velocity using TMC2209 internal step generator (VACTUAL)
** Parameters:
**   velocity - Signed velocity in microsteps / t
** Return:
**   bool: True if commanded
** Notes:
**   Set velocity to 0 to restore external STEP/DIR pin control
*/
bool TMC2209_SetVActual(int32_t velocity)
{
  return TMC2209_WriteRegister(TMC2209_REG_VACTUAL, (uint32_t)velocity);
} /* TMC2209_SetVActual() */

/* Read logic level states of physical hardware pins
** Parameters:
**   None
** Return:
**   uint32_t: Raw IOIN register value
** Notes:
**   None
*/
uint32_t TMC2209_ReadIO(void)
{
  uint32_t val = 0;
  TMC2209_ReadRegister(TMC2209_REG_IOIN, &val);
  return val;
} /* TMC2209_ReadIO() */

/* Query comprehensive driver health, temperature, and coil short diagnostics
** Parameters:
**   status - Pointer to TMC2209_Status_t struct to populate
** Return:
**   bool: True if telemetry read succeeded
** Notes:
**   None
*/
bool TMC2209_ReadStatus(TMC2209_Status_t *status)
{
  if ( status == (TMC2209_Status_t *)0 )
  {
    return false;
  }

  uint32_t drv_status = 0;
  if ( !TMC2209_ReadRegister(TMC2209_REG_DRV_STATUS, &drv_status) )
  {
    status->uart_online = false;
    return false;
  }

  status->uart_online               = true;
  status->over_temperature_warning  = ((drv_status & (1U << 0)) != 0);
  status->over_temperature_shutdown = ((drv_status & (1U << 1)) != 0);
  status->short_to_ground_a         = ((drv_status & (1U << 2)) != 0);
  status->short_to_ground_b         = ((drv_status & (1U << 3)) != 0);
  status->short_to_supply_a         = ((drv_status & (1U << 4)) != 0);
  status->short_to_supply_b         = ((drv_status & (1U << 5)) != 0);
  status->open_load_a               = ((drv_status & (1U << 6)) != 0);
  status->open_load_b               = ((drv_status & (1U << 7)) != 0);
  status->current_scale             = (uint8_t)((drv_status >> 16) & 0x1F);
  status->stealthchop_active        = ((drv_status & (1U << 30)) != 0);
  status->standstill                = ((drv_status & (1U << 31)) != 0);

  status->stallguard_result         = TMC2209_ReadStallGuard();

  /* Fault is active if over-temperature shutdown or coil short detected */
  status->driver_fault              = status->over_temperature_shutdown ||
                                      status->short_to_ground_a         ||
                                      status->short_to_ground_b         ||
                                      status->short_to_supply_a         ||
                                      status->short_to_supply_b;

  return true;
} /* TMC2209_ReadStatus() */
