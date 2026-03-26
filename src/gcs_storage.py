"""
Google Cloud Storage helper module for ICICI Financial Data Extraction Platform.
Handles essential GCS operations for file storage and retrieval.
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from google.cloud import storage
from google.cloud.exceptions import NotFound, Conflict
import tempfile
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GCSStorageManager:
    """Manages essential GCS operations for the ICICI financial data platform."""
    
    def __init__(self):
        """Initialize GCS client and configuration."""
        self.project_id = os.getenv("PROJECT")
        self.bucket_name = os.getenv("GCS_BUCKET_NAME")
        self.location = os.getenv("LOCATION", "us-central1")
        
        if not self.project_id or not self.bucket_name:
            raise ValueError("PROJECT and GCS_BUCKET_NAME must be set in environment variables")
        
        self.client = storage.Client(project=self.project_id)
        self.bucket = None
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self) -> None:
        """Create bucket if it doesn't exist, otherwise get reference to existing bucket."""
        try:
            # Try to get the bucket
            self.bucket = self.client.bucket(self.bucket_name)
            self.bucket.reload()  # Check if bucket exists
            logger.info(f"Using existing GCS bucket: {self.bucket_name}")
            
        except NotFound:
            # Bucket doesn't exist, create it
            logger.info(f"Creating new GCS bucket: {self.bucket_name}")
            try:
                self.bucket = self.client.create_bucket(
                    self.bucket_name,
                    location=self.location
                )
                logger.info(f"Successfully created bucket: {self.bucket_name}")
                
            except Conflict:
                # Bucket name already exists globally (different project)
                logger.error(f"Bucket name {self.bucket_name} already exists globally. Please choose a different name.")
                raise
            except Exception as e:
                logger.error(f"Failed to create bucket: {e}")
                raise
    
    def upload_template(self, local_template_path: str) -> str:
        """Upload spreadsheet template to GCS."""
        if not os.path.exists(local_template_path):
            raise FileNotFoundError(f"Template file not found: {local_template_path}")
        
        blob_name = f"templates/{os.path.basename(local_template_path)}"
        blob = self.bucket.blob(blob_name)
        
        blob.upload_from_filename(local_template_path)
        logger.info(f"Uploaded template to: gs://{self.bucket_name}/{blob_name}")
        
        return blob_name
    
    def upload_fields_config(self, local_fields_path: str) -> str:
        """Upload fieldstoextract.json configuration to GCS."""
        if not os.path.exists(local_fields_path):
            raise FileNotFoundError(f"Fields config file not found: {local_fields_path}")
        
        blob_name = f"config/{os.path.basename(local_fields_path)}"
        blob = self.bucket.blob(blob_name)
        
        blob.upload_from_filename(local_fields_path)
        logger.info(f"Uploaded fields config to: gs://{self.bucket_name}/{blob_name}")
        
        return blob_name
    
    def download_template(self, template_name: str = "CMA_Format_Financials.xlsx") -> str:
        """Download spreadsheet template from GCS to local temp file."""
        blob_name = f"templates/{template_name}"
        logger.info(f"Attempting to download template from blob: gs://{self.bucket_name}/{blob_name}")
        
        try:
            blob = self.bucket.blob(blob_name)
            
            # Diagnostic logging
            blob_exists = blob.exists()
            logger.info(f"Checking for blob existence... Blob exists: {blob_exists}")
            
            if not blob_exists:
                raise FileNotFoundError(f"Template not found in GCS: {blob_name}")
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            blob.download_to_filename(temp_file.name)
            
            logger.info(f"Successfully downloaded template to local path: {temp_file.name}")
            return temp_file.name
            
        except NotFound:
            logger.error(f"NotFound error: Template blob not found at gs://{self.bucket_name}/{blob_name}")
            raise FileNotFoundError(f"Template not found in GCS: {blob_name}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during template download: {e}", exc_info=True)
            raise
    
    def download_fields_config(self, config_name: str = "fieldstoextract-financials.json") -> str:
        """Download fields configuration from GCS to local temp file."""
        blob_name = f"config/{config_name}"
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            raise FileNotFoundError(f"Fields config not found in GCS: {blob_name}")
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w+')
        content = blob.download_as_text()
        temp_file.write(content)
        temp_file.close()
        
        logger.info(f"Downloaded fields config from: gs://{self.bucket_name}/{blob_name}")
        return temp_file.name
    
    def save_company_data(self, company_name: str, year: int, data: Dict[str, Any], is_updated: bool = False) -> str:
        """Save company data (JSON) to GCS."""
        if is_updated:
            folder = "updated_json"
            filename = f"{year}.json"
        else:
            folder = "extracted_json"
            filename = f"{year}.json"
            
        blob_name = f"companies/{company_name}/{folder}/{filename}"
        
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(json.dumps(data, indent=2))
        
        logger.info(f"Saved company data to: gs://{self.bucket_name}/{blob_name}")
        return blob_name
    
    def load_company_data(self, company_name: str, year: int, is_updated: bool = False) -> Optional[Dict[str, Any]]:
        """Load company data (JSON) from GCS."""
        if is_updated:
            folder = "updated_json"
            filename = f"{year}.json"
        else:
            folder = "extracted_json"
            filename = f"{year}.json"
        
        blob_name = f"companies/{company_name}/{folder}/{filename}"
        
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            logger.info(f"Company data not found: gs://{self.bucket_name}/{blob_name}")
            return None
        
        try:
            content = blob.download_as_text()
            data = json.loads(content)
            logger.info(f"Loaded company data from: gs://{self.bucket_name}/{blob_name}")
            return data
        except Exception as e:
            logger.error(f"Failed to load company data: {e}")
            return None

    def company_data_exists(self, company_name: str, year: int) -> bool:
        """Check if extracted data (JSON) exists for a specific year."""
        # Check extracted_json folder
        blob_name = f"companies/{company_name}/extracted_json/{year}.json"
        blob = self.bucket.blob(blob_name)
        if blob.exists():
            return True
        
        # Check updated_json folder (optional, but good for completeness)
        blob_name_updated = f"companies/{company_name}/updated_json/{year}.json"
        blob_updated = self.bucket.blob(blob_name_updated)
        return blob_updated.exists()

    def load_all_company_data(self, company_name: str) -> Dict[str, Any]:
        """Load all yearly data for a company from GCS, prioritizing updated data."""
        all_data = {}
        
        # Load extracted data first
        extracted_prefix = f"companies/{company_name}/extracted_json/"
        extracted_blobs = self.bucket.list_blobs(prefix=extracted_prefix)
        for blob in extracted_blobs:
            try:
                year_str = blob.name.split('/')[-1].replace('.json', '')
                content = blob.download_as_text()
                data = json.loads(content)
                if "extracted_data" in data:
                    all_data[year_str] = data["extracted_data"]
                else:
                    all_data[year_str] = data
            except Exception as e:
                logger.error(f"Failed to load or parse {blob.name}: {e}")

        # Load updated data, overwriting extracted data if it exists
        updated_prefix = f"companies/{company_name}/updated_json/"
        updated_blobs = self.bucket.list_blobs(prefix=updated_prefix)
        for blob in updated_blobs:
            try:
                year_str = blob.name.split('/')[-1].replace('.json', '')
                content = blob.download_as_text()
                data = json.loads(content)
                if "extracted_data" in data:
                    all_data[year_str] = data["extracted_data"]
                else:
                    all_data[year_str] = data
            except Exception as e:
                logger.error(f"Failed to load or parse {blob.name}: {e}")
                
        logger.info(f"Loaded data for {len(all_data)} years for company {company_name}")
        return all_data
    
    def save_spreadsheet_report(self, company_name: str, local_spreadsheet_path: str, is_calculated: bool = False) -> str:
        """Save spreadsheet report to GCS."""
        if not os.path.exists(local_spreadsheet_path):
            raise FileNotFoundError(f"Spreadsheet file not found: {local_spreadsheet_path}")
        
        # Use different naming for calculated vs regular versions
        if is_calculated:
            filename = f"{company_name}_financial_data_calculated.xlsx"
        else:
            filename = f"{company_name}_financial_data.xlsx"
            
        blob_name = f"companies/{company_name}/spreadsheet/{filename}"
        blob = self.bucket.blob(blob_name)
        
        blob.upload_from_filename(local_spreadsheet_path)
        logger.info(f"Saved spreadsheet report to: gs://{self.bucket_name}/{blob_name}")
        
        return blob_name
    
    
    # Backward compatibility aliases
    def save_excel_report(self, company_name: str, local_excel_path: str) -> str:
        """Alias for save_spreadsheet_report for backward compatibility."""
        return self.save_spreadsheet_report(company_name, local_excel_path)
    
    def download_spreadsheet_report(self, company_name: str) -> Optional[str]:
        """Download spreadsheet report from GCS to local temp file. Prefers calculated version."""
        import time
        
        # First try to get calculated version
        calculated_blob_name = f"companies/{company_name}/spreadsheet/{company_name}_financial_data_calculated.xlsx"
        calculated_blob = self.bucket.blob(calculated_blob_name)
        
        if calculated_blob.exists():
            # Create temporary file with timestamp to avoid caching
            timestamp = str(int(time.time()))
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{timestamp}_calculated.xlsx")
            calculated_blob.download_to_filename(temp_file.name)
            
            logger.info(f"Downloaded calculated spreadsheet report from: gs://{self.bucket_name}/{calculated_blob_name}")
            return temp_file.name
        
        # Fallback to regular version
        blob_name = f"companies/{company_name}/spreadsheet/{company_name}_financial_data.xlsx"
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            logger.info(f"Spreadsheet report not found: gs://{self.bucket_name}/{blob_name}")
            return None
        
        # Create temporary file with timestamp to avoid caching
        timestamp = str(int(time.time()))
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{timestamp}.xlsx")
        blob.download_to_filename(temp_file.name)
        
        logger.info(f"Downloaded spreadsheet report from: gs://{self.bucket_name}/{blob_name}")
        return temp_file.name

    def download_excel_report(self, company_name: str) -> Optional[str]:
        """Alias for download_spreadsheet_report for backward compatibility."""
        return self.download_spreadsheet_report(company_name)

    def save_credit_memo_report(self, company_name: str, local_report_path: str) -> str:
        """Save credit memo report to GCS."""
        if not os.path.exists(local_report_path):
            raise FileNotFoundError(f"Credit memo file not found: {local_report_path}")
        
        blob_name = f"companies/{company_name}/memo/{os.path.basename(local_report_path)}"
        blob = self.bucket.blob(blob_name)
        
        blob.upload_from_filename(local_report_path)
        logger.info(f"Saved credit memo report to: gs://{self.bucket_name}/{blob_name}")
        
        return blob_name

    def download_html_report(self, company_name: str, report_name: str) -> Optional[str]:
        """Download an HTML report from GCS to a local temp file."""
        import time
        
        blob_name = f"companies/{company_name}/memo/{report_name}"
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            logger.info(f"HTML report not found: gs://{self.bucket_name}/{blob_name}")
            return None
        
        # Create temporary file with timestamp to avoid caching
        timestamp = str(int(time.time()))
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{timestamp}.html")
        blob.download_to_filename(temp_file.name)
        
        logger.info(f"Downloaded HTML report from: gs://{self.bucket_name}/{blob_name}")
        return temp_file.name

    def download_markdown_report(self, company_name: str, report_name: str) -> Optional[str]:
        """Download a Markdown report from GCS to a local temp file."""
        import time
        
        blob_name = f"companies/{company_name}/memo/{report_name}"
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            logger.info(f"Markdown report not found: gs://{self.bucket_name}/{blob_name}")
            return None
        
        # Create temporary file with timestamp to avoid caching
        timestamp = str(int(time.time()))
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{timestamp}.md")
        blob.download_to_filename(temp_file.name)
        
        logger.info(f"Downloaded Markdown report from: gs://{self.bucket_name}/{blob_name}")
        return temp_file.name

    def download_credit_memo_report(self, company_name: str, as_text: bool = False) -> Optional[str]:
        """Download the latest credit memo report from GCS."""
        import time
        
        # Find the correct file based on the as_text flag
        if as_text:
            # This part remains for potential future use with MD files
            file_name = "credit_assessment_memo.md"
            blob_name = f"companies/{company_name}/memo/{file_name}"
        else:
            file_name = f"{company_name}_credit_memo.docx"
            blob_name = f"companies/{company_name}/memo/{file_name}"

        latest_blob = self.bucket.blob(blob_name)

        if not latest_blob.exists():
            # Fallback for original filename for backward compatibility
            logger.warning(f"Credit memo '{blob_name}' not found. Trying fallback 'final_report.docx'.")
            blob_name = f"companies/{company_name}/memo/final_report.docx"
            latest_blob = self.bucket.blob(blob_name)
            if not latest_blob.exists():
                 logger.error(f"No credit memo DOCX file found for company: {company_name}")
                 return None

        if as_text:
            return latest_blob.download_as_text()
        else:
            # Create temporary file with timestamp to avoid caching
            timestamp = str(int(time.time()))
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{timestamp}_{latest_blob.name.split('/')[-1]}")
            latest_blob.download_to_filename(temp_file.name)
            
            logger.info(f"Downloaded latest credit memo from: gs://{self.bucket_name}/{latest_blob.name}")
            return temp_file.name
    
    # Company metadata operations
    def save_company_metadata(self, company_name: str, metadata: Dict[str, Any]) -> str:
        """Save company metadata to GCS."""
        blob_name = f"companies/{company_name}/metadata.json"
        blob = self.bucket.blob(blob_name)
        
        blob.upload_from_string(json.dumps(metadata, indent=2))
        logger.info(f"Saved company metadata to: gs://{self.bucket_name}/{blob_name}")
        
        return blob_name
    
    def load_company_metadata(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Load company metadata from GCS."""
        blob_name = f"companies/{company_name}/metadata.json"
        blob = self.bucket.blob(blob_name)
        
        if not blob.exists():
            logger.info(f"Company metadata not found: gs://{self.bucket_name}/{blob_name}")
            return None
        
        try:
            content = blob.download_as_text()
            data = json.loads(content)
            logger.info(f"Loaded company metadata from: gs://{self.bucket_name}/{blob_name}")
            return data
        except Exception as e:
            logger.error(f"Failed to load company metadata: {e}")
            return None
    
    def list_companies(self) -> list:
        """List all companies in GCS bucket."""
        try:
            blobs = self.bucket.list_blobs(prefix="companies/")
            company_names = set()
            
            for blob in blobs:
                # Extract company name from path: companies/{company_name}/{file}
                path_parts = blob.name.split('/')
                # Ensure the path is deep enough and the company name part is not empty
                if len(path_parts) > 1 and path_parts[0] == "companies" and path_parts[1]:
                    company_names.add(path_parts[1])
            
            companies = sorted(list(company_names))
            logger.info(f"Found {len(companies)} companies in GCS")
            return companies
        except Exception as e:
            logger.error(f"Failed to list companies: {e}")
            return []
    
    def company_exists(self, company_name: str) -> bool:
        """Check if a company directory exists in GCS."""
        prefix = f"companies/{company_name}/"
        blobs = list(self.bucket.list_blobs(prefix=prefix, max_results=1))
        return len(blobs) > 0

    def delete_company_data(self, company_name: str) -> bool:
        """Delete all data for a specific company from GCS."""
        try:
            prefix = f"companies/{company_name}/"
            blobs = self.bucket.list_blobs(prefix=prefix)
            
            deleted_count = 0
            for blob in blobs:
                blob.delete()
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} files for company '{company_name}' from GCS")
            return True
        except Exception as e:
            logger.error(f"Failed to delete company data for {company_name}: {e}")
            return False

    def save_uploaded_file(self, company_name: str, folder_name: str, uploaded_file, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Save an uploaded file to a specific folder in GCS with optional metadata."""
        blob_name = f"companies/{company_name}/{folder_name}/{uploaded_file.filename}"
        blob = self.bucket.blob(blob_name)
        
        if metadata:
            blob.metadata = metadata
            
        blob.upload_from_file(uploaded_file.file)
        logger.info(f"Saved uploaded file to: gs://{self.bucket_name}/{blob_name} with metadata: {metadata}")
        
        return blob_name

    def list_files(self, company_name: str, folder: str) -> list:
        """List all files in a specific folder for a company."""
        try:
            prefix = f"companies/{company_name}/{folder}/"
            blobs = self.bucket.list_blobs(prefix=prefix)
            return [blob for blob in blobs]
        except Exception as e:
            logger.error(f"Failed to list files for {company_name} in folder {folder}: {e}")
            return []


# Global instance for caching
_gcs_manager_instance = None

def get_gcs_manager() -> GCSStorageManager:
    """Get a cached GCS manager instance, creating it if it doesn't exist."""
    global _gcs_manager_instance
    if _gcs_manager_instance is None:
        try:
            _gcs_manager_instance = GCSStorageManager()
        except ValueError as e:
            logger.error(f"Failed to initialize GCSStorageManager: {e}")
            # Return None or raise an exception to indicate failure
            return None
    return _gcs_manager_instance


def setup_initial_files():
    """Upload initial template and config files to GCS if they exist locally."""
    manager = get_gcs_manager()
    
    # Upload spreadsheet template
    local_template = "data/CMA_Format_Financials.xlsx"
    if os.path.exists(local_template):
        try:
            manager.upload_template(local_template)
            logger.info("Spreadsheet template uploaded to GCS successfully")
        except Exception as e:
            logger.error(f"Failed to upload template: {e}")
    else:
        logger.warning(f"Local template not found: {local_template}")
    
    # Upload fields configuration
    local_fields = "prompts/fieldstoextract.json"
    if os.path.exists(local_fields):
        try:
            manager.upload_fields_config(local_fields)
            logger.info("Fields configuration uploaded to GCS successfully")
        except Exception as e:
            logger.error(f"Failed to upload fields config: {e}")
    else:
        logger.warning(f"Local fields config not found: {local_fields}")


if __name__ == "__main__":
    # Test the GCS manager
    try:
        manager = GCSStorageManager()
        print(f"✅ GCS bucket '{manager.bucket_name}' is ready")
        
        # Upload initial files if available
        setup_initial_files()
        
        print("� GCS setup completed successfully!")
        
    except Exception as e:
        print(f"❌ Error setting up GCS: {e}")
