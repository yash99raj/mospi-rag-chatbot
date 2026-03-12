import os
import sqlite3
import hashlib
import time
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ensure DB directories exist
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed"))
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "mospi_data.db")

# Configuration
SEED_URL = "https://www.mospi.gov.in/publications-reports"

def init_db():
    """Initializes the SQLite database with the documents table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT,
            date TEXT,
            url TEXT,
            content_hash TEXT UNIQUE
        )
    ''')
    conn.commit()
    conn.close()
    logging.info(f"Database initialized at {DB_PATH}")

def compute_hash(content: str) -> str:
    """Computes SHA-256 hash of a string."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def is_duplicate(content_hash: str) -> bool:
    """Checks if the document already exists in the database by hash."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM documents WHERE content_hash = ?", (content_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_document(doc_id: str, title: str, date: str, url: str, content_hash: str):
    """Saves document metadata to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO documents (id, title, date, url, content_hash)
            VALUES (?, ?, ?, ?, ?)
        ''', (doc_id, title, date, url, content_hash))
        conn.commit()
        logging.info(f"Saved new document: '{title}'")
    except sqlite3.IntegrityError:
        logging.warning(f"Integrity Error: Document '{title}' already exists.")
    finally:
        conn.close()

def parse_and_store(html_content: str, base_url: str = "https://www.mospi.gov.in") -> int:
    """
    Parses the HTML response using BeautifulSoup and stores new documents.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    pdf_links = soup.find_all("a", href=lambda href: href and ".pdf" in href.lower())
    
    if not pdf_links:
        logging.warning("No PDF links found on the page.")
        return 0
        
    items_saved = 0
    for link in pdf_links:
        href = link.get('href')
        full_url = urljoin(base_url, href)
        
        # Determine title from link text or nearby context
        title_raw = link.get_text(strip=True)
        if not title_raw or "download" in title_raw.lower() or "pdf" in title_raw.lower():
            # Try to grab the parent's contextual text
            parent = link.parent
            if parent and parent.parent:
                title_raw = parent.parent.get_text(" | ", strip=True)
                
            # If still nothing or bad text, fallback to filename
            if not title_raw or len(title_raw) < 5 or ".pdf" in title_raw.lower():
                title_raw = full_url.split("/")[-1].replace(".pdf", "")

        # Clean title
        title = title_raw.replace("&nbsp;", " ").replace("<p>", "").replace("</p>", "").strip()
        # Clean up some weird artifacts from parent text concatenation
        if " | " in title:
            # Often the title is the first or second segment
            parts = [p.strip() for p in title.split(" | ") if len(p.strip()) > 5 and not p.lower().endswith(".pdf")]
            if parts:
                title = parts[0]
                
        # Best guess for date
        date = time.strftime("%Y-%m-%d")
        
        unique_string = f"{title}-{full_url}"
        content_hash = compute_hash(unique_string)
        
        if not is_duplicate(content_hash):
            doc_id = compute_hash(full_url)[:16]
            save_document(doc_id, title, date, full_url, content_hash)
            items_saved += 1
        else:
            logging.debug(f"Skipping duplicate document: {title}")
            
    return items_saved

def crawl():
    """Crawls the MoSPI publications page dynamically using Playwright and BeautifulSoup."""
    with sync_playwright() as p:
        logging.info("Launching Playwright browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/100.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/100.0",
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()
        
        try:
            logging.info(f"Navigating to {SEED_URL}")
            page.goto(SEED_URL, wait_until="domcontentloaded", timeout=60000)
            
            logging.info("Checking for language modal...")
            try:
                lang_btn = page.locator("button:has-text('English')")
                lang_btn.wait_for(timeout=10000)
                if lang_btn.is_visible():
                    logging.info("Clicking English language button...")
                    lang_btn.click()
                    page.wait_for_timeout(3000)
            except Exception as e:
                logging.debug(f"No language modal found: {e}")
                
            logging.info("Waiting for data to load in DOM...")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass 
                
            page.wait_for_timeout(5000)
            
            html_content = page.content()
            items_count = parse_and_store(html_content)
            
            logging.info(f"API crawl complete. Processed {items_count} new listings.")
            
        except Exception as e:
            logging.error(f"Failed to crawl {SEED_URL}: {e}")
            
        browser.close()

if __name__ == "__main__":
    init_db()
    logging.info("Starting MoSPI Playwright Scraper...")
    crawl()
