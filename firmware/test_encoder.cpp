// =============================================================================
// HIGH-SPEED 4X ENCODER DECODER (STM32F401RE Port Manipulation Version)
// Optimized for LM324 Schmitt Triggers & 2400 CPR Resolution
// =============================================================================

#include <Arduino.h>

// Using PA0 and PA1 (Nucleo pins A0 and A1) because they share the same GPIOA port,
// allowing for a single atomic hardware register read.
#define ENC_A_PIN PA0
#define ENC_B_PIN PA1

volatile long encoderCount = 0;
const float DEG_PER_COUNT = 360.0f / 2400.0f;

// Lookup table for 4X quadrature states
// This is the fastest way to determine direction
static const int8_t enc_states[] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
static uint8_t old_AB = 0;

void handleInterrupt();

void setup() {
  Serial.begin(115200);
  
  pinMode(ENC_A_PIN, INPUT);
  pinMode(ENC_B_PIN, INPUT);

  // Initialize the state so the first tick is accurate.
  // GPIOA->IDR reads the entire 16-bit Input Data Register for Port A.
  // Bits 0 and 1 correspond exactly to PA0 and PA1.
  uint32_t current_PORTA = GPIOA->IDR;
  old_AB = (current_PORTA & 0x03);

  attachInterrupt(digitalPinToInterrupt(ENC_A_PIN), handleInterrupt, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B_PIN), handleInterrupt, CHANGE);

  Serial.println("STM32F401RE GNC-Optimized 4X Decoder Ready.");
  Serial.println("Rotate 360 degrees to verify 2400 ticks...");
}

void loop() {
  static long lastCount = -999;
  
  // Atomic read of the volatile variable
  noInterrupts();
  long currentCount = encoderCount;
  interrupts();

  if (currentCount != lastCount) {
    float angle = currentCount * DEG_PER_COUNT;
    
    Serial.print("Ticks: ");
    Serial.print(currentCount);
    Serial.print(" | Angle: ");
    Serial.println(angle, 2);
    
    lastCount = currentCount;
  }
}

// THE ENGINE: Uses Direct Port Manipulation for zero-latency reading
void handleInterrupt() {
  // Read GPIOA register. This captures BOTH PA0 and PA1 in the exact same clock cycle.
  uint32_t current_PORTA = GPIOA->IDR; 
  uint8_t current_AB = (current_PORTA & 0x03);

  old_AB <<= 2;
  old_AB |= current_AB;
  
  // Update count based on the 16-state quadrature transition table
  encoderCount += enc_states[(old_AB & 0x0F)];
}
