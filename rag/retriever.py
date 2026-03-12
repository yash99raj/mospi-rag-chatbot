import os
import json
import logging
import numpy as np
import faiss
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Paths configuration
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHUNK_DIR = os.path.join(BASE_DIR, "data", "processed", "chunks")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "data", "processed", "faiss_index")
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

INDEX_PATH = os.path.join(VECTOR_DB_DIR, "index.faiss")
METADATA_PATH = os.path.join(VECTOR_DB_DIR, "metadata.json")

# Initialize Sentence Transformer model
# all-MiniLM-L6-v2 is fast and efficient for general semantic search
MODEL_NAME = 'all-MiniLM-L6-v2'
try:
    logging.info(f"Loading SentenceTransformer model: {MODEL_NAME}")
    encoder = SentenceTransformer(MODEL_NAME)
    EMBEDDING_DIM = encoder.get_sentence_embedding_dimension()
except Exception as e:
    logging.error(f"Failed to load sentence-transformers model: {e}")
    # Fallback to a placeholder if the library is stubbed/missing in this env
    encoder = None
    EMBEDDING_DIM = 384


class FAISSRetriever:
    def __init__(self):
        self.index = None
        self.metadata_store = []
        self.load_index()

    def load_index(self):
        """Loads the FAISS index and metadata store if they exist, otherwise initializes new ones."""
        if os.path.exists(INDEX_PATH) and os.path.exists(METADATA_PATH):
            logging.info("Loading existing FAISS index...")
            self.index = faiss.read_index(INDEX_PATH)
            with open(METADATA_PATH, 'r', encoding='utf-8') as f:
                self.metadata_store = json.load(f)
            logging.info(f"Loaded index with {self.index.ntotal} vectors.")
        else:
            logging.info("Initializing new FAISS index...")
            # Using Inner Product (IP) index for cosine similarity (requires normalized vectors)
            # or L2 for euclidean distance. Sentence transformers often work well with cosine.
            self.index = faiss.IndexFlatL2(EMBEDDING_DIM) 
            self.metadata_store = []

    def save_index(self):
        """Saves the FAISS index and metadata to disk."""
        faiss.write_index(self.index, INDEX_PATH)
        with open(METADATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(self.metadata_store, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved FAISS index with {self.index.ntotal} vectors.")

    def build_index_from_chunks(self, batch_size: int = 64):
        """
        Reads processed chunk files from CHUNK_DIR, embeds them, and adds them to the FAISS index.
        This function should only ingest new/unindexed documents in a real production system.
        For simplicity, this reconstructs the index from scratch.
        """
        logging.info(f"Building index from chunks in {CHUNK_DIR}...")
        
        self.index = faiss.IndexFlatL2(EMBEDDING_DIM)
        self.metadata_store = []
        
        all_chunks_text = []
        chunk_metadata_list = []
        
        if not os.path.exists(CHUNK_DIR):
            logging.warning(f"Chunk directory not found: {CHUNK_DIR}")
            return
            
        for filename in os.listdir(CHUNK_DIR):
            if not filename.endswith('.json'):
                continue
                
            filepath = os.path.join(CHUNK_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    doc_data = json.load(f)
                    
                doc_id = doc_data.get('doc_id')
                doc_metadata = doc_data.get('metadata', {})
                chunks = doc_data.get('chunks', [])
                
                for i, chunk_text in enumerate(chunks):
                    # We store exactly what's needed for citation and context retrieval
                    meta = {
                        "doc_id": doc_id,
                        "title": doc_metadata.get("title", "Unknown Title"),
                        "url": doc_metadata.get("url", ""),
                        "chunk_idx": i,
                        "text": chunk_text
                    }
                    all_chunks_text.append(chunk_text)
                    chunk_metadata_list.append(meta)
                    
            except Exception as e:
                logging.error(f"Error processing {filename}: {e}")
                
        if not all_chunks_text:
            logging.info("No chunks found to index.")
            return

        logging.info(f"Encoding {len(all_chunks_text)} total chunks...")
        
        # Process in batches to manage memory
        for i in range(0, len(all_chunks_text), batch_size):
            batch_texts = all_chunks_text[i:i + batch_size]
            batch_meta = chunk_metadata_list[i:i + batch_size]
            
            if encoder is None:
                # Mock embeddings if sentence-transformers isn't fully set up yet
                logging.warning("Using MOCK embeddings.")
                embeddings = np.random.rand(len(batch_texts), EMBEDDING_DIM).astype('float32')
            else:
                # encode returns a numpy array
                embeddings = encoder.encode(batch_texts, convert_to_numpy=True)
                
            # FAISS requires float32
            embeddings = np.array(embeddings).astype('float32')
            
            # Add to index
            self.index.add(embeddings)
            self.metadata_store.extend(batch_meta)
            
            logging.info(f"Indexed batch {i//batch_size + 1}/{(len(all_chunks_text) + batch_size - 1)//batch_size}")
            
        self.save_index()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Embeds the query and searches the FAISS index for the top_k most similar chunks.
        """
        if self.index is None or self.index.ntotal == 0:
            logging.warning("FAISS index is empty or not loaded.")
            return []
            
        if encoder is None:
            logging.warning("Encoder not available for query embedding.")
            query_embedding = np.random.rand(1, EMBEDDING_DIM).astype('float32')
        else:
            query_embedding = encoder.encode([query], convert_to_numpy=True).astype('float32')
            
        # D is distances, I is indices of the nearest neighbors
        distances, indices = self.index.search(query_embedding, top_k)
        
        results = []
        # indices[0] contains the indices for our single query
        for i, idx in enumerate(indices[0]):
            if idx == -1: # FAISS returns -1 if there aren't enough vectors
                continue
            
            # idx is an index into our metadata_store
            if idx < len(self.metadata_store):
                result_meta = self.metadata_store[idx].copy()
                result_meta['distance'] = float(distances[0][i])
                results.append(result_meta)
                
        return results


def build_llama_prompt(query: str, retrieved_chunks: List[Dict[str, Any]]) -> str:
    """
    Constructs the prompt for the LLaMA 3 model using the retrieved context.
    Enforces strict grounding and requires bulleted citations.
    """
    
    context_blocks = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        title = chunk.get('title', 'Unknown Source')
        url = chunk.get('url', 'No URL available')
        text = chunk.get('text', '')
        
        context_blocks.append(f"[Source {i}: {title}] ({url})\n{text}")
        
    context_str = "\n\n---\n\n".join(context_blocks)
    
    prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert research assistant answering questions based solely on the official publications provided in the context. 
Your task is to answer the user's question accurately using ONLY the information found in the Context blocks below.

Strict Rules:
1. Do not use external knowledge or invent information. If the answer is not contained in the context, state clearly: "I cannot answer this question based on the provided documents."
2. You must include bulleted citations for every factual claim you make.
3. Citations must include the exact Title and URL of the source document used.

Format your response clearly.

<|eot_id|><|start_header_id|>user<|end_header_id|>

Query: {query}

Context:
{context_str}

<|eot_id|><|start_header_id|>assistant<|end_header_id|>"""

    return prompt

if __name__ == "__main__":
    # Example standalone execution to build index
    retriever = FAISSRetriever()
    
    # Uncomment to trigger indexing of current chunks
    # retriever.build_index_from_chunks()
    
    # Example query test
    # query = "What is the latest GDP growth rate?"
    # results = retriever.search(query)
    # prompt = build_llama_prompt(query, results)
    # print(prompt)
