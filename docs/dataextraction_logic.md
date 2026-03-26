# Data Extraction Logic

The application employs a **Priority-Based Extraction Strategy** to ensure the highest quality of financial data is used for analysis. This logic is handled by the backend `/extract/` endpoint and the `src/data_extractor.py` module.

## 1. Source Document Priority

When the user triggers extraction, the system automatically checks for available documents in Google Cloud Storage (GCS) and prioritizes them as follows:

### Priority A: Detailed Financial Reports
*   **Target Folder:** `financial_reports/`
*   **Logic:** The system first checks for PDF files in the `financial_reports` folder of the specific company.
*   **Behavior:**
    *   **If found:** The system **EXLCUSIVELY** uses these files for data extraction.
    *   **Reasoning:** "Detailed Financial Reports" (often standalone financial statements) are assumed to contain cleaner, more specific data than full Annual Reports.
    *   **Outcome:** The `annual_reports` folder is **IGNORED** to prevent duplicate or lower-quality data extraction.

### Priority B: Annual Reports (Fallback)
*   **Target Folder:** `annual_reports/`
*   **Logic:** If **NO** files are found in `financial_reports`, the system falls back to scanning the `annual_reports` folder.
*   **Behavior:**
    *   **If found:** The system proceeds to extract data from these full Annual Report PDFs.
    *   **Refinement:** The extraction prompt is robust enough to handle the larger context of an Annual Report, but this is considered a secondary source if a focused financial report is available.

## 2. Extraction Verification & Deduplication

Regardless of the source (Priority A or B), the extraction process includes:

*   **Year Detection:** The LLM first scans the document to identify which Fiscal Years are present (e.g., "FY2023", "FY2024").
*   **Deduplication:**
    *   If multiple files contain data for the **same year**, the system processes the **first valid occurrence** and skips subsequent ones for that year.
    *   This prevents overwriting verified data with potential duplicates.
*   **Existing Data Check:**
    *   Before saving, the system checks if data for a specific year already exists in the "Extracted JSON" store.
    *   Unless `Force Refresh` is enabled, existing data is preserved to respect manual edits made by the user.

## 3. Technical Implementation

The logic is implemented in `src/backend.py` (Orchestration) and `src/data_extractor.py` (AI Logic):

```python
# Pseudo-code of backend logic
if exists(financial_reports):
    sources = financial_reports
    ignore(annual_reports)
else:
    sources = annual_reports

for source in sources:
    years = extract_years_from_pdf(source)
    for year in years:
        if not data_exists(year):
             extract_and_save(year, source)
```
