/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: motor.c
** --------
** Implementation of the Series Elastic Actuator (SEA) brake controller.
** Stepper carriage pulls compliant spring attached to bicycle brake handle
** trigger (lever mechanical advantage) driving hydraulic disc brake caliper.
** Combines feedforward lead-screw positioning with Laplace-tuned PI
** handle load cell feedback trim and non-blocking stepper pulse engine.
*/

#include "motor.h"
#include "brake_lut.h"
#include "telemetry.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

/* Private Module Variables */
static float            s_target_resistance_lbs = 0.0f;
static float            s_integral              = 0.0f;
static float            s_feedforward_pos_mm    = 0.0f;
static float            s_commanded_pos_mm      = 0.0f;
static float            s_profiled_pos_mm       = 0.0f;
static float            s_current_pos_mm        = 0.0f;
static float            s_current_vel_mm_s      = 0.0f;
static float            s_filt_force_lbs        = 0.0f;

static int32_t          s_target_step           = 0;
static int32_t          s_current_step          = 0;
static uint32_t         s_last_step_cycle       = 0;
static uint32_t         s_step_interval_cycles  = 0;

static float            s_steps_per_mm          = MOTOR_STEPS_PER_MM;
static bool             s_motor_enabled         = false;
static bool             s_direct_pos_active     = false;
static float            s_direct_pos_override_mm = 0.0f;
static bool             s_dir_inverted          = true; /* Default inverted polarity so homing retracts towards home switch */
static uint16_t         s_configured_run_mA     = TMC2209_DEFAULT_RUN_CURRENT_MA;
static uint8_t          s_configured_hold_pct   = TMC2209_DEFAULT_HOLD_PERCENT;

/* Torque & Forearm Lever State */
static float            s_forearm_length_in     = 12.0f; /* Default Pin 4: 12.0 inches */
static float            s_target_torque_lbf_in  = 0.0f;
static bool             s_curl_reversing        = false;
static uint32_t         s_curl_stopped_ms       = 0;
static bool             s_limit_was_triggered   = false;
static uint8_t          s_limit_debounce        = 0;
static uint8_t          s_limit_release_cnt     = 0;

/* TMC2209 UART State */
static bool             s_tmc_online            = false;
static bool             s_is_standby_current    = false;
static bool             s_is_homing             = false;
static TMC2209_Status_t s_tmc_status;

static void motor_apply_dynamic_current(bool need_active)
{
  if ( (!s_tmc_online) || s_is_homing )
  {
    return;
  }

  if ( need_active && s_is_standby_current )
  {
    if ( TMC2209_SetCurrent(s_configured_run_mA, s_configured_hold_pct) )
    {
      s_is_standby_current = false;
    }
  }
  else if ( (!need_active) && (!s_is_standby_current) )
  {
    if ( TMC2209_SetCurrent(TMC2209_STANDBY_RUN_CURRENT_MA, s_configured_hold_pct) )
    {
      s_is_standby_current = true;
    }
  }
}

/* Initialize GPIO outputs and DWT cycle counter for stepper motor stage
** Parameters:
**   None
** Return:
**   None
** Notes:
**   Enables GPIOA and configures STEP, DIR, EN outputs
*/
void Motor_Init(void)
{
  /* 1. Ensure GPIO Port A and Port B clocks are active */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* 2. Configure STEP (PA5), DIR (PA4), and EN (PA6) pins as high-speed push-pull outputs */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  GPIO_InitStruct.Pin   = MOTOR_STEP_PIN | MOTOR_DIR_PIN | MOTOR_EN_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull  = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* 3. Configure MS1 (PA7) and MS2 (PB0) as Outputs driven LOW (UART Slave Address 0) */
  GPIO_InitStruct.Pin   = MOTOR_MS1_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull  = GPIO_PULLDOWN;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(MOTOR_MS1_PORT, &GPIO_InitStruct);
  HAL_GPIO_WritePin(MOTOR_MS1_PORT, MOTOR_MS1_PIN, GPIO_PIN_RESET);

  GPIO_InitStruct.Pin   = MOTOR_MS2_PIN;
  HAL_GPIO_Init(MOTOR_MS2_PORT, &GPIO_InitStruct);
  HAL_GPIO_WritePin(MOTOR_MS2_PORT, MOTOR_MS2_PIN, GPIO_PIN_RESET);

  /* 4. Configure DIAG (PB1) and INDEX (PA3) inputs */
  GPIO_InitStruct.Pin   = MOTOR_DIAG_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull  = GPIO_PULLDOWN;
  HAL_GPIO_Init(MOTOR_DIAG_PORT, &GPIO_InitStruct);

  GPIO_InitStruct.Pin   = MOTOR_INDEX_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull  = GPIO_NOPULL;
  HAL_GPIO_Init(MOTOR_INDEX_PORT, &GPIO_InitStruct);

  /* 5. Configure Physical Limit Switch (PB13) with internal pull-up (Active LOW switch to free GND) */
  GPIO_InitStruct.Pin   = MOTOR_LIMIT_PIN;
  GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull  = GPIO_PULLUP;
  HAL_GPIO_Init(MOTOR_LIMIT_PORT, &GPIO_InitStruct);

  /* 5. Initialize pins to safe idle state (driver disabled/coasting) */
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(MOTOR_DIR_PORT,  MOTOR_DIR_PIN,  GPIO_PIN_RESET);
  HAL_GPIO_WritePin(MOTOR_EN_PORT,   MOTOR_EN_PIN,   MOTOR_EN_INACTIVE_LEVEL);

  /* 4. Enable Cortex-M4 DWT cycle counter for microsecond-resolution timing */
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL        |= DWT_CTRL_CYCCNTENA_Msk;

  /* 5. Initialize TMC2209 via Single-Wire UART (PA2) */
  s_tmc_online = TMC2209_Init();
  memset(&s_tmc_status, 0, sizeof(s_tmc_status));

  /* 6. Reset all control states */
  s_target_resistance_lbs = 0.0f;
  s_direct_pos_active     = false;
  s_direct_pos_override_mm = 0.0f;
  s_integral              = 0.0f;
  s_feedforward_pos_mm    = 0.0f;
  s_commanded_pos_mm      = 0.0f;
  s_profiled_pos_mm       = 0.0f;
  s_current_pos_mm        = 0.0f;
  s_current_vel_mm_s      = 0.0f;
  s_filt_force_lbs        = 0.0f;
  s_target_step           = 0;
  s_current_step          = 0;
  s_last_step_cycle       = DWT->CYCCNT;
  s_step_interval_cycles  = (SystemCoreClock / 1000000) * MOTOR_MIN_STEP_INTERVAL_US;
  s_motor_enabled         = false;
  s_curl_reversing        = false;
  s_curl_stopped_ms       = 0;
  s_limit_was_triggered   = Motor_IsLimitSwitchTriggered();
  s_limit_debounce        = 0;
  s_limit_release_cnt     = 0;
  s_is_homing             = false;
  s_is_standby_current    = false;
  s_dir_inverted          = true;  /* Default inverted polarity so homing search retracts towards limit switch */
  s_steps_per_mm          = MOTOR_STEPS_PER_MM;

  motor_apply_dynamic_current(false); /* Drop IRUN to 500 mA standby while parked at 0.0 mm */
} /* Motor_Init() */

