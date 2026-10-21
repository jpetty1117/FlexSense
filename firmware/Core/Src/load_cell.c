/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: load_cell.c
** --------
** Non-blocking hardware driver for NAU7802 24-bit ADC via I2C1 (PB6/PB7).
*/

#include "load_cell.h"
#include "i2c.h"
#include <stdio.h>

/* NAU7802 I2C 7-bit address: 0x2A (0x54 write, 0x55 read) */
#define NAU7802_I2C_ADDR        (0x2A << 1)

/* Register Map */
#define NAU7802_REG_PU_CTRL     0x00
#define NAU7802_REG_CTRL1       0x01
#define NAU7802_REG_CTRL2       0x02
#define NAU7802_REG_ADCO_B2     0x12
#define NAU7802_REG_ADCO_B1     0x13
#define NAU7802_REG_ADCO_B0     0x14
#define NAU7802_REG_ADC         0x15
#define NAU7802_REG_PGA         0x1B
#define NAU7802_REG_PGA_PWR     0x1C
#define NAU7802_REG_REV_ID      0x1F

/* PU_CTRL Bit Definitions */
#define NAU7802_PU_RR           (1U << 0)  /* Register Reset */
#define NAU7802_PU_PUD          (1U << 1)  /* Power Up Digital */
#define NAU7802_PU_PUA          (1U << 2)  /* Power Up Analog */
#define NAU7802_PU_PUR          (1U << 3)  /* Power Up Ready */
#define NAU7802_PU_CS           (1U << 4)  /* Cycle Start */
#define NAU7802_PU_CR           (1U << 5)  /* Cycle Ready */
#define NAU7802_PU_AVDDS        (1U << 7)  /* Internal LDO Enable */

/* CTRL2 Bit Definitions */
#define NAU7802_CTRL2_CALS      (1U << 2)  /* Calibration Start */

/* Operational Timeouts */
#define NAU7802_I2C_TIMEOUT_MS  5
#define NAU7802_PUR_TIMEOUT_MS  200
#define NAU7802_CAL_TIMEOUT_MS  400
#define NAU7802_MAX_FAIL_COUNT  100

/* Private Module Variables */
static bool     s_is_ready   = false;
static int32_t  s_last_raw   = 0;
static int32_t  s_tare_raw   = 0;
static uint32_t s_fail_count = 0;
static uint8_t  s_init_step  = 0;

/* Calibrated conversion scale factor: 42297 counts per lb */
static float    s_cal_scale  = (1.0f / 42296.7f);

/* Internal Helper Prototypes */
static bool nau7802_write_reg(uint8_t reg, uint8_t val);
static bool nau7802_read_reg(uint8_t reg, uint8_t *val);
static bool nau7802_set_bit(uint8_t reg, uint8_t bit_mask);
static bool nau7802_clear_bit(uint8_t reg, uint8_t bit_mask);

/* Write single byte to NAU7802 register over I2C1
** Parameters:
**   reg - 8-bit register address
**   val - 8-bit value to write
** Return:
**   true on success, false on I2C error
** Notes:
**   None
*/
static bool nau7802_write_reg(uint8_t reg, uint8_t val)
{
  HAL_StatusTypeDef status;
  status = HAL_I2C_Mem_Write(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, (uint16_t)reg,
                             I2C_MEMADD_SIZE_8BIT, &val, 1, NAU7802_I2C_TIMEOUT_MS);
  return (status == HAL_OK);
} /* nau7802_write_reg() */

/* Read single byte from NAU7802 register over I2C1
** Parameters:
**   reg - 8-bit register address
**   val - pointer to destination byte
** Return:
**   true on success, false on I2C error
** Notes:
**   None
*/
static bool nau7802_read_reg(uint8_t reg, uint8_t *val)
{
  HAL_StatusTypeDef status;
  status = HAL_I2C_Mem_Read(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, (uint16_t)reg,
                            I2C_MEMADD_SIZE_8BIT, val, 1, NAU7802_I2C_TIMEOUT_MS);
  return (status == HAL_OK);
} /* nau7802_read_reg() */

