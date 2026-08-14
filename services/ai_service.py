"""Read-only Hospital Copilot data retrieval and AI response helpers."""
from datetime import date

from config import DOCTOR_COPILOT_DEMO_MODE, OPENAI_API_KEY, OPENAI_MODEL
from services.database import get_connection

MEDICAL_SAFETY_MESSAGE = (
    "Hospital Copilot supports administration only. It cannot diagnose conditions, "
    "recommend treatment, or provide emergency medical advice. Please consult a qualified clinician."
)


class CopilotAPIError(Exception):
    """A safe wrapper for an upstream AI provider error."""

    def __init__(self, provider_error):
        self.provider_error = provider_error
        super().__init__(str(provider_error))


def generate_doctor_summary(patient, consultation):
    """Generate documentation text. Demo mode intentionally makes no API calls."""
    history = patient["medical_notes"] or "No additional history recorded."
    patient_summary = f"{patient['full_name']} · DOB: {patient['date_of_birth']} · {patient['gender'] or 'Gender not recorded'} · Blood group: {patient['blood_group'] or 'Not recorded'}"
    follow_up = consultation["plan"] or "No follow-up items were documented."
    draft = (
        f"Patient: {patient['full_name']}\n"
        f"Chief complaint: {consultation['symptoms']}\n"
        f"Relevant history: {history}\n"
        f"Observations: {consultation['observations']}\n"
        f"Assessment (clinician-entered): {consultation['assessment']}\n"
        f"Plan (clinician-entered): {consultation['plan']}\n\n"
        "This draft is a documentation aid and requires clinician review."
    )
    return {
        "mode": "demo" if DOCTOR_COPILOT_DEMO_MODE else "mock",
        "label": "DEMO / AI DRAFT — Requires clinician review",
        "patient_summary": patient_summary,
        "chief_complaint": consultation["symptoms"],
        "relevant_history": history,
        "current_symptoms": consultation["symptoms"],
        "key_observations": consultation["observations"],
        "assessment_summary": consultation["assessment"],
        "suggested_follow_up_items": f"Review the clinician-entered plan: {follow_up}",
        "draft_clinical_note": draft,
    }


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def _find_named_doctor(question):
    with get_connection() as connection:
        doctors = connection.execute("SELECT full_name FROM doctors").fetchall()
    question_lower = question.lower()
    return next((row["full_name"] for row in doctors if row["full_name"].lower() in question_lower), None)


def _find_named_patient(question):
    with get_connection() as connection:
        patients = connection.execute("SELECT full_name FROM patients").fetchall()
    question_lower = question.lower()
    return next((row["full_name"] for row in patients if row["full_name"].lower() in question_lower), None)


def retrieve_hospital_context(question):
    """Choose one of a small set of fixed, read-only queries. No model-generated SQL."""
    normalized = question.lower().strip()
    if any(term in normalized for term in ("diagnos", "treatment", "prescri", "emergency", "medical advice")):
        return {"safety_message": MEDICAL_SAFETY_MESSAGE}

    named_patient = _find_named_patient(question)
    named_doctor = _find_named_doctor(question)
    with get_connection() as connection:
        if named_patient and any(term in normalized for term in ("summary", "patient", "about", "details")):
            patient = connection.execute(
                """SELECT full_name, date_of_birth, gender, blood_group, medical_notes
                   FROM patients WHERE full_name = ?""", (named_patient,)
            ).fetchone()
            visits = connection.execute(
                """SELECT a.appointment_date, a.reason, a.status, d.full_name AS doctor_name
                   FROM appointments a JOIN doctors d ON d.id = a.doctor_id
                   JOIN patients p ON p.id = a.patient_id WHERE p.full_name = ?
                   ORDER BY datetime(a.appointment_date) DESC LIMIT 5""", (named_patient,)
            ).fetchall()
            return {"intent": "patient summary", "patient": dict(patient), "recent_appointments": _rows_to_dicts(visits)}

        if named_doctor:
            appointments = connection.execute(
                """SELECT a.appointment_date, a.reason, a.status, p.full_name AS patient_name,
                          d.full_name AS doctor_name, d.specialization
                   FROM appointments a JOIN patients p ON p.id = a.patient_id
                   JOIN doctors d ON d.id = a.doctor_id WHERE d.full_name = ?
                   ORDER BY datetime(a.appointment_date) ASC LIMIT 10""", (named_doctor,)
            ).fetchall()
            return {"intent": "doctor appointments", "doctor": named_doctor, "appointments": _rows_to_dicts(appointments)}

        if "most appointments" in normalized or "busiest" in normalized:
            doctor = connection.execute(
                """SELECT d.full_name, d.specialization, COUNT(a.id) AS appointment_count
                   FROM doctors d LEFT JOIN appointments a ON a.doctor_id = d.id
                   GROUP BY d.id ORDER BY appointment_count DESC, d.full_name LIMIT 1"""
            ).fetchone()
            return {"intent": "busiest doctor", "doctor": dict(doctor) if doctor else None}

        if "today" in normalized and "appointment" in normalized:
            count = connection.execute("SELECT COUNT(*) AS count FROM appointments WHERE date(appointment_date) = ?", (date.today().isoformat(),)).fetchone()
            return {"intent": "today appointments", "date": date.today().isoformat(), "count": count["count"]}

        if "how many" in normalized and "patient" in normalized:
            count = connection.execute("SELECT COUNT(*) AS count FROM patients").fetchone()
            return {"intent": "patient count", "count": count["count"]}

        if "how many" in normalized and "doctor" in normalized:
            count = connection.execute("SELECT COUNT(*) AS count FROM doctors").fetchone()
            return {"intent": "doctor count", "count": count["count"]}

        if "upcoming" in normalized and "appointment" in normalized:
            appointments = connection.execute(
                """SELECT a.appointment_date, a.reason, a.status, p.full_name AS patient_name,
                          d.full_name AS doctor_name, d.specialization
                   FROM appointments a JOIN patients p ON p.id = a.patient_id
                   JOIN doctors d ON d.id = a.doctor_id
                   WHERE a.status = 'Scheduled' AND datetime(a.appointment_date) >= datetime('now', 'localtime')
                   ORDER BY datetime(a.appointment_date) LIMIT 10"""
            ).fetchall()
            return {"intent": "upcoming appointments", "appointments": _rows_to_dicts(appointments)}
    return {"intent": "unsupported", "message": "I can help with patient and doctor counts, today's or upcoming appointments, a doctor's appointments, busiest doctor, or a named patient summary."}


def answer_hospital_question(question):
    """Answer from safe retrieved context, using OpenAI only when configured."""
    context = retrieve_hospital_context(question)
    if "safety_message" in context:
        return {"answer": context["safety_message"], "configured": bool(OPENAI_API_KEY)}
    if not OPENAI_API_KEY:
        return {"answer": "AI is not configured yet. Set the OPENAI_API_KEY environment variable, restart the Flask app, and try again.", "configured": False}

    from openai import OpenAI, OpenAIError

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.responses.create(
            model=OPENAI_MODEL,
            store=False,
            instructions=(
                "You are CareWell Hospital Copilot for administrative support only. "
                "Answer only from the supplied hospital data. Be concise and factual. "
                "Never diagnose, recommend treatment, provide emergency guidance, or invent information."
            ),
            input=f"Question: {question}\n\nSafe read-only hospital data: {context}",
        )
    except OpenAIError as error:
        # The route logs this exception. Do not print or include the API key here.
        raise CopilotAPIError(error) from error
    return {"answer": response.output_text, "configured": True}