/* Command target shaft braking torque directly in lbf*in
** Parameters:
**   torque_lbf_in - Commanded braking torque in lbf*in [0.0, BRAKE_LUT_MAX_TORQUE_LBF_IN]
** Return:
**   None
*/
void Motor_SetTorqueLbfIn(float torque_lbf_in)
{
  if ( (torque_lbf_in > 0.0f) && Motor_IsLimitSwitchTriggered() )
  {
    /* Refuse engaging load while hardware limit switch PB13 is pressed */
    Motor_EmergencyStop();
    return;
  }

  s_direct_pos_active = false;
  s_curl_reversing    = false;
  s_curl_stopped_ms   = 0;
  if ( torque_lbf_in < 0.0f )
  {
    torque_lbf_in = 0.0f;
  }
  else if ( torque_lbf_in > BRAKE_LUT_MAX_TORQUE_LBF_IN )
  {
    torque_lbf_in = BRAKE_LUT_MAX_TORQUE_LBF_IN;
  }

  s_target_torque_lbf_in = torque_lbf_in;
  if ( s_forearm_length_in > 0.1f )
  {
    s_target_resistance_lbs = torque_lbf_in / s_forearm_length_in;
  }

  if ( (torque_lbf_in > 0.0f) && (!s_motor_enabled) && (s_current_step == s_target_step) )
  {
    /* Ensure trapezoidal ramp always starts from 0 velocity at actual carriage position */
    s_profiled_pos_mm  = s_current_pos_mm;
    s_current_vel_mm_s = 0.0f;
  }

  if ( torque_lbf_in > 0.0f )
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
    HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);
  }
} /* Motor_SetTorqueLbfIn() */

/* Command target rehabilitation resistance load in pounds
** Parameters:
**   resistance_lbs - Commanded load in pounds (0.0 to 25.0 lbf)
** Return:
**   None
** Notes:
**   Internally converts to shaft torque using current forearm length
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
  Motor_SetTorqueLbfIn(resistance_lbs * s_forearm_length_in);
} /* Motor_SetResistanceLbs() */

/* Configure patient forearm lever length in inches
** Parameters:
**   arm_in - Forearm length in inches [5.0 to 20.0 in]
*/
void Motor_SetForearmLengthIn(float arm_in)
{
  if ( (arm_in >= 5.0f) && (arm_in <= 20.0f) )
  {
    s_forearm_length_in = arm_in;
    if ( s_target_resistance_lbs > 0.0f )
    {
      Motor_SetTorqueLbfIn(s_target_resistance_lbs * s_forearm_length_in);
    }
  }
}

float Motor_GetForearmLengthIn(void)
{
  return s_forearm_length_in;
}

float Motor_GetTargetTorqueLbfIn(void)
{
  return s_target_torque_lbf_in;
}

/* Directly command physical carriage displacement in mm (bypasses LUT for calibration)
** Parameters:
**   pos_mm - Desired linear displacement in mm [0.0, X_MAX_TRAVEL_MM]
** Return:
**   None
** Notes:
**   Used during LUT capture and mechanical calibration
*/
void Motor_SetCommandedPositionMm(float pos_mm)
{
  if ( Motor_IsLimitSwitchTriggered() )
  {
    /* Refuse motion while hardware limit switch PB13 is active */
    Motor_EmergencyStop();
    return;
  }

  if ( pos_mm < X_MIN_TRAVEL_MM )
  {
    pos_mm = X_MIN_TRAVEL_MM;
  }
  else if ( pos_mm > X_MAX_TRAVEL_MM )
  {
    pos_mm = X_MAX_TRAVEL_MM;
  }

  if ( (!s_motor_enabled) && (s_current_step == s_target_step) )
  {
    /* Sync profiler origin when waking from idle so velocity ramp always starts at 0 mm/s */
    s_profiled_pos_mm  = s_current_pos_mm;
    s_current_vel_mm_s = 0.0f;
  }

  s_direct_pos_override_mm = pos_mm;
  s_direct_pos_active      = true;
  s_commanded_pos_mm       = pos_mm;
  s_target_resistance_lbs  = 0.0f;
  s_target_torque_lbf_in   = 0.0f;
  s_integral               = 0.0f;

  s_motor_enabled = true;
  HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);
} /* Motor_SetCommandedPositionMm() */

