/**
  ******************************************************************************
  * Texas A&M University
  * Electronic Systems Engineering Technology
  * ESET-469 Embedded Real Time Software Development
  * Author: Squish Therapy
  * File: load_cell.h
  * Brief: Interface for handle load cell force acquisition and calibration.
  ******************************************************************************
  */

#ifndef LOAD_CELL_H
#define LOAD_CELL_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

/* Public Function Prototypes */
void  LoadCell_Init(void);
float LoadCell_ReadForceLbs(void);
void  LoadCell_Tare(void);
bool  LoadCell_IsConnected(void);

#ifdef __cplusplus
}
#endif

#endif /* LOAD_CELL_H */
