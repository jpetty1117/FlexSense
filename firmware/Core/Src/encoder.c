/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: encoder.c
  * Brief: Implementation of rotary encoder kinematics & windowed velocity filter.
  ******************************************************************************
  */

#include "encoder.h"
#include <math.h>

/* Private Constants */
#define VEL_WINDOW_SIZE         5
#define VEL_FILTER_ALPHA        0.25f
#define VEL_DEADBAND_DEG_S      0.5f

/* Private Module Variables */
static TIM_HandleTypeDef *s_htim = NULL;
static int32_t            s_pos_history[VEL_WINDOW_SIZE];
static uint32_t           s_time_history[VEL_WINDOW_SIZE];
static uint8_t            s_hist_idx = 0;
static uint8_t            s_hist_count = 0;
static float              s_filtered_velocity = 0.0f;

/* Private Function Prototypes */
static void Velocity_Reset(int32_t initial_count, uint32_t initial_tick);

/**
  * @brief  Initialize hardware timer in encoder mode and zero state buffers.
  * @param  htim: Pointer to TIM_HandleTypeDef configured in encoder mode.
  * @retval None
  */
void Encoder_Init(TIM_HandleTypeDef *htim)
{
  s_htim = htim;

  if ( s_htim != NULL )
  {
    HAL_TIM_Encoder_Start(s_htim, TIM_CHANNEL_ALL);
    __HAL_TIM_SET_COUNTER(s_htim, 0);
  }

  Velocity_Reset(0, HAL_GetTick());
} /* Encoder_Init() */

/**
  * @brief  Read the current signed 32-bit encoder hardware tick count.
  * @param  None
  * @retval int32_t: Signed encoder count.
  */
int32_t Encoder_GetCount(void)
{
  if ( s_htim != NULL )
  {
    return (int32_t)__HAL_TIM_GET_COUNTER(s_htim);
  }
  return 0;
} /* Encoder_GetCount() */

/**
  * @brief  Calculate absolute joint angle in degrees from encoder count.
  * @param  None
  * @retval float: Joint angle in degrees.
  */
float Encoder_GetAngleDeg(void)
{
  int32_t count = Encoder_GetCount();
  return ( (float)count * ENCODER_DEG_PER_COUNT );
} /* Encoder_GetAngleDeg() */

/**
  * @brief  Update 40ms sliding window velocity difference and EMA filter.
  * @param  now_ms: Current system timestamp in milliseconds.
  * @retval None
  */
void Encoder_UpdateVelocity(uint32_t now_ms)
{
  int32_t count = Encoder_GetCount();

  /* Append current sample to circular sliding history buffer */
  s_pos_history[s_hist_idx] = count;
  s_time_history[s_hist_idx] = now_ms;
  s_hist_idx = (uint8_t)( (s_hist_idx + 1) % VEL_WINDOW_SIZE );

  if ( s_hist_count < VEL_WINDOW_SIZE )
  {
    s_hist_count++;
  }

  if ( s_hist_count > 1 )
  {
    /* Oldest sample is at current hist_idx when full, else at index 0 */
    uint8_t oldest_idx = (s_hist_count < VEL_WINDOW_SIZE) ? 0 : s_hist_idx;
    int32_t delta_count = count - s_pos_history[oldest_idx];
    float dt = (float)(now_ms - s_time_history[oldest_idx]) / 1000.0f;

    if ( dt > 0.0f )
    {
      float raw_velocity = ( (float)delta_count * ENCODER_DEG_PER_COUNT ) / dt;

      /* Low-pass Exponential Moving Average filter */
      s_filtered_velocity += VEL_FILTER_ALPHA * (raw_velocity - s_filtered_velocity);

      /* Zero deadband snapping */
      if ( (delta_count == 0) && (fabsf(s_filtered_velocity) < VEL_DEADBAND_DEG_S) )
      {
        s_filtered_velocity = 0.0f;
      }
    }
  }
} /* Encoder_UpdateVelocity() */

/**
  * @brief  Get filtered angular velocity in degrees per second.
  * @param  None
  * @retval float: Filtered velocity in deg/s.
  */
float Encoder_GetVelocityDegS(void)
{
  return s_filtered_velocity;
} /* Encoder_GetVelocityDegS() */

/**
  * @brief  Zero the encoder hardware counter and flush velocity filter history.
  * @param  None
  * @retval None
  */
void Encoder_Zero(void)
{
  if ( s_htim != NULL )
  {
    __HAL_TIM_SET_COUNTER(s_htim, 0);
  }
  Velocity_Reset(0, HAL_GetTick());
} /* Encoder_Zero() */

/**
  * @brief  Helper to flush circular velocity history buffer.
  * @param  initial_count: Starting count value.
  * @param  initial_tick: Starting system tick.
  * @retval None
  */
static void Velocity_Reset(int32_t initial_count, uint32_t initial_tick)
{
  for ( uint8_t i = 0; i < VEL_WINDOW_SIZE; i++ )
  {
    s_pos_history[i] = initial_count;
    s_time_history[i] = initial_tick;
  }
  s_hist_idx = 0;
  s_hist_count = 0;
  s_filtered_velocity = 0.0f;
} /* Velocity_Reset() */
