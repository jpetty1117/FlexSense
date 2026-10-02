/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: load_cell.c
  * Brief: Non-blocking hardware driver for NAU7802 24-bit ADC via I2C1 (PB6/PB7).
  ******************************************************************************
  */

#include "load_cell.h"
#include "i2c.h"

/* NAU7802 I2C 7-bit address: 0x2A (0x54 write, 0x55 read) */
#define NAU7802_I2C_ADDR       (0x2A << 1)

/* Register Map */
#define NAU7802_REG_PU_CTRL    0x00
#define NAU7802_REG_CTRL1      0x01
#define NAU7802_REG_CTRL2      0x02
#define NAU7802_REG_ADCO_B2    0x12
#define NAU7802_REG_ADCO_B1    0x13
#define NAU7802_REG_ADCO_B0    0x14
#define NAU7802_REG_ADC        0x15
#define NAU7802_REG_PGA        0x1B
#define NAU7802_REG_PGA_PWR    0x1C
#define NAU7802_REG_REV_ID     0x1F

/* PU_CTRL Bit Definitions */
#define NAU7802_PU_RR          (1U << 0) /* Register Reset */
#define NAU7802_PU_PUD         (1U << 1) /* Power Up Digital */
#define NAU7802_PU_PUA         (1U << 2) /* Power Up Analog */
#define NAU7802_PU_PUR         (1U << 3) /* Power Up Ready */
#define NAU7802_PU_CS          (1U << 4) /* Cycle Start */
#define NAU7802_PU_CR          (1U << 5) /* Cycle Ready */
#define NAU7802_PU_AVDDS       (1U << 7) /* Internal LDO Enable (1 = Internal LDO on, 0 = External) */

/* CTRL2 Bit Definitions */
#define NAU7802_CTRL2_CALS     (1U << 2) /* Calibration Start */

/* Private Module Variables */
static bool     s_is_ready = false;
static int32_t  s_last_raw = 0;
static int32_t  s_tare_raw = 0;
static uint32_t s_fail_count = 0;
/* Default conversion scale factor: ~1.0 / 15000.0 counts per lb for 128x gain */
static float    s_cal_scale = (1.0f / 15000.0f);

/* Helper static functions for I2C register access with 5ms timeout */
static bool nau7802_write_reg(uint8_t reg, uint8_t val)
{
  return (HAL_I2C_Mem_Write(&hi2c1, NAU7802_I2C_ADDR, reg, I2C_MEMADD_SIZE_8BIT, &val, 1, 5) == HAL_OK);
}

static bool nau7802_read_reg(uint8_t reg, uint8_t *val)
{
  return (HAL_I2C_Mem_Read(&hi2c1, NAU7802_I2C_ADDR, reg, I2C_MEMADD_SIZE_8BIT, val, 1, 5) == HAL_OK);
}

static bool nau7802_set_bit(uint8_t reg, uint8_t bit_mask)
{
  uint8_t val = 0;
  if (!nau7802_read_reg(reg, &val)) return false;
  val |= bit_mask;
  return nau7802_write_reg(reg, val);
}

static bool nau7802_clear_bit(uint8_t reg, uint8_t bit_mask)
{
  uint8_t val = 0;
  if (!nau7802_read_reg(reg, &val)) return false;
  val &= (uint8_t)(~bit_mask);
  return nau7802_write_reg(reg, val);
}

/**
  * @brief  Initialize NAU7802 24-bit ADC via I2C1 and run AFE calibration.
  * @param  None
  * @retval None
  */
