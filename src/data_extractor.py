from google import genai
from google.genai import types
import json
import os
import re
import logging
from typing import Dict, Union, Optional, List
from .gcs_storage import get_gcs_manager
from .utils import get_prompt
from . import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _repair_json(json_str: str) -> str:
    """
    Attempts to repair common JSON errors in a string response from an LLM.
    Handles:
    - Markdown code blocks
    - Trailing commas
    - Missing quotes around keys
    - Unclosed brackets/braces
    """
    # 1. Extract from Markdown code blocks
    json_str = json_str.strip()
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str, re.DOTALL)
    if match:
        json_str = match.group(1)
    
    # 2. Extract strictly from first { or [ to last } or ]
    start_bracket = re.search(r'[{[]', json_str)
    if not start_bracket:
        return json_str # Give up and return original to let parser fail naturally
        
    start_idx = start_bracket.start()
    start_char = json_str[start_idx]
    end_char = '}' if start_char == '{' else ']'
    end_idx = json_str.rfind(end_char)
    
    if end_idx != -1:
        json_str = json_str[start_idx : end_idx + 1]
    else:
        # If no closing bracket found, try to append one (risky but better than crashing)
        json_str = json_str[start_idx:] + end_char

    # 3. Common Fixes via Regex
    
    # Remove trailing commas before closing braces/brackets
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    
    # Fix unquoted keys (simple case: word chars followed by colon)
    # Be careful not to quote already quoted keys or text inside strings
    # This is hard to do perfectly with regex, so we'll stick to safer fixes first.
    
    return json_str

def _clean_json_response(raw_response: str) -> str:
    # Wrapper for backward compatibility or future expansion
    return _repair_json(raw_response)

def _extract_years(client, pdf_data: bytes) -> List[str]:
    """
    Step 1: Identify fiscal years from Standalone Financial Statements.
    """
    logger.info("Step 1: extracting fiscal years...")
    
    prompt_text = get_prompt("year_extractor")
    
    parts = [types.Part.from_text(text=prompt_text)]
    # Add PDF content to the prompt
    parts.append(types.Part.from_bytes(data=pdf_data, mime_type="application/pdf"))

    model = config.GEMINI_FLASH_MODEL
    contents = [types.Content(role="user", parts=parts)]
    
    generate_content_config = types.GenerateContentConfig(
        temperature=0.0, # Low temperature for extraction
        response_mime_type="text/plain"
    )

    try:
        response = client.models.generate_content(
            model=model, 
            contents=contents, 
            config=generate_content_config
        )
        years = response.text.strip()
        logger.info(f"Extracted Years: {years}")
        return [y.strip() for y in years.split(',') if y.strip()]
    except Exception as e:
        logger.error(f"Error during year extraction: {e}")
        raise

