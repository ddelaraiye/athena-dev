import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

APP_NAME = os.getenv("APP_NAME", "ATHENA")
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "athena-llama:3b"
)
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))

DATABASE_PATH = ROOT_DIR / "data" / "conversations.db"
FRONTEND_DIR = ROOT_DIR / "frontend"
