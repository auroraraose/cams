# Financial Data Extraction and Analysis Platform

## 1. Project Overview

This platform is a comprehensive solution designed to automate the process of credit analysis for financial institutions. It ingests a variety of unstructured financial documents for a given company (or "Entity"), leverages the **Google Gemini AI API** to perform a multi-faceted analysis, and generates a structured, downloadable **Credit Appraisal Memo (CAM)** in DOCX format.

The primary goal is to significantly reduce the manual effort involved in data extraction and analysis, allowing financial analysts to focus on higher-level decision-making.

## 2. Architecture Overview

![Architecture Flow](docs/Architecture.png)

The application is built on a modern, decoupled architecture:

-   **Frontend:** A static web interface (HTML/JS/CSS) providing a dashboard for entity management, analysis visualization, and an **AI Assistant Sidebar** for conversational queries.
-   **Backend:** A robust **FastAPI** service handling business logic, document processing, and analysis orchestration.
-   **AI Agent Service (ADK):** A dedicated microservice built with the **Google AI SDK (ADK)** and deployed as a **Vertex AI Reasoning Engine**, providing a conversational agent grounded in the company's financial documents.
-   **Google Cloud Storage (GCS):** The central repository for all documents (Annual Reports, Earnings Calls), extracted data (JSON), and generated reports (HTML/DOCX).
-   **Google Gemini Models:**
    -   **Gemini 2.5 Flash:** High-speed extraction, summarization, and quantitative analysis.
    -   **Gemini 2.5 Pro:** Complex reasoning, industry research, and strategic analysis.

For a detailed breakdown, please see the [Architecture Document](docs/architecture.md).

## 3. Setup and Configuration

### Local Environment Setup

1.  **Clone the Repository:**
    ```bash
    git clone https://gitlab.com/google-cloud-ce/communities/APAC-Solutions-Acceleration/indusind-cam.git
    cd indusind-cam
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Pandoc:**
    The application uses `pypandoc` for document conversion. Ensure Pandoc is installed on your system.
    -   **Mac:** `brew install pandoc`
    -   **Linux:** `sudo apt-get install pandoc`

5.  **Configure Environment Variables:**
    -   Copy the example environment file: `cp .env.example .env`
    -   Edit `.env` with your Google Cloud details.

### `.env` Configuration

| Variable | Description | Example |
| :--- | :--- | :--- |
| `PROJECT` | Google Cloud Project ID. | `my-gcp-project` |
| `LOCATION` | GCP Region. | `us-central1` |
| `GCS_BUCKET_NAME` | Storage bucket name. | `my-financial-data` |
| `GEMINI_FLASH_MODEL` | Model for fast tasks. | `gemini-2.0-flash` |
| `GEMINI_PRO_MODEL` | Model for reasoning tasks. | `gemini-2.5-pro` |

## 4. Application Workflow

### Core Pipeline

1.  **Create Entity:** User creates a company profile in the dashboard.
2.  **Upload Documents:** User uploads PDFs (Annual Reports, Returns) and Audio (Earnings Calls).
3.  **Modular Generation:** User triggers specific analysis sections:
    -   **Financial Commentary:** Trends and ratio analysis.
    -   **Borrower Profile:** Business model and background.
    -   **Media Monitoring:** Live Adverse Media checks via Google Search.
    -   **SWOT Analysis:** Strategic assessment.
    -   **Forensics:** Red flag detection.
    -   **Industry Analysis:** Competitive landscape research.
4.  **Assembly:** The system stitches these modular reports into a final `Credit_Memo.docx` using a standardized template.



## 5. Deployment

### Backend (Cloud Run)

```bash
./deploy.sh
```
Deploys the FastAPI backend to Cloud Run.


## 6. GCS Structure

The application maintains a structured data hierarchy in Google Cloud Storage:
for data extraction the prompts and field extraction is stored in GCS bucket. Prompts for each section of CAM is in the /prompts folder in the code.

```
[BUCKET_NAME]/
├── config/
│   └── fieldstoextract-financials.json       # JSON 
├── prompts/
│   ├── simple_extraction.txt
│   └── year_extract.txt # Prompts for data extraction
└── companies/
    └── {Company Name}/
        ├── metadata.json          # Entity details (Industry, CIN, etc.)
        ├── annual_reports/        # Uploaded Annual Report PDFs
        ├── financial_reports/     # Detailed Financial Statement PDFs
        ├── earnings_recording/    # Mp3/Wav Audio files for Earnings Calls
        ├── extracted_json/        # Raw JSON data extracted by Gemini (Yearly dicts)
        ├── updated_json/          # User-edited JSON data (Overrides extracted)
        ├── spreadsheet/           # Generated Excel Financial Models (.xlsx)
        └── memo/                  # Generated Analysis Reports
            ├── {Company}_financial_commentary.md   # Intermediate analysis
            ├── {Company}_swot.md                   # Intermediate analysis
            ├── ...                                 # Other section files
            └── {Company}_credit_memo.docx          # FINAL ASSEMBLED DOCUMENT
```
