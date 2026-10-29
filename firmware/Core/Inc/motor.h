/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: motor.h
** --------
** Interface for Series Elastic Actuator (SEA) brake resistance controller.
** Stepper carriage pulls compliant spring attached to bicycle brake handle
** trigger (lever mechanical advantage) driving hydraulic disc brake caliper.
** Combines feedforward lead-screw positioning with Laplace-tuned PI
** handle load cell feedback trim and stepper motion generation.
*/

#ifndef MOTOR_H
#define MOTOR_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* Physical Plant & Drivetrain Model Constants */
#define G_BRAKE_NOMINAL             1.75f     /* Dimensionless brake gain */
#define K_SPRING_NOMINAL            1.25f     /* lbf / mm */
#define K_PLANT_NOMINAL             (G_BRAKE_NOMINAL * K_SPRING_NOMINAL) /* 2.1875 lbf / mm */
#define X_SLACK_MM                  2.5f      /* mm of initial carriage take-up */
#define X_MAX_TRAVEL_MM             35.0f     /* mm maximum allowed travel */

/* Laplace-Tuned Closed-Loop Feedback Constants */
#define KP_FORCE                    0.091f    /* mm / lbf (proportional gain) */
#define KI_FORCE                    1.64f     /* mm / (lbf * s) (integral gain) */
#define FORCE_DEADBAND_LBS          0.50f     /* +/- 0.5 lbf deadband */
#define VELOCITY_GATE_DEG_S         3.0f      /* deg/s minimum joint speed */
#define FORCE_GATE_LBS              0.50f     /* lbf minimum patient applied load */
#define INTEGRAL_MAX_TRIM_MM        3.0f      /* mm maximum feedback trim */
#define MAX_SLEW_VELOCITY_MM_S      25.0f     /* mm/s maximum linear speed */

/* Stepper Motor & Lead Screw Mechanical Geometry */
#define MOTOR_FULL_STEPS_PER_REV    200.0f    /* 1.8 deg per full step */
#define MOTOR_LEAD_SCREW_PITCH_MM   8.0f      /* mm travel per motor revolution */
#define MOTOR_DEFAULT_MICROSTEP     16.0f     /* 1/16 microstepping driver */
#define MOTOR_STEPS_PER_MM          ((MOTOR_FULL_STEPS_PER_REV * MOTOR_DEFAULT_MICROSTEP) / MOTOR_LEAD_SCREW_PITCH_MM)
#define MOTOR_MIN_STEP_INTERVAL_US  100       /* microseconds */

/* Hardware Pin Allocations (Adafruit TMC2209 Breakout) */
#define MOTOR_DIR_PIN               GPIO_PIN_4
#define MOTOR_DIR_PORT              GPIOA
#define MOTOR_STEP_PIN              GPIO_PIN_5
#define MOTOR_STEP_PORT             GPIOA
#define MOTOR_EN_PIN                GPIO_PIN_6
#define MOTOR_EN_PORT               GPIOA
#define MOTOR_MS1_PIN               GPIO_PIN_7
#define MOTOR_MS1_PORT              GPIOA
#define MOTOR_MS2_PIN               GPIO_PIN_0
#define MOTOR_MS2_PORT              GPIOB
#define MOTOR_DIAG_PIN              GPIO_PIN_1
#define MOTOR_DIAG_PORT             GPIOB
#define MOTOR_INDEX_PIN             GPIO_PIN_3
#define MOTOR_INDEX_PORT            GPIOA
#define MOTOR_LIMIT_PIN             GPIO_PIN_12
#define MOTOR_LIMIT_PORT            GPIOB

/* Driver enable levels */
#define MOTOR_EN_ACTIVE_LEVEL       GPIO_PIN_RESET
#define MOTOR_EN_INACTIVE_LEVEL     GPIO_PIN_SET

/* TMC2209 UART Current Limits */
#define TMC2209_DEFAULT_RUN_CURRENT_MA 1300   /* 1.3 A RMS driver coil current limit */
#define TMC2209_DEFAULT_HOLD_PERCENT   50     /* 50% hold current at standstill */

#include "tmc2209.h"

/* Public Function Prototypes */
void     Motor_Init(void);
void     Motor_SetResistanceLbs(float resistance_lbs);
float    Motor_GetTargetResistanceLbs(void);
float    Motor_GetCommandedPositionMm(void);
float    Motor_GetCurrentPositionMm(void);
float    Motor_GetIqCurrent(void);
void     Motor_EmergencyStop(void);
bool     Motor_IsEnabled(void);
void     Motor_UpdateControl(float measured_force_lbs, float velocity_deg_s, float dt_s);
void     Motor_StepTask(void);
void     Motor_SetInvertedDirection(bool inverted);
void     Motor_SetMicrostepping(float ustep_div);

/* TMC2209 Single-Wire UART Features */
bool     Motor_IsTMC2209Online(void);
uint16_t Motor_GetStallGuardResult(void);
bool     Motor_GetTMC2209Status(TMC2209_Status_t *status);
bool     Motor_SetDriverCurrent(uint16_t run_mA, uint8_t hold_percent);
bool     Motor_SetDriverStealthChop(bool enable);
bool     Motor_SetDriverCoolStep(uint8_t semin, uint8_t semax);
bool     Motor_SetDriverStallGuardThreshold(uint8_t threshold);
void     Motor_SetHomingStallGuardThreshold(uint8_t threshold);
uint8_t  Motor_GetHomingStallGuardThreshold(void);
void     Motor_SetHomingSpeedUs(uint32_t speed_us);
uint32_t Motor_GetHomingSpeedUs(void);
void     Motor_SetHomingCurrentMa(uint16_t ma);
uint16_t Motor_GetHomingCurrentMa(void);
bool     Motor_SensorlessHome(void);
bool     Motor_IsLimitSwitchTriggered(void);
bool     Motor_Home(void);
const char *Motor_GetHomingDiagnostic(void);

#ifdef __cplusplus
}
#endif

#endif /* MOTOR_H */
