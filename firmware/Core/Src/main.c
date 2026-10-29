/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: main.c
** --------
** Executive state machine and real-time scheduler for FlexSense.
*/
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "tim.h"
#include "gpio.h"
#include "usb_device.h"
#include "i2c.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "encoder.h"
#include "telemetry.h"
#include "load_cell.h"
#include "motor.h"
#include "spo2.h"
#include "usbd_core.h"
#include <stdio.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef enum
{
  SYS_STATE_IDLE = 0,
  SYS_STATE_STREAMING
} SystemState_t;
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define TELEMETRY_INTERVAL_MS 10
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
static SystemState_t s_sys_state = SYS_STATE_IDLE;
static uint32_t      s_last_tick = 0;
static uint32_t      s_stream_start_tick = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */
  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */
  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_I2C1_Init();
  MX_I2C3_Init();
  MX_USB_DEVICE_Init();
  /* Note: USART2 is initialized in Single-Wire Half-Duplex mode inside Motor_Init() -> TMC2209_Init() */

  /* USER CODE BEGIN 2 */
  /* Initialize all modular hardware and communication subsystems */
  Encoder_Init(&htim2);
  Telemetry_Init((UART_HandleTypeDef *)0); /* Telemetry uses USB CDC; USART2 is dedicated to TMC2209 */
  LoadCell_Init();
  Motor_Init();
  SpO2_Init();

  Telemetry_SendAck("\r\n=== STM32F411CE FlexSense Embedded System Ready ===\r\n");
  Telemetry_SendAck("Commands: START, STOP, ZERO, STATUS, RES <lbs>, CURR <mA>, TMC, SPO2, HOME\r\n");
  /* Indicate boot by turning ON LED (PC13 active-low) */
  HAL_GPIO_WritePin(LED_PIN_GPIO_Port, LED_PIN_Pin, GPIO_PIN_RESET);

  /* Start in IDLE state by default so USB is quiet until host connects and sends START */
  s_sys_state = SYS_STATE_IDLE;
  s_last_tick = HAL_GetTick();
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while ( 1 )
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    /* 1. Poll incoming serial commands from GUI / host */
    SystemCommand_t cmd = Telemetry_PollCommand();

    switch ( cmd )
    {
      case CMD_START:
        s_sys_state = SYS_STATE_STREAMING;
        Encoder_Zero();
        LoadCell_Tare();
        s_stream_start_tick = HAL_GetTick();
        Telemetry_SendAck("ACK:START\r\n");
        break;

      case CMD_STOP:
        s_sys_state = SYS_STATE_IDLE;
        Motor_SetResistanceLbs(0.0f);
        Telemetry_SendAck("ACK:STOP\r\n");
        break;

      case CMD_SET_RESISTANCE:
        {
          float r = Telemetry_GetCommandParam();
          Motor_SetResistanceLbs(r);
          char ack[48];
          snprintf(ack, sizeof(ack), "ACK:RES:%.2f\r\n", r);
          Telemetry_SendAck(ack);
        }
        break;

      case CMD_ZERO:
        Encoder_Zero();
        LoadCell_Tare();
        Telemetry_SendAck("ACK:ZERO\r\n");
        break;

      case CMD_STATUS:
        {
          char st_msg[128];
          LoadCell_Diagnose(st_msg, sizeof(st_msg));
          Telemetry_SendAck(st_msg);
        }
        break;

      case CMD_TMC:
        {
          char tmc_msg[256];
          if ( Motor_IsTMC2209Online() )
          {
            TMC2209_Status_t st;
            Motor_GetTMC2209Status(&st);
            uint32_t ifcnt = 0, gconf = 0, gstat = 0, ioin = 0, ihold_irun = 0, drv_status = 0;
            TMC2209_ReadRegister(TMC2209_REG_IFCNT, &ifcnt);
            TMC2209_ReadRegister(TMC2209_REG_GCONF, &gconf);
            TMC2209_ReadRegister(TMC2209_REG_GSTAT, &gstat);
            TMC2209_ReadRegister(TMC2209_REG_IOIN, &ioin);
            TMC2209_ReadRegister(TMC2209_REG_IHOLD_IRUN, &ihold_irun);
            TMC2209_ReadRegister(TMC2209_REG_DRV_STATUS, &drv_status);

            snprintf(tmc_msg, sizeof(tmc_msg),
                     "ACK:TMC:ONLINE=1,IFCNT=%lu,GCONF=0x%lX,GSTAT=0x%lX,IOIN=0x%lX,IHOLD=0x%lX,DRV=0x%lX,SG=%u,CS=%u,OTPW=%d,FAULT=%d,STST=%d\r\n",
                     (unsigned long)ifcnt, (unsigned long)gconf, (unsigned long)gstat,
                     (unsigned long)ioin, (unsigned long)ihold_irun, (unsigned long)drv_status,
                     st.stallguard_result, st.current_scale,
                     st.over_temperature_warning ? 1 : 0,
                     st.driver_fault ? 1 : 0,
                     st.standstill ? 1 : 0);
          }
          else
          {
            TMC2209_GetDiagnostic(tmc_msg, sizeof(tmc_msg));
          }
          Telemetry_SendAck(tmc_msg);
        }
        break;

      case CMD_SPO2:
        {
          char spo2_msg[128];
          SpO2_Diagnose(spo2_msg, sizeof(spo2_msg));
          Telemetry_SendAck(spo2_msg);
        }
        break;

      case CMD_SET_CURRENT:
        {
          uint16_t current_ma = (uint16_t)Telemetry_GetCommandParam();
          if ( current_ma < 100 ) current_ma = 100;
          if ( current_ma > 2000 ) current_ma = 2000;
          bool ok = Motor_SetDriverCurrent(current_ma, 50);
          char curr_ack[64];
          snprintf(curr_ack, sizeof(curr_ack), "ACK:CURR:%u_MA:%s\r\n", current_ma, ok ? "OK" : "ERR");
          Telemetry_SendAck(curr_ack);
        }
        break;

      case CMD_HOME:
        {
          bool ok = Motor_Home();
          char home_ack[96];
          snprintf(home_ack, sizeof(home_ack), "ACK:HOME:%s,%s,CLEAR=5MM,POS=0.0\r\n",
                   ok ? "OK" : "TIMEOUT", Motor_GetHomingDiagnostic());
          Telemetry_SendAck(home_ack);
        }
        break;

      case CMD_TARE:
        {
          bool ok = Motor_Home();
          Encoder_Zero();
          LoadCell_Tare();
          char tare_ack[96];
          snprintf(tare_ack, sizeof(tare_ack), "ACK:TARE:%s,%s,CLEAR=5MM,POS=0.0\r\n",
                   ok ? "OK" : "TIMEOUT", Motor_GetHomingDiagnostic());
          Telemetry_SendAck(tare_ack);
        }
        break;

      case CMD_SET_HOMETHR:
        {
          uint8_t thrs = (uint8_t)Telemetry_GetCommandParam();
          Motor_SetHomingStallGuardThreshold(thrs);
          char thr_ack[64];
          snprintf(thr_ack, sizeof(thr_ack), "ACK:HOMETHR:%u\r\n", thrs);
          Telemetry_SendAck(thr_ack);
        }
        break;

      case CMD_SET_HOMESPEED:
        {
          uint32_t speed = (uint32_t)Telemetry_GetCommandParam();
          Motor_SetHomingSpeedUs(speed);
          char spd_ack[64];
          snprintf(spd_ack, sizeof(spd_ack), "ACK:HOMESPEED:%lu\r\n", (unsigned long)speed);
          Telemetry_SendAck(spd_ack);
        }
        break;

      case CMD_SET_HOMECURR:
        {
          uint16_t curr = (uint16_t)Telemetry_GetCommandParam();
          Motor_SetHomingCurrentMa(curr);
          char curr_ack[64];
          snprintf(curr_ack, sizeof(curr_ack), "ACK:HOMECURR:%u\r\n", curr);
          Telemetry_SendAck(curr_ack);
        }
        break;

      case CMD_DFU:
        {
          Telemetry_SendAck("ACK:DFU:REBOOTING_TO_BOOTLOADER\r\n");
          HAL_Delay(100);
          extern USBD_HandleTypeDef hUsbDeviceFS;
          USBD_Stop(&hUsbDeviceFS);
          USBD_DeInit(&hUsbDeviceFS);
          HAL_Delay(50);
          HAL_RCC_DeInit();
          SysTick->CTRL = 0;
          SysTick->LOAD = 0;
          SysTick->VAL = 0;
          __disable_irq();
          __HAL_RCC_SYSCFG_CLK_ENABLE();
          SYSCFG->MEMRMP = 0x01;
          uint32_t JumpAddress = *(__IO uint32_t*)(0x1FFF0004);
          void (*SysMemBootJump)(void) = (void (*)(void))JumpAddress;
          __set_MSP(*(__IO uint32_t*)0x1FFF0000);
          SysMemBootJump();
          while(1);
        }
        break;

      case CMD_NONE:
      default:
        break;
    }

    /* 2. Run non-blocking stepper pulse engine (checked on every loop iteration) */
    Motor_StepTask();

    /* 3. Periodic 10ms real-time control & telemetry loop */
    uint32_t now = HAL_GetTick();

    if ( (now - s_last_tick) >= TELEMETRY_INTERVAL_MS )
    {
      s_last_tick = now;

      /* Update kinematics differentiation */
      Encoder_UpdateVelocity(now);

      /* Always sample load cell so s_last_raw and tare baseline remain fresh in all states */
      float current_force = LoadCell_ReadForceLbs();

      /* Update Series Elastic Actuator dynamic brake controller (100 Hz, dt = 0.010 s) */
      Motor_UpdateControl(current_force, Encoder_GetVelocityDegS(), 0.010f);

      /* Update MAX30102 pulse oximeter acquisition */
      SpO2_Update();

      /* Heartbeat LED: toggle every 500ms to indicate healthy execution */
      static uint32_t s_led_tick = 0;
      if ( (now - s_led_tick) >= 500 )
      {
        s_led_tick = now;
        HAL_GPIO_TogglePin(LED_PIN_GPIO_Port, LED_PIN_Pin);
      }

      /* In STREAMING state, transmit 28-byte binary telemetry frame */
      if ( s_sys_state == SYS_STATE_STREAMING )
      {
        TelemetryPacket_t pkt;
        pkt.timestamp_ms   = now - s_stream_start_tick;
        pkt.angle_deg      = Encoder_GetAngleDeg();
        pkt.velocity_deg_s = Encoder_GetVelocityDegS();
        pkt.load_cell      = current_force;
        pkt.motor_iq_a     = Motor_GetIqCurrent();
        pkt.spo2           = SpO2_ReadPercent();

        Telemetry_SendPacket(&pkt);
      }
    }
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 25;
  RCC_OscInitStruct.PLL.PLLN = 192;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK)
  {
    Error_Handler();
  }
}



/* USER CODE BEGIN 4 */
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
