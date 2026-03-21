from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCRIPTS_DIR = PROJECT_ROOT / "Scripts"
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"

NCAAM_RESULTS_XLSX = LOGS_DIR / "NCAAM Results.xlsx"