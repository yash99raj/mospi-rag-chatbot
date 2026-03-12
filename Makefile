.PHONY: env install crawl etl up down clean pull-model

# Variables
PYTHON = python3
PIP = pip3
APP_DIR = $(PWD)

env:
	test -f .env || cp .env.example .env

install:
	$(PIP) install -r requirements.txt

pull-model:
	@echo "Ensuring Ollama is running and pulling llama3 model (Requires local Ollama installation)..."
	ollama pull llama3

crawl:
	@echo "Starting MoSPI data crawler..."
	PYTHONPATH=$(APP_DIR) $(PYTHON) scraper/crawl.py

etl:
	@echo "Starting Processing Pipeline (Chunking and extracting)..."
	PYTHONPATH=$(APP_DIR) $(PYTHON) pipeline/run.py

up: env
	@echo "Starting the application stack via Docker Compose..."
	docker compose up -d
	@echo "Waiting for services to start..."
	@sleep 5
	@echo "Pulling LLaMA-3 inside the docker container (takes time if first run)..."
	docker compose exec ollama ollama pull llama3
	@echo "Stack is running!"
	@echo "UI: http://localhost:8501"
	@echo "API: http://localhost:8000/docs"

down:
	@echo "Stopping Docker containers..."
	docker compose down

clean:
	@echo "Cleaning up volumes and __pycache__..."
	find . -type d -name "__pycache__" -exec rm -r {} +
	rm -rf data/processed/*
	rm -rf data/raw/*
	docker compose down -v
