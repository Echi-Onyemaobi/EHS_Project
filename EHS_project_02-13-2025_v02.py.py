# Import necessary libraries
import sqlite3
import random
import json
from datetime import datetime, timedelta
from faker import Faker
import matplotlib.pyplot as plt
import io
import base64
from flask import Flask, request, jsonify

from ml_model import HospitalMLModel

# Initialize Faker and Flask app
fake = Faker()
app = Flask(__name__)


# Load configuration from JSON
def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


config = load_config()
departments_info = config.get('departments_info', [])
NUM_PATIENTS = config.get('num_patients', 200)
CANCELLATION_RATE = config.get('cancellation_rate', 0.1)
SHIFTS = config.get('shifts', ["Day", "Night"])
SHIFT_TIMES = config.get('shift_times', {"Day": {"start": "07:00", "end": "19:00"}})

# Global role counters and custom ID generation
role_counters = {role['name']: 0 for dept in departments_info for role in dept.get('staffing', [])}


def generate_staff_id(role):
    """Generates a custom staff ID based on the role."""
    prefix = role[:2].upper() + role[-1].upper()
    role_counters[role] += 1
    return f"{prefix}700{role_counters[role]}"


# Database and table creation
def create_db():
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS medical_records")
    cursor.execute("DROP TABLE IF EXISTS appointments")
    cursor.execute("DROP TABLE IF EXISTS patients")
    cursor.execute("DROP TABLE IF EXISTS staff")
    cursor.execute("DROP TABLE IF EXISTS departments")
    cursor.execute('''
            CREATE TABLE departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                capacity INTEGER DEFAULT 0,
                is_clinical INTEGER DEFAULT 0
            )''')
    cursor.execute('''
            CREATE TABLE staff (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                department_id INTEGER,
                availability TEXT DEFAULT 'available',
                shift TEXT DEFAULT 'day',
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )''')
    cursor.execute('''
            CREATE TABLE patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dob DATE,
                gender TEXT,
                triage_level INTEGER DEFAULT 1,
                arrival_time DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
    cursor.execute('''
            CREATE TABLE appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                staff_id TEXT,
                department_id INTEGER,
                scheduled_time DATETIME,
                duration INTEGER,
                status TEXT DEFAULT 'scheduled',
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (staff_id) REFERENCES staff(id),
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )''')
    cursor.execute('''
            CREATE TABLE medical_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                staff_id TEXT,
                record_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                diagnosis TEXT,
                treatment TEXT,
                notes TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (staff_id) REFERENCES staff(id)
            )''')
    conn.commit()
    conn.close()
    print("Database and tables created from scratch.")


# Populate departments and staff
def populate_departments_and_staff():
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()
    department_ids = {}
    for dept in departments_info:
        name = dept["name"]
        capacity = dept["capacity"]
        is_clinical = 1 if dept.get("is_clinical", False) else 0
        cursor.execute("INSERT INTO departments (name, capacity, is_clinical) VALUES (?, ?, ?)",
                       (name, capacity, is_clinical))
        dept_id = cursor.lastrowid
        department_ids[name] = dept_id
        staffing = dept.get("staffing", [])
        for role in staffing:
            num_staff = random.randint(role['min'], role['max'])
            for _ in range(num_staff):
                staff_id = generate_staff_id(role['name'])
                staff_name = fake.name()
                assigned_shift = random.choice(SHIFTS) if is_clinical else "day"
                cursor.execute(
                    "INSERT INTO staff (id, name, role, department_id, availability, shift) VALUES (?, ?, ?, ?, ?, ?)",
                    (staff_id, staff_name, role['name'], dept_id, 'available', assigned_shift))
    conn.commit()
    conn.close()
    print("Departments and staff data populated successfully.")
    return department_ids


# Populate patient data
def populate_patients(num_patients=NUM_PATIENTS):
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()
    patient_ids = []
    for _ in range(num_patients):
        name = fake.name()
        dob = fake.date_of_birth(minimum_age=0, maximum_age=99)
        gender = random.choice(['Male', 'Female'])
        triage_level = random.randint(1, 5)
        arrival_time = (datetime.now() - timedelta(minutes=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO patients (name, dob, gender, triage_level, arrival_time) VALUES (?, ?, ?, ?, ?)",
                       (name, dob, gender, triage_level, arrival_time))
        patient_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    print("Patients data populated successfully.")
    return patient_ids


# Simulate a shift with dynamic appointment scheduling
def simulate_shift(shift="Day", shift_start_str="07:00", shift_end_str="19:00"):
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()
    today = datetime.now().date()
    shift_start = datetime.combine(today, datetime.strptime(shift_start_str, "%H:%M").time())
    shift_end = datetime.combine(today, datetime.strptime(shift_end_str, "%H:%M").time())
    clinical_roles = ["Doctor", "Registered Nurse", "Nursing Assistant", "Respiratory Therapist",
                      "Radiology Technician", "Ophthalmic Technician", "Physical Therapist"]
    cursor.execute(
        f"SELECT id, department_id FROM staff WHERE role IN ({','.join('?' * len(clinical_roles))}) AND shift = ?",
        (*clinical_roles, shift))
    staff_data = cursor.fetchall()
    if not staff_data:
        print("No clinical staff available for shift:", shift)
        conn.close()
        return
    staff_next_available = {staff_id: shift_start for staff_id, _ in staff_data}
    staff_department = {staff_id: dept_id for staff_id, dept_id in staff_data}
    cursor.execute("SELECT id, triage_level, arrival_time FROM patients")
    patient_data = cursor.fetchall()
    filtered_patients = [(pid, triage, datetime.strptime(arrival, "%Y-%m-%d %H:%M:%S")) for pid, triage, arrival in
                         patient_data if shift_start <= datetime.strptime(arrival, "%Y-%m-%d %H:%M:%S") <= shift_end]
    filtered_patients.sort(key=lambda x: x[2])
    cancellation_rate = CANCELLATION_RATE
    appointments_scheduled = 0
    for pid, triage, arrival_dt in filtered_patients:
        available_staff = sorted((staff_id for staff_id in staff_next_available),
                                 key=lambda id: staff_next_available[id])
        if not available_staff:
            break
        staff_id = available_staff[0]
        appointment_start = max(arrival_dt, staff_next_available[staff_id])
        if appointment_start > shift_end:
            continue
        duration = random.randint(15, 45)
        appointment_end = appointment_start + timedelta(minutes=duration)
        if random.random() < cancellation_rate:
            status = "cancelled"
        else:
            status = "completed"
            staff_next_available[staff_id] = appointment_end
        cursor.execute(
            "INSERT INTO appointments (patient_id, staff_id, department_id, scheduled_time, duration, status) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, staff_id, staff_department[staff_id], appointment_start, duration, status))
        appointments_scheduled += 1
    conn.commit()
    conn.close()
    print(f"Shift simulation complete: {appointments_scheduled} appointments scheduled for the {shift} shift.")


# Generate report and visualization of simulation data
def generate_report():
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")
    data = cursor.fetchall()
    status_counts = {row[0]: row[1] for row in data}
    print("Appointment Status Counts:", status_counts)
    labels = list(status_counts.keys())
    sizes = list(status_counts.values())
    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title("Appointment Status Distribution")
    plt.axis('equal')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()
    plt.close()
    conn.close()
    return status_counts, image_base64


# Flask API setup and endpoints
@app.route('/create_db', methods=['POST'])
def api_create_db():
    create_db()
    return jsonify({"message": "Database created from scratch."}), 200


@app.route('/populate', methods=['POST'])
def api_populate():
    department_ids = populate_departments_and_staff()
    patient_ids = populate_patients()
    return jsonify(
        {"message": "Database populated.", "departments": department_ids, "num_patients": len(patient_ids)}), 200


@app.route('/simulate', methods=['POST'])
def api_simulate():
    data = request.get_json() or {}
    shift = data.get('shift', 'Day')
    shift_start_str = data.get('shift_start', None)
    shift_end_str = data.get('shift_end', None)
    simulate_shift(shift, shift_start_str, shift_end_str)
    return jsonify({"message": f"Shift simulation completed for shift {shift}."}), 200


@app.route('/report', methods=['GET'])
def api_report():
    status_counts, chart_image = generate_report()
    return jsonify({"report": status_counts, "chart": chart_image}), 200


if __name__ == "__main__":
    app.run(debug=True)
