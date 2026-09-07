/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: motor.h
  * Brief: Interface for rehabilitation resistance torque motor & FOC controller.
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

/* Public Function Prototypes */
void  Motor_Init(void);
void  Motor_SetResistanceLbs(float resistance_lbs);
float Motor_GetIqCurrent(void);
void  Motor_EmergencyStop(void);
bool  Motor_IsEnabled(void);

#ifdef __cplusplus
}
#endif

#endif /* MOTOR_H */
