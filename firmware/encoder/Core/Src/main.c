/* Texas A&M University
** Electronic Systems Engineering Technology
** ESET-469 Embedded Real Time Software Development
** Author: Squish Therapy
** File: main.c
** --------
** Real-time optical encoder decoding, state machine, and 100 Hz binary
** telemetry packet generation for the FlexSense rehabilitation device.
*/

/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/*
** System State Machine enumeration.
** SYS_STATE_IDLE: Awaiting host command; no transmission.
** SYS_STATE_STREAMING: Streaming 24-byte binary telemetry at 100 Hz.
*/
typedef enum { SYS_STATE_IDLE = 0, SYS_STATE_STREAMING = 1 } SystemState_t;

/*
** Packed 24-byte binary telemetry packet structure.
** Little-Endian layout for ARM Cortex-M and x86 host compatibility.
*/
#pragma pack(push, 1)
typedef struct {
  uint8_t preamble[2];   /* Sync bytes: 0xAA, 0x55                        */
  uint32_t timestamp_ms; /* System uptime from HAL_GetTick() in ms        */
  float angle_deg;       /* Joint angle in degrees from rotary encoder    */
  float velocity_deg_s;  /* Filtered angular velocity in degrees/second   */
  float load_cell;       /* Handle load cell force (reserved, 0.0f)       */
  float motor_iq_a;      /* Motor q-axis current in Amps (reserved, 0.0f) */
  uint16_t crc16;        /* CRC-16-CCITT across bytes 0..21               */
} TelemetryPacket_t;
#pragma pack(pop)

/* Compile-time verification of packed structure size */
_Static_assert(sizeof(TelemetryPacket_t) == 24,
               "TelemetryPacket_t must be exactly 24 bytes!");

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define ENCODER_CPR 2400 /* Counts per revolution (4X mode on 600 PPR) */
#define DEG_PER_COUNT (360.0f / (float)ENCODER_CPR)
#define SERIAL_INTERVAL_MS 10  /* Telemetry interval in ms (100 Hz stream)   */
#define VEL_WINDOW_SIZE 5      /* 5 taps = 40 ms window for smooth derivative */
#define VEL_FILTER_ALPHA 0.25f /* EMA filter coefficient for velocity         */
#define VEL_DEADBAND_DEG_S 0.2f /* Velocity cutoff threshold to snap to zero  */
#define PKT_PREAMBLE_0 0xAA /* First sync byte of telemetry frame         */
#define PKT_PREAMBLE_1 0x55 /* Second sync byte of telemetry frame        */
#define PKT_SIZE_BYTES 24   /* Total binary packet size in bytes          */
#define CMD_BUF_SIZE 32     /* UART ASCII command buffer capacity         */
#define TX_BUF_SIZE 128     /* UART diagnostic string buffer capacity     */
#define UART_TIMEOUT_MS 10  /* Blocking UART transmit timeout (ms)        */
#define UART_STATUS_TIMEOUT_MS                                                 \
  50 /* Status string UART transmit timeout (ms)   */
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim2;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
static volatile SystemState_t sys_state = SYS_STATE_IDLE;
static int32_t last_count = 0;
static float last_angle = 0.0f;
static float filtered_velocity = 0.0f;
static uint32_t last_tick = 0;
static char tx_buf[TX_BUF_SIZE];
static char cmd_buf[CMD_BUF_SIZE];
static uint8_t cmd_idx = 0;

/* Circular history buffer for windowed velocity differentiation */
static int32_t pos_history[VEL_WINDOW_SIZE];
static uint32_t time_history[VEL_WINDOW_SIZE];
static uint8_t hist_idx = 0;
static uint8_t hist_count = 0;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM2_Init(void);
static void MX_USART2_UART_Init(void);

