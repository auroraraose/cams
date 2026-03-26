import os
import sys
import json
import re
import logging
from google import genai
from google.genai import types
import pypandoc
from src import config
from src.utils import get_gemini_client, get_gcs_manager, read_prompt, clean_ai_output, call_gemini_model, process_document
# from src.ratio_analysis_html import generate_financial_report_html
# from src.html_converter import convert_html_to_docx_new
# from src.json_to_html import json_to_html
from docxcompose.composer import Composer
from docx import Document
from docxtpl import DocxTemplate

template_path = os.path.join(config.TEMPLATES_DIR, "pypandoc_template.docx")
lua_filter_path = os.path.join(config.SRC_DIR, "table_borders.lua")

def save_json(data, output_dir, filename):
    """Helper to save JSON data to a file."""
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logging.info(f"Saved JSON to {filepath}")
    return filepath

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_financial_report_files(company_name):
    """
    Returns a list of PDF blobs from the Financial Reports GCS folder.
    """
    gcs = get_gcs_manager()
    prefix = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/financial_reports/"
    blobs = list(gcs.bucket.list_blobs(prefix=prefix))
    pdf_blobs = [blob for blob in blobs if blob.name.endswith('.pdf')]
    
    if not pdf_blobs:
        logging.warning(f"No PDF files found in {prefix}")
    else:
        logging.info(f"Found {len(pdf_blobs)} PDF files in {prefix}")
        
    return pdf_blobs

def extract_fiscal_years(company_name):
    """
    Step 1: Identify fiscal years from Extracted JSON files in GCS.
    """
    logging.info("Step 1: Extracting fiscal years from existing JSON files...")
    gcs = get_gcs_manager()
    prefix = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/extracted_json/"
    blobs = list(gcs.bucket.list_blobs(prefix=prefix))
    
    years = []
    for blob in blobs:
        if blob.name.endswith('.json'):
            filename = os.path.basename(blob.name)
            year_label = filename.replace('.json', '')
            years.append(year_label)
            
    # Sort years in descending order (e.g. FY 2024-25 before FY 2023-24)
    # This helps in presenting the latest data first
    years.sort(reverse=True)
    
    years_str = ", ".join(years)
    
    if not years:
        logging.warning(f"No JSON files found in {prefix}. Years list is empty.")
    else:
        logging.info(f"Extracted Years from JSONs: {years_str}")
        
    return years_str

def get_combined_financial_data(company_name):
    """Refactored helper to get financial data from GCS."""
    gcs = get_gcs_manager()
    prefix = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/extracted_json/"
    blobs = list(gcs.bucket.list_blobs(prefix=prefix))
    
    combined_financial_data = {}
    
    for blob in blobs:
        if blob.name.endswith('.json'):
            year_label = os.path.basename(blob.name).replace('.json', '')
            try:
                json_content = json.loads(blob.download_as_string())
                combined_financial_data[year_label] = json_content
            except Exception as e:
                logging.warning(f"Failed to load JSON for {year_label}: {e}")
    return combined_financial_data

