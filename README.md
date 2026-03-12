# MoSPI Scraper and RAG Chatbot

This project is a complete data pipeline and Retrieval-Augmented Generation (RAG) system designed to scrape publications from the MoSPI (Ministry of Statistics and Programme Implementation) website, process and index the data, and provide an interactive AI chatbot powered by LLaMA 3.

## Architecture Overview

The system is composed of several modules:

1. **Scraper (`scraper/`)**: Crawls the MoSPI publications page, tracks duplicates using SHA-256 hashes in a SQLite database, and downloads the PDF files to the local `data/raw/` directory.
2. **Processing Pipeline (`pipeline/`)**: Uses `pdfplumber` to extract text and tables from the downloaded PDFs, chunks the text with configurable overlap (for context preservation), and saves the chunks.
3. **RAG Backend (`rag/`)**: 
   - Uses `sentence-transformers` (`all-MiniLM-L6-v2`) to embed text chunks into dense vectors.
   - Stores embeddings in a fast `FAISS` vector index.
   - Provides a FastAPI server (`rag/api.py`) exposing `/ask`, `/ingest`, and `/health` endpoints. It handles querying the vector index, formatting prompts with strict constraints, and calling the LLaMA model via Ollama.
4. **UI (`ui/`)**: A Streamlit frontend that provides a chat interface, allowing you to ask questions, view the cited sources retrieved from FAISS, and adjust LLM parameters.

## Directory Structure

```text
.
├── scraper/
│   ├── crawl.py          # Crawls listings and stores metadata in SQLite
│   └── parse.py          # Downloads and extracts text/tables from PDFs
├── pipeline/
│   └── run.py            # Chunks extracted text and stages for indexing
├── rag/
│   ├── retriever.py      # FAISS indexing and Sentence Transformers logic
│   └── api.py            # FastAPI backend (Ingestion & Generation loops)
├── ui/
│   └── app.py            # Streamlit Chatbot Frontend
├── data/
│   ├── raw/              # Scraped raw PDF files
│   └── processed/        # SQLite DB, text Chunks, and FAISS index
├── docker-compose.yml    # Orchestrates FastAPI, Streamlit, and Ollama
├── Makefile              # Helper commands
├── requirements.txt      # Python dependencies
└── .env.example          # Environment variables template
```

## Prerequisites

- **Python 3.10+** (if running locally without Docker)
- **Docker & Docker Compose**
- **Ollama**: If you are running the backend natively or want to persist models easily, you need Ollama installed and the LLaMA 3 model pulled (`ollama pull llama3`).

## Getting Started

### 1. Environment Setup

Copy the example environment file:
```bash
make env
# or manually: cp .env.example .env
```

Open `.env` and configure the database paths or API ports if necessary.

### 2. Running Data Pipeline (ETL) Locally

Before asking questions, you need to populate the database with chunks.

1. **Install Dependencies**:
   ```bash
   make install
   ```

2. **Crawl Data**: 
   *Note: Update the `SEED_URL` and CSS selectors in `scraper/crawl.py` to match the current HTML structure of the real MoSPI website before running this.*
   ```bash
   make crawl
   ```

3. **Process and Chunk**:
   Extracts text from downloaded PDFs and chunks them for the Vector DB.
   ```bash
   make etl
   ```

### 3. Running the App Stack (Docker Compose)

You can spin up the unified stack, including the API, the Streamlit UI, and the LLaMA engine (Ollama) through Docker Compose:

```bash
make up
```
*Note: On its first run, `make up` will execute `ollama pull llama3` inside the container, which may take several minutes depending on your internet connection.*

### 4. Interacting with the Chatbot

1. Open your browser and go to the Streamlit UI:
   [http://localhost:8501](http://localhost:8501)
2. In the left sidebar, click **"Rebuild Index from Data"**. This triggers the API to ingest the JSON chunks created in step 2 and build the FAISS vector index.
3. Once the index is built (the Vector DB status should say "Loaded"), you can start chatting with the MoSPI AI Assistant!

## Stopping the Services

To stop and remove the running Docker containers:
```bash
make down
```

To entirely wipe out the databases and cached data:
```bash
make clean
```
