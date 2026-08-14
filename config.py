from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "hospital.db"
SECRET_KEY = "development-only-secret-key"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
DOCTOR_COPILOT_DEMO_MODE = os.getenv("DOCTOR_COPILOT_DEMO_MODE", "true").lower() in ("1", "true", "yes")
