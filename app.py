from datetime import datetime

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from config import SECRET_KEY
from services.database import initialize_database
from services.ai_service import CopilotAPIError, answer_hospital_question, generate_doctor_summary
from services.hospital_service import (
    create_appointment, create_doctor, create_patient, get_appointment_form_options,
    get_appointments, get_dashboard_data, get_doctors, get_patient_and_doctor, get_patients,
    get_scheduled_appointments_for_patient, save_clinical_note,
)


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY

    initialize_database()

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html", **get_dashboard_data())

    @app.route("/patients")
    def patients():
        search_term = request.args.get("q", "").strip()
        return render_template("patients.html", patients=get_patients(search_term), search_term=search_term)

    @app.route("/patients/new", methods=["GET", "POST"])
    def add_patient():
        form_data = {}
        if request.method == "POST":
            fields = ("full_name", "date_of_birth", "gender", "phone", "email", "address", "blood_group", "medical_notes")
            form_data = {field: request.form.get(field, "").strip() for field in fields}
            required_fields = {"full_name": "Full name", "date_of_birth": "Date of birth", "gender": "Gender", "phone": "Phone number"}
            errors = [label for field, label in required_fields.items() if not form_data[field]]
            try:
                if form_data["date_of_birth"]:
                    datetime.strptime(form_data["date_of_birth"], "%Y-%m-%d")
            except ValueError:
                errors.append("a valid date of birth")
            if errors:
                flash("Please provide " + ", ".join(errors) + ".", "error")
            else:
                create_patient(form_data)
                flash(f"{form_data['full_name']} was added successfully.", "success")
                return redirect(url_for("patients"))
        return render_template("patient_form.html", form_data=form_data)

    @app.route("/doctors")
    def doctors():
        search_term = request.args.get("q", "").strip()
        return render_template("doctors.html", doctors=get_doctors(search_term), search_term=search_term)

    @app.route("/doctors/new", methods=["GET", "POST"])
    def add_doctor():
        form_data = {}
        if request.method == "POST":
            fields = ("full_name", "specialization", "phone", "email", "availability")
            form_data = {field: request.form.get(field, "").strip() for field in fields}
            required_fields = {"full_name": "Full name", "specialization": "Specialization", "phone": "Phone number"}
            errors = [label for field, label in required_fields.items() if not form_data[field]]
            if errors:
                flash("Please provide " + ", ".join(errors) + ".", "error")
            else:
                create_doctor(form_data)
                flash(f"{form_data['full_name']} was added successfully.", "success")
                return redirect(url_for("doctors"))
        return render_template("doctor_form.html", form_data=form_data)

    @app.route("/appointments")
    def appointments():
        search_term = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        return render_template("appointments.html", appointments=get_appointments(search_term, status), search_term=search_term, selected_status=status)

    @app.route("/appointments/new", methods=["GET", "POST"])
    def add_appointment():
        patients, doctors = get_appointment_form_options()
        form_data = {"status": "Scheduled"}
        if request.method == "POST":
            fields = ("patient_id", "doctor_id", "appointment_date", "reason", "status")
            form_data = {field: request.form.get(field, "").strip() for field in fields}
            errors = [field.replace("_", " ").title() for field in ("patient_id", "doctor_id", "appointment_date", "reason") if not form_data[field]]
            if form_data["status"] not in ("Scheduled", "Completed", "Cancelled"):
                errors.append("a valid status")
            try:
                patient_id, doctor_id = int(form_data["patient_id"]), int(form_data["doctor_id"])
            except ValueError:
                patient_id = doctor_id = None
                if not errors:
                    errors.append("valid patient and doctor selections")
            try:
                if form_data["appointment_date"]:
                    datetime.strptime(form_data["appointment_date"], "%Y-%m-%dT%H:%M")
            except ValueError:
                errors.append("a valid appointment date and time")
            if errors:
                flash("Please provide " + ", ".join(errors) + ".", "error")
            else:
                try:
                    create_appointment({**form_data, "patient_id": patient_id, "doctor_id": doctor_id, "appointment_date": form_data["appointment_date"].replace("T", " ")})
                except ValueError as error:
                    flash(str(error), "error")
                else:
                    flash("Appointment booked successfully.", "success")
                    return redirect(url_for("appointments"))
        return render_template("appointment_form.html", form_data=form_data, patients=patients, doctors=doctors)

    @app.route("/copilot")
    def copilot():
        return render_template("copilot.html")

    @app.post("/api/copilot/chat")
    def copilot_chat():
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question", "")).strip()
        if not question:
            return jsonify({"error": "Please enter a hospital administration question."}), 400
        try:
            return jsonify(answer_hospital_question(question))
        except CopilotAPIError as error:
            request_id = getattr(error.provider_error, "request_id", None)
            app.logger.exception(
                "OpenAI Hospital Copilot request failed. error_type=%s request_id=%s",
                type(error.provider_error).__name__, request_id or "not provided",
            )
            return jsonify({"error": "Hospital Copilot could not complete that request. Check the Flask terminal for the OpenAI API error details."}), 503
        except Exception:
            app.logger.exception("Unexpected Hospital Copilot failure.")
            return jsonify({"error": "Hospital Copilot could not complete that request. Please check the AI configuration and try again."}), 503

    @app.route("/doctor-copilot")
    def doctor_copilot():
        patients, doctors = get_appointment_form_options()
        return render_template("doctor_copilot.html", patients=patients, doctors=doctors)

    @app.post("/api/doctor-copilot/summary")
    def doctor_copilot_summary():
        payload = request.get_json(silent=True) or {}
        fields = ("patient_id", "doctor_id", "appointment_id", "symptoms", "observations", "assessment", "plan")
        consultation = {field: str(payload.get(field, "")).strip() for field in fields}
        missing = [field.replace("_", " ") for field in fields if not consultation[field]]
        if missing:
            return jsonify({"error": "Please provide " + ", ".join(missing) + "."}), 400
        try:
            patient_id, doctor_id = int(consultation.pop("patient_id")), int(consultation.pop("doctor_id"))
            appointment_id = int(consultation.pop("appointment_id"))
        except ValueError:
            return jsonify({"error": "Please select a valid patient and documenting doctor."}), 400
        patient, doctor = get_patient_and_doctor(patient_id, doctor_id)
        if not patient or not doctor:
            return jsonify({"error": "The selected patient or documenting doctor does not exist."}), 400
        if not any(appointment["id"] == appointment_id for appointment in get_scheduled_appointments_for_patient(patient_id)):
            return jsonify({"error": "Select an existing Scheduled appointment for the selected patient."}), 400
        return jsonify(generate_doctor_summary(dict(patient), consultation))

    @app.get("/api/doctor-copilot/appointments/<int:patient_id>")
    def doctor_copilot_appointments(patient_id):
        patient, _ = get_patient_and_doctor(patient_id, 0)
        if not patient:
            return jsonify({"error": "The selected patient does not exist."}), 404
        return jsonify({"appointments": [dict(item) for item in get_scheduled_appointments_for_patient(patient_id)]})

    @app.post("/api/doctor-copilot/save")
    def doctor_copilot_save():
        payload = request.get_json(silent=True) or {}
        fields = ("patient_id", "doctor_id", "appointment_id", "symptoms", "observations", "assessment", "plan", "draft_note")
        note = {field: str(payload.get(field, "")).strip() for field in fields}
        missing = [field.replace("_", " ") for field in fields if not note[field]]
        if missing:
            return jsonify({"error": "Please complete " + ", ".join(missing) + " before saving."}), 400
        try:
            note["patient_id"], note["doctor_id"], note["appointment_id"] = int(note["patient_id"]), int(note["doctor_id"]), int(note["appointment_id"])
            note["visit_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            note_id = save_clinical_note(note)
        except (ValueError, TypeError) as error:
            return jsonify({"error": str(error) or "Please select a valid patient and documenting doctor."}), 400
        return jsonify({"message": "Clinical note saved and appointment marked as Completed.", "note_id": note_id})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
