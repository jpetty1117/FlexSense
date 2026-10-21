/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: spo2.c
** --------
** Implementation skeleton for pulse oximeter sensor (MAX30102 / I2C).
*/

#include "spo2.h"

/* Private Module Variables */
static float s_last_spo2_pct = 98.0f;
static float s_last_hr_bpm   = 72.0f;
static bool  s_finger_present = true;

/* Initialize I2C bus and MAX30102 pulse oximeter registers
** Parameters:
**   None
** Return:
**   None
** Notes:
**   None
*/
void SpO2_Init(void)
{
  s_last_spo2_pct  = 98.0f;
  s_last_hr_bpm    = 72.0f;
  s_finger_present = true;
} /* SpO2_Init() */

/* Read blood oxygen saturation level in percent (90 - 100%)
** Parameters:
**   None
** Return:
**   float: SpO2 percentage
** Notes:
**   None
*/
float SpO2_ReadPercent(void)
{
  return s_last_spo2_pct;
} /* SpO2_ReadPercent() */

/* Read instantaneous patient heart rate in Beats Per Minute (BPM)
** Parameters:
**   None
** Return:
**   float: Heart rate BPM
** Notes:
**   None
*/
float SpO2_ReadHeartRateBpm(void)
{
  return s_last_hr_bpm;
} /* SpO2_ReadHeartRateBpm() */

/* Check if optical reflection confirms patient finger contact
** Parameters:
**   None
** Return:
**   bool: True if finger detected
** Notes:
**   None
*/
bool SpO2_IsFingerDetected(void)
{
  return s_finger_present;
} /* SpO2_IsFingerDetected() */
