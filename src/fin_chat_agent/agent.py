import os
import asyncio
import google.adk.agents as agents
from google.genai import types
from dotenv import load_dotenv
from vertexai.agent_engines import AdkApp  # <--- The magic import

# # Import tools (ensure this path is correct)
# # try:
# #     from .tools import list_uploaded_documents, read_document_content
# # except ImportError:
# #     # Safe fallback for local testing if tools aren't found
# #     print("WARNING: Tools not found. Using placeholders.")
# #     list_uploaded_documents = None
# #     read_document_content = None

# # ADK Imports
# from google.adk.runners import Runner
# from google.adk.sessions.in_memory_session_service import InMemorySessionService
# # For production, uncomment and use FirestoreSessionService:
# # from google.adk.sessions.firestore_session_service import FirestoreSessionService

# Load environment variables
load_dotenv()

PROJECT = os.getenv("PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION")
MODEL_NAME = os.getenv("GEMINI_PRO_MODEL", "gemini-1.5-pro-002")






if not PROJECT or not LOCATION:
    print("WARNING: PROJECT and LOCATION not fully set. Agent execution may fail.")

# Set standard Google Cloud env vars
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT or ""
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION or ""
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "1"
os.environ["VERTEXAI"] = "true"


import os
import logging
from google.cloud import storage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_bucket():
    """Lazily initializes and returns the GCS bucket."""
    try:
        storage_client = storage.Client()
        bucket_name = os.getenv("GCS_BUCKET_NAME", "indusind-cam")
        return storage_client.bucket(bucket_name)
    except Exception as e:
        logger.error(f"Failed to initialize GCS client: {e}")
        return None

def list_uploaded_documents(company_name: str, category: str = None) -> str:
    """
    Lists the uploaded documents for a specific company in the GCS bucket.
    
    Args:
        company_name (str): The name of the company (e.g., "Uno Minda").
        category (str, optional): Filter by category (e.g., "annual_reports", "earnings_call").
    
    Returns:
        str: A list of available files or an error message.
    """
    bucket = get_bucket()
    if not bucket:
        return "Error: GCS storage is not operational."

    prefix = f"companies/{company_name}/"
    if category:
        prefix += f"{category}/"

    try:
        blobs = list(bucket.list_blobs(prefix=prefix))
        if not blobs:
            return f"No documents found for '{company_name}'" + (f" in category '{category}'" if category else "") + "."
        
        file_list = []
        for blob in blobs:
            # Skip folders
            if blob.name.endswith('/'):
                continue
            file_list.append(blob.name)
            
        return "Found the following documents:\n" + "\n".join(file_list)
    except Exception as e:
        return f"Error listing documents: {str(e)}"

def read_document_content(company_name: str, filename: str) -> str:
    """
    Reads the content of a specific document for a company from GCS.
    Supports .txt, .md, .pdf (text extraction).
    
    Args:
        company_name (str): The name of the company.
        filename (str): The full GCS path or filename (e.g., "companies/Uno Minda/annual_reports/report.pdf").
                        If just filename is provided, it attempts to find it under the company folder.
    
    Returns:
        str: The content of the document or an error message.
    """
    bucket = get_bucket()
    if not bucket:
        return "Error: GCS storage is not operational."
    
    # improved path resolution
    blob_path = filename
    if not filename.startswith(f"companies/{company_name}"):
        # User provided just the filename? We need to find it? 
        # For safety/simplicity, we assume the user picks from the list which gives full paths usually.
        # But if they say "read the annual report", we might need to search.
        # Let's assume the List tool returns full paths, so the model passes full paths.
        if not filename.startswith("companies/"):
             blob_path = f"companies/{company_name}/{filename}" # Guessing
    
    blob = bucket.blob(blob_path)
    if not blob.exists():
        return f"File not found: {blob_path}"

    try:
        content_type = blob.content_type
        if not content_type:
            # Guess based on extension
            if blob.name.endswith(".pdf"):
                content_type = "application/pdf"
            elif blob.name.endswith(".md") or blob.name.endswith(".txt"):
                content_type = "text/plain"

        if content_type == "application/pdf" or blob.name.endswith(".pdf"):
             # PDF Handling
             # Download to tmp
             import tempfile
             import pdfplumber
             
             with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                 blob.download_to_filename(tmp.name)
                 text = ""
                 with pdfplumber.open(tmp.name) as pdf:
                     # Limit to first 50 pages or similar to avoid overload?
                     # Or read all. Let's read all but catch size.
                     for i, page in enumerate(pdf.pages):
                         extracted = page.extract_text()
                         if extracted:
                             text += f"\n--- Page {i+1} ---\n{extracted}"
                 return text
        else:
             # Text Handling
             return blob.download_as_text()
             
    except Exception as e:
        return f"Error reading document: {str(e)}"



# Define the root agent
root_agent = agents.Agent(
    name="financial_analyst_agent",
    model=MODEL_NAME,
    description="A specialized financial analyst agent that can access and analyze company documents.",
    instruction=(
        "You are an expert financial analyst assistant. "
        "Your primary goal is to help users analyze company documents such as Annual Reports and Financial Statements. "
        "ALWAYS ask for the 'Company Name' first if it is not provided. "
        "Use `list_uploaded_documents` to see what is available before reading with `read_document_content`."
    ),
    tools=[list_uploaded_documents, read_document_content]
)

# # --- THE NEW DEPLOYMENT WRAPPER ---
# # AdkApp automatically handles:
# # 1. Sessions (VertexAiSessionService in cloud, InMemory locally)
# # 2. Async/Sync execution
# # 3. Telemetry (Tracing)
app = AdkApp(
    agent=root_agent,
    enable_tracing=True  # <--- Enables OpenTelemetry automatically!
)