/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: motor.c
  * Brief: Implementation of the Series Elastic Actuator (SEA) brake controller.
  *        Combines feedforward lead-screw positioning with Laplace-tuned PI
  *        handle load cell feedback trim and non-blocking stepper pulse engine.
  ******************************************************************************
  */

#include "motor.h"
#include <math.h>
#include <string.h>

/* Private Module Variables */
static float    s_target_resistance_lbs = 0.0f;
static float    s_integral              = 0.0f;
static float    s_feedforward_pos_mm    = 0.0f;
static float    s_commanded_pos_mm      = 0.0f;
static float    s_profiled_pos_mm       = 0.0f;
static float    s_current_pos_mm        = 0.0f;

static int32_t  s_target_step           = 0;
static int32_t  s_current_step          = 0;
static uint32_t s_last_step_cycle       = 0;

static float    s_steps_per_mm          = MOTOR_STEPS_PER_MM;
static bool     s_motor_enabled         = false;
static bool     s_dir_inverted          = false;

/* TMC2209 UART State */
static bool             s_tmc_online    = false;
static TMC2209_Status_t s_tmc_status;

/**
  * @brief  Initialize GPIO outputs and DWT cycle counter for stepper motor stage.
  * @param  None
  * @retval None
  */
void Motor_Init(void)
{
  /* 1. Ensure GPIO Port A clock is active */
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* 2. Configure STEP, DIR, and EN pins as high-speed push-pull outputs */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin   = MOTOR_STEP_PIN | MOTOR_DIR_PIN | MOTOR_EN_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull  = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* 3. Initialize pins to safe idle state (driver disabled/coasting) */
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(MOTOR_DIR_PORT,  MOTOR_DIR_PIN,  GPIO_PIN_RESET);
  HAL_GPIO_WritePin(MOTOR_EN_PORT,   MOTOR_EN_PIN,   MOTOR_EN_INACTIVE_LEVEL);

  /* 4. Enable Cortex-M4 DWT cycle counter for microsecond-resolution timing */
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL        |= DWT_CTRL_CYCCNTENA_Msk;

  /* 5. Initialize TMC2209 via Single-Wire UART (PA9) */
  s_tmc_online = TMC2209_Init();
  memset(&s_tmc_status, 0, sizeof(s_tmc_status));

  /* 6. Reset all control states */
  s_target_resistance_lbs = 0.0f;
  s_integral              = 0.0f;
  s_feedforward_pos_mm    = 0.0f;
  s_commanded_pos_mm      = 0.0f;
  s_profiled_pos_mm       = 0.0f;
  s_current_pos_mm        = 0.0f;
  s_target_step           = 0;
  s_current_step          = 0;
  s_last_step_cycle       = DWT->CYCCNT;
  s_motor_enabled         = false;
  s_dir_inverted          = false;
  s_steps_per_mm          = MOTOR_STEPS_PER_MM;
} /* Motor_Init() */

/**
  * @brief  Command target rehabilitation resistance load in pounds.
  * @param  resistance_lbs: Commanded load in pounds (0.0 to 25.0 lbf).
  * @retval None
  */
void Motor_SetResistanceLbs(float resistance_lbs)
{
  if ( resistance_lbs < 0.0f )
  {
    resistance_lbs = 0.0f;
  }
  else if ( resistance_lbs > 25.0f )
  {
    resistance_lbs = 25.0f;
  }

  s_target_resistance_lbs = resistance_lbs;

  if ( resistance_lbs > 0.0f )
  {
    s_motor_enabled = true;
    HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);
  }
  else
  {
    /* Homing / slack release commanded */
    s_motor_enabled = false;
    s_integral = 0.0f;
    s_commanded_pos_mm = 0.0f;
    /* Driver remains enabled until carriage reaches home position in Motor_StepTask */
    HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);
  }
} /* Motor_SetResistanceLbs() */

/**
  * @brief  Read the currently commanded resistance target in pounds.
  * @retval float: Commanded target resistance in pounds.
  */
float Motor_GetTargetResistanceLbs(void)
{
  return s_target_resistance_lbs;
} /* Motor_GetTargetResistanceLbs() */

/**
  * @brief  Read total commanded carriage position (feedforward + PI trim) in mm.
  * @retval float: Commanded linear position in mm.
  */