def generate_financial_commentary(company_name):
    """
    Standalone function to generate Financial Commentary.
    Fetches inputs, calls AI, saves MD/DOCX/HTML to GCS.
    """
    logging.info(f"--- Generating Financial Commentary for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Extract Years
    years = extract_fiscal_years(company_name)
    combined_data = get_combined_financial_data(company_name)

    prompt_template = read_prompt("financial_commentary.txt")
    prompt_text = prompt_template.replace("{{ discovered_years }}", years)
    prompt_text = prompt_text.replace("{{ financial_data }}", json.dumps(combined_data, indent=2))
    
    try:
        fin_md = call_gemini_model(
            prompt_text=prompt_text,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_financial_commentary.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(fin_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_financial_commentary.html")
        try:
             pypandoc.convert_text(fin_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/financial_commentary.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Financial Commentary Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_financial_commentary.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(fin_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Financial Commentary DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Financial Commentary docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during commentary generation: {e}")
        raise

def generate_credit_rating(company_name):
    """
    Standalone function to generate Credit Rating Analysis.
    """
    logging.info(f"--- Generating Credit Rating for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Financial Reports
    pdf_blobs = get_financial_report_files(company_name)
    if not pdf_blobs:
        logging.warning(f"Skipping Credit Rating: No PDF files found")
        return None

    prompt_text = read_prompt("credit_rating.txt")
    parts = [types.Part.from_text(text=prompt_text)]
    
    for blob in pdf_blobs:
        pdf_data = blob.download_as_bytes()
        parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))

    try:
        rating_md = call_gemini_model(
            prompt_text=None, # Passed in parts
            parts=parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_credit_rating.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(rating_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_credit_rating.html")
        try:
             pypandoc.convert_text(rating_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/credit_rating.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Credit Rating Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_credit_rating.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(rating_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Credit Rating DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Credit Rating docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during credit rating generation: {e}")
        raise

def generate_risk_policy(company_name):
    """
    Standalone function to generate Risk Policy.
    """
    logging.info(f"--- Generating Risk Policy for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Financial Data
    combined_data = get_combined_financial_data(company_name)

    prompt_template = read_prompt("risk_policy.txt")
    prompt_text = prompt_template.replace("{{ financial_data }}", json.dumps(combined_data, indent=2))
    
    try:
        policy_md = call_gemini_model(
            prompt_text=prompt_text,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.5,
            thinking_enabled=True, # Robust config from copy.py
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_risk_policy.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(policy_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_risk_policy.html")
        try:
             pypandoc.convert_text(policy_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/risk_policy.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Risk Policy Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_risk_policy.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(policy_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Risk Policy DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Risk Policy docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during risk policy generation: {e}")
        raise

def get_annual_report_files(company_name):
    """
    Fetches the latest annual report from GCS.
    """
    gcs = get_gcs_manager()
    prefix = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/annual_reports/"
    blobs = list(gcs.bucket.list_blobs(prefix=prefix))
    
    pdf_blobs = [b for b in blobs if b.name.endswith('.pdf')]
    if not pdf_blobs:
        logging.warning(f"No annual reports found in {prefix}")
        return []
        
    logging.info(f"Found {len(pdf_blobs)} Annual Report PDF files in {prefix}")
    # Ideally sort by date if possible, for now just take all or the first one if too many?
    # Usually we just want the latest ONE for business analysis.
    # Let's take the latest uploaded one for now.
    pdf_blobs.sort(key=lambda x: x.updated, reverse=True)
    return [pdf_blobs[0]] if pdf_blobs else []

def generate_business_analysis(company_name):
    """
    Standalone function to generate Business Analysis.
    """
    logging.info(f"--- Generating Business Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Annual Reports
    pdf_blobs = get_annual_report_files(company_name)
    if not pdf_blobs:
         logging.warning(f"Skipping Business Analysis: No Annual Reports found")
         return None

    prompt_text = read_prompt("business_analysis.txt")
    parts = [types.Part.from_text(text=prompt_text)]
    
    for blob in pdf_blobs:
        pdf_data = blob.download_as_bytes()
        parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))

    try:
        analysis_md = call_gemini_model(
            prompt_text=None,
            parts=parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_business_analysis.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(analysis_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_business_analysis.html")
        try:
             pypandoc.convert_text(analysis_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/business_analysis.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Business Analysis Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_business_analysis.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(analysis_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Business Analysis DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Business Analysis docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during business analysis generation: {e}")
        raise



def add_citations_to_text(response):
    """
    Parses groundingMetadata to insert Markdown citations: [Source Title](URL).
    Ensures citations appear at the end of sentences/segments.
    """
    logging.info("Starting add_citations_to_text...")
    candidate = response.candidates[0]
    
    # Check if content exists
    if not candidate.content or not candidate.content.parts:
        logging.warning("No content in response candidate.")
        return ""
        
    text = candidate.content.parts[0].text
    metadata = candidate.grounding_metadata

    if not metadata or not metadata.grounding_supports:
        logging.info("No grounding metadata found. Returning text as is.")
        return text

    logging.info(f"Found {len(metadata.grounding_supports)} grounding supports. Sorting...")

    # Sort supports by end_index in reverse to prevent character offset shifts during insertion
    sorted_supports = sorted(
        metadata.grounding_supports, 
        key=lambda s: s.segment.end_index, 
        reverse=True
    )

    logging.info("Iterating through grounding supports to insert citations...")
    count = 0
    for support in sorted_supports:
        count += 1
        if count % 10 == 0:
            logging.debug(f"Processed {count} supports...")

        original_end = support.segment.end_index
        
        # Ensure we don't go out of bounds
        if original_end > len(text):
            logging.warning(f"Grounding index {original_end} out of bounds for text len {len(text)}")
            original_end = len(text)
        
        # --- Logic to find the true end of the sentence/header/word ---
        # Look ahead from the model's suggested end_index
        look_ahead_text = text[original_end:]
        
        # Regex explanation:
        # Match a sentence terminator (.!?) followed by whitespace or end-of-string or newline
        # OR Match a newline character
        # OR Match the next whitespace (to find word text boundary if no sentence end found)
        match = re.search(r'([.!?](?=\s|$|\n))|(\n)|(\s)', look_ahead_text)
        
        insertion_index = original_end
        
        if match:
            # If we found a punctuation mark (Group 1), insert AFTER it
            if match.group(1):
                insertion_index = original_end + match.end()
            # If we found a newline (Group 2), insert BEFORE it (so it stays on the same line)
            elif match.group(2):
                insertion_index = original_end + match.start()
            # If we found a generic whitespace (Group 3), insert BEFORE it (end of word)
            # But only if we didn't find a better sentence terminator nearby?
            # Actually, standard citation logic:
            # "Word[1] word." -> Inline
            # "Word word.[1]" -> Sentence end
            # Use space match to ensure we don't cut words.
            # But priority is Sentence End if within reasonable distance (e.g. 20 chars? No, model grounding is usually precise about segment)
            # If model says segment ends at "In|dian", we want "Indian[1]".
            # So searching for next \s is the safest minimum move.
            # Searching for next [.!?] might move it too far if the segment was really just one specific fact in a long sentence.
            elif match.group(3):
                 insertion_index = original_end + match.start()
        
        # Clamp insertion_index to text length
        if insertion_index > len(text):
            insertion_index = len(text)

        citation_parts = []
        for index in support.grounding_chunk_indices:
            if index < len(metadata.grounding_chunks):
                chunk = metadata.grounding_chunks[index]
                if chunk.web:
                    uri = chunk.web.uri
                    # Using a standard [index] format for cleaner inline display
                    citation_parts.append(f"[[{index + 1}]]({uri})")

        if citation_parts:
            # Add a leading space if we aren't at the start of a line
            prefix = ""
            # Only add space if we are NOT at the start of a line and previous char is not a space
            if insertion_index > 0 and insertion_index <= len(text):
                 if text[insertion_index-1] not in ["\n", " ", "["]:
                     prefix = " "
            
            citation_string = prefix + "".join(citation_parts)
            # Insert citation
            text = text[:insertion_index] + citation_string + text[insertion_index:]

    logging.info("Finished adding citations.")
    return text

def generate_industry_analysis(company_name):
    """
    Standalone function to generate Industry Analysis.
    """
    logging.info(f"--- Generating Industry Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Business Analysis Context
    # We fetch it from the previously generated Markdown file in GCS
    business_analysis_blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{safe_company_name}_business_analysis.md"
    business_analysis_blob = gcs.bucket.blob(business_analysis_blob_name)
    
    business_context = ""
    if business_analysis_blob.exists():
        business_context = business_analysis_blob.download_as_text()
    else:
        logging.warning("Business Analysis MD not found for Industry Analysis context.")

    prompt_template = read_prompt("industry_analysis.txt")
    prompt_text = prompt_template.replace("{{ business_analysis_context }}", business_context)
    
    tools = [types.Tool(google_search=types.GoogleSearch())]
    
    try:
        industry_md = call_gemini_model(
            prompt_text=prompt_text,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=1.0,
            tools=tools,
            thinking_enabled=False, # Removed thinking for Industry Analysis as per previous logic (avoid hangs)
            client=client
        )
        
        # Add Citations (call_gemini_model doesn't do it automatically yet if we didn't include it in utils?)
        # Wait, I did NOT include `add_citations_to_text` logic in `call_gemini_model`. 
        # `add_citations_to_text` needs the full response object. 
        # My `call_gemini_model` returns text.
        # FIX: `call_gemini_model` should support returning response object OR I use `add_citations` inside it?
        # Ideally inside. But `add_citations_to_text` is specific logic.
        # Or I handle it here by NOT using `call_gemini_model` OR updating `call_gemini_model`.
        # Updating `call_gemini_model` might be too much if it's specialized.
        # But `industry_analysis` logic used `add_citations_to_text`.
        # I should manually invoke it or use the original logic but standalone.
        # Let's keep `add_citations_to_text` usage by COPYING `call_gemini_model` logic but modifying slightly OR
        # Just stick to raw client call here for special handling?
        # NO, user asked for common utility.
        # Let's update `call_gemini_model` to handle citations? No, citations logic is complex.
        # I will use `call_gemini_model` BUT `add_citations_to_text` requires `response.candidates[0].grounding_metadata`.
        # `call_gemini_model` returns `response.text`.
        # I will revert to raw call here OR modify `utils.py` later.
        # For now, I will use raw call inside this standalone function to preserve citation logic safely.
        
        pass # Placeholder comment, effectively I will implement the raw call below same as before but standalone.
    except:
         pass

    # Actually, let's just implement standalone wrapper preserving original logic for now
    # to avoid breaking citations.
    
    # ... Original Logic ...
    parts = [types.Part.from_text(text=prompt_text)]
    contents = [types.Content(role="user", parts=parts)]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=1,
        top_p=0.95,
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
        ],
        tools=tools
    )
    
    try:
        response = client.models.generate_content(
            model=config.GEMINI_FLASH_MODEL,
            contents=contents,
            config=generate_content_config,
        )
        industry_md = add_citations_to_text(response)
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_industry_analysis.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(industry_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_industry_analysis.html")
        try:
             pypandoc.convert_text(industry_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/industry_analysis.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Industry Analysis Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_industry_analysis.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(industry_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Industry Analysis DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Industry Analysis docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during industry analysis generation: {e}")
        raise

def generate_earnings_call(company_name):
    """
    Standalone function to generate Earnings Call Analysis.
    """
    logging.info(f"--- Generating Earnings Call Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # List audio files
    audio_blobs = gcs.list_files(company_name, "earnings_recording")
    if not audio_blobs:
        logging.warning("No earnings call recordings found.")
        return None

    audio_parts = []
    for blob in audio_blobs:
        if blob.name.endswith('/'): continue
        mime_type = "audio/wav" if blob.name.endswith(".wav") else "audio/mpeg"
        uri = f"gs://{config.GCS_BUCKET_NAME}/{blob.name}"
        audio_parts.append(types.Part.from_uri(file_uri=uri, mime_type=mime_type))
        logging.info(f"Added audio file: {uri}")
        
    if not audio_parts:
        return None

    prompt_text = read_prompt("earnings_call.txt")
    
    try:
        # Appending prompt text to audio parts
        # call_gemini_model logic helper:
        # If we pass parts, it uses them. prompt_text is prepended/appended if not in parts.
        # But here prompt text is instructions.
        
        # Manually constructing parts to ensure order: Audio then Prompt? Or Prompt then Audio?
        # Usually Prompt then Audio is fine, or Audio then Prompt.
        # Let's add prompt as text part at end.
        audio_parts.append(types.Part.from_text(text=prompt_text))
        
        earnings_md = call_gemini_model(
            prompt_text=None,
            parts=audio_parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=1.0,
            safety_settings=[ # Explicit OFF settings
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            client=client
        )
        
        if not earnings_md:
             return None

        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_earnings_call.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(earnings_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_earnings_call.html")
        try:
             pypandoc.convert_text(earnings_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/earnings_call.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Earnings Call Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_earnings_call.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(earnings_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Earnings Call DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Earnings Call docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during earnings call analysis generation: {e}")
        return None

def generate_forensics(company_name):
    """
    Standalone function to generate Forensic Analysis.
    """
    logging.info(f"--- Generating Forensic Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Annual Reports
    pdf_blobs = get_annual_report_files(company_name)
    if not pdf_blobs:
         logging.warning(f"Skipping Forensic Analysis: No Annual Reports found")
         return None

    prompt_text = read_prompt("forensics.txt")
    parts = [types.Part.from_text(text=prompt_text)]
    
    for blob in pdf_blobs:
        pdf_data = blob.download_as_bytes()
        parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))

    try:
        forensics_md = call_gemini_model(
            prompt_text=None,
            parts=parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.1,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_forensics.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(forensics_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_forensics.html")
        try:
             pypandoc.convert_text(forensics_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/forensics.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Forensic Analysis Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_forensics.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(forensics_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Forensic Analysis DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Forensic Analysis docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during forensic analysis generation: {e}")
        return None

def generate_swot_analysis(company_name):
    """
    Standalone function to generate SWOT Analysis.
    """
    logging.info(f"--- Generating SWOT Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Annual Reports & Financial Commentary
    pdf_blobs = get_annual_report_files(company_name)
    fin_commentary_blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{safe_company_name}_financial_commentary.md"
    fin_commentary_blob = gcs.bucket.blob(fin_commentary_blob_name)
    
    fin_context = ""
    if fin_commentary_blob.exists():
        fin_context = fin_commentary_blob.download_as_text()
    else:
        logging.warning("Financial Commentary MD not found for SWOT context.")

    prompt_text = read_prompt("swot_analysis.txt")
    prompt_text = prompt_text.replace("{{ financial_context }}", fin_context)
    
    parts = [types.Part.from_text(text=prompt_text)]
    
    if pdf_blobs:
        for blob in pdf_blobs:
            pdf_data = blob.download_as_bytes()
            parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))
            
    tools = [types.Tool(google_search=types.GoogleSearch())]

    try:
        swot_md = call_gemini_model(
            prompt_text=None,
            parts=parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=1.0, # High temp + search
            tools=tools,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_swot.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(swot_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_swot.html")
        try:
             pypandoc.convert_text(swot_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/swot.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert SWOT Analysis Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_swot.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(swot_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ SWOT Analysis DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: SWOT Analysis docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during SWOT analysis generation: {e}")
        return None

def generate_promoter_analysis(company_name):
    """
    Standalone function to generate Promoter Analysis.
    """
    logging.info(f"--- Generating Promoter Analysis for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Annual Reports
    pdf_blobs = get_annual_report_files(company_name)
    if not pdf_blobs:
         logging.warning(f"Skipping Promoter Analysis: No Annual Reports found")
         return None

    prompt_text = read_prompt("promoter_analysis.txt")
    parts = [types.Part.from_text(text=prompt_text)]
    
    for blob in pdf_blobs:
        pdf_data = blob.download_as_bytes()
        parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))

    try:
        promoter_md = call_gemini_model(
            prompt_text=None,
            parts=parts,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_promoter.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(promoter_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_promoter.html")
        try:
             pypandoc.convert_text(promoter_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/promoter.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Promoter Analysis Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_promoter.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(promoter_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Promoter Analysis DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Promoter Analysis docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during promoter analysis generation: {e}")
        return None

def generate_business_summary(company_name):
    """
    Standalone function to generate Business Summary.
    """
    logging.info(f"--- Generating Business Summary for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Business Analysis
    biz_analysis_blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{safe_company_name}_business_analysis.md"
    biz_analysis_blob = gcs.bucket.blob(biz_analysis_blob_name)
    
    biz_context = ""
    if biz_analysis_blob.exists():
        biz_context = biz_analysis_blob.download_as_text()
    else:
        logging.warning("Business Analysis MD not found for Business Summary context.")

    prompt = read_prompt("business_summary.txt")
    prompt_text = prompt.replace("{{ business_analysis_context }}", biz_context)
    
    try:
        summary_md = call_gemini_model(
            prompt_text=prompt_text,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_summary.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(summary_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_summary.html")
        try:
             pypandoc.convert_text(summary_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/summary.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Business Summary Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_summary.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(summary_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Business Summary DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Business Summary docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during business summary generation: {e}")
        return None

def generate_financial_summary(company_name):
    """
    Standalone function to generate Financial Summary.
    """
    logging.info(f"--- Generating Financial Summary for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Prerequisite: Financial Commentary, SWOT, Forensics
    # Fetching contexts from MD files on GCS
    
    def get_context(suffix):
        blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{safe_company_name}_{suffix}"
        blob = gcs.bucket.blob(blob_name)
        if blob.exists():
            return blob.download_as_text()
        return ""

    fin_context = get_context("financial_commentary.md")
    swot_context = get_context("swot.md")
    forensics_context = get_context("forensics.md")

    prompt = read_prompt("financial_summary.txt")
    prompt_text = prompt.replace("{{ financial_commentary_context }}", fin_context or "Not available")
    prompt_text = prompt_text.replace("{{ swot_analysis_context }}", swot_context or "Not available")
    prompt_text = prompt_text.replace("{{ forensics_analysis_context }}", forensics_context or "Not available")
    
    try:
        summary_md = call_gemini_model(
            prompt_text=prompt_text,
            model_name=config.GEMINI_FLASH_MODEL,
            temperature=0.2,
            client=client
        )
        
        # Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_fin_summary.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(summary_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
            
        # Convert MD to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_fin_summary.html")
        try:
             pypandoc.convert_text(summary_md, 'html', format='md', outputfile=fin_html_path)
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/fin_summary.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Financial Summary Markdown to HTML: {e}")
        
        # Convert MD to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_fin_summary.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(summary_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Financial Summary DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Financial Summary docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error during financial summary generation: {e}")
        return None

def get_latest_annual_report(company_name):
    """
    Finds the latest Annual Report PDF for the company in GCS.
    Searches in 'annual_reports' folder and parses years from filenames if possible,
    or falls back to 'financial_reports' if needed.
    """
    gcs = get_gcs_manager()
    
    # Try specific annual_reports folder first
    prefix = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/annual_reports/"
    blobs = list(gcs.bucket.list_blobs(prefix=prefix))
    pdf_blobs = [blob for blob in blobs if blob.name.lower().endswith('.pdf')]
    
    if not pdf_blobs:
        # Fallback to general financial_reports or root? 
        # The user said "Annual Report", implying it might be in 'annual_reports' or uploaded via the new UI.
        # New UI uploads to 'annual_reports' folder for type 'Annual Report'.
        logging.warning(f"No Annual Reports found in {prefix}")
        return None
        
    # Sort by year if present in filename, else creation time?
    # Simple sort by name might work if format is standard, but let's try to find year
    def extract_year(blob):
        match = re.search(r'20\d{2}', blob.name)
        return int(match.group(0)) if match else 0
        
    # Sort descending by year, then name
    pdf_blobs.sort(key=lambda x: (extract_year(x), x.name), reverse=True)
    
    latest_blob = pdf_blobs[0]
    logging.info(f"Selected latest Annual Report: {latest_blob.name}")
    return latest_blob

def generate_borrower_profile(company_name):
    """
    Generates the Borrower Profile using the latest Annual Report.
    """
    logging.info(f"--- Generating Borrower Profile for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # 1. Get Annual Report
    pdf_blob = get_latest_annual_report(company_name)
    if not pdf_blob:
        logging.error("Cannot generate Borrower Profile: No Annual Report found.")
        return None
        
    # 2. Prepare Prompt
    prompt_template = read_prompt("borrower_profile.txt")
    
    # 3. Call Gemini
    try:
        logging.info("Sending Annual Report to Gemini for Borrower Profile...")
        
        # Create input part for the PDF
        pdf_part = types.Part.from_uri(
            file_uri=f"gs://{gcs.bucket_name}/{pdf_blob.name}",
            mime_type="application/pdf"
        )
        
        response = call_gemini_model(
            prompt_text=prompt_template,
            model_name=config.GEMINI_FLASH_MODEL, # Flash is good for long context extraction
            temperature=0.2, # Low temp for extraction
            client=client,
            parts=[pdf_part] # Attach PDF
        )
        
        profile_md = clean_ai_output(response)
        
        # 4. Save & Upload Markdown
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_borrower_profile.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(profile_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
        
        # 5. Convert to HTML & Upload
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_borrower_profile.html")
        try:
             pypandoc.convert_text(profile_md, 'html', format='md', outputfile=fin_html_path)
             # Use standard name for view-analysis fallback if needed, but we rely on MD now
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/borrower_profile.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.error(f"Failed to convert Borrower Profile to HTML: {e}")
             
        # 6. Convert to DOCX & Upload
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_borrower_profile.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(profile_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            process_document(fin_docx_path, fin_docx_path) # Apply Styling
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Borrower Profile DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
             logging.error(f"⚠️ Warning: Borrower Profile docx generation failed: {e}")
             return None

    except Exception as e:
        logging.error(f"Error generating Borrower Profile: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_media_monitoring(company_name):
    """
    Generates Media Monitoring / Adverse Media report using Google Search.
    """
    logging.info(f"--- Generating Media Monitoring for {company_name} ---")
    gcs = get_gcs_manager()
    client = get_gemini_client()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')

    prompt_template = read_prompt("media_monitoring.txt")
    prompt_text = prompt_template.replace("{company_name}", company_name)
    
    # Enable Google Search Tool
    tools = [types.Tool(google_search=types.GoogleSearch())]
    
    # Configure generation
    parts = [types.Part.from_text(text=prompt_text)]
    contents = [types.Content(role="user", parts=parts)]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        temperature=0.3, # Lower temperature for factual reporting
        max_output_tokens=config.MAX_OUTPUT_TOKENS,
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
        ],
        tools=tools
    )

    try:
        # Call Gemini (Standalone to handle citations)
        response = client.models.generate_content(
            model=config.GEMINI_FLASH_MODEL,
            contents=contents,
            config=generate_content_config,
        )
        
        # Add citations if available
        try:
             media_md = add_citations_to_text(response)
        except NameError:
             logging.warning("add_citations_to_text not found, using clean_ai_output or raw text.")
             media_md = clean_ai_output(response.text) if hasattr(response, 'text') else str(response)

        # Save MD
        fin_md_path = os.path.join(output_dir, f"{safe_company_name}_media_monitoring.md")
        with open(fin_md_path, 'w', encoding='utf-8') as f:
            f.write(media_md)
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_md_path)}").upload_from_filename(fin_md_path)
        
        # Convert to HTML
        fin_html_path = os.path.join(output_dir, f"{safe_company_name}_media_monitoring.html")
        try:
             pypandoc.convert_text(media_md, 'html', format='md', outputfile=fin_html_path)
             # Use generic name for view-analysis consumption if needed
             gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/media_monitoring.html").upload_from_filename(fin_html_path)
        except Exception as e:
             logging.warning(f"Pandoc conversion failed for Media Monitoring HTML: {e}")

        # Convert to DOCX
        fin_docx_path = os.path.join(output_dir, f"{safe_company_name}_media_monitoring.docx")
        extra_args = [
            f'--reference-doc={template_path}',
            '--shift-heading-level-by=2',
            f'--lua-filter={lua_filter_path}'
        ]
        try:
            pypandoc.convert_text(media_md, 'docx', format='md', outputfile=fin_docx_path, extra_args=extra_args)
            # Apply Styling
            process_document(fin_docx_path, fin_docx_path)
            gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{os.path.basename(fin_docx_path)}").upload_from_filename(fin_docx_path)
            logging.info(f"✅ Media Monitoring DOCX created: {fin_docx_path}")
            return fin_docx_path
        except Exception as e:
            logging.error(f"⚠️ Warning: Media Monitoring DOXC generation failed: {e}")
            return None


    except Exception as e:
        logging.error(f"Error generating Media Monitoring: {e}")
        import traceback
        traceback.print_exc()
        return None

def assemble_credit_memo(company_name):
    """
    Assembles the final Credit Memo from generated intermediate DOCX files
    using the master template and subdocuments.
    """
    logging.info(f"--- Assembling Credit Memo for {company_name} ---")
    gcs = get_gcs_manager()
    output_dir = config.OUTPUT_DATA_DIR
    os.makedirs(output_dir, exist_ok=True)
    safe_company_name = company_name.replace(' ', '_')
    
    # Template path
    master_template_path = os.path.join(config.TEMPLATES_DIR, "cam_template.docx")
    if not os.path.exists(master_template_path):
        # Fallback to downloading if not local? Or assume it's part of deployment.
        # For now assume it exists or try to download from GCS templates?
        # gcs.download_template() returns a temp path usually.
        # Let's try downloading if missing.
        logging.warning("Master template not found locally. Attempting download from GCS.")
        try:
             downloaded_path = gcs.download_template() # This usually gets 'CMA_Format_Financials.xlsx' or 'cam_template.docx' depending on impl.
             # Actually gcs.download_template() in gcs_storage.py is hardcoded for excel template often.
             # Let's check if we can download 'cam_template.docx' specifically.
             blob = gcs.bucket.blob(f"templates/cam_template.docx")
             if blob.exists():
                 blob.download_to_filename(master_template_path)
             else:
                 logging.error(f"Master template not found in GCS either: templates/cam_template.docx")
                 return None
        except Exception as e:
             logging.error(f"Failed to download master template: {e}")
             return None

    LEGACY_MAPPING = {
        "financial_commentary": "financial_intermediate",
        "credit_rating": "rating_intermediate",
        "risk_policy": "risk_policy_intermediate",
        "business_analysis": "business_intermediate",
        "industry_analysis": "industry_intermediate",
        "business_summary": "summary"
    }

    # Helper to download docx if missing locally
    def ensure_local_docx(section_name):
        # 1. Check Standard Name
        standard_name = f"{safe_company_name}_{section_name}.docx"
        local_path = os.path.join(output_dir, standard_name)
        if os.path.exists(local_path):
             return local_path
             
        # Try download standard
        blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{standard_name}"
        blob = gcs.bucket.blob(blob_name)
        if blob.exists():
             blob.download_to_filename(local_path)
             logging.info(f"Downloaded {section_name} from {blob_name}")
             return local_path

        # 2. Check Legacy Name (if applicable)
        if section_name in LEGACY_MAPPING:
            legacy_key = LEGACY_MAPPING[section_name]
            legacy_name = f"{safe_company_name}_{legacy_key}.docx"
            legacy_local_path = os.path.join(output_dir, legacy_name)
            
            # Check local legacy
            if os.path.exists(legacy_local_path):
                return legacy_local_path
            
            # Try download legacy
            legacy_blob_name = f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{legacy_name}"
            blob = gcs.bucket.blob(legacy_blob_name)
            if blob.exists():
                 blob.download_to_filename(legacy_local_path)
                 logging.info(f"Downloaded Legacy {section_name} from {legacy_blob_name}")
                 return legacy_local_path

        return None

    try:
        doc = DocxTemplate(master_template_path)
        context = {'company_name': company_name}
        
        # Section Mapping to Context Keys
        # Key: Section function name suffix, Value: Template context key
        section_map = {
            "financial_commentary": "financial_commentary",
            "credit_rating": "credit_rating",
            "risk_policy": "risk_policy",
            "business_analysis": "business_analysis",
            "industry_analysis": "industry_analysis",
            "earnings_call": "earnings_call",
            "forensics": "forensics",
            "swot": "swot",
            "promoter": "promoter_analysis",
            "business_summary": "business_summary", # Generated file suffix is _business_summary.docx? No, check generator.
            "financial_summary": "financial_summary"
        }
        
        # Verify suffixes:
        # generate_business_summary -> f"{safe_company_name}_business_summary.docx" -> ensure_local_docx("business_summary") matches.
        # generate_promoter_analysis -> f"{safe_company_name}_promoter.docx" (Wait, verify suffix!)
        # Let's verify suffixes in `ensure_local_docx` calls vs generator outputs.
        # generate_promoter_analysis: output is "{safe_company_name}_promoter.docx" -> section name "promoter"
        # generate_business_summary: output "{safe_company_name}_business_summary.docx" -> section name "business_summary" 
        # (Wait, existing code calls it `summary_docx_path` but filename is `..._business_summary.md`? Let's check view.)
        
        # Correcting keys based on likely generation outputs:
        # We need to call ensure_local_docx with the EXACT suffix used in generation (minus company name and .docx)
        
        section_suffixes = {
             "financial_commentary": "financial_commentary",
             "credit_rating": "credit_rating",
             "risk_policy": "risk_policy",
             "business_analysis": "business_analysis",
             "industry_analysis": "industry_analysis",
             "earnings_call": "earnings_call",
             "forensics": "forensics",
             "swot": "swot",
             "promoter_analysis": "promoter", # Context Key: promoter_analysis. File suffix: promoter (commonly)
             "business_summary": "business_summary",
             "financial_summary": "fin_summary", # Suffix often 'fin_summary'
             "borrower_profile": "borrower_profile",
             "media_monitoring": "media_monitoring"
        }
        
        for context_key, file_suffix in section_suffixes.items():
            path = ensure_local_docx(file_suffix)
            if path:
                context[context_key] = doc.new_subdoc(path)
                logging.info(f"Included section: {context_key} from {path}")
            else:
                context[context_key] = f"No {context_key.replace('_', ' ').title()} Available."
                logging.warning(f"Missing section for assembly: {context_key} (expected suffix: {file_suffix})")

        doc.render(context)
        
        final_output_file = os.path.join(output_dir, f"{safe_company_name}_credit_memo.docx")
        doc.save(final_output_file)
        
        # Upload Final Memo
        gcs.bucket.blob(f"{config.GCS_COMPANIES_FOLDER}/{company_name}/memo/{company_name}_credit_memo.docx").upload_from_filename(final_output_file)
        logging.info(f"✅ Final Credit Memo assembled: {final_output_file}")
        
        return final_output_file

    except Exception as e:
        logging.error(f"Error assembling credit memo: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/financial_commentary.py <company_name>")
        company_name = "Uno Minda" 
        print(f"No company provided, defaulting to: {company_name}")
    else:
        company_name = sys.argv[1]
        
    generate_memo(company_name)

def generate_memo(company_name):
    """
    Orchestrator function that now calls standalone generation functions.
    Legacy entry point for full pipeline run.
    """
    logging.info(f"=== Starting Full Memo Generation for {company_name} ===")
    
    # 1. Financial Commentary
    generate_financial_commentary(company_name)
    
    # 2. Credit Rating
    generate_credit_rating(company_name)
    
    # 3. Risk Policy
    generate_risk_policy(company_name)
    
    # 4. Business Analysis
    generate_business_analysis(company_name)
    
    # 5. Industry Analysis
    generate_industry_analysis(company_name)
    
    # 6. Earnings Call
    generate_earnings_call(company_name)
    
    # 7. Forensics
    generate_forensics(company_name)
    
    # 8. SWOT
    generate_swot_analysis(company_name)
    
    # 9. Promoter
    generate_promoter_analysis(company_name)
    
    # 10. Business Summary
    generate_business_summary(company_name)
    
    # 11. Financial Summary
    generate_financial_summary(company_name)
    
    # 12. Borrower Profile
    generate_borrower_profile(company_name)

    # 13. Media Monitoring
    generate_media_monitoring(company_name)

    # 14. Assemble
    assemble_credit_memo(company_name)
    
    logging.info("=== Full Memo Generation Complete ===")


if __name__ == "__main__":
    main()