/* USER CODE BEGIN PFP */
static void Encoder_Start(void);
static int32_t Encoder_Read(void);
static void Serial_SendLine(const char *str);
static void Process_Serial_Commands(void);
static void Execute_Command(const char *cmd);
static uint16_t Compute_CRC16(const uint8_t *data, size_t length);
static void Velocity_Reset(int32_t initial_count, uint32_t initial_tick);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/*
** Application entry point.
** Parameters:
**   void
** Return:
**   int (never returns in embedded context)
** Notes:
**   Initializes peripherals, starts encoder, and enters real-time execution
* loop.
*/
int main(void) {
  /* Reset of all peripherals, Initializes the Flash interface and Systick. */
  HAL_Init();

  /* Configure the system clock */
  SystemClock_Config();

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_USART2_UART_Init();

  /* USER CODE BEGIN 2 */
  /* Start TIM2 in hardware encoder mode and initialize position to zero */
  Encoder_Start();
  __HAL_TIM_SET_COUNTER(&htim2, 0);

  /* Send startup banner and protocol description */
  Serial_SendLine("\r\n=== STM32F401RE Encoder Binary Protocol Ready ===\r\n");
  Serial_SendLine("Commands: START, STOP, ZERO, STATUS\r\n");
  Serial_SendLine("Packet: 24B [0xAA 0x55, time_u32, ang_f, vel_f, load_f, "
                  "iq_f, crc16_u16]\r\n");

  sys_state = SYS_STATE_IDLE;
  last_tick = HAL_GetTick();
  Velocity_Reset(0, last_tick);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1) /* infinite loop */
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    /* 1. Process any incoming serial commands from GUI / host */
    Process_Serial_Commands();

    /* 2. Periodic telemetry state machine tick */
    uint32_t now = HAL_GetTick();

    if ( (now - last_tick) >= SERIAL_INTERVAL_MS )
    {
      int32_t count = Encoder_Read();
      float angle = (float)count * DEG_PER_COUNT;

      /* Update circular history buffer for windowed velocity differentiation */
      pos_history[hist_idx] = count;
      time_history[hist_idx] = now;
      hist_idx = (uint8_t)( (hist_idx + 1) % VEL_WINDOW_SIZE );
      if ( hist_count < VEL_WINDOW_SIZE )
      {
        hist_count++;
      }

      if ( hist_count > 1 )
      {
        /* Oldest sample is at current hist_idx when buffer full, else at index 0 */
        uint8_t oldest_idx = (hist_count < VEL_WINDOW_SIZE) ? 0 : hist_idx;
        int32_t delta_count = count - pos_history[oldest_idx];
        float dt = (float)(now - time_history[oldest_idx]) / 1000.0f;

        if ( dt > 0.0f )
        {
          float raw_velocity = ( (float)delta_count * DEG_PER_COUNT ) / dt;

          /* Exponential Moving Average low-pass filter for smooth velocity */
          filtered_velocity += VEL_FILTER_ALPHA * (raw_velocity - filtered_velocity);

          /* Snap cleanly to zero when position is stationary across window */
          if ( (delta_count == 0) && (fabsf(filtered_velocity) < VEL_DEADBAND_DEG_S) )
          {
            filtered_velocity = 0.0f;
          }
        }
      }

      /* In STREAMING state, transmit packed 24-byte binary telemetry packet */
      if ( sys_state == SYS_STATE_STREAMING )
      {
        TelemetryPacket_t pkt;
        pkt.preamble[0] = PKT_PREAMBLE_0;
        pkt.preamble[1] = PKT_PREAMBLE_1;
        pkt.timestamp_ms = now;
        pkt.angle_deg = angle;
        pkt.velocity_deg_s = filtered_velocity;
        pkt.load_cell = 0.0f;
        pkt.motor_iq_a = 0.0f;
        pkt.crc16 = Compute_CRC16((const uint8_t *)&pkt, sizeof(pkt) - sizeof(pkt.crc16));

        HAL_UART_Transmit(&huart2, (uint8_t *)&pkt, (uint16_t)sizeof(pkt), UART_TIMEOUT_MS);
      }

      last_count = count;
      last_angle = angle;
      last_tick = now;
    } /* if ( (now - last_tick) >= SERIAL_INTERVAL_MS ) */
  } /* while ( 1 ) */
  /* USER CODE END 3 */
} /* main() */

