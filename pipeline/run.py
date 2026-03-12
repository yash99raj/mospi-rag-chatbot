import os
import json
import sqlite3
import logging
from typing import List, Dict

# Assuming parse.py is accessible - you might need to adjust imports based on how you run this
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scraper.parse import process_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed"))
DB_PATH = os.path.join(DB_DIR, "mospi_data.db")
CHUNK_DIR = os.path.join(DB_DIR, "chunks")
os.makedirs(CHUNK_DIR, exist_ok=True)

CHUNK_SIZE = 1000  # Target token size (approximation)
CHUNK_OVERLAP = 200 # Overlap to maintain context between chunks

def init_db_extensions():
    """Adds a status column to track processing state if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'pending'")
        conn.commit()
    except sqlite3.OperationalError:
        # Column likely already exists
        pass
    conn.close()

def get_pending_documents():
    """Retrieves documents that haven't been processed yet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, date, url FROM documents WHERE status = 'pending'")
    results = cursor.fetchall()
    conn.close()
    return results

def mark_document_status(doc_id: str, status: str):
    """Updates the status of a document (e.g., 'completed', 'failed')."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET status = ? WHERE id = ?", (status, doc_id))
    conn.commit()
    conn.close()

def validate_metadata(title: str, date: str) -> bool:
    """Validates that title and date are present and seemingly valid."""
    if not title or not title.strip():
        logging.warning("Validation failed: Empty title")
        return False
    
    if not date or not date.strip():
        logging.warning("Validation failed: Empty date")
        return False
        
    # Basic date format check could be added here depending on expected MoSPI format
    # e.g., using datetime.strptime()
    
    return True

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits text into chunks of approximately `chunk_size` words/tokens,
    with `overlap` to maintain context.
    Using a simple whitespace split as a proxy for tokens. 
    For better accuracy, use a proper tokenizer (e.g., from transformers).
    """
    words = text.split()
    chunks = []
    
    if not words:
        return chunks
        
    start_idx = 0
    while start_idx < len(words):
        end_idx = min(start_idx + chunk_size, len(words))
        chunk_words = words[start_idx:end_idx]
        chunks.append(" ".join(chunk_words))
        
        # Move forward, accounting for overlap
        start_idx += chunk_size - overlap
        
    return chunks

def save_chunks(doc_id: str, metadata: dict, chunks: List[str], tables: List[dict]):
    """Saves the extracted text chunks and tables to a JSON file for the vector DB pipeline."""
    output_data = {
        "doc_id": doc_id,
        "metadata": metadata,
        "chunks": chunks,
        "tables": tables
    }
    
    out_path = os.path.join(CHUNK_DIR, f"{doc_id}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    logging.info(f"Saved {len(chunks)} chunks and {len(tables)} tables to {out_path}")

def process_local_raw_files():
    """Scans data/raw/ for any manually downloaded PDFs and processes them if they aren't chunked yet."""
    import glob
    raw_pdfs = glob.glob(os.path.join(DB_DIR, "..", "raw", "*.pdf"))
    
    for pdf_path in raw_pdfs:
        filename = os.path.basename(pdf_path)
        doc_id = filename.replace(".pdf", "").replace(" ", "_")
        
        # Check if already processed
        chunk_file = os.path.join(CHUNK_DIR, f"{doc_id}.json")
        if os.path.exists(chunk_file):
            continue
            
        logging.info(f"Found manually downloaded PDF: {filename}")
        
        # We need to import the extract_content directly to skip the download step
        try:
            from scraper.parse import extract_content
            extracted_data = extract_content(pdf_path)
            
            text_content = extracted_data.get("text", "")
            chunks = chunk_text(text_content)
            
            metadata = {
                "title": filename,
                "date": "Manual Upload",
                "url": f"local://{filename}"
            }
            
            save_chunks(doc_id, metadata, chunks, extracted_data.get("tables", []))
            logging.info(f"Successfully processed local file {filename}")
            
            # Put dummy row in DB so we don't process it in the scrape loop later
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO documents (id, title, date, url, content_hash, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (doc_id, filename, "Manual", f"local://{filename}", f"manual_{doc_id}", "completed")
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass
            conn.close()
            
        except ImportError:
            logging.error("Could not load extract_content from scraper.parse")

def run_pipeline():
    """Main pipeline execution loop."""
    init_db_extensions()
    
    # 1. First run the fallback for manually dropped PDFs in data/raw/
    process_local_raw_files()
    
    # 2. Then proceed with normal DB pending documents
    pending_docs = get_pending_documents()
    if not pending_docs:
        logging.info("No pending scraped documents to process.")
        return
        
    print(f"\n=======================================================")
    print(f" 🔍 Found {len(pending_docs)} NEW online documents waiting to be downloaded.")
    print(f"=======================================================")
    
    # Check if we are in an interactive terminal to prevent hanging in headless mode
    if sys.stdout.isatty():
        user_input = input("How many would you like to download right now? (Enter a number, 'all', or 0 to skip): ").strip().lower()
    else:
        # If running via cron/non-interactive, default to 0 to prevent unintentional mass-downloads
        user_input = '0'
        
    if user_input in ['0', 'skip', 'no', 'n', '']:
        logging.info("Skipping online document downloads.")
        return
        
    limit = len(pending_docs)
    if user_input != 'all':
        try:
            limit = int(user_input)
        except ValueError:
            logging.warning("Invalid input. Skipping online downloads.")
            return

    docs_to_process = pending_docs[:limit]
    logging.info(f"Starting extraction for {len(docs_to_process)} documents...")
    
    for doc_id, title, date, url in docs_to_process:
        logging.info(f"Processing document: {title} ({doc_id})")
        
        if not validate_metadata(title, date):
            logging.error(f"Invalid metadata for {doc_id}. Skipping.")
            mark_document_status(doc_id, "invalid_metadata")
            continue
            
        from scraper.parse import process_document
        extracted_data = process_document(url, doc_id)
        
        if not extracted_data:
            logging.error(f"Failed to extract content for {doc_id}.")
            mark_document_status(doc_id, "extraction_failed")
            continue
            
        text_content = extracted_data.get("text", "")
        chunks = chunk_text(text_content)
        
        metadata = {
            "title": title,
            "date": date,
            "url": url
        }
        
        save_chunks(doc_id, metadata, chunks, extracted_data.get("tables", []))
        mark_document_status(doc_id, "completed")
        logging.info(f"Successfully processed {doc_id}")

if __name__ == "__main__":
    run_pipeline()