/* Set specific bits in a NAU7802 register
** Parameters:
**   reg - 8-bit register address
**   bit_mask - bitmask to OR into register
** Return:
**   true on success, false on error
** Notes:
**   None
*/
static bool nau7802_set_bit(uint8_t reg, uint8_t bit_mask)
{
  uint8_t val = 0;
  if ( !nau7802_read_reg(reg, &val) )
  {
    return false;
  }
  val |= bit_mask;
  return nau7802_write_reg(reg, val);
} /* nau7802_set_bit() */

/* Clear specific bits in a NAU7802 register
** Parameters:
**   reg - 8-bit register address
**   bit_mask - bitmask to clear from register
** Return:
**   true on success, false on error
** Notes:
**   None
*/
static bool nau7802_clear_bit(uint8_t reg, uint8_t bit_mask)
{
  uint8_t val = 0;
  if ( !nau7802_read_reg(reg, &val) )
  {
    return false;
  }
  val &= (uint8_t)( ~bit_mask );
  return nau7802_write_reg(reg, val);
} /* nau7802_clear_bit() */

/* Initialize NAU7802 24-bit ADC via I2C1 and run AFE calibration
** Parameters:
**   None
** Return:
**   None
** Notes:
**   Follows NAU7802 power-on and calibration sequence
*/
void LoadCell_Init(void)
{
  s_is_ready = false;
  s_last_raw = 0;
  s_tare_raw = 0;
  s_fail_count = 0;
  s_init_step = 0;

  /* 1. Probe NAU7802: Check if device ACKs at 0x2A via PU_CTRL read */
  uint8_t pu_val = 0;
  bool probed = false;
  for ( int retry = 0; retry < 5; retry++ )
  {
    if ( HAL_I2C_Mem_Read(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, NAU7802_REG_PU_CTRL,
                          I2C_MEMADD_SIZE_8BIT, &pu_val, 1, 10) == HAL_OK )
    {
      probed = true;
      break;
    }
    HAL_Delay(20);
  }
  if ( !probed )
  {
    s_is_ready = false;
    s_init_step = 1;
    return;
  }

  /* 2. Soft Reset registers */
  nau7802_set_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_RR);
  HAL_Delay(10);
  nau7802_clear_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_RR);
  HAL_Delay(10);

  /* 3. Power Up Digital and Analog sections, and enable internal LDO (AVDDS = 1) */
  if ( !nau7802_write_reg(NAU7802_REG_PU_CTRL, (uint8_t)(NAU7802_PU_PUD | NAU7802_PU_PUA | NAU7802_PU_AVDDS)) )
  {
    s_is_ready = false;
    s_init_step = 3;
    return;
  }

  /* 4. Wait for PUR (Power Up Ready) bit with 200ms timeout */
  uint32_t start_tick = HAL_GetTick();
  uint8_t pu_status = 0;
  bool pur_ok = false;
  while ( (HAL_GetTick() - start_tick) < NAU7802_PUR_TIMEOUT_MS )
  {
    if ( nau7802_read_reg(NAU7802_REG_PU_CTRL, &pu_status) &&
         ((pu_status & NAU7802_PU_PUR) != 0) )
    {
      pur_ok = true;
      break;
    }
    HAL_Delay(5);
  }
  if ( !pur_ok )
  {
    s_is_ready = false;
    s_init_step = 4;
    return;
  }

  /* 5. Configure LDO to 3.3V and Gain to 128x */
  nau7802_write_reg(NAU7802_REG_CTRL1, 0x27);

  /* 6. Set Sample Rate to 80 SPS on Channel 1 */
  nau7802_write_reg(NAU7802_REG_CTRL2, 0x30);

  /* 7. Turn off CLK_CHP */
  uint8_t adc_reg = 0;
  if ( nau7802_read_reg(NAU7802_REG_ADC, &adc_reg) )
  {
    nau7802_write_reg(NAU7802_REG_ADC, (uint8_t)(adc_reg | 0x30));
  }

  /* 8. Enable 330pF decoupling cap on channel 2 */
  nau7802_set_bit(NAU7802_REG_PGA_PWR, 0x80);

  /* 9. Clear LDOMODE for high DC gain */
  nau7802_clear_bit(NAU7802_REG_PGA, 0x40);

  /* 10. Wait for internal LDO excitation to stabilize */
  HAL_Delay(200);

  /* 11. Perform AFE calibration with 400ms timeout */
  nau7802_set_bit(NAU7802_REG_CTRL2, NAU7802_CTRL2_CALS);
  start_tick = HAL_GetTick();
  while ( (HAL_GetTick() - start_tick) < NAU7802_CAL_TIMEOUT_MS )
  {
    uint8_t ctrl2 = 0;
    if ( nau7802_read_reg(NAU7802_REG_CTRL2, &ctrl2) )
    {
      if ( (ctrl2 & NAU7802_CTRL2_CALS) == 0 )
      {
        break;
      }
    }
    HAL_Delay(10);
  }

  /* 12. Start continuous conversion cycles */
  nau7802_set_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_CS);

  /* Flush and capture baseline reading for tare */
  HAL_Delay(50);
  uint8_t buf[3];
  if ( HAL_I2C_Mem_Read(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, NAU7802_REG_ADCO_B2,
                        I2C_MEMADD_SIZE_8BIT, buf, 3, 10) == HAL_OK )
  {
    int32_t raw = ((int32_t)buf[0] << 16) | ((int32_t)buf[1] << 8) | ((int32_t)buf[2]);
    if ( (raw & 0x00800000) != 0 )
    {
      raw |= 0xFF000000;
    }
    s_last_raw = raw;
    s_tare_raw = raw;
  }

  s_is_ready = true;
  s_init_step = 0;
} /* LoadCell_Init() */

