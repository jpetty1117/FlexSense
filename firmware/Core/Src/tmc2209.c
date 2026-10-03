/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: tmc2209.c
  * Brief: Complete single-wire UART driver implementation for TMC2209.
  *        Provides digital current scaling, StealthChop2, CoolStep,
  *        StallGuard4 load sensing, 256 microstepping, VACTUAL velocity
  *        control, and comprehensive hardware fault diagnostics.
  ******************************************************************************
  */

#include "tmc2209.h"
#include <string.h>

/* Private Module Variables */
static UART_HandleTypeDef s_tmc_uart;
static bool                s_is_initialized = false;
static uint32_t            s_gconf_shadow   = 0;
static uint32_t            s_chopconf_shadow= 0x10000053; /* Default chopper */

/**
  * @brief  Calculate Trinamic 8-bit CRC using CRC-8-ATM polynomial (0x07).
  * @param  datagram: Pointer to buffer to checksum.
  * @param  datagram_len: Length of datagram including CRC byte.
  * @retval uint8_t: Computed CRC-8 checksum.
  */
static uint8_t TMC2209_CalcCRC(const uint8_t *datagram, uint8_t datagram_len)
{
  uint8_t crc = 0;
  for ( uint8_t i = 0; i < (datagram_len - 1); i++ )
  {
    uint8_t current_byte = datagram[i];
    for ( uint8_t j = 0; j < 8; j++ )
    {
      if ( (crc >> 7) ^ (current_byte & 0x01) )
      {
        crc = (uint8_t)( (crc << 1) ^ 0x07 );
      }
      else
      {
        crc = (uint8_t)( crc << 1 );
      }
      current_byte >>= 1;
    }
  }
  return crc;
}

/**
  * @brief  Write a 32-bit register to the TMC2209 over single-wire UART.
  * @param  reg: Register address (0x00 to 0x7F).
  * @param  data: 32-bit value to write.
  * @retval bool: True if transmitted successfully.
  */
bool TMC2209_WriteRegister(uint8_t reg, uint32_t data)
{
  uint8_t tx[8];
  tx[0] = 0x05;                        /* Sync nibble */
  tx[1] = 0x00;                        /* Slave address (0) */
  tx[2] = (uint8_t)( reg | 0x80 );     /* Register address with write bit */
  tx[3] = (uint8_t)( (data >> 24) & 0xFF );
  tx[4] = (uint8_t)( (data >> 16) & 0xFF );
  tx[5] = (uint8_t)( (data >> 8)  & 0xFF );
  tx[6] = (uint8_t)( data & 0xFF );
  tx[7] = TMC2209_CalcCRC(tx, 8);

#if TMC2209_USE_HALF_DUPLEX
  HAL_HalfDuplex_EnableTransmitter(&s_tmc_uart);
#endif

  HAL_StatusTypeDef status = HAL_UART_Transmit(&s_tmc_uart, tx, 8, 20);

#if TMC2209_USE_HALF_DUPLEX
  HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);
#endif

  /* Small inter-datagram gap (min 8 bit times = ~70 us) */
  for ( volatile int i = 0; i < 200; i++ )
  {
    __NOP();
  }

  return ( status == HAL_OK );
} /* TMC2209_WriteRegister() */

/**
  * @brief  Read a 32-bit register from the TMC2209 over single-wire UART.
  * @param  reg: Register address (0x00 to 0x7F).
  * @param  data: Pointer to store received 32-bit value.
  * @retval bool: True if valid reply received with correct CRC.
  */
bool TMC2209_ReadRegister(uint8_t reg, uint32_t *data)
{
  if ( data == NULL )
  {
    return false;
  }

  uint8_t req[4];
  req[0] = 0x05;                       /* Sync nibble */
  req[1] = 0x00;                       /* Slave address (0) */
  req[2] = (uint8_t)( reg & 0x7F );    /* Register address with read bit (0) */
  req[3] = TMC2209_CalcCRC(req, 4);

#if TMC2209_USE_HALF_DUPLEX
  HAL_HalfDuplex_EnableTransmitter(&s_tmc_uart);
#endif

  HAL_StatusTypeDef tx_status = HAL_UART_Transmit(&s_tmc_uart, req, 4, 15);

#if TMC2209_USE_HALF_DUPLEX
  HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);
#else
  /* In 2-wire resistor mode, discard the 4-byte transmitted echo */
  uint8_t echo[4];
  HAL_UART_Receive(&s_tmc_uart, echo, 4, 10);
