import sqlite3
import random
import json
from datetime import datetime, timedelta
from faker import Faker
import matplotlib.pyplot as plt  # For visualization

fake = Faker()


#######################################
# 1. Load Configuration from JSON File#
#######################################
def load_config(config_path='config.json'):
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


# Load the configuration at startup
config = load_config()

# Use configuration values to override defaults.
departments_info = config.get('departments_info', [])
NUM_PATIENTS = config.get('num_patients', 200)
CANCELLATION_RATE = config.get('cancellation_rate', 0.1)
SHIFTS = config.get('shifts', ["Day", "Night"])
SHIFT_TIMES = config.get('shift_times', {"Day": {"start": "07:00", "end": "19:00"}})

###############################################
# 2. Global Role Counters & Custom ID Generation  #
###############################################
role_counters = {
    "Doctor": 0,
    "Registered Nurse": 0,
    "Nursing Assistant": 0,
    "Respiratory Therapist": 0,
    "Radiology Technician": 0,
    "Administrative Staff": 0,
    "Receptionist": 0,
    "Human Resources": 0,
    "Cleaner": 0,
    "Cook": 0,
    "Kitchen Assistant": 0,
    "Maintenance Technician": 0,
    "Pharmacist": 0,
    "Pharmacy Technician": 0,
    "Lab Technician": 0,
    "IT Support": 0,
    "Security Personnel": 0,
    "Ophthalmic Technician": 0,
    "Physical Therapist": 0
}


def generate_staff_id(role):
    """
    Generates a custom staff ID based on the role.
    The ID follows the pattern: {PREFIX}700{counter}
    e.g., first Doctor -> MD7001, first Registered Nurse -> RN7001, etc.
    """
    prefix_map = {
        "Doctor": "MD",
        "Registered Nurse": "RN",
        "Nursing Assistant": "NA",
        "Respiratory Therapist": "RT",
        "Radiology Technician": "RDT",
        "Administrative Staff": "AD",
        "Receptionist": "RC",
        "Human Resources": "HR",
        "Cleaner": "CL",
        "Cook": "CK",
        "Kitchen Assistant": "KA",
        "Maintenance Technician": "MT",
        "Pharmacist": "PH",
        "Pharmacy Technician": "PT",
        "Lab Technician": "LT",
        "IT Support": "IT",
        "Security Personnel": "SC",
        "Ophthalmic Technician": "OT",
        "Physical Therapist": "PHT"
    }
    prefix = prefix_map.get(role, "ST")
    role_counters[role] += 1
    return f"{prefix}700{role_counters[role]}"


