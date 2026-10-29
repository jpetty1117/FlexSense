/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: spo2.h
** --------
** Interface for patient pulse oximeter & heart rate biometric acquisition.
*/

#ifndef SPO2_H
#define SPO2_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* Public Function Prototypes */
void  SpO2_Init(void);
void  SpO2_Update(void);
float SpO2_ReadPercent(void);
float SpO2_ReadHeartRateBpm(void);
bool  SpO2_IsFingerDetected(void);
bool  SpO2_IsOnline(void);
void  SpO2_Diagnose(char *out_buf, size_t max_len);

#ifdef __cplusplus
}
#endif

#endif /* SPO2_H */