float Motor_GetCommandedPositionMm(void)
{
  return s_commanded_pos_mm;
} /* Motor_GetCommandedPositionMm() */

/**
  * @brief  Read current physical carriage position in mm.
  * @retval float: Current carriage position in mm.
  */
float Motor_GetCurrentPositionMm(void)
{
  return s_current_pos_mm;
} /* Motor_GetCurrentPositionMm() */

/**
  * @brief  Read instantaneous actuator effort / carriage position for telemetry.
  * @retval float: Current carriage position in mm.
  */
float Motor_GetIqCurrent(void)
{
  return s_current_pos_mm;
} /* Motor_GetIqCurrent() */

/**
  * @brief  Instant safety disable of torque actuator output.
  * @param  None
  * @retval None
  */
void Motor_EmergencyStop(void)
{
  s_target_resistance_lbs = 0.0f;
  s_integral              = 0.0f;
  s_commanded_pos_mm      = 0.0f;
  s_profiled_pos_mm       = 0.0f;
  s_target_step           = s_current_step; /* Freeze pulse generator immediately */
  s_motor_enabled         = false;

  HAL_GPIO_WritePin(MOTOR_EN_PORT,   MOTOR_EN_PIN,   MOTOR_EN_INACTIVE_LEVEL);
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);
} /* Motor_EmergencyStop() */

/**
  * @brief  Query if torque actuator is actively engaged.
  * @retval bool: True if enabled.
  */
bool Motor_IsEnabled(void)
{
  return s_motor_enabled;
} /* Motor_IsEnabled() */

/**
  * @brief  Configure motor direction polarity (in case wiring is reversed).
  * @param  inverted: True to invert DIR pin logic.
  * @retval None
  */
void Motor_SetInvertedDirection(bool inverted)
{
  s_dir_inverted = inverted;
} /* Motor_SetInvertedDirection() */

/**
  * @brief  Configure microstepping divider (e.g. 1, 4, 8, 16).
  * @param  ustep_div: Microstepping divisor.
  * @retval None
  */
void Motor_SetMicrostepping(float ustep_div)
{
  if ( ustep_div < 1.0f )
  {
    ustep_div = 1.0f;
  }
  s_steps_per_mm = (MOTOR_FULL_STEPS_PER_REV * ustep_div) / MOTOR_LEAD_SCREW_PITCH_MM;
} /* Motor_SetMicrostepping() */

/**
  * @brief  Periodic dynamic brake control update.
  *         Calculates feedforward carriage displacement from target resistance,
  *         computes Laplace-tuned PI feedback trim with deadband filtering
  *         and motion gating, and velocity-slew-rates the target trajectory.
  * @param  measured_force_lbs: Current force reading from handle load cell.
  * @param  velocity_deg_s: Instantaneous angular velocity from rotary encoder.
  * @param  dt_s: Time step in seconds (nominally 0.010 s for 100 Hz loop).
  * @retval None
  */
