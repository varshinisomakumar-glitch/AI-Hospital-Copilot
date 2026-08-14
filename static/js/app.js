// Reserved for small interactive enhancements as the MVP grows.
document.documentElement.classList.add("js-ready");

const copilotForm = document.querySelector("#copilot-form");
if (copilotForm) {
  const input = document.querySelector("#copilot-question");
  const messages = document.querySelector("#chat-messages");
  const addMessage = (type, text) => {
    const item = document.createElement("div");
    item.className = `chat-message ${type}`;
    item.innerHTML = `<strong>${type === "user" ? "You" : "CareWell Copilot"}</strong><p></p>`;
    item.querySelector("p").textContent = text;
    messages.appendChild(item);
    messages.scrollTop = messages.scrollHeight;
    return item;
  };
  const ask = async (question) => {
    const trimmed = question.trim();
    if (!trimmed) return;
    addMessage("user", trimmed); input.value = "";
    const pending = addMessage("assistant", "Checking the read-only hospital records…");
    try {
      const response = await fetch("/api/copilot/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question:trimmed})});
      const data = await response.json();
      pending.querySelector("p").textContent = data.answer || data.error || "I could not answer that question.";
    } catch { pending.querySelector("p").textContent = "I could not connect to Hospital Copilot. Please try again."; }
  };
  copilotForm.addEventListener("submit", (event) => { event.preventDefault(); ask(input.value); });
  document.querySelectorAll(".example-question").forEach((button) => button.addEventListener("click", () => ask(button.textContent)));
}

const doctorCopilotForm = document.querySelector("#doctor-copilot-form");
if (doctorCopilotForm) {
  const summary = document.querySelector("#doctor-summary");
  const summaryFields = document.querySelector("#summary-fields");
  const draftNote = document.querySelector("#draft-note");
  const feedback = document.querySelector("#save-feedback");
  const fieldValues = () => Object.fromEntries(new FormData(doctorCopilotForm).entries());
  const showFeedback = (text, error = false) => { feedback.textContent = text; feedback.className = `save-feedback ${error ? "error" : "success"}`; };
  const patientSelect = document.querySelector("#copilot-patient");
  const appointmentSelect = document.querySelector("#copilot-appointment");
  patientSelect.addEventListener("change", async () => {
    appointmentSelect.disabled = true;
    appointmentSelect.replaceChildren(new Option("Loading scheduled appointments…", ""));
    if (!patientSelect.value) { appointmentSelect.replaceChildren(new Option("Select a patient first", "")); return; }
    try {
      const response = await fetch(`/api/doctor-copilot/appointments/${patientSelect.value}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to load appointments.");
      appointmentSelect.replaceChildren(new Option(data.appointments.length ? "Select scheduled appointment" : "No Scheduled appointments for this patient", ""));
      data.appointments.forEach((appointment) => appointmentSelect.add(new Option(`${appointment.appointment_date} — ${appointment.doctor_name} (${appointment.reason})`, appointment.id)));
      appointmentSelect.disabled = !data.appointments.length;
    } catch (error) { appointmentSelect.replaceChildren(new Option(error.message, "")); }
  });
  doctorCopilotForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = doctorCopilotForm.querySelector("button[type=submit]");
    button.disabled = true; button.textContent = "Generating…";
    try {
      const response = await fetch("/api/doctor-copilot/summary", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(fieldValues())});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to generate a draft.");
      const labels = {patient_summary:"Patient Summary", chief_complaint:"Chief Complaint", relevant_history:"Relevant History", current_symptoms:"Current Symptoms", key_observations:"Key Observations", assessment_summary:"Assessment Summary", suggested_follow_up_items:"Suggested Follow-up Items"};
      summaryFields.replaceChildren();
      Object.entries(labels).forEach(([key, label]) => { const item = document.createElement("div"); item.className = "summary-item"; item.innerHTML = `<strong>${label}</strong><p></p>`; item.querySelector("p").textContent = data[key]; summaryFields.appendChild(item); });
      document.querySelector(".draft-label").textContent = data.label;
      draftNote.value = data.draft_clinical_note;
      summary.hidden = false; feedback.textContent = ""; summary.scrollIntoView({behavior:"smooth", block:"start"});
    } catch (error) { window.alert(error.message); }
    finally { button.disabled = false; button.textContent = "Generate summary"; }
  });
  document.querySelector("#save-clinical-note").addEventListener("click", async () => {
    const button = document.querySelector("#save-clinical-note");
    button.disabled = true; button.textContent = "Saving…";
    try {
      const response = await fetch("/api/doctor-copilot/save", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({...fieldValues(), draft_note:draftNote.value})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to save the note.");
      showFeedback(data.message);
    } catch (error) { showFeedback(error.message, true); }
    finally { button.disabled = false; button.textContent = "Save Clinical Note"; }
  });
}