def _extract_single_year_data(client, pdf_data: bytes, year: Union[int, str], fields_to_extract: dict) -> dict:
    """
    Helper function to extract data for a specific year.
    """
    system_instruction = """You are a highly intelligent financial data analyst. Your primary directive is to follow all instructions with extreme precision. You must adhere strictly to the `extractionGuidance` provided for each field. 

CRITICAL: Your output must be a single, valid JSON object and nothing else. Do not include any text before or after the JSON. Do not truncate the JSON response. Ensure all strings are properly quoted and escaped. Ensure all objects and arrays are properly closed with matching braces and brackets.

JSON Requirements:
- Use double quotes for all strings
- No trailing commas
- Properly escape special characters in strings
- Complete all field objects fully
- End the JSON with a single closing brace

If you cannot find a specific value, use an empty string "" for the value field."""

    # Read prompt template
    prompt_template = get_prompt("simple_extraction")
    
    # Calculate derived values for the prompt
    short_year = str(year)[-2:] if str(year).isdigit() and len(str(year))==4 else str(year)
    prev_year = str(int(year)-1) if str(year).isdigit() else "Previous Year"
    
    # Inject variables into the prompt
    filled_prompt = prompt_template.replace("{{year}}", str(year))
    filled_prompt = filled_prompt.replace("{{short_year}}", short_year)
    filled_prompt = filled_prompt.replace("{{prev_year}}", prev_year)
    filled_prompt = filled_prompt.replace("{{fields_to_extract}}", json.dumps(fields_to_extract, indent=2))

    msg1_text1 = types.Part.from_text(text=filled_prompt)
    msg1_document1 = types.Part.from_bytes(data=pdf_data, mime_type="application/pdf")
    
    generate_content_config = types.GenerateContentConfig(
        temperature=0.1,  # Zero temperature for strict extraction
        top_p=0.8,
        response_mime_type="application/json",
        max_output_tokens=20480,
        candidate_count=1,
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        ],
        system_instruction=[types.Part.from_text(text=system_instruction)],
    )

    model = config.GEMINI_FLASH_MODEL
    # Only send the filled prompt instructions + document. No trailing message.
    contents = [types.Content(role="user", parts=[msg1_text1, msg1_document1])]

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1} of {max_retries} to extract data for year {year}...")
            response_stream = client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            )
            full_response = "".join(chunk.text for chunk in response_stream if chunk.text)

            # Clean and attempt to parse the JSON
            cleaned_response = _clean_json_response(full_response)
            extracted_data = json.loads(cleaned_response)
            logger.info(f"Successfully extracted and parsed JSON for year {year}.")
            return extracted_data

        except json.JSONDecodeError as e:
            logger.warning(f"Warning: Attempt {attempt + 1} failed with JSONDecodeError: {e}")
            # Log the problematic response for debugging
            logger.warning("--- Problematic JSON Response Snippet ---")
            error_pos = e.pos
            start = max(0, error_pos - 150)
            end = min(len(full_response), error_pos + 150)
            logger.warning(f"...{full_response[start:end]}...")
            logger.warning("---------------------------------------")
            
            if attempt < max_retries - 1:
                logger.info("Retrying...")
            else:
                logger.error("CRITICAL: All extraction attempts failed.")
                # Log the full failed response for later analysis
                with open(f"failed_json_response_{year}.txt", "w") as f:
                    f.write(full_response)
                logger.error(f"Full failed response saved to failed_json_response_{year}.txt")
                raise Exception(f"Failed to extract valid JSON from the AI model after multiple attempts for year {year}.")
        except ValueError as e:
            logger.warning(f"Warning: Attempt {attempt + 1} failed with ValueError: {e}")
            if attempt < max_retries - 1:
                logger.info("Retrying...")
            else:
                logger.error("CRITICAL: All extraction attempts failed.")
                raise Exception(f"Failed to extract valid JSON from the AI model after multiple attempts for year {year}.")
        except Exception as e:
            raise Exception(f"An unexpected error occurred during data extraction: {e}")


def extract_financial_data(pdf_path: str, year: Optional[Union[int, str]] = None, processed_years: Optional[set] = None) -> Union[Dict, Dict[str, Dict]]:
    """
    Extracts financial data from a PDF file using the Gemini API.
    
    Args:
        pdf_path (str): Path to the PDF file
        year (int|str, optional): Year for which to extract data. If None, extracts years from PDF first.
        processed_years (set, optional): Set of years already processed in this batch to skip.
    
    Returns:
        dict: Extracted financial data. If year is None, returns a dict of {year: data}.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError("PDF file not found.")

    # Configure the Gemini API key
    PROJECT = os.getenv("PROJECT")
    LOCATION = os.getenv("LOCATION")

    if not all([PROJECT, LOCATION]):
        raise ValueError("Missing environment variables for Gemini API (PROJECT, LOCATION).")

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

    # Read PDF data
    with open(pdf_path, 'rb') as f:
        pdf_data = f.read()
    
    # Read fields to extract from GCS
    try:
        gcs = get_gcs_manager()
        fields_config_path = gcs.download_fields_config()
        with open(fields_config_path, 'r') as f:
            fields_to_extract = json.load(f)
        # Clean up temporary file
        os.unlink(fields_config_path)
    except Exception as e:
        logger.error(f"Error loading fields config from GCS: {e}")
        raise

    if year is not None:
        if processed_years and year in processed_years:
             logger.info(f"Skipping extraction for {year} (already processed).")
             return {}
        return _extract_single_year_data(client, pdf_data, year, fields_to_extract)
    else:
        logger.info("No year provided, attempting to discover years from PDF...")
        discovered_years = _extract_years(client, pdf_data)
        results = {}
        for y in discovered_years:
            if processed_years and y in processed_years:
                logger.info(f"Skipping extraction for duplicate year: {y}")
                continue
                
            logger.info(f"Extracting data for discovered year: {y}")
            results[y] = _extract_single_year_data(client, pdf_data, y, fields_to_extract)
        return results
