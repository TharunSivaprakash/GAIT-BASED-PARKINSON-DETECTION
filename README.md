StepSafe – EMG & IMU Based Freezing of Gait Detection System

StepSafe is a prototype wearable system designed to detect Freezing of Gait (FOG) by combining muscle activity (EMG) and leg movement (IMU) signals.
The system provides real-time vibration feedback and cloud-based monitoring to assist users during gait freezing events.

This project is currently a proof-of-concept implementation built on a breadboard prototype, validated through controlled self-testing.

📌 Problem Statement

Freezing of Gait is a common symptom in neurological conditions like Parkinson’s disease, where a person intends to walk but their leg fails to move.
Most existing systems rely only on motion sensors, which can cause delayed detection or false alarms.

💡 Key Idea (Core Concept)

StepSafe detects freezing using the principle:

“Muscle is active, but the leg is not moving.”

This is achieved by:

EMG sensor → detects muscle intent

IMU sensor → detects actual leg movement

When muscle activity is detected without corresponding motion for a short duration, the system identifies it as a freezing event.

🧠 System Architecture

Flow:

EMG + IMU → ESP32 → Signal Processing →
Gait Analysis → FOG Detection →
Vibration Feedback + Cloud Logging → Remote Alerts

The architecture diagram is generated programmatically using Python.

⚙️ Hardware Components

ESP32 microcontroller

EMG sensor module (surface electrodes)

IMU sensor (accelerometer + gyroscope)

Vibration motor (neck-mounted cue)

Li-ion battery

Breadboard and jumper wires (prototype stage)

🧪 Prototype Status

Breadboard-based hardware

Fixed to lower leg using tape for testing

Tested on developer under simulated walking and pause conditions

Focused on validating:

Sensor fusion logic

Detection latency

Vibration feedback response

Cloud data transmission

⚠️ Note: This is not a finalized wearable or clinical device.

🔬 Sensor Fusion Algorithm

EMG and IMU data are sampled continuously

Signals are filtered and converted to RMS values

Adaptive thresholds are set using a short calibration phase

Fusion logic:

If EMG_RMS > EMG_threshold AND Motion_RMS < Motion_threshold
for ≥ 0.5 seconds → Freeze Detected


Vibration feedback is triggered

Event is logged to the cloud

This dual-sensor logic reduces false positives compared to IMU-only systems.

🤖 Machine Learning Integration

To improve accuracy and adaptability, StepSafe includes an optional ML layer:

Model: CNN + LSTM

Input: 0.8-second windows of EMG and IMU data

CNN: Extracts short-term signal patterns

LSTM: Learns walking rhythm and temporal gait behavior

Output: Freeze probability (0–1)

If probability > 0.5 for a sustained period, freezing is confirmed.

The ML model runs on the server (Flask) and can be converted to TensorFlow Lite for embedded deployment.

☁️ Cloud & Alert System

Flask server receives sensor data

Firebase Realtime Database stores:

Gait metrics

Freeze events

Session history

Alert logic:

Long freezing events

Fall detection (high acceleration + inactivity)

Notifications can be viewed by caregivers or doctors

📊 Current Results (Prototype Testing)
Metric	Result
Detection Latency	~0.8 seconds
False Alarms	Reduced vs IMU-only
Cloud Upload	Successful
Vibration Response	Immediate & noticeable
Battery Life	~8–10 hours

⚠️ Results are based on single-subject prototype testing and are intended as functional validation only.

🧯 Limitations

Not clinically tested

Single-user validation

Breadboard hardware (not wearable-grade)

EMG signal quality depends on electrode placement

ML model trained on limited data

🚀 Future Work

Miniaturized wearable enclosure

Multi-user data collection

Clinical testing on Parkinson’s patients

On-device ML inference (ESP32 + TensorFlow Lite)

Mobile app integration

Improved fall detection logic

🛡️ Ethics & Safety

Intended for research and educational purposes only

Not a medical device

User consent required for data collection

Secure data transmission via HTTPS
