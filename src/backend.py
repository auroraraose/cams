from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import Response, FileResponse
from starlette.background import BackgroundTask
from starlette.staticfiles import StaticFiles
import shutil
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import tempfile
import os
import json
import logging
from datetime import datetime
from .data_extractor import extract_financial_data
from .update_excel import update_excel
from .gcs_storage import get_gcs_manager
# from .models import AnalysisRequest
# from .services import generate_comprehensive_analysis
from . import financial_commentary
# from .services import generate_comprehensive_analysis
from . import financial_commentary
from .chat_service import ChatService
from fastapi.responses import StreamingResponse
# from .generate_report import generate_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year

# --- FastAPI App ---
app = FastAPI(title="Financial Data Extraction API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# STEP 1: UPLOAD PDF
@app.post("/upload-pdf/")
async def upload_pdf(pdf_file: UploadFile = File(...), company_name: str = Form(...), year: int = Form(...)):
    company_name = " ".join(company_name.strip().split())
    """Step 1: Upload PDF and save temporarily"""
    try:
        if not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        content = await pdf_file.read()
        temp_file.write(content)
        temp_file.close()
        
        logger.info(f"PDF uploaded: {pdf_file.filename} for {company_name} year {year}")
        
        return {
            "success": True,
            "message": "PDF uploaded successfully",
            "temp_path": temp_file.name,
            "filename": pdf_file.filename,
            "company_name": company_name,
            "year": year
        }
        
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

async def _process_pdf_extraction(gcs, company_name: str, blob, force_refresh: bool, processed_years: set):
    """
    Helper to process a single PDF blob from GCS.
    - downloads only if needed (optimization can be added here if we had metadata, but user asked to use LLM)
    - extracts data
    - saves to GCS (if year not already processed)
    """
    try:
        # Download to temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        blob.download_to_filename(temp_file.name)
        temp_path = temp_file.name
        
        # Extract data (auto-detect year)
        # Pass processed_years to skip redundant extraction for already processed years
        results = extract_financial_data(temp_path, year=None, processed_years=processed_years)
        
        os.unlink(temp_path) # Clean up temp file immediately
        
        if not results:
             logger.warning(f"No data extracted from {blob.name}")
             return {"status": "failed", "file": blob.name, "message": "No data extracted"}

        saved_records = []
        
        if isinstance(results, dict):
            # Results is {year: data}
            for year, data in results.items():
                # Duplicate Check: If year already processed in this batch, ignore
                if year in processed_years:
                    logger.info(f"Skipping duplicate year {year} found in {blob.name}")
                    continue

                if not force_refresh and gcs.company_data_exists(company_name, year):
                    # Also check against GCS if not forced
                    logger.info(f"Skipping save for {year} from {blob.name}: Data already exists in GCS.")
                    processed_years.add(year) # Mark as processed so we don't try again
                    continue
                    
                # Save extracted data
                structured_data = {
                    "company_name": company_name,
                    "year": year,
                    "extracted_data": data,
                    "extraction_timestamp": datetime.now().isoformat(),
                    "source_file": blob.name
                }
                blob_saved = gcs.save_company_data(company_name, year, structured_data, is_updated=False)
                saved_records.append(blob_saved)
                processed_years.add(year)
                logger.info(f"Saved extracted data for {year} from {blob.name}")

        status = "processed" if saved_records else "skipped_all"
        return {"status": status, "file": blob.name, "saved_records": saved_records}

    except Exception as e:
        logger.error(f"Error processing {blob.name}: {e}")
        return {"status": "error", "file": blob.name, "error": str(e)}

@app.post("/upload-pdf/")
async def upload_pdf(
    company_name: str = Form(...),
    folder: str = Form("annual_reports"),
    pdf_file: UploadFile = File(...)
):
    company_name = " ".join(company_name.strip().split())
    """Upload PDF to specific GCS folder (annual_reports or detailed_reports)"""
    try:
        if not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        gcs = get_gcs_manager()
        
        # Save to GCS
        blob_name = gcs.save_uploaded_file(company_name, folder, pdf_file)
        
        return {
            "success": True,
            "message": "PDF uploaded successfully",
            "blob_name": blob_name,
            "company_name": company_name,
            "folder": folder
        }
        
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/extract/")
async def extract_data(company_name: str = Form(...), force_refresh: bool = Form(False)):
    company_name = " ".join(company_name.strip().split())
    """
    Priority Extraction:
    1. Check 'detailed_reports'. If files exist -> Extract from them & IGNORE 'annual_reports'.
    2. Else -> Extract from 'annual_reports'.
    3. Ignore duplicate years (first found wins).
    """
    try:
        logger.info(f"Starting Priority Extraction for {company_name} (Force Refresh: {force_refresh})")
        gcs = get_gcs_manager()
        
        processed_years = set()
        summary = {"processed": 0, "skipped": 0, "errors": 0, "details": [], "source": ""}

        # 1. Check Detailed Reports (in 'financial_reports' folder)
        detailed_blobs = gcs.list_files(company_name, "financial_reports")
        # Filter for PDFs
        detailed_blobs = [b for b in detailed_blobs if b.name.lower().endswith('.pdf')]

        blobs_to_process = []
        
        if detailed_blobs:
            logger.info(f"Detailed Reports found in 'financial_reports' ({len(detailed_blobs)}). Ignoring Annual Reports.")
            blobs_to_process = detailed_blobs
            summary["source"] = "financial_reports"
        else:
            logger.info("No Detailed Reports found. Scanning Annual Reports.")
            annual_blobs = gcs.list_files(company_name, "annual_reports")
            blobs_to_process = [b for b in annual_blobs if b.name.lower().endswith('.pdf')]
            summary["source"] = "annual_reports"
        
        if not blobs_to_process:
             raise HTTPException(status_code=404, detail="No PDF files found to extract.")

        for blob in blobs_to_process:
            result = await _process_pdf_extraction(gcs, company_name, blob, force_refresh, processed_years)
            
            summary["details"].append(result)
            if result["status"] == "processed":
                summary["processed"] += 1
            elif result["status"] in ["skipped", "skipped_all"]:
                 summary["skipped"] += 1
            elif result["status"] == "error":
                 summary["errors"] += 1

        return {
             "success": True,
             "message": f"Extraction complete from {summary['source']}.",
             "summary": summary
        }


        
    except Exception as e:
        logger.error(f"Error extracting data: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

# STEP 1 (Multi-Year): UPLOAD PDF
@app.post("/upload-pdf-multi-year/")
async def upload_pdf_multi_year(pdf_file: UploadFile = File(...), company_name: str = Form(...)):
    company_name = " ".join(company_name.strip().split())
    """Step 1 (Multi-Year): Upload PDF and save temporarily without requiring year"""
    try:
        if not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        content = await pdf_file.read()
        temp_file.write(content)
        temp_file.close()
        
        logger.info(f"PDF uploaded (multi-year): {pdf_file.filename} for {company_name}")
        
        return {
            "success": True,
            "message": "PDF uploaded successfully",
            "temp_path": temp_file.name,
            "filename": pdf_file.filename,
            "company_name": company_name
        }
        
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# STEP 2 (Multi-Year): EXTRACT DATA
@app.post("/extract-multi-year/")
def extract_multi_year_data(temp_path: str = Form(...), company_name: str = Form(...)):
    company_name = " ".join(company_name.strip().split())
    """Step 2 (Multi-Year): Extract data from PDF for ALL discovered years and save to GCS"""
    try:
        if not os.path.exists(temp_path):
            raise HTTPException(status_code=400, detail="PDF file not found")
        
        # Extract data (year=None triggers multi-year logic)
        results = extract_financial_data(temp_path, year=None)
        
        if not results:
            raise HTTPException(status_code=500, detail="Failed to extract data from PDF")
        
        # Results should be a dict of {year: data}
        saved_blobs = []
        extracted_years = []

        gcs = get_gcs_manager()
        
        if isinstance(results, dict):
             for year_key, data in results.items():
                try:
                    # Construct structured data for this year
                    structured_data = {
                        "company_name": company_name,
                        "year": year_key,
                        "extracted_data": data,
                        "extraction_timestamp": datetime.now().isoformat()
                    }
                    
                    # Save to GCS
                    blob_name = gcs.save_company_data(company_name, year_key, structured_data, is_updated=False)
                    saved_blobs.append(blob_name)
                    extracted_years.append(year_key)
                    logger.info(f"Data saved for {year_key}: {blob_name}")
                         
                except Exception as loop_err:
                    logger.error(f"Error processing year {year_key}: {loop_err}")

        # Clean up temp file
        os.unlink(temp_path)
        
        if not saved_blobs:
             raise HTTPException(status_code=500, detail="Extraction produced results but failed to save any years.")

        return {
            "success": True,
            "message": "Data extracted and saved successfully for multiple years",
            "years": extracted_years,
            "saved_blobs": saved_blobs
        }
        
    except Exception as e:
        logger.error(f"Error extracting data (multi-year): {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

# STEP 3: LOAD DATA
@app.get("/load-data/")
async def load_data(company_name: str, year: int, is_updated: bool = False):
    """Step 3: Load data from GCS for display"""
    try:
        gcs = get_gcs_manager()
        data = gcs.load_company_data(company_name, year, is_updated)
        
        if not data:
            raise HTTPException(status_code=404, detail="Data not found")
        
        return {
            "success": True,
            "data": data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load data: {str(e)}")

@app.get("/load-all-data/")
async def load_all_data(company_name: str):
    """Load all yearly data for a company from GCS."""
    try:
        gcs = get_gcs_manager()
        data = gcs.load_all_company_data(company_name)
        
        if not data:
            raise HTTPException(status_code=404, detail="No data found for this company.")
        
        return {
            "success": True,
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading all data for {company_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load data: {str(e)}")

# STEP 4A: SAVE UPDATED DATA
@app.post("/save-updated-data/")
async def save_updated_data(company_name: str = Form(...), year: int = Form(...), data: str = Form(...)):
    company_name = " ".join(company_name.strip().split())
    """Step 4a: Save updated JSON to GCS"""
    try:
        updated_data = json.loads(data)
        
        gcs = get_gcs_manager()
        blob_name = gcs.save_company_data(company_name, year, updated_data, is_updated=True)
        
        logger.info(f"Updated data saved to GCS: {blob_name}")
        
        return {
            "success": True,
            "message": "Updated data saved successfully",
            "blob_name": blob_name
        }
        
    except Exception as e:
        logger.error(f"Error saving updated data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save data: {str(e)}")

class UpdateExcelRequest(BaseModel):
    company_name: str
    years: List[int]


class GenerateSheetRequest(BaseModel):
    company_name: str
    updated_data: Dict[str, Any] = {}

@app.post("/generate-and-download-spreadsheet/")
def generate_and_download_spreadsheet(request: GenerateSheetRequest):
    """Saves updated data, generates a spreadsheet, and returns it for download."""
    try:
        gcs = get_gcs_manager()
        company_name = request.company_name
        updated_data = request.updated_data

        if updated_data:
            # 1. Save updated data for each year
            for year_str, year_data in updated_data.items():
                year = int(year_str)
                full_year_data = {
                    "company_name": company_name,
                    "year": year,
                    "extracted_data": year_data,
                    "last_updated": datetime.now().isoformat()
                }
                gcs.save_company_data(company_name, year, full_year_data, is_updated=True)
            
            logger.info(f"Saved updated data for {company_name}")

            # 2. Generate spreadsheet
            years_list = [int(y) for y in updated_data.keys()]
            template_path = gcs.download_template()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_output:
                update_excel(updated_data, template_path, temp_output.name, years_list=years_list)
                temp_output_path = temp_output.name
            
            os.unlink(template_path)
            
            # 3. Save the generated spreadsheet to GCS
            blob_name = gcs.save_excel_report(company_name, temp_output_path)
            logger.info(f"Saved generated spreadsheet to GCS for {company_name} as {blob_name}")
        else:
             # If no updated data, just regenerate/ensure spreadsheet exists from GCS data
             temp_output_path = _generate_spreadsheet_if_needed(company_name)

        download_filename = f"{company_name}_financials.xlsx"

        # 4. Return for download
        return FileResponse(
            path=temp_output_path,
            filename=download_filename,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            background=BackgroundTask(os.unlink, temp_output_path)
        )
    except Exception as e:
        logger.error(f"Error in /generate-and-download-spreadsheet/ endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Spreadsheet generation failed: {str(e)}")

@app.get("/list-all-documents/")
async def list_all_documents(company_name: str):
    """
    List all documents for a company from various GCS folders.
    """
    try:
        gcs = get_gcs_manager()
        documents = []
        
        # Define folders to map (folder_name -> display_type)
        folder_mapping = {
            "annual_reports": "Annual Report",
            "financial_reports": "Financial Report",
            "earnings_recording": "Earnings Call",
            "memo": "Generated Memo"
        }

        for folder, display_type in folder_mapping.items():
            blobs = gcs.list_files(company_name, folder)
            for blob in blobs:
                # Skip directories
                if blob.name.endswith('/'):
                    continue
                    
                filename = os.path.basename(blob.name)
                
                # Filter memo folder to only show the final credit memo
                if folder == "memo":
                    expected_name = f"{company_name}_credit_memo.docx"
                    if filename != expected_name:
                        continue

                # Determine "upload date" (blob.updated)
                updated_dt = blob.updated
                date_str = updated_dt.strftime("%Y-%m-%d") if updated_dt else "Unknown"
                
                documents.append({
                    "name": filename,
                    "type": display_type,
                    "upload_date": date_str,
                    "status": "Available",
                    "folder": folder, # needed for download
                    "filename": filename # needed for download
                })

        # Sort by date descending
        documents.sort(key=lambda x: x["upload_date"], reverse=True)
        
        return {"documents": documents}

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-document/")
async def download_document(company_name: str, folder: str, filename: str):
    """
    Generic download endpoint for company documents.
    """
    try:
        gcs = get_gcs_manager()
        blob_name = f"companies/{company_name}/{folder}/{filename}"
        blob = gcs.bucket.blob(blob_name)
        
        if not blob.exists():
             raise HTTPException(status_code=404, detail="File not found")
             
        # Create temp file
        import mimetypes
        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            blob.download_to_filename(temp_file.name)
            temp_path = temp_file.name
            
        # Determine media type
        media_type, _ = mimetypes.guess_type(filename)
        if not media_type:
            media_type = "application/octet-stream"
            
        return FileResponse(
            path=temp_path,
            filename=filename,
            media_type=media_type,
            background=BackgroundTask(os.unlink, temp_path)
        )

    except Exception as e:
        logger.error(f"Error downloading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-and-download-credit-memo/")
def generate_and_download_credit_memo(request: GenerateSheetRequest):
    """
    Saves updated data, generates a new spreadsheet and credit memo,
    saves them to GCS, and returns the memo for download.
    """
    memo_local_path = None
    try:
        gcs = get_gcs_manager()
        company_name = request.company_name
        updated_data = request.updated_data

        if updated_data:
            # 1. Save updated data
            for year_str, year_data in updated_data.items():
                year = year_str  # Keep as string
                full_year_data = {
                    "company_name": company_name,
                    "year": year,
                    "extracted_data": year_data,
                    "last_updated": datetime.now().isoformat()
                }
                gcs.save_company_data(company_name, year, full_year_data, is_updated=True)
            
            # 2. Generate a new spreadsheet with the updated data
            years_list = list(updated_data.keys())  # Keep as strings
            template_path = gcs.download_template()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_sheet:
                update_excel(updated_data, template_path, temp_sheet.name, years_list=years_list)
                spreadsheet_path = temp_sheet.name
            os.unlink(template_path)
            gcs.save_excel_report(company_name, spreadsheet_path)
        else:
            # Use existing data/spreadsheet if no updates provided
            _generate_spreadsheet_if_needed(company_name)

        # 3. Run the comprehensive analysis to generate a new credit memo
        # The analysis service will automatically use the latest spreadsheet from GCS
        # memo_gcs_path = generate_comprehensive_analysis(company_name, "") # document_directory is not used, can be empty
        logger.info("Running Financial Commentary Pipeline...")
        memo_gcs_path = financial_commentary.generate_memo(company_name)
        
        # 4. Download the newly generated memo for the user
        # Expectation: generate_memo returns something like "companies/Uno Minda/memo/Uno Minda_credit_memo.docx"
        # download_credit_memo_report expects company_name and looks for "companies/{company_name}/memo/{company_name}_credit_memo.docx"
        
        memo_local_path = gcs.download_credit_memo_report(company_name, as_text=False)
        download_filename = f"{company_name}_credit_memo.docx"

        return FileResponse(
            path=memo_local_path,
            filename=download_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            background=BackgroundTask(os.unlink, memo_local_path)
        )

    except Exception as e:
        logger.error(f"Error in /generate-and-download-credit-memo/ endpoint: {e}")
        import traceback
        traceback.print_exc()
        if memo_local_path and os.path.exists(memo_local_path):
            os.unlink(memo_local_path)
        raise HTTPException(status_code=500, detail=f"Credit memo generation failed: {str(e)}")


def _generate_spreadsheet_if_needed(company_name: str) -> str:
    """
    Checks for an existing spreadsheet and generates one if not found.
    Returns the local path to the spreadsheet.
    """
    gcs = get_gcs_manager()
    spreadsheet_path = gcs.download_excel_report(company_name)

    if spreadsheet_path:
        logger.info(f"Found existing spreadsheet for {company_name}")
        return spreadsheet_path

    logger.info(f"No spreadsheet found for {company_name}. Generating a new one.")
    
    # If no spreadsheet exists, generate it from the latest data
    all_years_data = gcs.load_all_company_data(company_name)
    if not all_years_data:
        raise HTTPException(status_code=404, detail="No data found to generate spreadsheet.")

    years_list = list(all_years_data.keys())  # Keep as strings
    template_path = gcs.download_template()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp_output:
        update_excel(all_years_data, template_path, temp_output.name, years_list=years_list)
        new_spreadsheet_path = temp_output.name
    
    os.unlink(template_path)
    gcs.save_excel_report(company_name, new_spreadsheet_path)
    logger.info(f"Generated and saved new spreadsheet for {company_name}")
    
    return new_spreadsheet_path

@app.get("/download-spreadsheet/")
def download_spreadsheet(company_name: str):
    """
    Downloads the latest spreadsheet from GCS. If it doesn't exist,
    it generates one from the available data.
    """
    try:
        spreadsheet_path = _generate_spreadsheet_if_needed(company_name)
        download_filename = f"{company_name}_financials.xlsx"

        return FileResponse(
            path=spreadsheet_path,
            filename=download_filename,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            background=BackgroundTask(os.unlink, spreadsheet_path)
        )
    except Exception as e:
        logger.error(f"Error in download_spreadsheet endpoint for {company_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to provide spreadsheet: {str(e)}")


def _generate_credit_memo_if_needed(company_name: str) -> str:
    """
    Checks for an existing credit memo and generates one if not found.
    Returns the local path to the credit memo.
    """
    gcs = get_gcs_manager()
    memo_path = gcs.download_credit_memo_report(company_name, as_text=False)

    if memo_path:
        logger.info(f"Found existing credit memo for {company_name}")
        return memo_path

    logger.info(f"No credit memo found for {company_name}. Generating a new one.")
    
    # Ensure a spreadsheet exists first, as it's needed for the analysis
    _generate_spreadsheet_if_needed(company_name)
    
    # Run the comprehensive analysis to generate a new credit memo (using Financial Commentary pipeline)
    logger.info("Running Financial Commentary Pipeline (Fallback Generation)...")
    financial_commentary.generate_memo(company_name)
    
    # Download the newly created memo
    new_memo_path = gcs.download_credit_memo_report(company_name, as_text=False)
    if not new_memo_path:
        raise HTTPException(status_code=500, detail="Failed to generate and retrieve credit memo.")
        
    logger.info(f"Generated and saved new credit memo for {company_name}")
    return new_memo_path

@app.get("/download-credit-memo/")
def download_credit_memo(company_name: str):
    """
    Downloads the latest credit memo from GCS. If it doesn't exist,
    it generates one from the available data.
    """
    memo_path = None
    try:
        memo_path = _generate_credit_memo_if_needed(company_name)
        download_filename = f"{company_name}_credit_memo.docx"
        
        return FileResponse(
            path=memo_path,
            filename=download_filename,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            background=BackgroundTask(os.unlink, memo_path)
        )
        
    except Exception as e:
        logger.error(f"Error in download_credit_memo endpoint for {company_name}: {e}")
        if memo_path and os.path.exists(memo_path):
            os.unlink(memo_path)
        raise HTTPException(status_code=500, detail=f"Failed to provide credit memo: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy"}

@app.get("/test-health")
async def test_health_check():
    """Test health check"""
    return {"status": "test-healthy"}

@app.post("/generate-analysis/")
async def create_analysis(payload: dict = Body(...)):
    """
    Runs the comprehensive analysis pipeline and returns the path to the generated report.
    """
    try:
        company_name = payload.get("company_name")
        document_directory = payload.get("document_directory")
        if not company_name or not document_directory:
            raise HTTPException(status_code=400, detail="Missing company_name or document_directory")
            
        # report_path = generate_comprehensive_analysis(company_name, document_directory)
        logger.info("Running Financial Commentary Pipeline (via /generate-analysis/)...")
        report_path = financial_commentary.generate_memo(company_name)
        return {"message": "Analysis completed successfully", "report_path": report_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (ValueError, IOError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.post("/prepare-analysis-docs/")
async def prepare_analysis_docs(files: List[UploadFile] = File(...), company_name: str = Form(...)):
    """
    Uploads all necessary documents for an analysis, saves them to a unique temp directory,
    and returns the path to that directory.
    """
    try:
        # Create a unique temporary directory for this company's analysis
        temp_dir = tempfile.mkdtemp(prefix=f"{company_name}_")
        
        for file in files:
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"Prepared analysis documents for {company_name} at {temp_dir}")
        
        return {
            "success": True,
            "message": "Documents prepared for analysis.",
            "document_directory": temp_dir
        }
    except Exception as e:
        logger.error(f"Error preparing analysis documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to prepare documents: {str(e)}")

# --- Modular Generation Endpoints ---

class GenerateSectionRequest(BaseModel):
    company_name: str
    section_type: str

@app.post("/generate-section/")
async def generate_section(request: GenerateSectionRequest):
    """
    Generates a specific section of the credit memo.
    """
    company_name = request.company_name
    section_type = request.section_type
    
    logger.info(f"Received request to generate section '{section_type}' for {company_name}")
    
    try:
        result_path = None
        
        if section_type == 'financial_commentary':
            result_path = financial_commentary.generate_financial_commentary(company_name)
        elif section_type == 'credit_rating':
            result_path = financial_commentary.generate_credit_rating(company_name)
        elif section_type == 'risk_policy':
            result_path = financial_commentary.generate_risk_policy(company_name)
        elif section_type == 'business_analysis':
            result_path = financial_commentary.generate_business_analysis(company_name)
        elif section_type == 'industry_analysis':
            result_path = financial_commentary.generate_industry_analysis(company_name)
        elif section_type == 'earnings_call':
            result_path = financial_commentary.generate_earnings_call(company_name)
        elif section_type == 'forensics':
            result_path = financial_commentary.generate_forensics(company_name)
        elif section_type == 'swot':
            result_path = financial_commentary.generate_swot_analysis(company_name)
        elif section_type == 'promoter':
            result_path = financial_commentary.generate_promoter_analysis(company_name)
        elif section_type == 'business_summary':
            result_path = financial_commentary.generate_business_summary(company_name)
        elif section_type == 'financial_summary':
            result_path = financial_commentary.generate_financial_summary(company_name)
        elif section_type == 'borrower_profile':
            result_path = financial_commentary.generate_borrower_profile(company_name)
        elif section_type == 'media_monitoring':
            result_path = financial_commentary.generate_media_monitoring(company_name)
        else:
             raise HTTPException(status_code=400, detail=f"Unknown section type: {section_type}")

        if result_path:
             return {"success": True, "message": f"Section {section_type} generated successfully", "path": result_path}
        else:
             raise HTTPException(status_code=500, detail="Failed to generate section")
    except Exception as e:
        logger.error(f"Error generating section {section_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Chat Endpoints ---

chat_service = ChatService()

class CreateSessionRequest(BaseModel):
    user_id: str = "test_user"

class ChatQueryRequest(BaseModel):
    session_id: str
    message: str
    user_id: str = "test_user"

@app.post("/chat/session")
async def create_chat_session(request: CreateSessionRequest):
    """
    Creates a new chat session with the Vertex AI Reasoning Engine.
    """
    try:
        result = await chat_service.create_session(user_id=request.user_id)
        return {"success": True, "session_id": result["session_id"]}
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/query")
async def chat_query(request: ChatQueryRequest):
    """
    Streams a query response from the chat session.
    """
    try:
        async def event_generator():
            async for chunk in chat_service.stream_query(
                session_id=request.session_id,
                message=request.message,
                user_id=request.user_id
            ):
                # SSE format: data: <content>\n\n
                # Sanitize newlines to avoid breaking SSE format if needed,
                # but standard practice is often just to send data.
                # For simplicity, we'll send raw text chunks and let frontend handle,
                # OR use standard SSE format. Let's use standard SSE.
                import json
                payload = json.dumps({"text": chunk})
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"Failed to stream chat query: {e}")
        raise HTTPException(status_code=500, detail=str(e))



class AssembleMemoRequest(BaseModel):
    company_name: str

@app.post("/assemble-memo/")
async def assemble_memo_endpoint(request: AssembleMemoRequest):
    """
    Assembles the final credit memo from generated sections.
    """
    company_name = request.company_name
    logger.info(f"Received request to assemble memo for {company_name}")
    
    try:
        final_doc_path = financial_commentary.assemble_credit_memo(company_name)
        
        if final_doc_path:
             return {"success": True, "message": "Credit Memo assembled successfully", "path": final_doc_path}
        else:
             raise HTTPException(status_code=500, detail="Failed to assemble credit memo.")
             
    except Exception as e:
        logger.error(f"Error assembling memo: {e}")
        raise HTTPException(status_code=500, detail=f"Memo assembly failed: {str(e)}")

# Endpoint to get companies organized by industry
@app.get("/companies")
async def get_companies():
    """Returns a list of companies organized by industry."""
    try:
        gcs = get_gcs_manager()
        company_names = gcs.list_companies()
        
        companies_by_industry = {}
        for company_name in company_names:
            metadata = gcs.load_company_metadata(company_name)
            industry = metadata.get('industry', 'Unknown') if metadata else 'Unknown'
            
            if industry not in companies_by_industry:
                companies_by_industry[industry] = []
            
            companies_by_industry[industry].append({
                "name": company_name,
                "entity_type": metadata.get('entity_type', 'Unknown') if metadata else 'Unknown'
            })
            
        return companies_by_industry
    except Exception as e:
        logger.error(f"Error fetching companies: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch companies")

# Endpoint to create a new company
@app.post("/create-company")
async def create_company(
    company_name: str = Form(...), 
    industry: str = Form(...),
    entity_type: str = Form(None),
    cin: str = Form(None),
    key_contact: str = Form(None),
    credit_analyst: str = Form(None),
    listed_entity: str = Form("false"),  # Boolean comes as string "true"/"false" from FormData
    facility_details: str = Form(None)   # JSON string
):
    """Creates a new company with metadata."""
    try:
        company_name = " ".join(company_name.strip().split())
        gcs = get_gcs_manager()
        
        # Check if company already exists
        if gcs.company_exists(company_name):
            raise HTTPException(status_code=409, detail="Company already exists")
            
        # Parse facility details
        facility_data = {}
        if facility_details:
            try:
                facility_data = json.loads(facility_details)
            except Exception as e:
                logger.warning(f"Failed to parse facility_details for {company_name}: {e}")

        # Create metadata and save
        metadata = {
            "company_name": company_name,
            "industry": industry,
            "created_at": datetime.now().isoformat(),
            "entity_type": entity_type,
            "cin": cin,
            "key_contact": key_contact,
            "credit_analyst": credit_analyst,
            "listed_entity": listed_entity.lower() == 'true',
            "facility_details": facility_data
        }
        gcs.save_company_metadata(company_name, metadata)
        
        return {"success": True, "message": f"Company '{company_name}' created successfully."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating company: {e}")
        raise HTTPException(status_code=500, detail="Failed to create company")

@app.post("/upload-classified-documents")
async def upload_classified_documents(
    company_name: str = Form(...), 
    metadata: str = Form(...), 
    files: List[UploadFile] = File(...)
):
    """Uploads classified documents to the correct GCS folders."""
    try:
        gcs = get_gcs_manager()
        file_metadata = json.loads(metadata)
        
        metadata_map = {item['filename']: item for item in file_metadata}

        for file in files:
            meta = metadata_map.get(file.filename)
            if not meta:
                continue

            file_type = meta.get('type', 'Other')
            
            if file_type == 'Annual Report':
                folder_name = 'annual_reports'
            elif file_type == 'Annual Return':
                folder_name = 'annual_returns'
            elif file_type == 'Shareholding Pattern':
                folder_name = 'shareholding_pattern'
            elif file_type == 'Detail Financial Report':
                folder_name = 'financial_reports'
            elif file_type == 'Earnings Call Recording':
                folder_name = 'earnings_recording'
            else:
                folder_name = 'other'
            
            gcs.save_uploaded_file(company_name, folder_name, file)

        return {"success": True, "message": "Documents uploaded successfully."}

    except Exception as e:
        logger.error(f"Error uploading classified documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload documents")

@app.get("/view-analysis")
async def view_analysis(company_name: str, type: str = 'industry'):
    """
    Downloads the analysis report from GCS based on the type specified.
    If it doesn't exist, it returns a user-friendly message.
    """
    try:
        gcs = get_gcs_manager()
        safe_company_name = company_name.replace(' ', '_')
        
        if type == 'industry':
            report_name = f"{safe_company_name}_industry_analysis.md"
            analysis_type = "Industry Analysis"
        elif type == 'ratio':
            report_name = f"{safe_company_name}_ratio_analysis.md"
            analysis_type = "Key Ratio Analysis"
        elif type == 'media':
            report_name = f"{safe_company_name}_media_analysis.md"
            analysis_type = "Media Monitoring"
        elif type == 'shareholding':
            report_name = f"{safe_company_name}_shareholding_analysis.md"
            analysis_type = "Shareholding Pattern"
        elif type == 'summary':
            report_name = f"{safe_company_name}_summary.md" 
            analysis_type = "Company Overview"
        elif type == 'business_analysis':
            report_name = f"{safe_company_name}_business_analysis.md"
            analysis_type = "Business Analysis"
        elif type == 'rating':
            report_name = f"{safe_company_name}_credit_rating.md"
            analysis_type = "Credit Rating"
        elif type == 'risk_policy':
            report_name = f"{safe_company_name}_risk_policy.md"
            analysis_type = "Risk Policy"
        elif type == 'financial_profile':
            report_name = f"{safe_company_name}_financial_commentary.md"
            analysis_type = "Financial Profile"
        elif type == 'earnings_call':
            report_name = f"{safe_company_name}_earnings_call.md"
            analysis_type = "Earnings Call Analysis"
        elif type == 'forensics':
            report_name = f"{safe_company_name}_forensics.md"
            analysis_type = "Forensic Analysis"
        elif type == 'swot':
            report_name = f"{safe_company_name}_swot.md"
            analysis_type = "SWOT Analysis"
        elif type == 'promoter':
            report_name = f"{safe_company_name}_promoter.md"
            analysis_type = "Promoter Analysis"
        elif type == 'business_summary':
            report_name = f"{safe_company_name}_summary.md"
            analysis_type = "Business Summary"
        elif type == 'financial_summary':
            report_name = f"{safe_company_name}_fin_summary.md"
            analysis_type = "Financial Summary"
        elif type == 'borrower_profile':
            report_name = f"{safe_company_name}_borrower_profile.md"
            analysis_type = "Borrower Profile"
        elif type == 'media_monitoring':
            report_name = f"{safe_company_name}_media_monitoring.md"
            analysis_type = "Media Monitoring"
        else:
            raise HTTPException(status_code=400, detail="Invalid analysis type specified")

        report_path = gcs.download_markdown_report(company_name, report_name)

        if report_path:
            logger.info(f"Found existing {analysis_type} for {company_name}")
            return FileResponse(
                path=report_path,
                media_type='text/markdown',
                background=BackgroundTask(os.unlink, report_path)
            )

        # If report is not found, return a user-friendly message (as MD or plain text)
        return Response(content=f"# {analysis_type} Not Available\n\nPlease generate the Credit Memo first.", media_type="text/markdown", status_code=404)

    except Exception as e:
        logger.error(f"Error in /view-analysis endpoint for {company_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate or retrieve analysis report: {str(e)}")

@app.delete("/delete-company/{company_name}")
async def delete_company(company_name: str):
    """Deletes a company and all its data from GCS."""
    try:
        gcs = get_gcs_manager()
        if not gcs.company_exists(company_name):
            raise HTTPException(status_code=404, detail="Company not found")
        
        gcs.delete_company_data(company_name)
        return {"success": True, "message": f"Company '{company_name}' deleted successfully."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting company: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete company")

# --- Agent Proxy ---

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"

@app.post("/chat/")
async def chat_proxy(request: ChatRequest):
    """
    Proxies chat requests to the standalone Agent Service.
    Supports both standard HTTP (Cloud Run) and Vertex AI Reasoning Engine.
    """
    # 1. Check for Reasoning Engine ID (ADK Agent Engine)
    agent_resource_id = os.getenv("AGENT_RESOURCE_ID")
    if agent_resource_id:
        try:
            # Use direct REST API to avoid SDK introspection issues with async methods
            import google.auth
            from google.auth.transport.requests import Request
            
            credentials, project_id = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not credentials.valid:
                credentials.refresh(Request())
            
            # Construct URL
            # ID: projects/123/locations/us-central1/reasoningEngines/456
            # Endpoint: https://us-central1-aiplatform.googleapis.com/v1beta1/{ID}:query
            location = "us-central1" # Default or parse from ID
            if "/locations/" in agent_resource_id:
                parts = agent_resource_id.split("/")
                try:
                    loc_idx = parts.index("locations") + 1
                    location = parts[loc_idx]
                except:
                    pass
            
            api_endpoint = f"https://{location}-aiplatform.googleapis.com/v1beta1/{agent_resource_id}:query"
            
            headers = {
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json"
            }
            
            # ADK Agent usually expects {"input": ...} or matches the method signature.
            # method `query(input: str)` -> payload `{"input": "..."}`
            payload = {"input": {"message": request.message}}
            # Also try flat naming if above fails, but usually it's argument based.
            # Assuming agent.query(message=...) -> {"message": ...} vs agent.query(input=...)
            # My agent defines valid tool usage but the entry point is likely generic.
            # ADK default is often `query(input=...)`.
            
            # Note: The error "Unsupported api mode: async" on client suggests the server implementation is async.
            # REST API handles this fine.
            
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(api_endpoint, json=payload, headers=headers, timeout=60.0)
                
                if resp.status_code != 200:
                    # Try alternate payload structure if 400?
                    # But let's log error first.
                    logger.error(f"Reasoning Engine REST Error: {resp.status_code} {resp.text}")
                    raise HTTPException(status_code=resp.status_code, detail=f"Agent call failed: {resp.text}")
                
                result = resp.json()
                # Unpack response. Usually {"output": ...}
                if "output" in result:
                    return {"response": result["output"]}
                else:
                    return {"response": result}

        except Exception as e:
            logger.error(f"Error querying Reasoning Engine (REST): {e}")
            raise HTTPException(status_code=500, detail=f"Agent Engine failed: {str(e)}")

    # 2. Fallback to HTTP URL (Cloud Run / Local)
    agent_url = os.getenv("AGENT_SERVICE_URL")
    if not agent_url:
        # Fallback to localhost:8080 if not set (e.g. local Docker run)
        logger.warning("AGENT_SERVICE_URL/ID not set. Attempting localhost:8080")
        agent_url = "http://localhost:8080"
    
    # Ensure URL ends with /chat
    target_url = f"{agent_url.rstrip('/')}/chat"
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                target_url, 
                json=request.model_dump(), 
                timeout=60.0 # Agent might take time
            )
            
            if response.status_code != 200:
                logger.error(f"Agent service returned {response.status_code}: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Agent service error")
            
            return response.json()
            
    except ImportError:
        logger.error("httpx not installed")
        raise HTTPException(status_code=500, detail="Backend configuration error: httpx missing")
    except Exception as e:
        logger.error(f"Error communicating with agent service: {e}")
        raise HTTPException(status_code=500, detail=f"Agent communication failed: {str(e)}")

# --- Static File Serving ---
# Mount static files for assets (css, js)
app.mount("/static", StaticFiles(directory="src/frontend", html=True), name="static")

@app.get("/")
async def read_index():
    return FileResponse('src/frontend/index.html')

@app.get("/{filename:path}")
async def serve_static(filename: str):
    """
    Serve static files with fallback to index.html for SPA-like routing if needed,
    or just serve the file.
    """
    file_path = f"src/frontend/{filename}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    # If not found, and it's not an API call (already handled), return index?
    # Or just 404. For simplicity/safety vs conflicts/recursion:
    if filename.startswith("api") or filename.startswith("load-") or filename.startswith("upload-"):
         raise HTTPException(status_code=404, detail="Not Found")
         
    return FileResponse('src/frontend/index.html')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
