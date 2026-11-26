/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: encoder.h
** --------
** Public interface for rotary encoder kinematics and velocity filtering.
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
#define ENCODER_CPR             2400.0f  /* Optical encoder raw counts per revolution (4X decoding on TIM2) */
#define ENCODER_BELT_RATIO      2.0f     /* 2:1 timing belt ratio (1 encoder rev = 180 deg curl, 2 encoder revs = 360 deg curl) */
#define ENCODER_POLARITY        (-1)     /* Direction polarity (+1 or -1) so concentric curl UP reads positive deg / deg/s */
#define ENCODER_DEG_PER_COUNT   (360.0f / (ENCODER_CPR * ENCODER_BELT_RATIO)) /* 180.0f / 2400.0f = 0.075 deg / count */

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