/* Reset/zero carriage tracking position to 0.0 mm without mechanical movement
** Parameters:
**   None
** Return:
**   None
** Notes:
**   Call when physical carriage is at designated 0 mm reference
*/
void Motor_ZeroPosition(void)
{
  s_current_step           = 0;
  s_target_step            = 0;
  s_current_pos_mm         = 0.0f;
  s_commanded_pos_mm       = 0.0f;
  s_profiled_pos_mm        = 0.0f;
  s_direct_pos_override_mm = 0.0f;
  s_integral               = 0.0f;
} /* Motor_ZeroPosition() */

/* Read the currently commanded resistance target in pounds
** Parameters:
**   None
** Return:
**   float: Commanded target resistance in pounds
** Notes:
**   None
*/
float Motor_GetTargetResistanceLbs(void)
{
  return s_target_resistance_lbs;
} /* Motor_GetTargetResistanceLbs() */

/* Read total commanded carriage position (feedforward + PI trim) in mm
** Parameters:
**   None
** Return:
**   float: Commanded linear position in mm
** Notes:
**   None
*/
float Motor_GetCommandedPositionMm(void)
{
  return s_commanded_pos_mm;
} /* Motor_GetCommandedPositionMm() */

/* Read current physical carriage position in mm
** Parameters:
**   None
** Return:
**   float: Current carriage position in mm
** Notes:
**   None
*/
float Motor_GetCurrentPositionMm(void)
{
  return s_current_pos_mm;
} /* Motor_GetCurrentPositionMm() */

/* Read current instantaneous profiled carriage velocity in mm/s
** Parameters:
**   None
** Return:
**   float: Current linear velocity in mm/s
** Notes:
**   None
*/
float Motor_GetCurrentVelocityMmS(void)
{
  return s_current_vel_mm_s;
} /* Motor_GetCurrentVelocityMmS() */

/* Read instantaneous actuator effort / carriage position for telemetry
** Parameters:
**   None
** Return:
**   float: Current carriage position in mm
** Notes:
**   Mapped to telemetry packet motor_iq_a slot
*/
float Motor_GetIqCurrent(void)
{
  return s_current_pos_mm;
} /* Motor_GetIqCurrent() */

/* Instant safety disable of torque actuator output
** Parameters:
**   None
** Return:
**   None
** Notes:
**   Disables driver and resets step targets
*/
void Motor_EmergencyStop(void)
{
  s_target_resistance_lbs  = 0.0f;
  s_target_torque_lbf_in   = 0.0f;
  s_feedforward_pos_mm     = 0.0f;
  s_direct_pos_active      = false;
  s_direct_pos_override_mm = 0.0f;
  s_integral               = 0.0f;
  s_commanded_pos_mm       = s_current_pos_mm;
  s_profiled_pos_mm        = s_current_pos_mm;
  s_current_vel_mm_s       = 0.0f;
  s_target_step            = s_current_step; /* Freeze pulse generator immediately */
  s_motor_enabled          = false;
  s_curl_reversing         = false;
  s_curl_stopped_ms        = 0;

  HAL_GPIO_WritePin(MOTOR_EN_PORT,   MOTOR_EN_PIN,   MOTOR_EN_INACTIVE_LEVEL);
  HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);
} /* Motor_EmergencyStop() */

/* Query if torque actuator is actively engaged
** Parameters:
**   None
** Return:
**   bool: True if enabled
** Notes:
**   None
*/
bool Motor_IsEnabled(void)
{
  return s_motor_enabled;
} /* Motor_IsEnabled() */

/* Configure motor direction polarity
** Parameters:
**   inverted - True to invert DIR pin logic
** Return:
**   None
** Notes:
**   None
*/
void Motor_SetInvertedDirection(bool inverted)
{
  s_dir_inverted = inverted;
} /* Motor_SetInvertedDirection() */

/* Query if motor direction polarity is currently inverted
** Parameters:
**   None
** Return:
**   bool: True if inverted
*/
bool Motor_IsInvertedDirection(void)
{
  return s_dir_inverted;
} /* Motor_IsInvertedDirection() */

/* Configure microstepping divider (e.g. 1, 4, 8, 16)
** Parameters:
**   ustep_div - Microstepping divisor
** Return:
**   None
** Notes:
**   Recalculates steps per mm scaling
*/
void Motor_SetMicrostepping(float ustep_div)
{
  if ( ustep_div < 1.0f )
  {
    ustep_div = 1.0f;
  }
  s_steps_per_mm = (MOTOR_FULL_STEPS_PER_REV * ustep_div) / MOTOR_LEAD_SCREW_PITCH_MM;
} /* Motor_SetMicrostepping() */