/*
** System Clock Configuration.
** Parameters:
**   void
** Return:
**   void
** Notes:
**   Configures HCLK to 84 MHz via PLL with HSI oscillator.
*/
void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 84;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 4;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
    Error_Handler();
  }
} /* SystemClock_Config() */

/*
** TIM2 Hardware Quadrature Encoder Initialization.
** Parameters:
**   void
** Return:
**   void
** Notes:
**   Configures TIM2 in 4X encoder mode on TI1 and TI2 with input filtering.
*/
static void MX_TIM2_Init(void) {
  TIM_Encoder_InitTypeDef sConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 4294967295;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  sConfig.EncoderMode = TIM_ENCODERMODE_TI12;
  sConfig.IC1Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC1Filter = 15;
  sConfig.IC2Polarity = TIM_ICPOLARITY_RISING;
  sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
  sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
  sConfig.IC2Filter = 15;
  if (HAL_TIM_Encoder_Init(&htim2, &sConfig) != HAL_OK) {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK) {
    Error_Handler();
  }
} /* MX_TIM2_Init() */

/*
** USART2 Initialization.
** Parameters:
**   void
** Return:
**   void
** Notes:
**   Configures USART2 at 115200 baud, 8N1 over ST-Link Virtual COM Port.
*/
static void MX_USART2_UART_Init(void) {
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK) {
    Error_Handler();
  }
} /* MX_USART2_UART_Init() */

/*
** GPIO Port Clock Initialization.
** Parameters:
**   void
** Return:
**   void
*/
static void MX_GPIO_Init(void) {
  __HAL_RCC_GPIOA_CLK_ENABLE();
} /* MX_GPIO_Init() */

/* USER CODE BEGIN 4 */

/*
** Start TIM2 in Hardware Encoder Mode on both channels (TI1 and TI2).
** Parameters:
**   void
** Return:
**   void
*/
static void Encoder_Start(void) {
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);
} /* Encoder_Start() */

/*
** Read current 32-bit hardware encoder counter value.
** Parameters:
**   void
** Return:
**   int32_t - Signed 32-bit encoder tick count.
*/
static int32_t Encoder_Read(void) {
  return (int32_t)__HAL_TIM_GET_COUNTER(&htim2);
} /* Encoder_Read() */

/*
** Transmit null-terminated string over USART2.
** Parameters:
**   str - pointer to string buffer
** Return:
**   void
*/
static void Serial_SendLine(const char *str) {
  HAL_UART_Transmit(&huart2, (const uint8_t *)str, (uint16_t)strlen(str), 100);
} /* Serial_SendLine() */

/*
** Non-blocking check for incoming characters on USART2.
** Buffers characters until newline/carriage-return, then dispatches command.
** Parameters:
**   void
** Return:
**   void
*/
static void Process_Serial_Commands(void) {
  /* Clear overrun error flag if active */
  if (__HAL_UART_GET_FLAG(&huart2, UART_FLAG_ORE)) {
    __HAL_UART_CLEAR_OREFLAG(&huart2);
  }

  while (__HAL_UART_GET_FLAG(&huart2, UART_FLAG_RXNE)) {
    char c = (char)(huart2.Instance->DR & 0xFF);

    if ((c == '\r') || (c == '\n')) {
      if (cmd_idx > 0) {
        cmd_buf[cmd_idx] = '\0';
        Execute_Command(cmd_buf);
        cmd_idx = 0;
      }
    } else {
      if (cmd_idx < (CMD_BUF_SIZE - 1)) {
        /* Ignore leading whitespace */
        if (!((cmd_idx == 0) && ((c == ' ') || (c == '\t')))) {
          cmd_buf[cmd_idx++] = c;
        }
      } else {
        cmd_idx = 0; /* Buffer overflow protection: reset index */
      }
    }
  } /* while ( RXNE ) */
} /* Process_Serial_Commands() */

