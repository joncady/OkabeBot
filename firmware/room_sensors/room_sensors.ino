#include <DHT.h>

// HC-SR04 on a 5 V Uno: VCC=5V, GND=GND, TRIG=D12, ECHO=D11.
// Also: DHT11 DATA=D2; tilt contact=D3/GND; photoresistor divider=A0.
// Serial metadata only. No identity, home/away inference or actuator commands.
const byte TRIGGER_PIN = 12;
const byte ECHO_PIN = 11;
const unsigned long SAMPLE_MS = 200;
unsigned long lastSample = 0;
unsigned long sequence = 0;
const byte LIGHT_PIN = A0;
const bool LIGHT_ENABLED = false;  // No divider installed; do not report a floating ADC.
const byte TILT_PIN = 3;
const byte DHT_PIN = 2;
DHT climate(DHT_PIN, DHT11);
unsigned long lastClimate = 0;
unsigned long tiltChanged = 0;
bool tiltCandidate = false;
bool tiltClosed = false;
float temperatureC = NAN;
float humidityPercent = NAN;

void roomSignals(unsigned long now) {
  bool closed = digitalRead(TILT_PIN) == LOW;
  if (closed != tiltCandidate) { tiltCandidate = closed; tiltChanged = now; }
  if (now - tiltChanged >= 50) tiltClosed = tiltCandidate;
  if (now - lastClimate < 2500) return;
  lastClimate = now;
  temperatureC = climate.readTemperature();
  humidityPercent = climate.readHumidity();
  Serial.print(F("{\"sensor\":\"room\",\"uptime_ms\":"));
  Serial.print(now);
  Serial.print(F(",\"light_raw\":")); if (LIGHT_ENABLED) Serial.print(analogRead(LIGHT_PIN)); else Serial.print(F("null"));
  Serial.print(F(",\"tilt_closed\":")); Serial.print(tiltClosed ? F("true") : F("false"));
  Serial.print(F(",\"temperature_c\":"));
  if (!isnan(temperatureC) && temperatureC >= 0 && temperatureC <= 50) Serial.print(temperatureC, 1);
  else Serial.print(F("null"));
  Serial.print(F(",\"humidity_percent\":"));
  if (!isnan(humidityPercent) && humidityPercent >= 0 && humidityPercent <= 100) Serial.print(humidityPercent, 1);
  else Serial.print(F("null"));
  Serial.println(F("}"));
}

void setup() {
  pinMode(TRIGGER_PIN, OUTPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);
  pinMode(TILT_PIN, INPUT_PULLUP);
  climate.begin();
  Serial.begin(115200);
}

void loop() {
  unsigned long now = millis();
  roomSignals(now);
  if (now - lastSample < SAMPLE_MS) return;
  lastSample = now;
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);
  // Bound a missing echo to 30 ms; never hang the sampling loop.
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000UL);
  unsigned long millimeters = duration * 343UL / 2000UL;
  bool valid = duration > 0 && millimeters >= 20 && millimeters <= 4000;
  Serial.print(F("{\"sensor\":\"ultrasonic\",\"sequence\":"));
  Serial.print(sequence++);
  Serial.print(F(",\"uptime_ms\":"));
  Serial.print(now);
  Serial.print(F(",\"distance_mm\":"));
  if (valid) Serial.print(millimeters); else Serial.print(F("null"));
  Serial.println(F("}"));
}
