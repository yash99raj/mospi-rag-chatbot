import os
import json
import logging
import requests
import pdfplumber
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RAW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def download_pdf(url: str, doc_id: str) -> str | None:
    """Downloads a PDF file and saves it to the raw data directory."""
    file_path = os.path.join(RAW_DIR, f"{doc_id}.pdf")
    
    # Check if already downloaded
    if os.path.exists(file_path):
        logging.info(f"PDF already exists at {file_path}")
        return file_path

    try:
        logging.info(f"Downloading PDF via Playwright from {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/100.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/100.0",
                accept_downloads=True
            )
            page = context.new_page()
            
            # Since MoSPI blocks direct GET requests to PDFs with 61 Connection Refused,
            # we need Playwright to navigate to it. It usually triggers a download event.
            try:
                # Wait for the download event when navigating to the PDF URL
                with page.expect_download(timeout=60000) as download_info:
                    page.goto(url)
                
                download = download_info.value
                download.save_as(file_path)
                logging.info(f"Saved PDF to {file_path}")
                
            except Exception as nav_e:
                logging.warning(f"Failed via expect_download, attempting direct fetch in context: {nav_e}")
                # Sometimes navigating to a PDF just displays it in the browser
                # We can fetch the buffer manually inside the context
                response = page.request.get(url, timeout=60000)
                if response.ok:
                    buffer = response.body()
                    with open(file_path, "wb") as f:
                        f.write(buffer)
                    logging.info(f"Saved PDF to {file_path}")
                else:
                    logging.error(f"Failed to fetch PDF data. Status: {response.status}")
                    return None
            
            browser.close()
            return file_path
            
    except Exception as e:
        logging.error(f"Failed to download PDF {url}: {e}")
        return None

def extract_content(pdf_path: str) -> dict:
    """
    Extracts text and table structures from the provided PDF.
    Returns a dictionary containing the full text and extracted tables as JSON-compatible structures.
    """
    full_text = []
    extracted_tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract Text
                text = page.extract_text()
                if text:
                    full_text.append(text)
                
                # Extract Tables
                tables = page.extract_tables()
                for table_idx, table in enumerate(tables):
                    # Clean up empty rows/cells and format as list of lists
                    cleaned_table = []
                    for row in table:
                        # Replace None values with empty strings
                        cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                        # Only add rows that aren't entirely empty
                        if any(cleaned_row):
                            cleaned_table.append(cleaned_row)
                            
                    if cleaned_table:
                        extracted_tables.append({
                            "page": page_num,
                            "table_index": table_idx,
                            "data": cleaned_table
                        })
                        
    except Exception as e:
        logging.error(f"Error extracting content from {pdf_path}: {e}")
        
    return {
        "text": "\n\n".join(full_text),
        "tables": extracted_tables
    }

def process_document(url: str, doc_id: str) -> dict | None:
    """Downloads and extracts a single document."""
    pdf_path = download_pdf(url, doc_id)
    if not pdf_path:
        return None
        
    extracted_data = extract_content(pdf_path)
    return extracted_data

if __name__ == "__main__":
    # Example usage for testing
    # process_document("https://example.com/sample.pdf", "sample_test_doc")
    pass
