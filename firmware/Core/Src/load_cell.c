/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: load_cell.c
  * Brief: Implementation skeleton for handle load cell force acquisition.
  ******************************************************************************
  */

#include "load_cell.h"

/* Private Module Variables */
static float s_tare_offset = 0.0f;
static bool  s_is_ready = false;

/**
  * @brief  Initialize load cell ADC / GPIO peripherals and tare calibration.
  * @param  None
  * @retval None
  */
void LoadCell_Init(void)
{
  s_tare_offset = 0.0f;
  s_is_ready = true;
} /* LoadCell_Init() */

/**
  * @brief  Read instantaneous handle contact force in pounds.
  * @param  None
  * @retval float: Measured force in lbs (zeroed against tare offset).
  */
float LoadCell_ReadForceLbs(void)
{
  if ( !s_is_ready )
  {
    return 0.0f;
  }

  /* Placeholder: return calibrated force from hardware interface */
  float raw_force = 0.0f;
  return ( raw_force - s_tare_offset );
} /* LoadCell_ReadForceLbs() */

/**
  * @brief  Tare the load cell to current baseline unloaded state.
  * @param  None
  * @retval None
  */
void LoadCell_Tare(void)
{
  s_tare_offset = 0.0f;
} /* LoadCell_Tare() */

/**
  * @brief  Check if load cell peripheral is initialized and communicating.
  * @param  None
  * @retval bool: True if healthy.
  */
bool LoadCell_IsConnected(void)
{
  return s_is_ready;
} /* LoadCell_IsConnected() */