#endif

  if ( tx_status != HAL_OK )
  {
    return false;
  }

  /* Receive 8-byte response datagram from TMC2209 */
  uint8_t rx[8];
  memset(rx, 0, sizeof(rx));
  HAL_StatusTypeDef rx_status = HAL_UART_Receive(&s_tmc_uart, rx, 8, 25);

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

  *data = ( (uint32_t)rx[3] << 24 ) |
          ( (uint32_t)rx[4] << 16 ) |
          ( (uint32_t)rx[5] << 8  ) |
          ( (uint32_t)rx[6] );

  return true;
} /* TMC2209_ReadRegister() */

/**
  * @brief  Verify active UART communications with TMC2209 by reading IFCNT.
  * @retval bool: True if responding.
  */
bool TMC2209_Ping(void)
{
  uint32_t ifcnt = 0;
  return TMC2209_ReadRegister(TMC2209_REG_IFCNT, &ifcnt);
} /* TMC2209_Ping() */

/**
  * @brief  Initialize hardware UART peripheral and configure TMC2209 with optimal defaults.
  * @retval bool: True if TMC2209 is detected and initialized over UART.
  */
bool TMC2209_Init(void)
{
  /* 1. Enable Clocks for USART1 and GPIOA */
  __HAL_RCC_USART1_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* 2. Configure GPIO Pins for USART1 */
  GPIO_InitTypeDef GPIO_InitStruct = {0};

#if TMC2209_USE_HALF_DUPLEX
  /* Single-wire half-duplex on PA9 (Open Drain with Pull-up) */
  GPIO_InitStruct.Pin       = TMC2209_UART_TX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_OD;
  GPIO_InitStruct.Pull      = GPIO_PULLUP;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(TMC2209_UART_TX_PORT, &GPIO_InitStruct);
#else
  /* 2-Wire Mode: PA9 (TX) and PA10 (RX) */
  GPIO_InitStruct.Pin       = TMC2209_UART_TX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull      = GPIO_NOPULL;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(TMC2209_UART_TX_PORT, &GPIO_InitStruct);

  GPIO_InitStruct.Pin       = TMC2209_UART_RX_PIN;
  GPIO_InitStruct.Mode      = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull      = GPIO_PULLUP;
  GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(TMC2209_UART_RX_PORT, &GPIO_InitStruct);
#endif

  /* 3. Configure USART1 Peripheral Handle */
  s_tmc_uart.Instance                    = USART1;
  s_tmc_uart.Init.BaudRate               = TMC2209_DEFAULT_BAUD;
  s_tmc_uart.Init.WordLength             = UART_WORDLENGTH_8B;
  s_tmc_uart.Init.StopBits               = UART_STOPBITS_1;
  s_tmc_uart.Init.Parity                 = UART_PARITY_NONE;
  s_tmc_uart.Init.Mode                   = UART_MODE_TX_RX;
  s_tmc_uart.Init.HwFlowCtl              = UART_HWCONTROL_NONE;
  s_tmc_uart.Init.OverSampling           = UART_OVERSAMPLING_16;

#if TMC2209_USE_HALF_DUPLEX
  HAL_HalfDuplex_Init(&s_tmc_uart);
  HAL_HalfDuplex_EnableReceiver(&s_tmc_uart);
#else
  HAL_UART_Init(&s_tmc_uart);
#endif

  /* 4. Small delay to allow TMC2209 internal PLL to settle after power-up */
  HAL_Delay(10);

  /* 5. Ping TMC2209 to verify link */
  bool link_ok = false;
  for ( int attempt = 0; attempt < 3; attempt++ )
  {
    if ( TMC2209_Ping() )
    {
      link_ok = true;
      break;
    }
    HAL_Delay(5);
  }

  if ( !link_ok )
  {
    s_is_initialized = false;
    return false;
  }

  /* 6. Configure Base Global Configuration (GCONF) */
  /* - i_scale_analog = 0: Use digital current from IHOLD_IRUN (ignore analog VREF pot)
     - mstep_reg_select = 1: Control microstepping over UART (ignore MS1/MS2 pins)
     - pdn_disable = 1: Keep UART communication enabled on PDN pin
     - multistep_filt = 1: Enable step pulse smoothing filter */
  s_gconf_shadow = TMC2209_GCONF_MSTEP_REG_SELECT |
                   TMC2209_GCONF_PDN_DISABLE      |
                   TMC2209_GCONF_MULTISTEP_FILT;
  TMC2209_WriteRegister(TMC2209_REG_GCONF, s_gconf_shadow);

  /* 7. Set Standard Running Current (1000 mA RMS, 50% hold current) */
  TMC2209_SetCurrent(1000, 50);

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

/**
  * @brief  Program digital RMS coil current in milliamps and standstill hold percentage.
  *         Eliminates the need for screwdriver adjustment of the analog VREF potentiometer.
  * @param  run_current_mA: Commanded running current (e.g. 800 to 1400 mA RMS).
  * @param  hold_percent: Standstill current as percentage of run current (0 to 100%).
  * @retval bool: True if successfully written.
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
  int cs = (int)( ((float)run_current_mA / max_rms_mA) * 32.0f ) - 1;
  if ( cs < 0 )
  {
    cs = 0;
  }
  else if ( cs > 31 )
  {
    cs = 31;
  }

  uint8_t irun  = (uint8_t)cs;
  uint8_t ihold = (uint8_t)( (irun * hold_percent) / 100 );
  uint8_t iholddelay = 4; /* Standard ~130 ms power-down delay */

  uint32_t val = ( (uint32_t)iholddelay << 16 ) |
                 ( (uint32_t)irun       << 8  ) |
                 ( (uint32_t)ihold );

  return TMC2209_WriteRegister(TMC2209_REG_IHOLD_IRUN, val);
} /* TMC2209_SetCurrent() */