void Motor_UpdateControl(float measured_force_lbs, float velocity_deg_s, float dt_s)
{
  /* Sanity-check time step */
  if ( (dt_s <= 0.0f) || (dt_s > 0.1f) )
  {
    dt_s = 0.010f;
  }

  /* When resistance is disabled or homed, command carriage to slack home position */
  if ( (!s_motor_enabled) || (s_target_resistance_lbs <= 0.0f) )
  {
    s_feedforward_pos_mm = 0.0f;
    s_commanded_pos_mm   = 0.0f;
    s_integral           = 0.0f;
  }
  else
  {
    /* 1. Feedforward Position Calculation */
    /* x_ff = x_slack + (F_target / K_plant) */
    s_feedforward_pos_mm = X_SLACK_MM + (s_target_resistance_lbs / K_PLANT_NOMINAL);

    /* 2. Closed-Loop Force Error */
    /* e = F_target - F_measured */
    float error = s_target_resistance_lbs - measured_force_lbs;

    /* 3. Deadband Filtering (Rejects chatter and human tremor) */
    float error_eff = 0.0f;
    if ( fabsf(error) > FORCE_DEADBAND_LBS )
    {
      if ( error > 0.0f )
      {
        error_eff = error - FORCE_DEADBAND_LBS;
      }
      else
      {
        error_eff = error + FORCE_DEADBAND_LBS;
      }
    }

    /* 4. Motion Gating */
    /* Only accumulate integrator when arm is moving or patient is actively pulling */
    bool is_moving = ( fabsf(velocity_deg_s) > VELOCITY_GATE_DEG_S );
    bool is_loaded = ( measured_force_lbs > FORCE_GATE_LBS );

    if ( is_moving || is_loaded )
    {
      s_integral += ( error_eff * dt_s );

      /* Anti-windup clamping on integral trim */
      float max_integral = INTEGRAL_MAX_TRIM_MM / KI_FORCE;
      if ( s_integral > max_integral )
      {
        s_integral = max_integral;
      }
      else if ( s_integral < -max_integral )
      {
        s_integral = -max_integral;
      }
    }

    /* 5. Laplace-Derived PI Feedback Trim */
    /* x_trim = (Kp * error_eff) + (Ki * integral) */
    float trim_mm = ( KP_FORCE * error_eff ) + ( KI_FORCE * s_integral );

    /* 6. Total Commanded Carriage Position */
    s_commanded_pos_mm = s_feedforward_pos_mm + trim_mm;

    /* Safety clamp within physical mechanism stroke bounds */
    if ( s_commanded_pos_mm < 0.0f )
    {
      s_commanded_pos_mm = 0.0f;
    }
    else if ( s_commanded_pos_mm > X_MAX_TRAVEL_MM )
    {
      s_commanded_pos_mm = X_MAX_TRAVEL_MM;
    }
  }

  /* 7. Velocity Slew Rate Limiter (Protects stepper motor from stalling) */
  float max_step_delta = MAX_SLEW_VELOCITY_MM_S * dt_s;
  if ( s_commanded_pos_mm > (s_profiled_pos_mm + max_step_delta) )
  {
    s_profiled_pos_mm += max_step_delta;
  }
  else if ( s_commanded_pos_mm < (s_profiled_pos_mm - max_step_delta) )
  {
    s_profiled_pos_mm -= max_step_delta;
  }
  else
  {
    s_profiled_pos_mm = s_commanded_pos_mm;
  }

  /* 8. Convert Profiled Linear Position to Target Motor Steps */
  s_target_step = (int32_t)( s_profiled_pos_mm * s_steps_per_mm );

  /* 9. Periodic TMC2209 Health Diagnostics (polled every 100 ms) */
  static uint8_t s_tmc_check_cnt = 0;
  if ( s_tmc_online && (++s_tmc_check_cnt >= 10) )
  {
    s_tmc_check_cnt = 0;
    if ( TMC2209_ReadStatus(&s_tmc_status) )
    {
      if ( s_tmc_status.driver_fault )
      {
        Motor_EmergencyStop();
      }
    }
  }
} /* Motor_UpdateControl() */

/**
  * @brief  Non-blocking stepper pulse engine.
  *         Call frequently on each iteration of the main executive while(1) loop.
  *         Maintains precise minimum step period using Cortex-M4 DWT cycles.
  * @param  None
  * @retval None
  */
void Motor_StepTask(void)
{
  if ( s_current_step == s_target_step )
  {
    /* If disabled and carriage has returned completely home to 0, disable driver to keep cool */
    if ( (!s_motor_enabled) && (s_current_step <= 0) )
    {
      HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_INACTIVE_LEVEL);
    }
    return;
  }

  /* Check if minimum step interval has elapsed */
  uint32_t cycles_now     = DWT->CYCCNT;
  uint32_t cycles_elapsed = cycles_now - s_last_step_cycle;
  uint32_t min_cycles     = (SystemCoreClock / 1000000) * MOTOR_MIN_STEP_INTERVAL_US;

  if ( cycles_elapsed < min_cycles )
  {
    return;
  }

  /* Determine step direction */
  int32_t step_delta = 0;
  if ( s_target_step > s_current_step )
  {
    /* Extend carriage (increase brake cable tension) */
    HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_RESET : GPIO_PIN_SET);
    step_delta = 1;
  }
  else
  {
    /* Retract carriage (release brake cable tension) */
    HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_SET : GPIO_PIN_RESET);
    step_delta = -1;
  }

  /* Generate positive step pulse (minimum 2 us HIGH) */
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_SET);
  for ( volatile int i = 0; i < 50; i++ )
  {
    __NOP();
  }
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);

  /* Advance tracking position */
  s_current_step    += step_delta;
  s_current_pos_mm   = (float)s_current_step / s_steps_per_mm;
  s_last_step_cycle  = cycles_now;
} /* Motor_StepTask() */