/* Read instantaneous handle contact force in pounds
** Parameters:
**   None
** Return:
**   float: Measured force in lbs
** Notes:
**   Non-blocking (<= 5ms) to preserve 100 Hz loop timing
*/
float LoadCell_ReadForceLbs(void)
{
  if ( !s_is_ready )
  {
    /* Attempt auto-recovery periodically (every 2.0s) if disconnected */
    static uint32_t s_reinit_tick = 0;
    uint32_t now = HAL_GetTick();
    if ( (now - s_reinit_tick) >= 2000 )
    {
      s_reinit_tick = now;
      MX_I2C1_Init();
      LoadCell_Init();
    }
    return 0.0f;
  }

  /* Read PU_CTRL to check if conversion is ready */
  uint8_t pu_ctrl = 0;
  if ( HAL_I2C_Mem_Read(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, NAU7802_REG_PU_CTRL,
                        I2C_MEMADD_SIZE_8BIT, &pu_ctrl, 1, NAU7802_I2C_TIMEOUT_MS) == HAL_OK )
  {
    s_fail_count = 0;
    if ( (pu_ctrl & NAU7802_PU_CR) != 0 )
    {
      uint8_t buf[3];
      if ( HAL_I2C_Mem_Read(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, NAU7802_REG_ADCO_B2,
                            I2C_MEMADD_SIZE_8BIT, buf, 3, NAU7802_I2C_TIMEOUT_MS) == HAL_OK )
      {
        int32_t raw = ((int32_t)buf[0] << 16) | ((int32_t)buf[1] << 8) | ((int32_t)buf[2]);
        if ( (raw & 0x00800000) != 0 )
        {
          raw |= 0xFF000000;
        }
        s_last_raw = raw;
      }
    }
  }
  else
  {
    s_fail_count++;
    if ( s_fail_count > NAU7802_MAX_FAIL_COUNT )
    {
      s_is_ready = false;
    }
  }

  return ((float)(s_last_raw - s_tare_raw) * s_cal_scale);
} /* LoadCell_ReadForceLbs() */

