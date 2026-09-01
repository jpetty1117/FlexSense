// =============================================================================
// HIGH-SPEED 4X ENCODER DECODER (Port Manipulation Version)
// Optimized for LM324 Schmitt Triggers & 2400 CPR Resolution
// =============================================================================

#include <Arduino.h>

// Pins 2 and 3 are on Port D for Uno/Nano/Mega
#define ENC_A_PIN 2
#define ENC_B_PIN 3

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

  // Initialize the state so the first tick is accurate
  // PIND reads all of Port D; we shift and mask to get bits for Pins 2 & 3
  old_AB = (PIND >> 2) & 0x03;

  attachInterrupt(digitalPinToInterrupt(ENC_A_PIN), handleInterrupt, CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B_PIN), handleInterrupt, CHANGE);

  Serial.println(F("GNC-Optimized 4X Decoder Ready."));
  Serial.println(F("Rotate 360 degrees to verify 2400 ticks..."));
}

void loop() {
  static long lastCount = -999;
  
  // Atomic read of the volatile variable
  noInterrupts();
  long currentCount = encoderCount;
  interrupts();

  if (currentCount != lastCount) {
    float angle = currentCount * DEG_PER_COUNT;
    
    Serial.print(F("Ticks: "));
    Serial.print(currentCount);
    Serial.print(F(" | Angle: "));
    Serial.println(angle, 2);
    
    lastCount = currentCount;
  }
}

// THE ENGINE: Uses Direct Port Manipulation for zero-latency reading
void handleInterrupt() {
  // Read Port D (Pins 0-7). Pins 2 & 3 are bits 2 & 3.
  // This captures BOTH A and B in the exact same clock cycle.
  uint8_t current_PIND = PIND; 
  uint8_t current_AB = (current_PIND >> 2) & 0x03;

  old_AB <<= 2;
  old_AB |= current_AB;
  
  // Update count based on the 16-state quadrature transition table
  encoderCount += enc_states[(old_AB & 0x0F)];
}
