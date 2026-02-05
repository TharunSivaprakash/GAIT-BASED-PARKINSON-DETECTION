from flask import Flask, request, render_template, jsonify
from datetime import datetime, timedelta
import sqlite3, os, json, time, requests
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "stepsafe_secret_key_2024"

FIREBASE_BASE = "https://cloud-dbba7-default-rtdb.firebaseio.com"
DB_NAME = "fog_data.db"
BUFFER_MAX = 600

buffers = defaultdict(lambda: {"times": [], "emg": [], "motion": [], "statuses": [], "meta": {}})


# ===== Initialize Database =====
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS fog_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            name TEXT,
            age INTEGER,
            device_id TEXT,
            time_iso TEXT,
            emg REAL,
            motion REAL,
            gait_type TEXT,
            fog_event INTEGER,
            raw_json TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS fog_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            name TEXT,
            episode_start TEXT,
            episode_end TEXT,
            duration_s REAL,
            avg_emg REAL,
            avg_motion REAL,
            gait_type TEXT,
            reason TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialization completed")


init_db()


# ===== Firebase Integration =====
def push_to_firebase(patient_id, data_type, data):
    try:
        if data_type == "fog_episode":
            url = f"{FIREBASE_BASE}/patients/{patient_id}/fog_episodes.json"
        elif data_type == "profile":
            url = f"{FIREBASE_BASE}/patients/{patient_id}/profile.json"
        else:
            url = f"{FIREBASE_BASE}/patients/{patient_id}/readings.json"
        r = requests.post(url, json=data, timeout=10)
        print(f"Firebase {data_type} push: {r.status_code}")
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"Firebase push error: {e}")
        return False


# ===== Classify Gait =====
def classify_gait(emg, motion, gait_type):
    if "Freezing" in gait_type:
        return "Freezing of Gait (FOG)", "Muscles are active but motion is minimal, indicating freezing."
    elif "Crouching" in gait_type:
        return "Crouching Gait", "High EMG but low motion shows bent posture."
    elif "Antalgic" in gait_type:
        return "Antalgic Gait", "Low EMG and low motion suggests avoidance of pain."
    elif "Parkinsonian" in gait_type:
        return "Parkinsonian Gait", "Fast but short steps due to muscle rigidity."
    elif "Spastic" in gait_type:
        return "Spastic Gait", "High EMG with limited motion due to stiff muscles."
    elif "Steppage" in gait_type:
        return "Steppage Gait", "High leg lift with reduced EMG."
    elif "Waddling" in gait_type:
        return "Waddling Gait", "Hip weakness causing lateral movement."
    elif "Scissors" in gait_type:
        return "Scissors Gait", "Legs cross due to tight adductors."
    else:
        return "Normal Gait", "Regular movement pattern."


# ===== Update Buffer =====
def update_buffer(patient_id, emg, motion, status, meta):
    b = buffers[patient_id]
    b["times"].append(time.time())
    b["emg"].append(float(emg))
    b["motion"].append(float(motion))
    b["statuses"].append(status)
    if meta:
        b["meta"] = meta
    b["meta"]["session_time_iso"] = datetime.utcnow().isoformat() + "Z"
    for k in ("times", "emg", "motion", "statuses"):
        if len(b[k]) > BUFFER_MAX:
            b[k].pop(0)


# ===== Dashboard =====
@app.route("/")
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT patient_id, name, episode_start, episode_end, duration_s, gait_type, avg_emg, avg_motion, reason
        FROM fog_episodes ORDER BY episode_start DESC LIMIT 50
    """)
    data = c.fetchall()
    conn.close()

    fog_episodes = [
        {
            "patient_id": d[0],
            "name": d[1],
            "start": d[2],
            "end": d[3],
            "duration": d[4],
            "gait_type": d[5],
            "avg_emg": d[6],
            "avg_motion": d[7],
            "gait_reason": d[8]
        } for d in data
    ]

    patients_data = {}
    for pid, b in buffers.items():
        if b["meta"].get("name"):
            patients_data[pid] = b["meta"]

    return render_template("dashboard.html", patients_data=patients_data, fog_episodes=fog_episodes)


# ===== Data Endpoint =====
@app.route("/data", methods=["POST"])
def receive_data():
    try:
        payload = request.get_json(force=True)
        patient_id = payload.get("patient_id", "p003")
        name = "Test Patient"
        age = 45
        device_id = "esp32_003"
        emg = float(payload.get("emg_rms", 0))
        motion = float(payload.get("motion", 0))
        gait_type = payload.get("gait_type", "Unknown")
        fog_event = payload.get("fog_event", False)

        print(f"Data from {patient_id}: EMG={emg:.3f}, Motion={motion:.2f}, FOG={fog_event}, Gait={gait_type}")

        # Create patient profile if new
        if patient_id not in buffers:
            profile = {
                "patient_id": patient_id,
                "name": name,
                "age": age,
                "device_id": device_id,
                "registered_at": datetime.utcnow().isoformat() + "Z"
            }
            buffers[patient_id]["meta"] = profile
            push_to_firebase(patient_id, "profile", profile)
            print(f"New patient registered: {name}")

        # Insert raw reading
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("""
            INSERT INTO fog_readings (patient_id, name, age, device_id, time_iso, emg, motion, gait_type, fog_event, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (patient_id, name, age, device_id, datetime.utcnow().isoformat() + "Z", emg, motion, gait_type, int(fog_event), json.dumps(payload)))
        conn.commit()
        conn.close()

        update_buffer(patient_id, emg, motion, "FOG" if fog_event else "OK",
                      {"name": name, "age": age, "device_id": device_id})

        # If FOG detected → store episode
        if fog_event:
            gait, reason = classify_gait(emg, motion, gait_type)
            now = datetime.utcnow()
            start_time = now - timedelta(seconds=5)
            duration = 5.0

            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("""
                INSERT INTO fog_episodes (patient_id, name, episode_start, episode_end, duration_s, avg_emg, avg_motion, gait_type, reason, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (patient_id, name, start_time.isoformat(), now.isoformat(), duration, emg, motion, gait, reason, now.isoformat()))
            conn.commit()
            conn.close()

            firebase_data = {
                "patient_id": patient_id,
                "name": name,
                "episode_start": start_time.isoformat(),
                "episode_end": now.isoformat(),
                "duration_s": duration,
                "emg": emg,
                "motion": motion,
                "gait_type": gait,
                "reason": reason,
                "detected_at": now.isoformat()
            }
            push_to_firebase(patient_id, "fog_episode", firebase_data)
            print(f"FOG episode saved for {patient_id}: {gait}")

        return jsonify({"ok": True}), 200

    except Exception as e:
        print("Error in /data:", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


# ===== Run =====
if __name__ == "__main__":
    print("Starting StepSafe Flask Server...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print("Available tables:", c.fetchall())
    conn.close()
    app.run(host="0.0.0.0", port=5000, debug=True)
