#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <math.h>

// ===== WiFi Credentials =====
const char* ssid = "THARINI_EXT";
const char* password = "kodhai1204";
const char* serverURL = "http://192.168.1.7:5000/data";
String patient_id = "p003";

// ===== Pins =====
#define EMG_PIN 34
#define BUZZER_PIN 25

// ===== Constants =====
#define FOG_CONFIRM_TIME   1000
#define REPORT_INTERVAL    2000

// ===== Fixed Thresholds =====
#define EMG_THRESH_SHORT       0.03
#define EMG_THRESH_SUSTAIN     0.10
#define MOTION_LOW             1.5
#define ANGVEL_THRESH          12.0
#define ANGLE_TOLERANCE        18.0

// ===== Variables =====
unsigned long fogStartTime = 0;
bool fogDetected = false;
unsigned long lastReport = 0;
float angleWalk = -15.0;  // average walking pitch from your logs

// ===== Helper: RMS of EMG =====
float computeEMGRMS(int samples = 100) {
  float sumSq = 0;
  for (int i = 0; i < samples; i++) {
    int raw = analogRead(EMG_PIN);
    float volt = raw * 3.3 / 4095.0;
    sumSq += volt * volt;
    delayMicroseconds(500);
  }
  return sqrt(sumSq / samples);
}

// ===== MPU Read =====
bool readMPU(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
  Wire.beginTransmission(0x68);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  Wire.requestFrom(0x68, 14, true);
  if (Wire.available() < 14) return false;

  int16_t raw_ax = (Wire.read() << 8) | Wire.read();
  int16_t raw_ay = (Wire.read() << 8) | Wire.read();
  int16_t raw_az = (Wire.read() << 8) | Wire.read();
  Wire.read(); Wire.read(); // temp
  int16_t raw_gx = (Wire.read() << 8) | Wire.read();
  int16_t raw_gy = (Wire.read() << 8) | Wire.read();
  int16_t raw_gz = (Wire.read() << 8) | Wire.read();

  ax = (raw_ax / 16384.0) * 9.81;
  ay = (raw_ay / 16384.0) * 9.81;
  az = (raw_az / 16384.0) * 9.81;
  gx = raw_gx / 131.0;
  gy = raw_gy / 131.0;
  gz = raw_gz / 131.0;
  return true;
}

// ===== Motion and Pitch =====
float computeLinearAccelMagnitude(float ax, float ay, float az) {
  float g = 9.81;
  float mag = sqrt(ax * ax + ay * ay + az * az);
  return fabs(mag - g);
}

float computePitch(float ax, float ay, float az) {
  return atan2(ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
}

// ===== Smoothing =====
float smoothPitch(float newPitch) {
  static float buf[5];
  static int idx = 0;
  buf[idx] = newPitch;
  idx = (idx + 1) % 5;
  float sum = 0;
  for (int i = 0; i < 5; i++) sum += buf[i];
  return sum / 5.0;
}

// ===== WiFi =====
void connectWiFi() {
  Serial.print("Connecting to WiFi ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

// ===== Send Data =====
void sendToServer(bool fogEvent, float emg, float motion, float angVel, String gaitType) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["patient_id"] = patient_id;
  doc["fog_event"] = fogEvent;
  doc["emg_rms"] = emg;
  doc["motion"] = motion;
  doc["angular_velocity"] = angVel;
  doc["gait_type"] = gaitType;

  String json;
  serializeJson(doc, json);
  int code = http.POST(json);
  if (code > 0)
    Serial.printf("✅ Sent to server (%d)\n", code);
  else
    Serial.println("❌ HTTP failed (no response).");
  http.end();
}

// ===== Setup =====
void setup() {
  Serial.begin(115200);
  Wire.begin();
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  Wire.beginTransmission(0x68);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission(true);

  connectWiFi();
  Serial.println("System Ready ✅");
}

// ===== Main Loop =====
void loop() {
  float ax, ay, az, gx, gy, gz;
  if (!readMPU(ax, ay, az, gx, gy, gz)) return;

  float emg = computeEMGRMS(40);
  float motion = computeLinearAccelMagnitude(ax, ay, az);
  float angVel = sqrt(gx * gx + gy * gy + gz * gz);
  float pitch = smoothPitch(computePitch(ax, ay, az));

  // === Gait Classification ===
  String gait = "Unknown/Transition";
  if (motion > 1.0 && motion <= 1.8 && emg < 0.3) gait = "Normal Gait";
  else if (motion < 0.8 && emg > 0.35) gait = "Freezing of Gait";
  else if (motion < 0.6 && emg > 0.4) gait = "Crouching Gait";
  else if (motion < 1.0 && emg < 0.35) gait = "Antalgic Gait";
  else if (motion >= 1.8 && motion <= 2.5 && emg > 0.35) gait = "Parkinsonian Gait";
  else if (motion < 1.2 && emg > 0.45) gait = "Spastic Gait";
  else if (motion > 2.5 && emg < 0.4) gait = "Steppage Gait";
  else if (motion < 1.4 && emg >= 0.3 && emg <= 0.45) gait = "Waddling Gait";
  else if (motion < 1.2 && emg > 0.5) gait = "Scissors Gait";

  // === FOG Detection ===
  bool still = (motion < MOTION_LOW && angVel < ANGVEL_THRESH);
  bool strongEMG = (emg > EMG_THRESH_SUSTAIN);
  bool angleMatch = fabs(pitch - angleWalk) < ANGLE_TOLERANCE;

  if (strongEMG && still && angleMatch) {
    if (!fogDetected && millis() - fogStartTime > FOG_CONFIRM_TIME) {
      fogDetected = true;
      digitalWrite(BUZZER_PIN, HIGH);
      Serial.println("🚨 FOG DETECTED! Buzzer ON!");
    }
    if (fogStartTime == 0) fogStartTime = millis();
  } else {
    fogStartTime = 0;
    fogDetected = false;
    digitalWrite(BUZZER_PIN, LOW);
  }

  // === Report ===
  if (millis() - lastReport > REPORT_INTERVAL) {
    lastReport = millis();
    Serial.printf("📊 EMG:%.3f Motion:%.3f AngVel:%.2f Pitch:%.1f° Gait:%s FOG:%s\n",
                  emg, motion, angVel, pitch, gait.c_str(), fogDetected ? "YES" : "NO");
    sendToServer(fogDetected, emg, motion, angVel, gait);
  }
}