/* Periodic dynamic brake control update
** Parameters:
**   measured_force_lbs - Current force reading from handle load cell
**   velocity_deg_s - Instantaneous angular velocity from rotary encoder
**   dt_s - Time step in seconds (nominally 0.010 s for 100 Hz loop)
** Return:
**   None
** Notes:
**   Executes at 100 Hz rate
*/
void Motor_UpdateControl(float measured_force_lbs, float velocity_deg_s, float dt_s)
{
  /* Sanity-check time step */
  if ( (dt_s <= 0.0f) || (dt_s > 0.1f) )
  {
    dt_s = 0.010f;
  }

  /* Low-pass filter load cell force (1st order EMA, fc ~ 10 Hz at 100 Hz dt) to reject ADC noise */
  s_filt_force_lbs += 0.35f * (measured_force_lbs - s_filt_force_lbs);

  /* When in direct position mode (e.g. during LUT calibration), hold commanded displacement */
  if ( s_direct_pos_active )
  {
    s_feedforward_pos_mm = s_direct_pos_override_mm;
    s_commanded_pos_mm   = s_direct_pos_override_mm;
    s_integral           = 0.0f;
  }
  /* When resistance is disabled or homed, command carriage to slack home position */
  else if ( (!s_motor_enabled) || (s_target_torque_lbf_in <= 0.0f) )
  {
    s_feedforward_pos_mm = 0.0f;
    s_commanded_pos_mm   = 0.0f;
    s_integral           = 0.0f;
    s_curl_reversing     = false;
    s_curl_stopped_ms    = 0;
  }
  else
  {
    /* Detect curl reversal (eccentric lowering phase: negative angular velocity) and release brake.
    ** Lower -4.0 deg/s trigger catches slow controlled lowering; 250ms standstill settles re-engage. */
    if ( velocity_deg_s < -4.0f )
    {
      s_curl_reversing  = true;
      s_curl_stopped_ms = 0;
    }
    else if ( s_curl_reversing )
    {
      if ( velocity_deg_s > 6.0f )
      {
        s_curl_reversing  = false;
        s_curl_stopped_ms = 0;
      }
      else if ( fabsf(velocity_deg_s) < 2.5f )
      {
        uint32_t now_ms = HAL_GetTick();
        if ( s_curl_stopped_ms == 0 )
        {
          s_curl_stopped_ms = now_ms;
        }
        else if ( (now_ms - s_curl_stopped_ms) >= 250 )
        {
          s_curl_reversing  = false;
          s_curl_stopped_ms = 0;
        }
      }
      else
      {
        s_curl_stopped_ms = 0;
      }
    }

    if ( s_curl_reversing )
    {
      /* Release brake cleanly during eccentric / return half of the curl */
      s_feedforward_pos_mm = 0.0f;
      s_commanded_pos_mm   = 0.0f;
      s_integral           = 0.0f;
    }
    else
    {
      /* 1. Feedforward Position Calculation from Kinematic Torque Look-Up Table (LUT) */
      s_feedforward_pos_mm = Brake_LUT_TorqueToPositionMm(s_target_torque_lbf_in);

      /* 2. Closed-Loop Force Error using filtered load cell reading at handle */
      float error = s_target_resistance_lbs - s_filt_force_lbs;

      /* 3. Motion & Load Gating: freeze PI trim (both P and I) while patient sits unloaded at rest */
      bool is_moving = (fabsf(velocity_deg_s) > VELOCITY_GATE_DEG_S);
      bool is_loaded = (s_filt_force_lbs > FORCE_GATE_LBS);
      bool near_ff   = (fabsf(s_feedforward_pos_mm - s_profiled_pos_mm) < 1.5f);

      float error_eff = 0.0f;
      if ( is_moving || is_loaded )
      {
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

        /* 4. Slew Anti-Windup Gating: only integrate once loaded or near feedforward target */
        if ( is_loaded || near_ff )
        {
          s_integral += (error_eff * dt_s);

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
      }

      /* 5. Laplace-Derived PI Feedback Trim */
      float trim_mm = (KP_FORCE * error_eff) + (KI_FORCE * s_integral);

      /* 6. Total Commanded Carriage Position */
      s_commanded_pos_mm = s_feedforward_pos_mm + trim_mm;

      /* Safety clamp within physical mechanism stroke bounds */
      float min_pos = s_direct_pos_active ? X_MIN_TRAVEL_MM : 0.0f;
      if ( s_commanded_pos_mm < min_pos )
      {
        s_commanded_pos_mm = min_pos;
      }
      else if ( s_commanded_pos_mm > X_MAX_TRAVEL_MM )
      {
        s_commanded_pos_mm = X_MAX_TRAVEL_MM;
      }
    }
  }

  /* 6B. Auto-Scale IRUN only when stationary so UART never introduces step jitter mid-ramp:
  ** drop to 500 mA standby at 0.0 mm home, restore full configured run current before moving off 0.0 mm. */
  if ( s_current_step == s_target_step )
  {
    bool need_active = (s_current_step != 0) ||
                       (fabsf(s_commanded_pos_mm) >= 0.05f) ||
                       (s_direct_pos_active && (fabsf(s_direct_pos_override_mm) >= 0.05f)) ||
                       (s_motor_enabled && !s_curl_reversing && (s_target_torque_lbf_in > 0.0f));
    motor_apply_dynamic_current(need_active);
  }

  /* 7. Asymmetric Trapezoidal Profiler (Smooth engaging, crisp retraction on descent release) */
  /* Prevent profiler from drifting > 0.5 mm ahead of actual stepper position */
  float lag_mm = s_profiled_pos_mm - s_current_pos_mm;
  if ( lag_mm > 0.5f )
  {
    s_profiled_pos_mm = s_current_pos_mm + 0.5f;
  }
  else if ( lag_mm < -0.5f )
  {
    s_profiled_pos_mm = s_current_pos_mm - 0.5f;
  }

  float pos_err = s_commanded_pos_mm - s_profiled_pos_mm;
  bool is_releasing = (pos_err < -0.005f) && (!s_direct_pos_active);
  float slew_v_max = is_releasing ? MAX_RELEASE_VELOCITY_MM_S : MAX_SLEW_VELOCITY_MM_S;
  float accel_max  = is_releasing ? MAX_RELEASE_ACCEL_MM_S2  : MAX_ACCELERATION_MM_S2;
  float desired_vel = 0.0f;

  if ( fabsf(pos_err) > 0.005f )
  {
    /* Calculate stopping speed: v_max_decel = sqrt(2 * a * d) */
    float max_reachable_vel = sqrtf(2.0f * accel_max * fabsf(pos_err));
    if ( max_reachable_vel > slew_v_max )
    {
      max_reachable_vel = slew_v_max;
    }
    desired_vel = (pos_err > 0.0f) ? max_reachable_vel : -max_reachable_vel;
  }
  else
  {
    desired_vel = 0.0f;
  }

  /* Limit acceleration (dv/dt <= accel_max) */
  float max_v_step = accel_max * dt_s;
  if ( desired_vel > (s_current_vel_mm_s + max_v_step) )
  {
    s_current_vel_mm_s += max_v_step;
  }
  else if ( desired_vel < (s_current_vel_mm_s - max_v_step) )
  {
    s_current_vel_mm_s -= max_v_step;
  }
  else
  {
    s_current_vel_mm_s = desired_vel;
  }

  /* Integrate velocity to advance profiled position */
  s_profiled_pos_mm += (s_current_vel_mm_s * dt_s);

  /* Clamp within mechanical bounds (allow negative displacement in direct calibration mode) */
  float min_pos = s_direct_pos_active ? X_MIN_TRAVEL_MM : 0.0f;
  if ( s_profiled_pos_mm < min_pos )
  {
    s_profiled_pos_mm = min_pos;
    s_current_vel_mm_s = 0.0f;
  }
  else if ( s_profiled_pos_mm > X_MAX_TRAVEL_MM )
  {
    s_profiled_pos_mm = X_MAX_TRAVEL_MM;
    s_current_vel_mm_s = 0.0f;
  }

  /* 8. Convert Profiled Linear Position to Target Motor Steps */
  s_target_step = (int32_t)lroundf(s_profiled_pos_mm * s_steps_per_mm);

  /* Dynamically calculate step interval in DWT cycles based on instantaneous velocity */
  float abs_vel = fabsf(s_current_vel_mm_s);
  if ( (abs_vel < MIN_SLEW_VELOCITY_MM_S) && (s_current_step != s_target_step) )
  {
    abs_vel = MIN_SLEW_VELOCITY_MM_S; /* Smooth settling crawl */
  }
  else if ( abs_vel < 0.1f )
  {
    abs_vel = MIN_SLEW_VELOCITY_MM_S; /* Never jump to 100 us max speed from standstill */
  }

  float step_rate_hz = abs_vel * s_steps_per_mm;
  uint32_t cycles = (uint32_t)((float)SystemCoreClock / step_rate_hz);
  uint32_t min_cycles = (SystemCoreClock / 1000000) * MOTOR_MIN_STEP_INTERVAL_US;
  if ( cycles < min_cycles )
  {
    cycles = min_cycles;
  }
  s_step_interval_cycles = cycles;

  /* 9. Periodic TMC2209 Health Diagnostics (ONLY when stationary so UART never stalls active ramps) */
  static uint8_t s_tmc_check_cnt = 0;
  s_tmc_check_cnt++;
  if ( s_tmc_online && (s_tmc_check_cnt >= 20) && (s_current_step == s_target_step) )
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

/* Non-blocking stepper pulse engine
** Parameters:
**   None
** Return:
**   None
** Notes:
**   Maintains microsecond step period paced to current velocity using Cortex-M4 DWT cycles
*/
void Motor_StepTask(void)
{
  /* Hard hardware limit switch guard: halt stepping instantaneously if PB13 is active */
  if ( Motor_IsLimitSwitchTriggered() )
  {
    return;
  }

  if ( s_current_step == s_target_step )
  {
    /* If disabled and carriage has returned completely home to 0, disable driver to keep cool */
    if ( (!s_motor_enabled) && (!s_direct_pos_active) && (s_current_step == 0) )
    {
      HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_INACTIVE_LEVEL);
    }
    return;
  }

  /* Check if dynamically paced step interval has elapsed */
  uint32_t cycles_now     = DWT->CYCCNT;
  uint32_t cycles_elapsed = cycles_now - s_last_step_cycle;

  if ( cycles_elapsed < s_step_interval_cycles )
  {
    return;
  }

  /* Determine step direction */
  int32_t step_delta = 0;
  if ( s_target_step > s_current_step )
  {
    /* Positive step: advance carriage towards brake (tightens brake) */
    HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_SET : GPIO_PIN_RESET);
    step_delta = 1;
  }
  else
  {
    /* Negative step: retract carriage away from brake (loosens brake) */
    HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_RESET : GPIO_PIN_SET);
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

/* Query if TMC2209 responded over single-wire UART
** Parameters:
**   None
** Return:
**   bool: True if online
** Notes:
**   None
*/
bool Motor_IsTMC2209Online(void)
{
  if ( !s_tmc_online )
  {
    s_tmc_online = TMC2209_Init();
  }
  return s_tmc_online;
} /* Motor_IsTMC2209Online() */

/* Read instantaneous StallGuard4 mechanical coil load (0..1023)
** Parameters:
**   None
** Return:
**   uint16_t: StallGuard value
** Notes:
**   None
*/
uint16_t Motor_GetStallGuardResult(void)
{
  if ( s_tmc_online )
  {
    return TMC2209_ReadStallGuard();
  }
  return 0;
} /* Motor_GetStallGuardResult() */

/* Query driver health, temperature flags, and coil short diagnostics
** Parameters:
**   status - Pointer to TMC2209_Status_t struct
** Return:
**   bool: True if query succeeded
** Notes:
**   None
*/
bool Motor_GetTMC2209Status(TMC2209_Status_t *status)
{
  if ( (!s_tmc_online) || (status == (TMC2209_Status_t *)0) )
  {
    return false;
  }
  return TMC2209_ReadStatus(status);
} /* Motor_GetTMC2209Status() */

/* Configure digital coil current in mA and standstill hold percentage over UART
** Parameters:
**   run_mA - Commanded RMS run current in milliamps (e.g. 800..1400 mA)
**   hold_percent - Hold current percentage at standstill (e.g. 50%)
** Return:
**   bool: True if written
** Notes:
**   None
*/
bool Motor_SetDriverCurrent(uint16_t run_mA, uint8_t hold_percent)
{
  s_configured_run_mA   = run_mA;
  s_configured_hold_pct = hold_percent;
  if ( !s_tmc_online )
  {
    s_tmc_online = TMC2209_Init();
  }
  if ( !s_tmc_online )
  {
    return false;
  }
  uint16_t applied_mA = s_is_standby_current ? TMC2209_STANDBY_RUN_CURRENT_MA : s_configured_run_mA;
  return TMC2209_SetCurrent(applied_mA, hold_percent);
} /* Motor_SetDriverCurrent() */

uint16_t Motor_GetConfiguredRunCurrentMa(void)
{
  return s_configured_run_mA;
}

bool Motor_IsStandbyCurrent(void)
{
  return s_is_standby_current;
}

/* Toggle StealthChop2 vs SpreadCycle
** Parameters:
**   enable - True for StealthChop2, False for SpreadCycle
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool Motor_SetDriverStealthChop(bool enable)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_EnableStealthChop(enable);
} /* Motor_SetDriverStealthChop() */

/* Configure CoolStep load-dependent current reduction
** Parameters:
**   semin - Lower StallGuard threshold
**   semax - Upper StallGuard threshold
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool Motor_SetDriverCoolStep(uint8_t semin, uint8_t semax)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_ConfigureCoolStep(semin, semax);
} /* Motor_SetDriverCoolStep() */

static uint8_t  s_homing_sgthrs        = 100;
static uint32_t s_homing_speed_us      = 350;   /* 350 us step period (~7.1 mm/s / ~54 RPM) */
static uint16_t s_homing_current_mA    = 800;   /* 800 mA gentle homing current */
static float    s_homing_slack_mm      = 30.0f; /* 30.0 mm backoff clearance from limit switch */
static char     s_homing_diagnostic[128] = "INIT";

/* Read formatted diagnostic outcome string from last homing operation
** Parameters:
**   None
** Return:
**   const char *: Diagnostic outcome string
** Notes:
**   None
*/
const char *Motor_GetHomingDiagnostic(void)
{
  return s_homing_diagnostic;
} /* Motor_GetHomingDiagnostic() */

/* Microsecond-resolution busy wait utilizing Cortex-M4 DWT cycles
** Parameters:
**   us - Microseconds to delay
** Return:
**   None
** Notes:
**   Private helper function
*/
static inline void delay_us(uint32_t us)
{
  uint32_t start = DWT->CYCCNT;
  uint32_t cycles = us * (SystemCoreClock / 1000000U);
  while ( (DWT->CYCCNT - start) < cycles )
  {
    __NOP();
  }
} /* delay_us() */

/* Program StallGuard4 threshold sensitivity for sensorless homing
** Parameters:
**   threshold - StallGuard4 threshold value (0..255)
** Return:
**   None
** Notes:
**   None
*/
void Motor_SetHomingStallGuardThreshold(uint8_t threshold)
{
  s_homing_sgthrs = threshold;
  if ( !s_tmc_online )
  {
    s_tmc_online = TMC2209_Init();
  }
  if ( s_tmc_online )
  {
    TMC2209_ConfigureStallGuard(threshold);
  }
} /* Motor_SetHomingStallGuardThreshold() */

/* Read currently configured homing StallGuard4 threshold
** Parameters:
**   None
** Return:
**   uint8_t: Configured threshold value
** Notes:
**   None
*/
uint8_t Motor_GetHomingStallGuardThreshold(void)
{
  return s_homing_sgthrs;
} /* Motor_GetHomingStallGuardThreshold() */

/* Configure step period in microseconds for homing search
** Parameters:
**   speed_us - Microseconds per step pulse
** Return:
**   None
** Notes:
**   Clamped to safe search bounds (150..2000 us)
*/
void Motor_SetHomingSpeedUs(uint32_t speed_us)
{
  if ( speed_us < 150 )
  {
    speed_us = 150;
  }
  else if ( speed_us > 2000 )
  {
    speed_us = 2000;
  }
  s_homing_speed_us = speed_us;
} /* Motor_SetHomingSpeedUs() */

/* Read currently configured homing search step period
** Parameters:
**   None
** Return:
**   uint32_t: Microseconds per step
** Notes:
**   None
*/
uint32_t Motor_GetHomingSpeedUs(void)
{
  return s_homing_speed_us;
} /* Motor_GetHomingSpeedUs() */

/* Configure current in mA for soft homing contact
** Parameters:
**   ma - Motor RMS current in milliamps (400..1800 mA)
** Return:
**   None
** Notes:
**   None
*/
void Motor_SetHomingCurrentMa(uint16_t ma)
{
  if ( ma < 400 )
  {
    ma = 400;
  }
  else if ( ma > 1800 )
  {
    ma = 1800;
  }
  s_homing_current_mA = ma;
} /* Motor_SetHomingCurrentMa() */

/* Read currently configured soft homing current
** Parameters:
**   None
** Return:
**   uint16_t: Current in mA
** Notes:
**   None
*/
uint16_t Motor_GetHomingCurrentMa(void)
{
  return s_homing_current_mA;
} /* Motor_GetHomingCurrentMa() */

/* Program homing standoff clearance / slack distance in mm
** Parameters:
**   slack_mm - Distance to back off away from limit switch after contact (0.0 to 50.0 mm)
** Return:
**   None
*/
void Motor_SetHomingSlackMm(float slack_mm)
{
  if ( slack_mm < 0.0f )
  {
    slack_mm = 0.0f;
  }
  else if ( slack_mm > 50.0f )
  {
    slack_mm = 50.0f;
  }
  s_homing_slack_mm = slack_mm;
} /* Motor_SetHomingSlackMm() */

/* Read homing standoff clearance / slack distance in mm
** Parameters:
**   None
** Return:
**   float: Slack backoff distance in mm
*/
float Motor_GetHomingSlackMm(void)
{
  return s_homing_slack_mm;
} /* Motor_GetHomingSlackMm() */

/* Configure StallGuard4 stall sensitivity threshold (0..255)
** Parameters:
**   threshold - Sensitivity value
** Return:
**   bool: True if updated
** Notes:
**   None
*/
bool Motor_SetDriverStallGuardThreshold(uint8_t threshold)
{
  if ( !s_tmc_online )
  {
    return false;
  }
  return TMC2209_ConfigureStallGuard(threshold);
} /* Motor_SetDriverStallGuardThreshold() */

/* Check whether physical limit switch (PB13) is triggered
** Parameters:
**   None
** Return:
**   bool: True if limit reached
*/
bool Motor_IsLimitSwitchTriggered(void)
{
  /* Physical microswitch on PB13 with pull-up (Active LOW when pressed to free GND) */
  if ( HAL_GPIO_ReadPin(MOTOR_LIMIT_PORT, MOTOR_LIMIT_PIN) == GPIO_PIN_RESET )
  {
    return true;
  }
  return false;
} /* Motor_IsLimitSwitchTriggered() */

/* Poll hardware limit switch PB13 during normal operation as an E-Stop edge trigger.
** Parameters:
**   None
** Return:
**   bool: True on the rising event when switch was hit (caller cancels run & homes)
** Notes:
**   Latches while switch stays held down so a stuck switch cannot infinite-loop homing.
*/
bool Motor_ServiceLimitEstop(void)
{
  if ( Motor_IsLimitSwitchTriggered() )
  {
    s_limit_release_cnt = 0;
    if ( !s_limit_was_triggered )
    {
      s_limit_debounce++;
      if ( s_limit_debounce >= 3U )
      {
        s_limit_was_triggered = true;
        s_limit_debounce      = 0;
        Motor_EmergencyStop();
        return true;
      }
    }
  }
  else
  {
    s_limit_debounce = 0;
    if ( s_limit_was_triggered )
    {
      s_limit_release_cnt++;
      if ( s_limit_release_cnt >= 5U )
      {
        s_limit_was_triggered = false;
        s_limit_release_cnt   = 0;
      }
    }
  }
  return false;
} /* Motor_ServiceLimitEstop() */

/* Execute homing: step until physical limit switch PB13, then back off 5 mm away
** Parameters:
**   None
** Return:
**   bool: True if homed and backed off successfully
*/
bool Motor_Home(void)
{
  /* 1. Ensure driver is enabled and awake */
  s_is_homing     = true;
  s_motor_enabled = true;
  HAL_GPIO_WritePin(MOTOR_EN_PORT, MOTOR_EN_PIN, MOTOR_EN_ACTIVE_LEVEL);
  HAL_Delay(10);

  /* Ensure TMC2209 UART is online (retry if power was just switched on) */
  if ( !s_tmc_online )
  {
    s_tmc_online = TMC2209_Init();
  }

  /* Configure homing current and smooth StealthChop mode */
  if ( s_tmc_online )
  {
    /* TMC2209 operates in StealthChop2 mode for silent, smooth motion */
    TMC2209_EnableStealthChop(true);

    /* Dedicated soft homing current: s_homing_current_mA (protects mechanics) */
    TMC2209_SetCurrent(s_homing_current_mA, 50);
  }

  /* 2. Step in reverse/retract direction to search for physical limit switch */
  int32_t max_search_steps = (int32_t)(60.0f * s_steps_per_mm); /* Search up to 60 mm */
  bool end_found = false;
  int32_t limit_switch_debounce = 0;
  int32_t stop_step = 0;
  const char *stop_cause = "TIMEOUT";

  /* Check if carriage is ALREADY at physical limit switch before moving */
  if ( HAL_GPIO_ReadPin(MOTOR_LIMIT_PORT, MOTOR_LIMIT_PIN) == GPIO_PIN_RESET )
  {
    end_found = true;
    stop_cause = "ALREADY_AT_PB13";
  }

  /* Homing search direction (retract / reverse) */
  HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_SET : GPIO_PIN_RESET);

  for ( int32_t i = 0; (i < max_search_steps) && !end_found; i++ )
  {
    HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_SET);
    for ( volatile int d = 0; d < 50; d++ )
    {
      __NOP();
    }
    HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);

    /* Smooth acceleration ramp at start of homing to prevent sudden torque shock */
    uint32_t step_delay = s_homing_speed_us;
    if ( i < 200 )
    {
      step_delay = 800 - (((800 - s_homing_speed_us) * i) / 200);
    }
    delay_us(step_delay);

    /* Immediate Emergency Stop poll on EVERY step (< 350 us latency) */
    SystemCommand_t c = Telemetry_PollCommand();
    if ( c == CMD_STOP )
    {
      stop_cause = "ESTOP_COMMANDED";
      end_found = false;
      s_is_homing = false;
      s_is_standby_current = false;
      Motor_EmergencyStop();
      Telemetry_SendAck("ACK:STOP:ESTOP\r\n");
      return false;
    }

    /* Physical limit switch PB13: Check at EVERY step (active LOW to GND) */
    if ( HAL_GPIO_ReadPin(MOTOR_LIMIT_PORT, MOTOR_LIMIT_PIN) == GPIO_PIN_RESET )
    {
      limit_switch_debounce++;
      if ( limit_switch_debounce >= 3 )
      {
        end_found = true;
        stop_cause = "LIMIT_PB13";
        stop_step = i;
        break;
      }
    }
    else
    {
      limit_switch_debounce = 0;
    }
  }

  HAL_Delay(30);

  /* If end stop was not found (timeout or failure), stop immediately and do not back off */
  if ( !end_found )
  {
    s_is_homing = false;
    s_is_standby_current = false;
    Motor_EmergencyStop();
    snprintf(s_homing_diagnostic, sizeof(s_homing_diagnostic),
             "CAUSE=%s,STEPS=%ld",
             stop_cause, (long)max_search_steps);
    return false;
  }

  /* 3. Move s_homing_slack_mm AWAY from limit switch with smooth trapezoidal ramp */
  int32_t backoff_steps = (int32_t)lroundf(s_homing_slack_mm * s_steps_per_mm);
  /* Opposite of homing search direction */
  HAL_GPIO_WritePin(MOTOR_DIR_PORT, MOTOR_DIR_PIN, s_dir_inverted ? GPIO_PIN_RESET : GPIO_PIN_SET);

  if ( backoff_steps > 0 )
  {
    for ( int32_t i = 0; i < backoff_steps; i++ )
    {
      /* Immediate Emergency Stop check on every step during backoff */
      SystemCommand_t c = Telemetry_PollCommand();
      if ( c == CMD_STOP )
      {
        s_is_homing = false;
        s_is_standby_current = false;
        Motor_EmergencyStop();
        Telemetry_SendAck("ACK:STOP:ESTOP\r\n");
        return false;
      }

      HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_SET);
      for ( volatile int d = 0; d < 50; d++ )
      {
        __NOP();
      }
      HAL_GPIO_WritePin(MOTOR_STEP_PORT, MOTOR_STEP_PIN, GPIO_PIN_RESET);

      uint32_t backoff_delay = s_homing_speed_us;
      if ( (backoff_steps > 400) && (i < 200) )
      {
        backoff_delay = 800 - (((800 - s_homing_speed_us) * i) / 200);
      }
      else if ( (backoff_steps > 400) && (i > (backoff_steps - 200)) )
      {
        backoff_delay = s_homing_speed_us + (((800 - s_homing_speed_us) * (i - (backoff_steps - 200))) / 200);
      }
      delay_us(backoff_delay);
    }
  }

  /* 4. Calibrate new physical 0.0 mm home at this standoff position & clear prior active targets
  ** so stale resistance/torque/position setpoints from Live Test cannot re-engage after homing. */
  s_current_step           = 0;
  s_target_step            = 0;
  s_current_pos_mm         = 0.0f;
  s_profiled_pos_mm        = 0.0f;
  s_commanded_pos_mm       = 0.0f;
  s_feedforward_pos_mm     = 0.0f;
  s_current_vel_mm_s       = 0.0f;
  s_integral               = 0.0f;
  s_target_resistance_lbs  = 0.0f;
  s_target_torque_lbf_in   = 0.0f;
  s_direct_pos_active      = false;
  s_direct_pos_override_mm = 0.0f;
  s_curl_reversing         = false;
  s_curl_stopped_ms        = 0;
  s_motor_enabled          = false;
  s_limit_debounce         = 0;
  s_limit_release_cnt      = 0;
  s_limit_was_triggered    = Motor_IsLimitSwitchTriggered();
  s_step_interval_cycles   = (uint32_t)((float)SystemCoreClock / (MIN_SLEW_VELOCITY_MM_S * s_steps_per_mm));

  /* Record detailed diagnostic outcome */
  snprintf(s_homing_diagnostic, sizeof(s_homing_diagnostic),
           "CAUSE=%s,STEPS=%ld,CLEAR=%.1fMM,POS=0.0",
           stop_cause, (long)(end_found ? stop_step : max_search_steps),
           s_homing_slack_mm);

  /* Drop cleanly to 500 mA standby current at 0.0 mm home until active load moves off 0 */
  s_is_homing = false;
  s_is_standby_current = false;
  motor_apply_dynamic_current(false);

  return end_found;
} /* Motor_Home() */

/* Sensorless homing convenience alias
** Parameters:
**   None
** Return:
**   bool: True if homed and backed off successfully
** Notes:
**   Delegates directly to Motor_Home()
*/
bool Motor_SensorlessHome(void)
{
  return Motor_Home();
} /* Motor_SensorlessHome() */
