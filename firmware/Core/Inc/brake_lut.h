/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** FlexSense - Calibrated Shaft Torque Kinematics & Look-Up Table (LUT)
** Maps shaft braking torque (lbf*in) to stepper carriage linear displacement (mm)
*/

#ifndef BRAKE_LUT_H
#define BRAKE_LUT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

/* System Gain Parameters */
#define BRAKE_SYSTEM_GAIN_LBF_IN_PER_MM   72.39f    /* Plant stiffness in biting phase (~6.03 lbf/mm * 12 in) */
#define BRAKE_SLACK_TAKEUP_MM             2.50f     /* Lead screw take-up before lever actuation */
#define BRAKE_LUT_MIN_TORQUE_LBF_IN       0.0f
#define BRAKE_LUT_MAX_TORQUE_LBF_IN       325.0f    /* Spans up to 25.0 lbs on 13-inch forearm setting */
#define BRAKE_LUT_STEP_TORQUE_LBF_IN      5.0f      /* 5.0 lbf*in per table step */
#define BRAKE_LUT_NUM_ENTRIES             66

/* Pre-computed Inverse Look-Up Table: Target Torque (0.0 to 325.0 lbf*in in 5.0 lbf*in steps) -> Commanded mm */
static const float s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES] = {
     0.000f,  7.155f,  8.642f,  8.713f,  8.783f,  8.853f,
     8.922f,  8.992f,  9.062f,  9.131f,  9.201f,  9.271f,
     9.340f,  9.409f,  9.479f,  9.549f,  9.618f,  9.687f,
     9.756f,  9.825f,  9.894f,  9.963f, 10.033f, 10.102f,
    10.171f, 10.240f, 10.309f, 10.378f, 10.448f, 10.517f,
    10.586f, 10.655f, 10.724f, 10.793f, 10.862f, 10.931f,
    11.000f, 11.069f, 11.138f, 11.206f, 11.276f, 11.345f,
    11.413f, 11.482f, 11.551f, 11.620f, 11.689f, 11.758f,
    11.827f, 11.895f, 11.964f, 12.034f, 12.102f, 12.171f,
    12.240f, 12.308f, 12.377f, 12.446f, 12.515f, 12.584f,
    12.652f, 12.721f, 12.790f, 12.858f, 12.927f, 12.996f,
};

/* Fast O(1) Feedforward Position Look-Up with Linear Interpolation
** Parameters:
**   target_torque_lbf_in - Commanded shaft braking torque in lbf*in (0.0 to 325.0 lbf*in)
** Return:
**   float: Commanded stepper carriage position in mm
*/
static inline float Brake_LUT_TorqueToPositionMm(float target_torque_lbf_in)
{
  if ( target_torque_lbf_in <= 0.0f )
  {
    return 0.0f;
  }
  if ( target_torque_lbf_in >= BRAKE_LUT_MAX_TORQUE_LBF_IN )
  {
    return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  }

  /* Calculate table index and fractional interpolation factor */
  float idx_float = target_torque_lbf_in / BRAKE_LUT_STEP_TORQUE_LBF_IN;
  int idx = (int)idx_float;
  if ( idx >= (BRAKE_LUT_NUM_ENTRIES - 1) )
  {
    return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  }

  float frac = idx_float - (float)idx;
  float p0 = s_brake_torque_to_pos_mm[idx];
  float p1 = s_brake_torque_to_pos_mm[idx + 1];

  return p0 + frac * (p1 - p0);
}

/* Backward-compatible Force Look-Up assuming standard 12-inch nominal forearm
** Parameters:
**   target_force_lbs - Commanded resistance in pounds
** Return:
**   float: Commanded stepper carriage position in mm
*/
static inline float Brake_LUT_ForceToPositionMm(float target_force_lbs)
{
  return Brake_LUT_TorqueToPositionMm(target_force_lbs * 12.0f);
}

#ifdef __cplusplus
}
#endif

#endif /* BRAKE_LUT_H */