/**
  * @brief  Configure microstepping resolution and 256-microstep interpolation.
  * @param  microsteps: 1, 2, 4, 8, 16, 32, 64, 128, or 256.
  * @param  interpolate_256: True to enable internal 256-step interpolation.
  * @retval bool: True if successfully programmed.
  */
bool TMC2209_SetMicrostepping(uint16_t microsteps, bool interpolate_256)
{
  uint8_t mres = 4; /* Default 16 */

  switch ( microsteps )
  {
    case 256: mres = 0; break;
    case 128: mres = 1; break;
    case 64:  mres = 2; break;
    case 32:  mres = 3; break;
    case 16:  mres = 4; break;
    case 8:   mres = 5; break;
    case 4:   mres = 6; break;
    case 2:   mres = 7; break;
    case 1:   mres = 8; break;
    default:  mres = 4; break;
  }

  /* Read-modify-write CHOPCONF */
  uint32_t chopconf = s_chopconf_shadow;
  chopconf &= ~( (0x0FU << 24) | (1U << 28) ); /* Clear MRES and INTPOL bits */
  chopconf |= ( (uint32_t)mres << 24 );

  if ( interpolate_256 )
  {
    chopconf |= ( 1U << 28 ); /* Set intpol = 1 */
  }

  s_chopconf_shadow = chopconf;
  return TMC2209_WriteRegister(TMC2209_REG_CHOPCONF, s_chopconf_shadow);
} /* TMC2209_SetMicrostepping() */

/**
  * @brief  Toggle between StealthChop2 (whisper-quiet) and SpreadCycle (max dynamic torque).
  * @param  enable: True for StealthChop2, False for SpreadCycle.
  * @retval bool: True if updated.
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

/**
  * @brief  Set velocity threshold where driver automatically switches to SpreadCycle.
  * @param  speed_tstep: Measured step period threshold.
  * @retval bool: True if updated.
  */
bool TMC2209_SetSpreadCycleThreshold(uint32_t speed_tstep)
{
  return TMC2209_WriteRegister(TMC2209_REG_TPWMTHRS, speed_tstep);
} /* TMC2209_SetSpreadCycleThreshold() */

/**
  * @brief  Configure CoolStep load-dependent current reduction.
  *         Saves up to 75% power and keeps motor cool during static rehabilitation holds.
  * @param  semin: Lower StallGuard threshold to increase current (e.g. 2). Set 0 to disable.
  * @param  semax: Upper StallGuard threshold to decrease current (e.g. 5).
  * @retval bool: True if programmed.
  */