##########################################
# 3. Database Creation (with Shift Column)#
##########################################
def create_db():
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()

    # Drop existing tables so we start fresh.
    cursor.execute("DROP TABLE IF EXISTS medical_records")
    cursor.execute("DROP TABLE IF EXISTS appointments")
    cursor.execute("DROP TABLE IF EXISTS patients")
    cursor.execute("DROP TABLE IF EXISTS staff")
    cursor.execute("DROP TABLE IF EXISTS departments")

    # Create Departments table.
    cursor.execute('''
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        capacity INTEGER DEFAULT 0,
        is_clinical INTEGER DEFAULT 0
    )
    ''')

    # Create Staff table – note the added "shift" column.
    cursor.execute('''
    CREATE TABLE staff (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        department_id INTEGER,
        availability TEXT DEFAULT 'available',
        shift TEXT DEFAULT 'day',
        FOREIGN KEY (department_id) REFERENCES departments(id)
    )
    ''')

    # Create Patients table.
    cursor.execute('''
    CREATE TABLE patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        dob DATE,
        gender TEXT,
        triage_level INTEGER DEFAULT 1,
        arrival_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Create Appointments table.
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
    )
    ''')

    # Create Medical Records table.
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
    )
    ''')

    conn.commit()
    conn.close()
    print("Database and tables created from scratch.")


#########################################################
# 4. Populate Departments & Staff (with Shift Assignment)#
#########################################################
def populate_departments_and_staff():
    """
    Inserts departments and populates each with staff.
    For clinical departments, a random shift is assigned from the SHIFTS list.
    For non-clinical departments, a default shift "day" is assigned.
    """
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()

    department_ids = {}  # Map department name to its ID

    for dept in departments_info:
        name = dept["name"]
        capacity = dept["capacity"]
        is_clinical = 1 if dept.get("is_clinical", False) else 0
        cursor.execute(
            "INSERT INTO departments (name, capacity, is_clinical) VALUES (?, ?, ?)",
            (name, capacity, is_clinical)
        )
        dept_id = cursor.lastrowid
        department_ids[name] = dept_id

        staffing = dept.get("staffing", {})
        for role, (min_num, max_num) in staffing.items():
            num_staff = random.randint(min_num, max_num)
            for _ in range(num_staff):
                staff_id = generate_staff_id(role)
                staff_name = fake.name()
                # For clinical departments, assign a random shift from SHIFTS; otherwise, default to "day".
                assigned_shift = random.choice(SHIFTS) if is_clinical else "day"
                cursor.execute(
                    "INSERT INTO staff (id, name, role, department_id, availability, shift) VALUES (?, ?, ?, ?, ?, ?)",
                    (staff_id, staff_name, role, dept_id, 'available', assigned_shift)
                )

    conn.commit()
    conn.close()
    print("Departments and staff data populated successfully.")
    return department_ids


###################################
# 5. Populate Patient Data          #
###################################
def populate_patients(num_patients=NUM_PATIENTS):
    """
    Populates the patients table with realistic data.
    Each patient gets:
      - A name, date of birth, and gender.
      - A triage level (1–5) where 5 is most urgent.
      - An arrival time randomly assigned within the past hour.
    """
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()

    patient_ids = []
    for _ in range(num_patients):
        name = fake.name()
        dob = fake.date_of_birth(minimum_age=0, maximum_age=99)
        gender = random.choice(['Male', 'Female'])
        triage_level = random.randint(1, 5)
        # Format the arrival time to a consistent string format.
        arrival_time = (datetime.now() - timedelta(minutes=random.randint(0, 60))).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO patients (name, dob, gender, triage_level, arrival_time) VALUES (?, ?, ?, ?, ?)",
            (name, dob, gender, triage_level, arrival_time)
        )
        patient_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    print("Patients data populated successfully.")
    return patient_ids


#########################################################
# 6. Simulate a Shift with Dynamic Appointment Scheduling  #
#########################################################
def simulate_shift(shift="Day", shift_start_str=None, shift_end_str=None):
    """
    Simulates one shift (e.g., Day) of hospital operations:
      - Only clinical staff on the given shift are used for appointments.
      - Each staff member is assigned a 'next available time', initialized to the shift start.
      - Patients arriving during the shift are scheduled in order.
      - Appointment start time = max(patient arrival, staff's available time).
      - With a small probability, an appointment is cancelled.
    """
    # Use shift times from the config if not provided.
    if not shift_start_str or not shift_end_str:
        times = SHIFT_TIMES.get(shift, {"start": "07:00", "end": "19:00"})
        shift_start_str = times["start"]
        shift_end_str = times["end"]

    # Define shift start and end times for today.
    today = datetime.now().date()
    shift_start = datetime.combine(today, datetime.strptime(shift_start_str, "%H:%M").time())
    shift_end = datetime.combine(today, datetime.strptime(shift_end_str, "%H:%M").time())

    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()

    # Define clinical roles eligible for patient appointments.
    clinical_roles = (
        "Doctor", "Registered Nurse", "Nursing Assistant", "Respiratory Therapist", "Radiology Technician",
        "Ophthalmic Technician", "Physical Therapist"
    )
    # Retrieve clinical staff on the specified shift.
    query = f"SELECT id, department_id FROM staff WHERE role IN {clinical_roles} AND shift = ?"
    cursor.execute(query, (shift,))
    staff_data = cursor.fetchall()
    if not staff_data:
        print("No clinical staff available for shift:", shift)
        conn.close()
        return

    # Initialize each staff's next available time to the shift start.
    staff_next_available = {}
    staff_department = {}
    for staff_id, dept_id in staff_data:
        staff_next_available[staff_id] = shift_start
        staff_department[staff_id] = dept_id

    # Retrieve all patients.
    cursor.execute("SELECT id, triage_level, arrival_time FROM patients")
    patient_data = cursor.fetchall()
    # Filter patients who arrived during the shift.
    filtered_patients = []
    for pid, triage, arrival in patient_data:
        # Convert arrival time string to a datetime object.
        if isinstance(arrival, str):
            arrival_dt = datetime.strptime(arrival, "%Y-%m-%d %H:%M:%S")
        else:
            arrival_dt = arrival
        if shift_start <= arrival_dt <= shift_end:
            filtered_patients.append((pid, triage, arrival_dt))
    # Sort patients by arrival time.
    filtered_patients.sort(key=lambda x: x[2])

    cancellation_rate = CANCELLATION_RATE  # Use the config value
    appointments_scheduled = 0

    for pid, triage, arrival_dt in filtered_patients:
        # Find the clinical staff with the earliest next available time.
        available_staff = sorted(staff_next_available.items(), key=lambda x: x[1])
        if not available_staff:
            break
        staff_id, available_time = available_staff[0]
        # The appointment start time is the later of the patient's arrival and the staff's availability.
        appointment_start = max(arrival_dt, available_time)
        if appointment_start > shift_end:
            continue  # Cannot schedule if beyond the shift end.
        duration = random.randint(15, 45)  # Appointment duration in minutes.
        appointment_end = appointment_start + timedelta(minutes=duration)

        # Decide if the appointment is cancelled.
        if random.random() < cancellation_rate:
            status = "cancelled"
        else:
            status = "completed"
            # Update the staff's next available time.
            staff_next_available[staff_id] = appointment_end

        # Insert the appointment into the database.
        cursor.execute(
            "INSERT INTO appointments (patient_id, staff_id, department_id, scheduled_time, duration, status) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, staff_id, staff_department[staff_id], appointment_start, duration, status)
        )
        appointments_scheduled += 1

    conn.commit()
    conn.close()
    print(f"Shift simulation complete: {appointments_scheduled} appointments scheduled for the {shift} shift.")


#########################################################
# 7. Generate Report and Visualization of Simulation Data  #
#########################################################
def generate_report():
    """
    Generates a report by querying the appointments table and then visualizes the
    distribution of appointment statuses (e.g., completed, cancelled) using a pie chart.
    """
    conn = sqlite3.connect('hospital_simulation.db')
    cursor = conn.cursor()

    # Query to count appointments by status
    cursor.execute("SELECT status, COUNT(*) FROM appointments GROUP BY status")
    data = cursor.fetchall()

    # Build a dictionary from the query result
    status_counts = {row[0]: row[1] for row in data}
    print("Appointment Status Counts:", status_counts)

    # Create a pie chart for visualization
    labels = list(status_counts.keys())
    sizes = list(status_counts.values())

    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title("Appointment Status Distribution")
    plt.axis('equal')
    plt.show()

    conn.close()


######################################
# 8. Main Execution of the Simulation#
######################################
if __name__ == "__main__":
    # Step 1: Create the database and tables.
    create_db()

    # Step 2: Populate departments and staff.
    department_ids = populate_departments_and_staff()

    # Step 3: Populate patients.
    patient_ids = populate_patients()

    # Step 4: Simulate a specific shift (e.g., the Day shift).
    simulate_shift(shift="Day", shift_start_str="07:00", shift_end_str="19:00")

    # Step 5: Generate report and visualization.
    generate_report()
