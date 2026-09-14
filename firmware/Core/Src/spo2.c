/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: spo2.c
  * Brief: Implementation skeleton for pulse oximeter sensor (MAX30102 / I2C).
  ******************************************************************************
  */

#include "spo2.h"

/* Private Module Variables */
static float s_last_spo2_pct = 98.0f;
static float s_last_hr_bpm = 72.0f;
static bool  s_finger_present = true;

/**
  * @brief  Initialize I2C bus and MAX30102 pulse oximeter registers.
  * @param  None
  * @retval None
  */
void SpO2_Init(void)
{
  s_last_spo2_pct = 98.0f;
  s_last_hr_bpm = 72.0f;
  s_finger_present = true;
} /* SpO2_Init() */

/**
  * @brief  Read blood oxygen saturation level in percent (90 - 100%).
  * @param  None
  * @retval float: SpO2 percentage.
  */
float SpO2_ReadPercent(void)
{
  return s_last_spo2_pct;
} /* SpO2_ReadPercent() */

/**
  * @brief  Read instantaneous patient heart rate in Beats Per Minute (BPM).
  * @param  None
  * @retval float: Heart rate BPM.
  */
float SpO2_ReadHeartRateBpm(void)
{
  return s_last_hr_bpm;
} /* SpO2_ReadHeartRateBpm() */

/**
  * @brief  Check if optical reflection confirms patient finger contact.
  * @param  None
  * @retval bool: True if finger detected.
  */
bool SpO2_IsFingerDetected(void)
{
  return s_finger_present;
} /* SpO2_IsFingerDetected() */
