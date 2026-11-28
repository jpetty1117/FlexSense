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

/* Physical Plant & Drivetrain Model Constants (Measured 0.70 lbf/mm spring: ~15 lbs @ 15 mm from home) */
#define G_BRAKE_NOMINAL             2.86f     /* Dimensionless effective brake gain in biting phase */
#define K_SPRING_NOMINAL            0.70f     /* lbf / mm (installed SEA extension spring) */
#define K_PLANT_NOMINAL             (G_BRAKE_NOMINAL * K_SPRING_NOMINAL) /* ~2.00 lbf / mm */
#define X_SLACK_MM                  7.5f      /* mm of nominal clearance / take-up before pad bite */
#define X_MIN_TRAVEL_MM             -25.0f    /* mm minimum allowed travel for negative calibration & backlash */
#define X_MAX_TRAVEL_MM             28.0f     /* mm maximum allowed travel (2 mm margin inside 30 mm PB13 limit) */

/* Laplace-Tuned Closed-Loop Feedback Constants (Modulus Optimum: tau=0.080s, wc=3.0 rad/s, K_plant=2.0 lbf/mm) */
#define KP_FORCE                    0.120f    /* mm / lbf (proportional gain) */
#define KI_FORCE                    1.50f     /* mm / (lbf * s) (integral gain) */
#define FORCE_DEADBAND_LBS          0.50f     /* +/- 0.5 lbf deadband */
#define VELOCITY_GATE_DEG_S         3.0f      /* deg/s minimum joint speed */
#define FORCE_GATE_LBS              0.50f     /* lbf minimum patient applied load */
#define INTEGRAL_MAX_TRIM_MM        2.0f      /* mm maximum feedback trim (+/- 4 lbf @ 2.0 lbf/mm plant) */
#define MAX_SLEW_VELOCITY_MM_S      15.0f     /* mm/s smooth normal linear slew speed (engaging) */
#define MAX_ACCELERATION_MM_S2      45.0f     /* mm/s^2 smooth trapezoidal acceleration ramp (~0.33 s to full speed) */
#define MAX_RELEASE_VELOCITY_MM_S   16.0f     /* mm/s controlled crisp retraction without losing StealthChop sync */
#define MAX_RELEASE_ACCEL_MM_S2     60.0f     /* mm/s^2 smooth release acceleration so brake clears during lowering */
#define MIN_SLEW_VELOCITY_MM_S      0.5f      /* mm/s minimum crawling speed */

/* Stepper Motor & Lead Screw Mechanical Geometry */
#define MOTOR_FULL_STEPS_PER_REV    200.0f    /* 1.8 deg per full step */
#define MOTOR_LEAD_SCREW_PITCH_MM   8.0f      /* mm travel per motor revolution */
#define MOTOR_DEFAULT_MICROSTEP     16.0f     /* 1/16 microstepping driver */
#define MOTOR_STEPS_PER_MM          ((MOTOR_FULL_STEPS_PER_REV * MOTOR_DEFAULT_MICROSTEP) / MOTOR_LEAD_SCREW_PITCH_MM)
#define MOTOR_MIN_STEP_INTERVAL_US  125       /* microseconds (8 kHz cap = 20 mm/s max) */

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
#define MOTOR_LIMIT_PIN             GPIO_PIN_13
#define MOTOR_LIMIT_PORT            GPIOB

/* Driver enable levels */
#define MOTOR_EN_ACTIVE_LEVEL       GPIO_PIN_RESET
#define MOTOR_EN_INACTIVE_LEVEL     GPIO_PIN_SET

/* TMC2209 UART Current Limits (Calibrated to Adafruit Rsense=0.05 ohm, vsense=1: 1818 mA FS) */
#define TMC2209_DEFAULT_RUN_CURRENT_MA 1400   /* 1.40 A true RMS active run current */
#define TMC2209_STANDBY_RUN_CURRENT_MA 500    /* 0.50 A true RMS standby at 0.0 mm */
#define TMC2209_DEFAULT_HOLD_PERCENT   55     /* 55% hold (~770 mA active hold, ~275 mA at 0.0 mm standby) */

#include "tmc2209.h"

/* Public Function Prototypes */
void     Motor_Init(void);
void     Motor_StepISR(void);
void     Motor_SetResistanceLbs(float resistance_lbs);
void     Motor_SetTorqueLbfIn(float torque_lbf_in);
void     Motor_SetForearmLengthIn(float arm_in);
float    Motor_GetForearmLengthIn(void);
float    Motor_GetTargetTorqueLbfIn(void);
void     Motor_SetCommandedPositionMm(float pos_mm);
void     Motor_ZeroPosition(void);
float    Motor_GetTargetResistanceLbs(void);
float    Motor_GetCommandedPositionMm(void);
float    Motor_GetCurrentPositionMm(void);
float    Motor_GetCurrentVelocityMmS(void);
float    Motor_GetIqCurrent(void);
void     Motor_EmergencyStop(void);
bool     Motor_IsEnabled(void);
void     Motor_ResetCurlBaseline(void);
void     Motor_UpdateControl(float measured_force_lbs, float angle_deg, float velocity_deg_s, float dt_s);
void     Motor_StepTask(void);
void     Motor_SetInvertedDirection(bool inverted);
bool     Motor_IsInvertedDirection(void);
void     Motor_SetMicrostepping(float ustep_div);

/* TMC2209 Single-Wire UART Features */
bool     Motor_IsTMC2209Online(void);
uint16_t Motor_GetStallGuardResult(void);
bool     Motor_GetTMC2209Status(TMC2209_Status_t *status);
bool     Motor_SetDriverCurrent(uint16_t run_mA, uint8_t hold_percent);
uint16_t Motor_GetConfiguredRunCurrentMa(void);
bool     Motor_IsStandbyCurrent(void);
bool     Motor_SetDriverStealthChop(bool enable);
bool     Motor_SetDriverCoolStep(uint8_t semin, uint8_t semax);
bool     Motor_SetDriverStallGuardThreshold(uint8_t threshold);
void     Motor_SetHomingStallGuardThreshold(uint8_t threshold);
uint8_t  Motor_GetHomingStallGuardThreshold(void);
void     Motor_SetHomingSpeedUs(uint32_t speed_us);
uint32_t Motor_GetHomingSpeedUs(void);
void     Motor_SetHomingCurrentMa(uint16_t ma);
uint16_t Motor_GetHomingCurrentMa(void);
void     Motor_SetHomingSlackMm(float slack_mm);
float    Motor_GetHomingSlackMm(void);
bool     Motor_SensorlessHome(void);
bool     Motor_IsLimitSwitchTriggered(void);
bool     Motor_ServiceLimitEstop(void);
bool     Motor_Home(void);
const char *Motor_GetHomingDiagnostic(void);

#ifdef __cplusplus
}
#endif

#endif /* MOTOR_H */
