import streamlit as st
import requests
import json
import os

# API configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="MoSPI LLaMA RAG Chatbot",
    page_icon="📚",
    layout="wide"
)

st.title("📚 MoSPI Research Assistant Chatbot")
st.markdown("Powered by LLaMA 3 and FAISS Vector Search")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Check API Health
    try:
        health_resp = requests.get(f"{API_URL}/health", timeout=2)
        health_status = health_resp.json()
        
        st.success(f"API : {health_status.get('api', 'Unknown')}")
        st.success(f"Vector DB: {'Loaded' if health_status.get('index_loaded') else 'Empty'}")
        
        ollama_status = health_status.get('ollama', 'unreachable')
        if ollama_status == 'ok':
            st.success("LLaMA/Ollama: Connected")
        else:
            st.error("LLaMA/Ollama: Unreachable")
            
    except requests.exceptions.RequestException:
        st.error("API Server Unreachable.")
        st.stop()
        
    st.divider()
    
    # RAG Settings
    st.subheader("RAG Parameters")
    top_k = int(st.slider("Top-K Sources to Retrieve ($k$)", min_value=1, max_value=10, value=4))
    temperature = float(st.slider("LLM Temperature", min_value=0.0, max_value=1.0, value=0.1, step=0.1))
    
    st.divider()
    
    # Ingestion Trigger
    if st.button("Rebuild Index from Data"):
        with st.spinner("Starting build..."):
            try:
                resp = requests.post(f"{API_URL}/ingest", json={}, timeout=10)
                if resp.status_code == 200:
                    st.toast("Index rebuild started in background!", icon="🔥")
                else:
                    st.error("Failed to start ingestion.")
            except Exception as e:
                st.error(f"Error: {e}")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            with st.expander("View Retrieved Sources"):
                for idx, src in enumerate(message["sources"], 1):
                    st.markdown(f"**{idx}. [{src.get('title', 'Unknown Title')}]({src.get('url', '#')})** (Dist: {src.get('distance', 0):.4f})")

# React to user input
if prompt := st.chat_input("Ask a question about MoSPI publications..."):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Generate response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        with st.spinner('Accessing MoSPI publications...'):
            try:
                # Query API
                payload = {
                    "query": prompt,
                    "top_k": top_k,
                    "temperature": temperature
                }
                
                response = requests.post(f"{API_URL}/ask", json=payload, timeout=120)
                response.raise_for_status()
                result = response.json()
                
                answer = result.get("answer", "No answer received.")
                sources = result.get("sources", [])
                
                # Render answer
                message_placeholder.markdown(answer)
                
                # Save to history with sources
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": answer,
                    "sources": sources
                })
                
                # Show sources immediately in expander (since we just got them)
                if sources:
                    with st.expander("View Retrieved Sources"):
                        for idx, src in enumerate(sources, 1):
                            st.markdown(f"**{idx}. [{src.get('title', 'Unknown Title')}]({src.get('url', '#')})** (Dist: {src.get('distance', 0):.4f})")
                            
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to get response from Backend Context Server: {e}")
            except Exception as e:
                st.error(f"An error occurred: {e}")
