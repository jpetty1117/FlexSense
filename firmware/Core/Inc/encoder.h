/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: encoder.h
  * Brief: Public interface for rotary encoder kinematics and velocity filtering.
  ******************************************************************************
  */

#ifndef ENCODER_H
#define ENCODER_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* Public Constants */
#define ENCODER_CPR             2400.0f
#define ENCODER_DEG_PER_COUNT   (360.0f / ENCODER_CPR)

/* Public Function Prototypes */
void    Encoder_Init(TIM_HandleTypeDef *htim);
int32_t Encoder_GetCount(void);
float   Encoder_GetAngleDeg(void);
void    Encoder_UpdateVelocity(uint32_t now_ms);
float   Encoder_GetVelocityDegS(void);
void    Encoder_Zero(void);

#ifdef __cplusplus
}
#endif

#endif /* ENCODER_H */