/* ==========================================================================
   TMC2209 Advanced Feature Functions
   ========================================================================== */

/**
  * @brief  Query if TMC2209 responded over single-wire UART.
  * @retval bool: True if online.
  */
bool Motor_IsTMC2209Online(void)
{
  return s_tmc_online;
}

/**
  * @brief  Read instantaneous StallGuard4 mechanical coil load (0..1023).
  * @retval uint16_t: StallGuard value.
  */
uint16_t Motor_GetStallGuardResult(void)
{
  if ( s_tmc_online )
  {
    return TMC2209_ReadStallGuard();
  }
  return 0;
}

/**
  * @brief  Query driver health, temperature flags, and coil short diagnostics.
  * @param  status: Pointer to TMC2209_Status_t struct.
  * @retval bool: True if query succeeded.
  */
bool Motor_GetTMC2209Status(TMC2209_Status_t *status)
{
  if ( !s_tmc_online || (status == NULL) )
  {
    return false;
  }
  return TMC2209_ReadStatus(status);
}

/**
  * @brief  Configure digital coil current in mA and standstill hold percentage over UART.
  * @param  run_mA: Commanded RMS run current in milliamps (e.g. 800..1400 mA).
  * @param  hold_percent: Hold current percentage at standstill (e.g. 50%).
  * @retval bool: True if written.
  */
bool Motor_SetDriverCurrent(uint16_t run_mA, uint8_t hold_percent)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_SetCurrent(run_mA, hold_percent);
}

/**
  * @brief  Toggle StealthChop2 (whisper quiet) vs SpreadCycle (high dynamic torque).
  * @param  enable: True for StealthChop2, False for SpreadCycle.
  * @retval bool: True if updated.
  */
bool Motor_SetDriverStealthChop(bool enable)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_EnableStealthChop(enable);
}

/**
  * @brief  Configure CoolStep load-dependent current reduction.
  * @param  semin: Lower StallGuard threshold (e.g. 2). Set 0 to disable.
  * @param  semax: Upper StallGuard threshold (e.g. 5).
  * @retval bool: True if updated.
  */
bool Motor_SetDriverCoolStep(uint8_t semin, uint8_t semax)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_ConfigureCoolStep(semin, semax);
}

/**
  * @brief  Configure StallGuard4 stall sensitivity threshold (0..255).
  * @param  threshold: Sensitivity value.
  * @retval bool: True if updated.
  */
bool Motor_SetDriverStallGuardThreshold(uint8_t threshold)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_ConfigureStallGuard(threshold);
}

/**
  * @brief  Execute sensorless homing using StallGuard4.
  *         Retracts the carriage slowly until the mechanical reverse stop is reached.
  * @retval bool: True if homed successfully against hard stop.
  */
bool Motor_SensorlessHome(void)
{
  if ( !s_tmc_online )
  {
    s_current_step     = 0;
    s_target_step      = 0;
    s_current_pos_mm   = 0.0f;
    s_profiled_pos_mm  = 0.0f;
    s_commanded_pos_mm = 0.0f;
    return false;
  }

  /* Configure sensitive StallGuard threshold for homing */
  TMC2209_ConfigureStallGuard(70);
  HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);

  int32_t max_steps = (int32_t)(40.0f * s_steps_per_mm);
  bool stalled = false;

  for ( int32_t i = 0; i < max_steps; i++ )
  {
    /* Retract direction */
    HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_SET : GPIO_PIN_RESET);
    HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_SET);
    for ( volatile int d = 0; d < 50; d++ )
    {
      __NOP();
    }
    HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);

    HAL_Delay(2);

    /* Discard initial startup step transients */
    if ( i > 50 )
    {
      uint16_t sg = TMC2209_ReadStallGuard();
      if ( sg < 10 )
      {
        stalled = true;
        break;
      }
    }
  }

  s_current_step     = 0;
  s_target_step      = 0;
  s_current_pos_mm   = 0.0f;
  s_profiled_pos_mm  = 0.0f;
  s_commanded_pos_mm = 0.0f;

  /* Restore normal operating sensitivity */
  TMC2209_ConfigureStallGuard(64);
  return stalled;
}
