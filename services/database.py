import sqlite3
from datetime import date, datetime, timedelta

from config import DATABASE_PATH


def get_connection():
    """Return a SQLite connection that exposes columns by name."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    """Create the MVP schema and add demo records on the first run."""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                gender TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                blood_group TEXT,
                medical_notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                specialization TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                availability TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER NOT NULL,
                appointment_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Scheduled',
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (doctor_id) REFERENCES doctors(id)
            );

            CREATE TABLE IF NOT EXISTS clinical_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER NOT NULL,
                visit_date TEXT NOT NULL,
                symptoms TEXT,
                observations TEXT,
                assessment TEXT,
                plan TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (patient_id) REFERENCES patients(id),
                FOREIGN KEY (doctor_id) REFERENCES doctors(id)
            );
            """
        )

        patient_count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        if patient_count == 0:
            seed_demo_data(connection)


def seed_demo_data(connection):
    """Add a small, realistic fictional data set for the dashboard demo."""
    patients = [
        ("Aarav Mehta", "1988-04-17", "Male", "+91 98765 43210", "aarav.mehta@example.com", "Indiranagar, Bengaluru", "B+", "Seasonal asthma"),
        ("Priya Nair", "1994-09-03", "Female", "+91 98765 43211", "priya.nair@example.com", "Koramangala, Bengaluru", "O+", "No known allergies"),
        ("Rohan Kapoor", "1976-12-22", "Male", "+91 98765 43212", "rohan.kapoor@example.com", "Whitefield, Bengaluru", "A+", "Type 2 diabetes"),
        ("Meera Iyer", "2001-06-11", "Female", "+91 98765 43213", "meera.iyer@example.com", "HSR Layout, Bengaluru", "AB+", "Penicillin allergy"),
        ("Kabir Singh", "1968-02-28", "Male", "+91 98765 43214", "kabir.singh@example.com", "Jayanagar, Bengaluru", "O-", "Hypertension"),
    ]
    doctors = [
        ("Dr. Ananya Rao", "General Medicine", "+91 98765 44001", "ananya.rao@carewell.example", "Mon–Sat, 9:00 AM–4:00 PM"),
        ("Dr. Vikram Shah", "Cardiology", "+91 98765 44002", "vikram.shah@carewell.example", "Mon–Fri, 10:00 AM–5:00 PM"),
        ("Dr. Neha Patel", "Dermatology", "+91 98765 44003", "neha.patel@carewell.example", "Tue–Sat, 11:00 AM–6:00 PM"),
    ]
    connection.executemany(
        """INSERT INTO patients
           (full_name, date_of_birth, gender, phone, email, address, blood_group, medical_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        patients,
    )
    connection.executemany(
        """INSERT INTO doctors (full_name, specialization, phone, email, availability)
           VALUES (?, ?, ?, ?, ?)""",
        doctors,
    )

    today = date.today()
    now = datetime.now().replace(second=0, microsecond=0)
    appointments = [
        (1, 1, (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"), "Persistent cough", "Scheduled", "First consultation"),
        (2, 3, (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"), "Skin rash review", "Scheduled", ""),
        (3, 2, (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"), "Blood pressure follow-up", "Scheduled", "Bring recent lab reports"),
        (4, 1, (now + timedelta(days=1, hours=1)).strftime("%Y-%m-%d %H:%M"), "General wellness check", "Scheduled", ""),
        (5, 2, f"{today.isoformat()} 09:00", "Cardiac review", "Completed", "Routine follow-up completed"),
    ]
    connection.executemany(
        """INSERT INTO appointments
           (patient_id, doctor_id, appointment_date, reason, status, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        appointments,
    )
