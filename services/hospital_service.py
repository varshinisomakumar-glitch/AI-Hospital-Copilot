from datetime import date

from services.database import get_connection


def get_patients(search_term=""):
    """Return patients, optionally filtered by name, phone, or blood group."""
    query = "SELECT id, full_name, date_of_birth, gender, phone, email, blood_group, created_at FROM patients"
    parameters = []
    if search_term:
        query += " WHERE full_name LIKE ? OR phone LIKE ? OR blood_group LIKE ?"
        like_term = f"%{search_term}%"
        parameters = [like_term, like_term, like_term]
    query += " ORDER BY full_name COLLATE NOCASE"
    with get_connection() as connection:
        return connection.execute(query, parameters).fetchall()


def create_patient(patient):
    """Save a validated patient record and return its new ID."""
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO patients
               (full_name, date_of_birth, gender, phone, email, address, blood_group, medical_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient["full_name"], patient["date_of_birth"], patient["gender"], patient["phone"], patient["email"], patient["address"], patient["blood_group"], patient["medical_notes"]),
        )
        return cursor.lastrowid


def get_doctors(search_term=""):
    """Return doctors, optionally filtered by name or specialization."""
    query = "SELECT id, full_name, specialization, phone, email, availability, created_at FROM doctors"
    parameters = []
    if search_term:
        query += " WHERE full_name LIKE ? OR specialization LIKE ?"
        like_term = f"%{search_term}%"
        parameters = [like_term, like_term]
    query += " ORDER BY full_name COLLATE NOCASE"
    with get_connection() as connection:
        return connection.execute(query, parameters).fetchall()


def create_doctor(doctor):
    """Save a validated doctor record and return its new ID."""
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO doctors (full_name, specialization, phone, email, availability) VALUES (?, ?, ?, ?, ?)",
            (doctor["full_name"], doctor["specialization"], doctor["phone"], doctor["email"], doctor["availability"]),
        )
        return cursor.lastrowid


def get_appointments(search_term="", status=""):
    """Return appointments with patient and doctor details for the directory."""
    query = """
        SELECT a.id, a.appointment_date, a.reason, a.status,
               p.full_name AS patient_name, d.full_name AS doctor_name, d.specialization
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        JOIN doctors d ON d.id = a.doctor_id
    """
    conditions, parameters = [], []
    if search_term:
        conditions.append("(p.full_name LIKE ? OR d.full_name LIKE ?)")
        like_term = f"%{search_term}%"
        parameters.extend([like_term, like_term])
    if status:
        conditions.append("a.status = ?")
        parameters.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY datetime(a.appointment_date) DESC"
    with get_connection() as connection:
        return connection.execute(query, parameters).fetchall()


def get_appointment_form_options():
    """Return valid patients and doctors for the appointment form."""
    with get_connection() as connection:
        patients = connection.execute("SELECT id, full_name FROM patients ORDER BY full_name COLLATE NOCASE").fetchall()
        doctors = connection.execute("SELECT id, full_name, specialization FROM doctors ORDER BY full_name COLLATE NOCASE").fetchall()
    return patients, doctors


def create_appointment(appointment):
    """Save an appointment only when both foreign-key records exist."""
    with get_connection() as connection:
        patient = connection.execute("SELECT id FROM patients WHERE id = ?", (appointment["patient_id"],)).fetchone()
        doctor = connection.execute("SELECT id FROM doctors WHERE id = ?", (appointment["doctor_id"],)).fetchone()
        if not patient or not doctor:
            raise ValueError("The selected patient or doctor no longer exists.")
        cursor = connection.execute(
            """INSERT INTO appointments (patient_id, doctor_id, appointment_date, reason, status, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (appointment["patient_id"], appointment["doctor_id"], appointment["appointment_date"], appointment["reason"], appointment["status"], ""),
        )
        return cursor.lastrowid


def get_patient_and_doctor(patient_id, doctor_id):
    """Return existing patient and doctor records for Doctor Copilot validation."""
    with get_connection() as connection:
        patient = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
        doctor = connection.execute("SELECT id, full_name FROM doctors WHERE id = ?", (doctor_id,)).fetchone()
    return patient, doctor


def get_scheduled_appointments_for_patient(patient_id):
    """Return only bookable consultation appointments for one existing patient."""
    with get_connection() as connection:
        return connection.execute(
            """SELECT a.id, a.appointment_date, a.reason, d.full_name AS doctor_name
               FROM appointments a JOIN doctors d ON d.id = a.doctor_id
               WHERE a.patient_id = ? AND a.status = 'Scheduled'
               ORDER BY datetime(a.appointment_date)""",
            (patient_id,),
        ).fetchall()


def save_clinical_note(note):
    """Atomically save a note and complete its one validated appointment."""
    reviewed_assessment = f"Clinician assessment:\n{note['assessment']}\n\nReviewed draft clinical note:\n{note['draft_note']}"
    with get_connection() as connection:
        patient = connection.execute("SELECT id FROM patients WHERE id = ?", (note["patient_id"],)).fetchone()
        doctor = connection.execute("SELECT id FROM doctors WHERE id = ?", (note["doctor_id"],)).fetchone()
        appointment = connection.execute(
            "SELECT id FROM appointments WHERE id = ? AND patient_id = ? AND status = 'Scheduled'",
            (note["appointment_id"], note["patient_id"]),
        ).fetchone()
        if not patient or not doctor:
            raise ValueError("The selected patient or documenting doctor no longer exists.")
        if not appointment:
            raise ValueError("Select an existing Scheduled appointment for the selected patient.")
        cursor = connection.execute(
            """INSERT INTO clinical_notes (patient_id, doctor_id, visit_date, symptoms, observations, assessment, plan)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (note["patient_id"], note["doctor_id"], note["visit_date"], note["symptoms"], note["observations"], reviewed_assessment, note["plan"]),
        )
        connection.execute("UPDATE appointments SET status = 'Completed' WHERE id = ? AND status = 'Scheduled'", (note["appointment_id"],))
        return cursor.lastrowid


def get_dashboard_data():
    """Fetch the small set of facts displayed on the dashboard."""
    today = date.today().isoformat()
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM patients) AS patient_count,
                (SELECT COUNT(*) FROM doctors) AS doctor_count,
                (SELECT COUNT(*) FROM appointments WHERE date(appointment_date) = ?) AS today_appointments,
                (SELECT COUNT(*) FROM appointments WHERE status = 'Scheduled') AS scheduled_appointments
            """,
            (today,),
        ).fetchone()

        upcoming_appointments = connection.execute(
            """
            SELECT a.appointment_date, a.reason, a.status,
                   p.full_name AS patient_name,
                   d.full_name AS doctor_name,
                   d.specialization
            FROM appointments a
            JOIN patients p ON p.id = a.patient_id
            JOIN doctors d ON d.id = a.doctor_id
            WHERE a.status = 'Scheduled' AND datetime(a.appointment_date) >= datetime('now', 'localtime')
            ORDER BY datetime(a.appointment_date)
            LIMIT 5
            """
        ).fetchall()

        recent_patients = connection.execute(
            """
            SELECT full_name, blood_group, created_at
            FROM patients
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 4
            """
        ).fetchall()

    return {"totals": totals, "upcoming_appointments": upcoming_appointments, "recent_patients": recent_patients}
