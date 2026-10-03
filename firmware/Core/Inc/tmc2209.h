/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: tmc2209.h
  * Brief: Complete register interface and single-wire UART driver for Trinamic
  *        TMC2209 ultra-silent stepper motor driver.
  *        Features: Digital current control (IHOLD_IRUN), StealthChop2,
  *        SpreadCycle, CoolStep, StallGuard4 load measurement, 256-microstep
  *        interpolation, internal motion controller (VACTUAL), and full
  *        hardware diagnostics (thermal, short-circuit, open-load).
  ******************************************************************************
  */

#ifndef TMC2209_H
#define TMC2209_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* ==========================================================================
   TMC2209 Complete Register Map
   ========================================================================== */
#define TMC2209_REG_GCONF           0x00  /* Global configuration flags */
#define TMC2209_REG_GSTAT           0x01  /* Global status flags (reset, error) */
#define TMC2209_REG_IFCNT           0x02  /* UART interface transmission counter */
#define TMC2209_REG_SLAVECONF       0x03  /* Send delay configuration */
#define TMC2209_REG_OTP_PROG        0x04  /* OTP programming register */
#define TMC2209_REG_OTP_READ        0x05  /* OTP read register */
#define TMC2209_REG_IOIN            0x06  /* Read input pin states */
#define TMC2209_REG_FACTORY_CONF    0x07  /* Factory configuration */

#define TMC2209_REG_IHOLD_IRUN      0x10  /* Standstill & run current settings */
#define TMC2209_REG_TPOWERDOWN      0x11  /* Delay before power-down to hold current */
#define TMC2209_REG_TSTEP           0x12  /* Measured time between microsteps */
#define TMC2209_REG_TPWMTHRS        0x13  /* StealthChop upper velocity threshold */
#define TMC2209_REG_TCOOLTHRS       0x14  /* CoolStep & StallGuard velocity threshold */
#define TMC2209_REG_VACTUAL         0x22  /* Internal velocity motion controller */

#define TMC2209_REG_SGTHRS          0x40  /* StallGuard4 detection threshold */
#define TMC2209_REG_SG_RESULT       0x41  /* StallGuard4 load measurement output */
#define TMC2209_REG_COOLCONF        0x42  /* CoolStep smart current reduction */

#define TMC2209_REG_CHOPCONF        0x6C  /* Chopper and microstep configuration */
#define TMC2209_REG_DRV_STATUS      0x6F  /* Driver error flags, load, and temperature */
#define TMC2209_REG_PWMCONF         0x70  /* StealthChop voltage PWM parameters */
#define TMC2209_REG_PWM_SCALE       0x71  /* StealthChop amplitude scale result */
#define TMC2209_REG_PWM_AUTO        0x72  /* Auto-tuning results for StealthChop */

/* ==========================================================================
   GCONF Register Bitfield Masks
   ========================================================================== */
#define TMC2209_GCONF_I_SCALE_ANALOG    (1U << 0)  /* 0 = internal current, 1 = VREF */
#define TMC2209_GCONF_INTERNAL_RSENSE   (1U << 1)  /* 0 = external sense resistors */
#define TMC2209_GCONF_EN_SPREADCYCLE    (1U << 2)  /* 0 = StealthChop2, 1 = SpreadCycle */
#define TMC2209_GCONF_SHAFT             (1U << 3)  /* 0 = normal, 1 = inverse direction */
#define TMC2209_GCONF_INDEX_OTPW        (1U << 4)  /* 1 = INDEX pin shows overtemp warning */
#define TMC2209_GCONF_INDEX_STEP        (1U << 5)  /* 1 = INDEX pin pulses on microstep */
#define TMC2209_GCONF_PDN_DISABLE       (1U << 6)  /* 1 = disable PDN UART function on pin */
#define TMC2209_GCONF_MSTEP_REG_SELECT  (1U << 7)  /* 1 = microsteps from MRES register */
#define TMC2209_GCONF_MULTISTEP_FILT    (1U << 8)  /* 1 = enable step pulse filtering */
#define TMC2209_GCONF_TEST_MODE         (1U << 9)  /* 1 = factory test mode */

/* ==========================================================================
   Hardware UART Pin Allocations (STM32F411CEU6)
   ========================================================================== */
#define TMC2209_UART_TX_PIN         GPIO_PIN_9
#define TMC2209_UART_TX_PORT        GPIOA
#define TMC2209_UART_RX_PIN         GPIO_PIN_10
#define TMC2209_UART_RX_PORT        GPIOA

/* Set to 1 for single-wire half-duplex on PA9 (no external resistors needed)
   Set to 0 for standard 2-wire connection (PA9 TX with 1k resistor, PA10 RX) */
#define TMC2209_USE_HALF_DUPLEX     1

/* Standard sense resistor on BigTreeTech / Watterott TMC2209 breakout boards */
#define TMC2209_RSENSE_OHMS         0.11f

/* Default UART communication baud rate */
#define TMC2209_DEFAULT_BAUD        115200

/* ==========================================================================
   Exported Diagnostic & Status Structures
   ========================================================================== */
typedef struct {
  bool     over_temperature_warning;  /* otpw: 120 deg C pre-warning threshold reached */
  bool     over_temperature_shutdown; /* ot: 150 deg C thermal shutdown triggered */
  bool     short_to_ground_a;         /* s2ga: phase A short circuit to GND */
  bool     short_to_ground_b;         /* s2gb: phase B short circuit to GND */
  bool     short_to_supply_a;         /* s2vsa: phase A short circuit to VMOT */
  bool     short_to_supply_b;         /* s2vsb: phase B short circuit to VMOT */
  bool     open_load_a;               /* ola: phase A open load (motor disconnected) */
  bool     open_load_b;               /* olb: phase B open load (motor disconnected) */
  bool     standstill;                /* stst: motor is at standstill */
  bool     stealthchop_active;        /* stealth: operating in StealthChop2 mode */
  uint8_t  current_scale;             /* cs_actual: active coil current scale (0..31) */
  uint16_t stallguard_result;         /* sg_result: mechanical load indicator (0..1023) */
  bool     uart_online;               /* True if UART link responds to pings */
  bool     driver_fault;              /* True if any thermal or short fault is active */
} TMC2209_Status_t;

/* ==========================================================================
   Public Function Prototypes
   ========================================================================== */
bool TMC2209_Init(void);
bool TMC2209_Ping(void);

/* Digital Current & Thermal Management */
bool TMC2209_SetCurrent(uint16_t run_current_mA, uint8_t hold_percent);
bool TMC2209_ConfigureCoolStep(uint8_t semin, uint8_t semax);

/* Motion & Chopper Tuning */
bool TMC2209_SetMicrostepping(uint16_t microsteps, bool interpolate_256);
bool TMC2209_EnableStealthChop(bool enable);
bool TMC2209_SetSpreadCycleThreshold(uint32_t speed_tstep);
bool TMC2209_SetShaftInvert(bool invert);
bool TMC2209_SetVActual(int32_t velocity);

/* StallGuard4 Sensorless Load Sensing & Homing */
bool     TMC2209_ConfigureStallGuard(uint8_t threshold);
uint16_t TMC2209_ReadStallGuard(void);

/* Diagnostics & Health Monitoring */
bool     TMC2209_ReadStatus(TMC2209_Status_t *status);
uint32_t TMC2209_ReadIO(void);

/* Low-level Trinamic datagram register access */
bool TMC2209_WriteRegister(uint8_t reg, uint32_t data);
bool TMC2209_ReadRegister(uint8_t reg, uint32_t *data);

#ifdef __cplusplus
}
#endif

#endif /* TMC2209_H */