bool TMC2209_ConfigureCoolStep(uint8_t semin, uint8_t semax)
{
  if ( semin == 0 )
  {
    /* Disable CoolStep */
    return TMC2209_WriteRegister(TMC2209_REG_COOLCONF, 0);
  }

  /* semin (bits 3..0), seup (bits 6..5 = 1), semax (bits 11..8), sedn (bits 14..13 = 1) */
  uint32_t coolconf = ( (uint32_t)(semin & 0x0F) )        |
                      ( 1U << 5 )                         |
                      ( (uint32_t)(semax & 0x0F) << 8 )   |
                      ( 1U << 13 );

  /* Enable CoolStep threshold speed */
  TMC2209_WriteRegister(TMC2209_REG_TCOOLTHRS, 0x000FFFFF);
  return TMC2209_WriteRegister(TMC2209_REG_COOLCONF, coolconf);
} /* TMC2209_ConfigureCoolStep() */

/**
  * @brief  Configure StallGuard4 detection threshold (0..255).
  * @param  threshold: Sensitivity value (higher = triggers on lighter load).
  * @retval bool: True if programmed.
  */
bool TMC2209_ConfigureStallGuard(uint8_t threshold)
{
  return TMC2209_WriteRegister(TMC2209_REG_SGTHRS, (uint32_t)threshold);
} /* TMC2209_ConfigureStallGuard() */

/**
  * @brief  Read live mechanical load measurement from motor coils (0..1023).
  *         Higher values indicate light load; lower values indicate heavy load / stall.
  * @retval uint16_t: StallGuard load indicator.
  */
uint16_t TMC2209_ReadStallGuard(void)
{
  uint32_t val = 0;
  if ( TMC2209_ReadRegister(TMC2209_REG_SG_RESULT, &val) )
  {
    return (uint16_t)( val & 0x3FF );
  }
  return 0;
} /* TMC2209_ReadStallGuard() */

/**
  * @brief  Invert motor direction directly in software without swapping coil wires.
  * @param  invert: True to reverse shaft direction.
  * @retval bool: True if updated.
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

/**
  * @brief  Command motor velocity using TMC2209 internal step generator (VACTUAL).
  *         Enables driving the motor directly over UART without pulsing the STEP pin.
  *         Set velocity to 0 to restore external STEP/DIR pin control.
  * @param  velocity: Signed velocity in microsteps / t. Set 0 to stop internal drive.
  * @retval bool: True if commanded.
  */
bool TMC2209_SetVActual(int32_t velocity)
{
  return TMC2209_WriteRegister(TMC2209_REG_VACTUAL, (uint32_t)velocity);
} /* TMC2209_SetVActual() */

/**
  * @brief  Read logic level states of physical hardware pins (ENN, MS1, MS2, DIAG, STEP, DIR).
  * @retval uint32_t: Raw IOIN register value.
  */
uint32_t TMC2209_ReadIO(void)
{
  uint32_t val = 0;
  TMC2209_ReadRegister(TMC2209_REG_IOIN, &val);
  return val;
} /* TMC2209_ReadIO() */

/**
  * @brief  Query comprehensive driver health, temperature, and coil short diagnostics.
  * @param  status: Pointer to TMC2209_Status_t struct to populate.
  * @retval bool: True if telemetry read succeeded.
  */
bool TMC2209_ReadStatus(TMC2209_Status_t *status)
{
  if ( status == NULL )
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
  status->over_temperature_warning  = ( drv_status & (1U << 0) ) != 0;
  status->over_temperature_shutdown = ( drv_status & (1U << 1) ) != 0;
  status->short_to_ground_a         = ( drv_status & (1U << 2) ) != 0;
  status->short_to_ground_b         = ( drv_status & (1U << 3) ) != 0;
  status->short_to_supply_a         = ( drv_status & (1U << 4) ) != 0;
  status->short_to_supply_b         = ( drv_status & (1U << 5) ) != 0;
  status->open_load_a               = ( drv_status & (1U << 6) ) != 0;
  status->open_load_b               = ( drv_status & (1U << 7) ) != 0;
  status->current_scale             = (uint8_t)( (drv_status >> 16) & 0x1F );
  status->stealthchop_active        = ( drv_status & (1U << 30) ) != 0;
  status->standstill                = ( drv_status & (1U << 31) ) != 0;

  status->stallguard_result         = TMC2209_ReadStallGuard();

  /* Fault is active if over-temperature shutdown or coil short detected */
  status->driver_fault              = status->over_temperature_shutdown ||
                                      status->short_to_ground_a         ||
                                      status->short_to_ground_b         ||
                                      status->short_to_supply_a         ||
                                      status->short_to_supply_b;

  return true;
} /* TMC2209_ReadStatus() */