void LoadCell_Init(void)
{
  s_is_ready = false;
  s_last_raw = 0;
  s_tare_raw = 0;
  s_fail_count = 0;

  /* 1. Quick probe: Read Silicon Revision ID (0x1F) with 10ms timeout */
  uint8_t rev_id = 0;
  if (HAL_I2C_Mem_Read(&hi2c1, NAU7802_I2C_ADDR, NAU7802_REG_REV_ID, I2C_MEMADD_SIZE_8BIT, &rev_id, 1, 10) != HAL_OK)
  {
    s_is_ready = false;
    return;
  }

  /* 2. Soft Reset registers */
  nau7802_set_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_RR);
  HAL_Delay(5);
  nau7802_clear_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_RR);
  HAL_Delay(5);

  /* 3. Power Up Digital and Analog sections, and enable internal LDO (AVDDS = 1) */
  if (!nau7802_write_reg(NAU7802_REG_PU_CTRL, (NAU7802_PU_PUD | NAU7802_PU_PUA | NAU7802_PU_AVDDS)))
  {
    s_is_ready = false;
    return;
  }

  /* Wait for PUR (Power Up Ready) bit with 100ms timeout */
  uint32_t start_tick = HAL_GetTick();
  uint8_t pu_status = 0;
  while ((HAL_GetTick() - start_tick) < 100)
  {
    if (nau7802_read_reg(NAU7802_REG_PU_CTRL, &pu_status) && (pu_status & NAU7802_PU_PUR))
    {
      break;
    }
    HAL_Delay(5);
  }

  /* 4. Configure LDO to 3.3V (bits 5:3 = 0b100) and Gain to 128x (bits 2:0 = 0b111) */
  nau7802_write_reg(NAU7802_REG_CTRL1, 0x27);

  /* 5. Set Sample Rate to 80 SPS on Channel 1 (bits 6:4 = 0b011) */
  nau7802_write_reg(NAU7802_REG_CTRL2, 0x30);

  /* 6. Turn off CLK_CHP (App note 9.1 power-on sequencing) */
  uint8_t adc_reg = 0;
  if (nau7802_read_reg(NAU7802_REG_ADC, &adc_reg))
  {
    nau7802_write_reg(NAU7802_REG_ADC, adc_reg | 0x30);
  }

  /* 7. Enable 330pF decoupling cap on channel 2 (App note 9.14) */
  nau7802_set_bit(NAU7802_REG_PGA_PWR, 0x80);

  /* 8. Clear LDOMODE for high DC gain */
  nau7802_clear_bit(NAU7802_REG_PGA, 0x40);

  /* 9. Wait for internal LDO excitation to stabilize */
  HAL_Delay(200);

  /* 10. Perform AFE calibration with 400ms timeout */
  nau7802_set_bit(NAU7802_REG_CTRL2, NAU7802_CTRL2_CALS);
  start_tick = HAL_GetTick();
  while ((HAL_GetTick() - start_tick) < 400)
  {
    uint8_t ctrl2 = 0;
    if (nau7802_read_reg(NAU7802_REG_CTRL2, &ctrl2))
    {
      if ((ctrl2 & NAU7802_CTRL2_CALS) == 0)
      {
        break;
      }
    }
    HAL_Delay(10);
  }

  /* 11. Start continuous conversion cycles (Set CS bit) */
  nau7802_set_bit(NAU7802_REG_PU_CTRL, NAU7802_PU_CS);

  /* Flush and capture baseline reading for tare */
  HAL_Delay(50);
  uint8_t buf[3];
  if (HAL_I2C_Mem_Read(&hi2c1, NAU7802_I2C_ADDR, NAU7802_REG_ADCO_B2, I2C_MEMADD_SIZE_8BIT, buf, 3, 10) == HAL_OK)
  {
    int32_t raw = ((int32_t)buf[0] << 16) | ((int32_t)buf[1] << 8) | ((int32_t)buf[2]);
    if (raw & 0x00800000)
    {
      raw |= 0xFF000000;
    }
    s_last_raw = raw;
    s_tare_raw = raw;
  }

  s_is_ready = true;
} /* LoadCell_Init() */

/**
  * @brief  Read instantaneous handle contact force in pounds.
  *         Non-blocking (<= 5ms) to preserve 100 Hz loop timing.
  * @param  None
  * @retval float: Measured force in lbs.
  */
float LoadCell_ReadForceLbs(void)
{
  if (!s_is_ready)
  {
    return 0.0f;
  }

  /* Read PU_CTRL to check if conversion is ready */
  uint8_t pu_ctrl = 0;
  if (HAL_I2C_Mem_Read(&hi2c1, NAU7802_I2C_ADDR, NAU7802_REG_PU_CTRL, I2C_MEMADD_SIZE_8BIT, &pu_ctrl, 1, 5) == HAL_OK)
  {
    s_fail_count = 0;
    if (pu_ctrl & NAU7802_PU_CR)
    {
      uint8_t buf[3];
      if (HAL_I2C_Mem_Read(&hi2c1, NAU7802_I2C_ADDR, NAU7802_REG_ADCO_B2, I2C_MEMADD_SIZE_8BIT, buf, 3, 5) == HAL_OK)
      {
        int32_t raw = ((int32_t)buf[0] << 16) | ((int32_t)buf[1] << 8) | ((int32_t)buf[2]);
        if (raw & 0x00800000)
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
    if (s_fail_count > 50)
    {
      s_is_ready = false;
    }
  }

  return ((float)(s_last_raw - s_tare_raw) * s_cal_scale);
} /* LoadCell_ReadForceLbs() */

/**
  * @brief  Tare the load cell to current baseline unloaded state.
  * @param  None
  * @retval None
  */
void LoadCell_Tare(void)
{
  s_tare_raw = s_last_raw;
} /* LoadCell_Tare() */

/**
  * @brief  Check if load cell peripheral is initialized and communicating.
  * @param  None
  * @retval bool: True if healthy.
  */
bool LoadCell_IsConnected(void)
{
  return s_is_ready;
} /* LoadCell_IsConnected() */

/**
  * @brief  Return the latest raw 24-bit signed ADC count.
  * @param  None
  * @retval int32_t: Raw count.
  */
int32_t LoadCell_GetRawCount(void)
{
  return s_last_raw;
}

/**
  * @brief  Set user-defined calibration scale factor (lbs per count).
  * @param  lbs_per_count: Calibration slope.
  * @retval None
  */
void LoadCell_SetCalibrationScale(float lbs_per_count)
{
  s_cal_scale = lbs_per_count;
}

/**
  * @brief  Get current calibration scale factor.
  * @param  None
  * @retval float: Current scale factor.
  */
float LoadCell_GetCalibrationScale(void)
{
  return s_cal_scale;
}
