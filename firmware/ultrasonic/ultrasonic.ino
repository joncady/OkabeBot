// HC-SR04 on a 5 V Uno: VCC=5V, GND=GND, TRIG=D12, ECHO=D11.
// Serial metadata only. No identity, home/away inference or actuator commands.
const byte TRIGGER_PIN = 12;
const byte ECHO_PIN = 11;
const unsigned long SAMPLE_MS = 200;
unsigned long lastSample = 0;
unsigned long sequence = 0;

void setup() {
  pinMode(TRIGGER_PIN, OUTPUT);
  digitalWrite(TRIGGER_PIN, LOW);
  pinMode(ECHO_PIN, INPUT);
  Serial.begin(115200);
}

void loop() {
  unsigned long now = millis();
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
