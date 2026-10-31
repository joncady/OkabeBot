#include <DHT.h>

// Twilio Alfa / Seeed Wio LTE Cat-NB-IoT v1.0, Seeed STM32F4 core 1.2.5.
// Grove yellow signal: DHT11=A6/PA6; Button(P)=D20/PB4; ranger=A4/PA4.
// Pin numbering and switched Grove power match the vendor's board.h.
// USB JSON only: no SIM, cellular SDK, GNSS, storage, identity or actuators.
const uint8_t CLIMATE_PIN = 6;
const uint8_t BUTTON_PIN = 20;
const uint8_t RANGER_PIN = 4;
const uint8_t GROVE_POWER_PIN = 32;
const uint8_t VCCB_ENABLE_PIN = 26;
DHT climate(CLIMATE_PIN, DHT11);
unsigned long lastRange = 0, lastRoom = 0, changedAt = 0;
bool candidate = false, pressed = false;

// This legacy core has no pulseIn(). Bound the entire echo wait to 30 ms.
unsigned long echoMicros() {
  unsigned long started = micros();
  while (digitalRead(RANGER_PIN) == HIGH)
    if (micros() - started >= 30000UL) return 0;
  while (digitalRead(RANGER_PIN) == LOW)
    if (micros() - started >= 30000UL) return 0;
  unsigned long rising = micros();
  while (digitalRead(RANGER_PIN) == HIGH)
    if (micros() - started >= 30000UL) return 0;
  return micros() - rising;
}

void setup() {
  pinMode(GROVE_POWER_PIN, OUTPUT);
  digitalWrite(GROVE_POWER_PIN, HIGH);
  pinMode(VCCB_ENABLE_PIN, OUTPUT);
  digitalWrite(VCCB_ENABLE_PIN, HIGH);
  pinMode(BUTTON_PIN, INPUT); // Grove Button(P) includes its own resistor.
  pinMode(RANGER_PIN, INPUT);
  SerialUSB.begin(115200);
  delay(500);
  climate.begin();
}

void loop() {
  unsigned long now = millis();
  bool sample = digitalRead(BUTTON_PIN) == HIGH;
  if (sample != candidate) { candidate = sample; changedAt = now; }
  if (now - changedAt >= 50) pressed = candidate;
  if (now - lastRange >= 200) {
    lastRange = now;
    // Grove ranger uses one bidirectional signal, unlike the Uno HC-SR04.
    pinMode(RANGER_PIN, OUTPUT);
    digitalWrite(RANGER_PIN, LOW); delayMicroseconds(2);
    digitalWrite(RANGER_PIN, HIGH); delayMicroseconds(10);
    digitalWrite(RANGER_PIN, LOW);
    pinMode(RANGER_PIN, INPUT);
    unsigned long duration = echoMicros();
    unsigned long mm = duration * 343UL / 2000UL;
    SerialUSB.print("{\"sensor\":\"ultrasonic\",\"distance_mm\":");
    if (duration && mm >= 20 && mm <= 4000) SerialUSB.print(mm);
    else SerialUSB.print("null");
    SerialUSB.println("}");
    SerialUSB.print("{\"sensor\":\"button\",\"button_pressed\":");
    SerialUSB.print(pressed ? "true" : "false"); SerialUSB.println("}");
  }
  if (now - lastRoom >= 2500) {
    lastRoom = now;
    float t = climate.readTemperature(), h = climate.readHumidity();
    SerialUSB.print("{\"sensor\":\"room\",\"temperature_c\":");
    if (!isnan(t) && t >= 0 && t <= 50) SerialUSB.print(t, 1);
    else SerialUSB.print("null");
    SerialUSB.print(",\"humidity_percent\":");
    if (!isnan(h) && h >= 0 && h <= 100) SerialUSB.print(h, 1);
    else SerialUSB.print("null");
    SerialUSB.println("}");
  }
}
