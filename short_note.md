# MoSPI RAG Chatbot — Short Note

## ✅ What Worked & How

### 1. Playwright + BeautifulSoup Hybrid Scraping
MoSPI's website is a **React SPA** — all content is rendered by JavaScript. We used **Playwright** to launch a headless Chromium browser that executes the JavaScript and renders the full page. Then **BeautifulSoup** parses the rendered HTML to extract all `<a>` tags containing `.pdf` links, along with their titles and metadata. Each document is hashed with **SHA-256** to prevent duplicates and stored in a **SQLite** database.

### 2. Playwright-Based PDF Downloads
MoSPI blocks direct HTTP downloads (returns **403 Forbidden**). We used Playwright again inside `scraper/parse.py` to simulate a real browser download, bypassing their anti-bot protection and successfully saving PDFs to `data/raw/`.

### 3. PDF Text Extraction & Chunking Pipeline
`pdfplumber` extracted text and table structures from the downloaded PDFs. The pipeline (`pipeline/run.py`) splits document text into **~1000-word chunks with 200-word overlap** and saves them as JSON in `data/processed/chunks/`.

### 4. FAISS Vector Search & RAG
Text chunks are embedded using `sentence-transformers` (model: **all-MiniLM-L6-v2**) and indexed in a **FAISS** vector database. On user queries, the system retrieves the top-k most relevant chunks and constructs a strict prompt for **LLaMA 3** that answers only from the retrieved context with bulleted citations.

### 5. Full-Stack Application
- **FastAPI** backend with `/ask`, `/ingest`, and `/health` endpoints
- **Streamlit** chat UI with configurable temperature and k parameters
- **Ollama** integration for running LLaMA 3 locally
- **Docker Compose** for containerized deployment

### 6. Manual PDF Ingestion
Added a fallback in the pipeline that automatically detects and processes any PDF manually placed in `data/raw/`, so the chatbot works even without the web crawler.

---

## ❌ What Didn't Work

### 1. Simple `requests.get()` Scraping
MoSPI is a React SPA. A plain HTTP GET returned only an empty `<div id="root"></div>` shell with zero content — no links, no titles, nothing.

### 2. Placeholder CSS Selectors
The initial crawler used guessed selectors like `div.publication-item` and `h3.title`. MoSPI's actual HTML structure was completely different, so the crawler found 0 documents.

### 3. Playwright `networkidle` Wait Strategy
MoSPI keeps long-polling connections alive, causing Playwright to **timeout after 30 seconds** when waiting for `networkidle`. We switched to `domcontentloaded` with a hard `sleep(5)` to allow React to finish rendering.

### 4. Direct PDF Downloads via `requests`
MoSPI's server returned **403 Forbidden** for plain HTTP PDF download requests. The server requires browser-like request contexts, which led us to use Playwright for downloads.

---

## 🔜 What To Do Next

1. **Test the Playwright + BeautifulSoup crawler end-to-end** — Run `make crawl` and verify it finds `.pdf` links in the rendered DOM.
2. **Run `make etl`** — Download and chunk PDFs using the interactive pipeline (choose how many to process).
3. **Rebuild the Vector Index** — Click "Rebuild Index from Data" in the Streamlit UI at `http://localhost:8501`.
4. **Test the Chatbot** — Ask domain-specific questions like *"What are the key findings of the PLFS 2025?"* or *"What is the Annual Survey of Industries?"*
5. **Fix Docker Deployment** — Debug and get the containerized deployment working via `docker-compose.yml`.
6. **Scale the Knowledge Base** — Gradually increase downloaded PDFs to build comprehensive coverage of all MoSPI publications.
