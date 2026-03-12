from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import logging
import requests
import os

from rag.retriever import FAISSRetriever, build_llama_prompt

app = FastAPI(title="MoSPI RAG API")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Global retriever instance
retriever = FAISSRetriever()

# Ollama Endpoint
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3")

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    temperature: float = 0.7

class IngestRequest(BaseModel):
    # Optional parameters for ingestion could go here
    pass

@app.get("/health")
def health_check():
    """Health check endpoint to verify API and dependencies."""
    status = {"api": "ok", "index_loaded": retriever.index is not None}
    
    # Check Ollama connection
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        status["ollama"] = "ok" if response.status_code == 200 else "unreachable"
    except Exception:
        status["ollama"] = "unreachable"
        
    return status

@app.post("/ingest")
def start_ingestion(request: IngestRequest, background_tasks: BackgroundTasks):
    """Triggers the FAISS indexing process in the background."""
    def rebuild_task():
        try:
            logging.info("Starting background index rebuild...")
            retriever.build_index_from_chunks()
            logging.info("Background indexing complete.")
        except Exception as e:
            logging.error(f"Indexing failed: {e}")
            
    background_tasks.add_task(rebuild_task)
    return {"message": "Ingestion started in the background."}

@app.post("/ask")
def ask_question(request: QueryRequest):
    """Queries the document base and generates an answer using LLaMA via Ollama."""
    query = request.query
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    logging.info(f"Processing query: '{query}', top_k: {request.top_k}")
    
    # 1. Retrieve Context
    contexts = retriever.search(query, top_k=request.top_k)
    if not contexts:
        return {
            "query": query,
            "answer": "I cannot answer this question based on the provided documents because no relevant context was found.",
            "sources": []
        }
        
    # 2. Build Prompt
    prompt = build_llama_prompt(query, contexts)
    
    # 3. Call LLaMA (Ollama)
    ollama_payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": request.temperature
        }
    }
    
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate", 
            json=ollama_payload,
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        answer = result.get("response", "Error generating response.")
    except Exception as e:
        logging.error(f"Error calling Ollama: {e}")
        raise HTTPException(status_code=502, detail="Failed to communicate with LLM service.")
        
    return {
        "query": query,
        "answer": answer,
        "sources": [
            {"title": ctx.get("title"), "url": ctx.get("url"), "distance": ctx.get("distance")}
            for ctx in contexts
        ]
    }