/* Tare the load cell to current baseline unloaded state
** Parameters:
**   None
** Return:
**   None
** Notes:
**   None
*/
void LoadCell_Tare(void)
{
  s_tare_raw = s_last_raw;
} /* LoadCell_Tare() */

/* Check if load cell peripheral is initialized and communicating
** Parameters:
**   None
** Return:
**   bool: True if healthy
** Notes:
**   None
*/
bool LoadCell_IsConnected(void)
{
  return s_is_ready;
} /* LoadCell_IsConnected() */

/* Return the initialization failure step (0 if healthy)
** Parameters:
**   None
** Return:
**   uint8_t: Step number
** Notes:
**   None
*/
uint8_t LoadCell_GetInitStep(void)
{
  return s_init_step;
} /* LoadCell_GetInitStep() */

/* Return the latest raw 24-bit signed ADC count
** Parameters:
**   None
** Return:
**   int32_t: Raw count
** Notes:
**   None
*/
int32_t LoadCell_GetRawCount(void)
{
  return s_last_raw;
} /* LoadCell_GetRawCount() */

/* Set user-defined calibration scale factor (lbs per count)
** Parameters:
**   lbs_per_count: Calibration slope
** Return:
**   None
** Notes:
**   None
*/
void LoadCell_SetCalibrationScale(float lbs_per_count)
{
  s_cal_scale = lbs_per_count;
} /* LoadCell_SetCalibrationScale() */

/* Get current calibration scale factor
** Parameters:
**   None
** Return:
**   float: Current scale factor
** Notes:
**   None
*/
float LoadCell_GetCalibrationScale(void)
{
  return s_cal_scale;
} /* LoadCell_GetCalibrationScale() */

/* Perform comprehensive I2C pin, bus, and sensor diagnosis
** Parameters:
**   out_buf: Output string buffer
**   max_len: Buffer capacity
** Return:
**   None
** Notes:
**   None
*/
void LoadCell_Diagnose(char *out_buf, size_t max_len)
{
  /* 1. Read raw GPIO input states on PB6 (SCL) and PB7 (SDA) */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  __HAL_RCC_GPIOB_CLK_ENABLE();
  GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
  uint8_t scl_pin = (uint8_t)HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_6);
  uint8_t sda_pin = (uint8_t)HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_7);

  /* 2. Re-initialize I2C1 properly */
  MX_I2C1_Init();

  /* 3. Probe device ready on NAU7802 address */
  HAL_StatusTypeDef rdy_st = HAL_I2C_IsDeviceReady(&hi2c1, (uint16_t)NAU7802_I2C_ADDR, 2, 10);
  uint32_t i2c_err = hi2c1.ErrorCode;

  /* 4. Scan all 127 addresses to find any responding device on bus */
  int found_addr = 0;
  for ( int a = 1; a < 128; a++ )
  {
    if ( HAL_I2C_IsDeviceReady(&hi2c1, (uint16_t)(a << 1), 1, 2) == HAL_OK )
    {
      found_addr = a;
      break;
    }
  }

  /* 5. Attempt full LoadCell_Init() */
  LoadCell_Init();

  snprintf(out_buf, max_len,
           "ACK:STATUS:LC=%d,STEP=%d,SCL=%d,SDA=%d,RDY=%d,ERR=0x%lX,DEV=0x%02X,"
           "RAW=%ld,LBS=%.2f\r\n",
           s_is_ready, s_init_step, scl_pin, sda_pin, (int)rdy_st,
           (unsigned long)i2c_err, (unsigned int)found_addr, (long)s_last_raw,
           LoadCell_ReadForceLbs());
} /* LoadCell_Diagnose() */
