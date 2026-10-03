/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: motor.h
  * Brief: Interface for Series Elastic Actuator (SEA) brake resistance controller.
  *        Combines feedforward lead-screw positioning with Laplace-tuned PI
  *        handle load cell feedback trim and stepper motion generation.
  ******************************************************************************
  */

#ifndef MOTOR_H
#define MOTOR_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* ==========================================================================
   Physical Plant & Drivetrain Model Constants
   ========================================================================== */
/* Nominal brake leverage ratio: G_brake = (2 * mu * M_caliper * R_eff) / L_arm */
#define G_BRAKE_NOMINAL             1.75f     /* Dimensionless brake gain */

/* Physical extension spring compliance between carriage and cable */
#define K_SPRING_NOMINAL            1.25f     /* lbf / mm */

/* Combined plant stiffness: K_plant = G_brake * k_spring */
#define K_PLANT_NOMINAL             (G_BRAKE_NOMINAL * K_SPRING_NOMINAL) /* 2.1875 lbf / mm */

/* Cable slack and caliper pad clearance before rotor contact */
#define X_SLACK_MM                  2.5f      /* mm of initial carriage take-up */

/* Physical linear travel limit on integrated lead screw (130 mm max stroke) */
#define X_MAX_TRAVEL_MM             35.0f     /* mm maximum allowed travel */

/* ==========================================================================
   Laplace-Tuned Closed-Loop Feedback Constants
   Derived for critical damping (zeta = 1.0, omega_n = 12 rad/s, tau = 50 ms)
   ========================================================================== */
#define KP_FORCE                    0.091f    /* mm / lbf (proportional gain) */
#define KI_FORCE                    1.64f     /* mm / (lbf * s) (integral gain) */

/* Force error deadband to prevent motor chatter and reject hand tremor */
#define FORCE_DEADBAND_LBS          0.50f     /* +/- 0.5 lbf deadband */

/* Motion gating thresholds to prevent integrator windup when patient is idle */
#define VELOCITY_GATE_DEG_S         3.0f      /* deg/s minimum joint speed */
#define FORCE_GATE_LBS              0.50f     /* lbf minimum patient applied load */

/* Maximum integral trim travel limit (anti-windup guard) */
#define INTEGRAL_MAX_TRIM_MM        3.0f      /* mm maximum feedback trim */

/* Carriage velocity slew rate limit to protect stepper from stalling */
#define MAX_SLEW_VELOCITY_MM_S      25.0f     /* mm/s maximum linear speed */

/* ==========================================================================
   Stepper Motor & Lead Screw Mechanical Geometry
   NEMA 17 with integrated T8x8 lead screw (8.0 mm lead per revolution)
   ========================================================================== */
#define MOTOR_FULL_STEPS_PER_REV    200.0f    /* 1.8 deg per full step */
#define MOTOR_LEAD_SCREW_PITCH_MM   8.0f      /* mm travel per motor revolution */
#define MOTOR_DEFAULT_MICROSTEP     16.0f     /* 1/16 microstepping driver */

/* Calculated steps per mm of linear carriage motion */
#define MOTOR_STEPS_PER_MM          ((MOTOR_FULL_STEPS_PER_REV * MOTOR_DEFAULT_MICROSTEP) / MOTOR_LEAD_SCREW_PITCH_MM)

/* Minimum step period (100 us = 10 kHz max step frequency) */
#define MOTOR_MIN_STEP_INTERVAL_US  100       /* microseconds */

/* ==========================================================================
   Hardware Pin Allocations (STM32F411CEU6 BlackPill V2.0)
   ========================================================================== */
#define MOTOR_STEP_PIN              GPIO_PIN_4
#define MOTOR_STEP_PORT             GPIOA
#define MOTOR_DIR_PIN               GPIO_PIN_5
#define MOTOR_DIR_PORT              GPIOA
#define MOTOR_EN_PIN                GPIO_PIN_6
#define MOTOR_EN_PORT               GPIOA

/* Standard stepper driver enable levels (active-LOW for A4988 / TMC2208 / DRV8825) */
#define MOTOR_EN_ACTIVE_LEVEL       GPIO_PIN_RESET
#define MOTOR_EN_INACTIVE_LEVEL     GPIO_PIN_SET

/* ==========================================================================
   Public Function Prototypes
   ========================================================================== */
void  Motor_Init(void);
void  Motor_SetResistanceLbs(float resistance_lbs);
float Motor_GetTargetResistanceLbs(void);
float Motor_GetCommandedPositionMm(void);
float Motor_GetCurrentPositionMm(void);
float Motor_GetIqCurrent(void);
void  Motor_EmergencyStop(void);
bool  Motor_IsEnabled(void);

/* Periodic control loop update (call at 100 Hz / 10 ms interval) */
void  Motor_UpdateControl(float measured_force_lbs, float velocity_deg_s, float dt_s);

/* Non-blocking pulse generator task (call on each iteration of while(1) loop) */
void  Motor_StepTask(void);

#include "tmc2209.h"

/* Hardware configuration helpers */
void  Motor_SetInvertedDirection(bool inverted);
void  Motor_SetMicrostepping(float ustep_div);

/* TMC2209 Single-Wire UART Features */
bool     Motor_IsTMC2209Online(void);
uint16_t Motor_GetStallGuardResult(void);
bool     Motor_GetTMC2209Status(TMC2209_Status_t *status);
bool     Motor_SetDriverCurrent(uint16_t run_mA, uint8_t hold_percent);
bool     Motor_SetDriverStealthChop(bool enable);
bool     Motor_SetDriverCoolStep(uint8_t semin, uint8_t semax);
bool     Motor_SetDriverStallGuardThreshold(uint8_t threshold);
bool     Motor_SensorlessHome(void);

#ifdef __cplusplus
}
#endif

#endif /* MOTOR_H */
