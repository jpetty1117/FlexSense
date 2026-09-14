/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: motor.c
  * Brief: Implementation skeleton for torque actuator resistance HAL.
  ******************************************************************************
  */

#include "motor.h"

/* Private Module Variables */
static float s_target_resistance_lbs = 0.0f;
static float s_feedback_iq_a = 0.0f;
static bool  s_motor_enabled = false;

/**
  * @brief  Initialize PWM / CAN / UART communications with torque actuator stage.
  * @param  None
  * @retval None
  */
void Motor_Init(void)
{
  s_target_resistance_lbs = 0.0f;
  s_feedback_iq_a = 0.0f;
  s_motor_enabled = false;
} /* Motor_Init() */

/**
  * @brief  Command active isotonic resistance load in pounds.
  * @param  resistance_lbs: Commanded rehabilitation load.
  * @retval None
  */
void Motor_SetResistanceLbs(float resistance_lbs)
{
  s_target_resistance_lbs = resistance_lbs;
  s_motor_enabled = ( resistance_lbs > 0.0f );
} /* Motor_SetResistanceLbs() */

/**
  * @brief  Read instantaneous torque actuator effort / drive current.
  * @param  None
  * @retval float: Commanded or measured torque actuator effort.
  */
float Motor_GetIqCurrent(void)
{
  return s_feedback_iq_a;
} /* Motor_GetIqCurrent() */

/**
  * @brief  Instant safety disable of torque actuator output.
  * @param  None
  * @retval None
  */
void Motor_EmergencyStop(void)
{
  s_target_resistance_lbs = 0.0f;
  s_motor_enabled = false;
} /* Motor_EmergencyStop() */

/**
  * @brief  Query if torque actuator is actively generating resistance.
  * @param  None
  * @retval bool: True if enabled.
  */
bool Motor_IsEnabled(void)
{
  return s_motor_enabled;
} /* Motor_IsEnabled() */