/*
** State machine command dispatcher.
** Parameters:
**   cmd - pointer to ASCII command string
** Return:
**   void
** Notes:
**   Supported commands: START, STOP, ZERO, STATUS.
*/
static void Execute_Command(const char *cmd)
{
  if ( (strcasecmp(cmd, "START") == 0) || (strcasecmp(cmd, "S") == 0) )
  {
    sys_state = SYS_STATE_STREAMING;
    last_tick = HAL_GetTick();
    Velocity_Reset(Encoder_Read(), last_tick);
    Serial_SendLine("ACK:START\r\n");
  }
  else if ( (strcasecmp(cmd, "STOP") == 0) || (strcasecmp(cmd, "P") == 0) )
  {
    sys_state = SYS_STATE_IDLE;
    Serial_SendLine("ACK:STOP\r\n");
  }
  else if ( (strcasecmp(cmd, "ZERO") == 0) || (strcasecmp(cmd, "Z") == 0) )
  {
    __HAL_TIM_SET_COUNTER(&htim2, 0);
    last_count = 0;
    last_angle = 0.0f;
    Velocity_Reset(0, HAL_GetTick());
    Serial_SendLine("ACK:ZERO\r\n");
  } else if ((strcasecmp(cmd, "STATUS") == 0) || (strcasecmp(cmd, "?") == 0)) {
    int len = snprintf(
        tx_buf, sizeof(tx_buf), "STATUS:STATE=%s,TICKS=%ld,ANGLE=%.2f\r\n",
        (sys_state == SYS_STATE_STREAMING) ? "STREAMING" : "IDLE",
        (long)Encoder_Read(), (float)Encoder_Read() * DEG_PER_COUNT);
    if (len > 0) {
      HAL_UART_Transmit(&huart2, (const uint8_t *)tx_buf, (uint16_t)len,
                        UART_STATUS_TIMEOUT_MS);
    }
  } else {
    Serial_SendLine("ERR:UNKNOWN_CMD\r\n");
  }
} /* Execute_Command() */

/*
** Compute CRC-16-CCITT (polynomial 0x1021, initial value 0xFFFF).
** Parameters:
**   data   - pointer to byte buffer
**   length - number of bytes to checksum
** Return:
**   uint16_t - calculated 16-bit CRC checksum
*/
static uint16_t Compute_CRC16(const uint8_t *data, size_t length) {
  uint16_t crc = 0xFFFF;

  for (size_t i = 0; i < length; i++) {
    crc ^= ((uint16_t)data[i] << 8);

    for (uint8_t bit = 0; bit < 8; bit++) {
      if (crc & 0x8000) {
        crc = (crc << 1) ^ 0x1021;
      } else {
        crc = crc << 1;
      }
    } /* for bit */
  } /* for i */

  return crc;
} /* Compute_CRC16() */

/*
** Reset velocity estimation ring buffer and filtered state.
** Parameters:
**   initial_count - starting encoder count to pre-fill
**   initial_tick  - timestamp of reset in milliseconds
** Return:
**   void
*/
static void Velocity_Reset(int32_t initial_count, uint32_t initial_tick)
{
  for ( uint8_t i = 0; i < VEL_WINDOW_SIZE; i++ )
  {
    pos_history[i] = initial_count;
    time_history[i] = initial_tick;
  }
  hist_idx = 0;
  hist_count = 0;
  filtered_velocity = 0.0f;
} /* Velocity_Reset() */

/* USER CODE END 4 */

/*
** Error Handler executed on peripheral initialization failure.
** Parameters:
**   void
** Return:
**   void
*/
void Error_Handler(void) {
  /* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  while (1) /* trap execution on fatal error */
  {
  }
  /* USER CODE END Error_Handler_Debug */
} /* Error_Handler() */

#ifdef USE_FULL_ASSERT
/*
** Reports the name of the source file and line number on failed assert.
** Parameters:
**   file - pointer to source file name
**   line - assert line number
** Return:
**   void
*/
void assert_failed(uint8_t *file, uint32_t line) {
  /* USER CODE BEGIN 6 */
  /* USER CODE END 6 */
} /* assert_failed() */
#endif /* USE_FULL_ASSERT */
