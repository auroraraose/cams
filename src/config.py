import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -- AI Model Configuration --
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.5-flash")
GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")

# -- Generation Parameters --
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))
TOP_P = float(os.getenv("TOP_P", 0.9))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", 8192))
CANDIDATE_COUNT = int(os.getenv("CANDIDATE_COUNT", 1))

# -- Application Logic --
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
OUTPUT_DATA_DIR = os.getenv("OUTPUT_DATA_DIR", "data/output")
SCRIPT_DIR = os.getenv("SCRIPT_DIR", "scripts")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(PROJECT_ROOT, "prompts")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# -- GCS Configuration --
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
GCS_COMPANIES_FOLDER = os.getenv("GCS_COMPANIES_FOLDER", "companies")
GCS_PROMPTS_FOLDER = os.getenv("GCS_PROMPTS_FOLDER", "prompts")

# -- Prompt Configuration --
SUMMARY_PROMPT_NAME = os.getenv("SUMMARY_PROMPT_NAME", "summary")
INDUSTRY_ANALYSIS_PROMPT_NAME = os.getenv("INDUSTRY_ANALYSIS_PROMPT_NAME", "industry_analysis")
RATIO_ANALYSIS_PROMPT_NAME = os.getenv("RATIO_ANALYSIS_PROMPT_NAME", "ratio_analysis")
MEDIA_MONITORING_PROMPT_NAME = os.getenv("MEDIA_MONITORING_PROMPT_NAME", "media_monitoring")
SHAREHOLDING_PATTERN_PROMPT_NAME = os.getenv("SHAREHOLDING_PATTERN_PROMPT_NAME", "shareholding_pattern")
SIMPLE_EXTRACTION_PROMPT_NAME = os.getenv("SIMPLE_EXTRACTION_PROMPT_NAME", "simple_extraction")

# -- File Processing --
FINANCIALS_SHEET_NAME = os.getenv("FINANCIALS_SHEET_NAME", "Financials")
HEADER_ROW = int(os.getenv("HEADER_ROW", 2))
DATA_START_ROW = int(os.getenv("DATA_START_ROW", 3))
