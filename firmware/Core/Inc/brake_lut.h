/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** FlexSense - Calibrated Shaft Torque Kinematics & Look-Up Table (LUT)
** Auto-generated from Dev & Calibration Workstation
*/

#ifndef BRAKE_LUT_H
#define BRAKE_LUT_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

#define BRAKE_SYSTEM_GAIN_LBF_IN_PER_MM   7.86f
#define BRAKE_SLACK_TAKEUP_MM             2.50f
#define BRAKE_LUT_MIN_TORQUE_LBF_IN       0.0f
#define BRAKE_LUT_MAX_TORQUE_LBF_IN       325.0f
#define BRAKE_LUT_STEP_TORQUE_LBF_IN      5.0f
#define BRAKE_LUT_NUM_ENTRIES             66

static const float s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES] = {
     0.000f,  2.185f,  4.370f,  6.554f,  8.739f, 10.924f,
    13.109f, 15.293f, 16.996f, 17.329f, 17.662f, 17.995f,
    18.327f, 18.660f, 18.993f, 19.325f, 19.658f, 19.991f,
    20.618f, 21.254f, 21.890f, 22.526f, 23.161f, 23.797f,
    24.433f, 25.069f, 25.705f, 26.340f, 26.976f, 27.612f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
    28.000f, 28.000f, 28.000f, 28.000f, 28.000f, 28.000f,
};

static inline float Brake_LUT_TorqueToPositionMm(float target_torque_lbf_in)
{
  if ( target_torque_lbf_in <= 0.0f ) return 0.0f;
  if ( target_torque_lbf_in >= BRAKE_LUT_MAX_TORQUE_LBF_IN ) return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  float idx_float = target_torque_lbf_in / BRAKE_LUT_STEP_TORQUE_LBF_IN;
  int idx = (int)idx_float;
  if ( idx >= (BRAKE_LUT_NUM_ENTRIES - 1) ) return s_brake_torque_to_pos_mm[BRAKE_LUT_NUM_ENTRIES - 1];
  float frac = idx_float - (float)idx;
  return s_brake_torque_to_pos_mm[idx] + frac * (s_brake_torque_to_pos_mm[idx + 1] - s_brake_torque_to_pos_mm[idx]);
}

static inline float Brake_LUT_ForceToPositionMm(float target_force_lbs)
{
  return Brake_LUT_TorqueToPositionMm(target_force_lbs * 12.0f);
}

#ifdef __cplusplus
}
#endif

#endif /* BRAKE_LUT_H */
