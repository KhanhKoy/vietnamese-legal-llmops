# Law-Chatbot

A Retrieval‑Augmented Generation (RAG) chatbot specialized for Vietnamese legal documents.  
The project loads a large legal corpus, chunks the text, creates embeddings with a multilingual Sentence‑Transformer model, stores the vectors in a SQLite‑based vector store, and exposes a FastAPI service that can answer legal‑related questions.

## Table of Contents
- [Project Overview](#project-overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Building the Vector Store](#building-the-vector-store)
  - [Running the API Locally](#running-the-api-locally)
  - [Using Docker](#using-docker)
  - [Syncing Artefacts to AWS S3](#syncing-artefacts-to-aws-s3)
  - [Running Evaluation](#running-evaluation)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Project Overview

Law‑Chatbot implements a end‑to‑end RAG pipeline:

1. **Document ingestion** – streamed reading of metadata and content from HuggingFace datasets (or local parquet/files) via `src/rag_core/dataset_reader.py`.
2. **Text chunking** – overlapping character‑based chunks (`src/rag_core/chunking.py`).
3. **Embedding generation** – Sentence‑Transformer model (default `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) producing 384‑dim vectors (`src/rag_core/embeddings.py`).
4. **Vector storage** – SQLite database with BLOB embeddings (stored as `float16` to halve size) (`src/rag_core/vector_store.py`).
5. **Query service** – receives a question, embeds it, performs cosine similarity search, returns top‑k chunks together with a simple generator (`src/rag_core/qa_service.py` / `src/rag_core/generator.py`/`src/rag_core/prompt.py`).
6. **HTTP API** – FastAPI app exposing `/ask` endpoint (`src/api/app.py`, `src/api/routes.py`).
7. **Monitoring & feedback** – structured logging and a simple feedback store (`src/monitoring/`).
8. **Evaluation** – offline metrics (`src/evaluation/`) and test harness (`scripts/eval.py`).
9. **AWS integration** – helper script `scripts/sync_to_s3.py` to upload/download the built vector store to/from an S3 bucket.
10. **Deployment** – Dockerfile, docker‑compose.yml and entrypoint for easy containerised deployment.

## Features

- Streaming ingestion – low RAM footprint even for corpora of millions of documents.
- Configurable chunk size & overlap via environment variables.
- Embedding model can be swapped by changing `EMBEDDING_MODEL_NAME` in `.env`.
- Vector store uses `float16` embeddings → ~50% storage reduction.
- Periodic SQLite `COMMIT` + `PRAGMA` tweaks to keep WAL/memory usage low.
- FastAPI service with async support, automatic OpenAPI docs at `/docs`.
- Dockerised for local dev or cloud deployment (ECS, EKS, ECR, etc.).
- Script to sync artefacts to AWS S3 for reproducible builds across environments.
- Comprehensive test suite (`test/`) and evaluation scripts.
- Detailed logging and feedback collection for production observability.

## Architecture

```
┌─────────────────────┐
│   scripts/          │  │  build_index.py   → creates models/vector_store/
│   sync_to_s3.py     │  │  upload/download to S3
│   eval.py           │  │  run offline evaluation
│   run_api.py        │  │  alternative entrypoint
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   src/              │
│   ├─ rag_core/      │  │  core RAG pipeline
│   │   ├─ dataset_reader.py
│   │   ├─ chunking.py
│   │   ├─ embeddings.py
│   │   ├─ vector_store.py
│   │   ├─ pipeline.py
│   │   ├─ qa_service.py
│   │   ├─ generator.py
│   │   └─ prompt.py
│   │
│   ├─ api/           │  │  FastAPI application
│   │   ├─ app.py
│   │   ├─ routes.py
│   │   └─ schemas.py
│   │
│   ├─ evaluation/    │  │  metrics, eval_runner, test_cases.json
│   │
│   └─ monitoring/    │  │  logging_config.py, feedback_store.py
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   deploy/           │  │  Dockerfile, docker‑compose.yml, entrypoint.sh
└─────────────────────┘
          │
          ▼
┌─────────────────────┐
│   models/           │  │  (generated) vector_store/
└─────────────────────┘
```

## Prerequisites

- **Python 3.9+** (tested on 3.11)
- **Git**
- (Optional) **Docker** & **docker‑compose** for containerised deployment.
- **AWS CLI** or configured boto3 credentials if you plan to use the `sync_to_s3.py` script.
- At least **2 GB RAM** for building the index (more if you increase batch sizes).

## Installation

```bash
# 1️⃣ Clone the repository
git clone <repository‑url>
cd Law-Chatbot

# 2️⃣ Create a virtual environment (recommended)
python -m venv .venv
# Windows:
# .venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3️⃣ Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4️⃣ Prepare environment variables
cp .env.sample .env   # copy the template
# Edit .env and fill in:
#   - HF_DATASET_NAME / HF_METADATA_CONFIG / HF_CONTENT_PARQUET_URL (if not using defaults)
#   - EMBEDDING_MODEL_NAME, EMBEDDING_BATCH_SIZE
#   - AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
#   - VECTOR_S3_BUCKET, VECTOR_S3_PREFIX (for sync_to_s3)
#   - Any other secrets (DB passwords, etc.) if applicable
```

## Configuration

All configurable values are read from:

- **`.env`** file (loaded via `python‑dotenv` inside `src/rag_core/config.py`).
- **YAML files** in `configs/` (`dev.yaml`, `prod.yaml`, `logging.yaml`, `aws.yaml`) – used by specific scripts.
- **Environment variables** override YAML values.

Key variables (see `.env.sample` for defaults):

| Variable | Description |
|----------|-------------|
| `HF_DATASET_NAME` | HuggingFace dataset identifier (default: `th1nhng0/vietnamese-legal-documents`). |
| `HF_METADATA_CONFIG` | Dataset config for metadata (default: `metadata`). |
| `HF_CONTENT_PARQUET_URL` | Direct link to the content parquet file. |
| `EMBEDDING_MODEL_NAME` | SentenceTransformer model name. |
| `EMBEDDING_BATCH_SIZE` | Batch size for embedding generation (default: 32). |
| `CHUNK_SIZE_CHARS` | Approximate max characters per chunk (default: 1200). |
| `CHUNK_OVERLAP_CHARS` | Overlap between chunks (default: 200). |
| `VECTOR_STORE_DIR` | Folder where SQLite vector store is saved (default: `models/vector_store`). |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` | Credentials for boto3/S3 sync. |
| `VECTOR_S3_BUCKET` | S3 bucket to store/retrieve vector store artefacts. |
| `VECTOR_S3_PREFIX` | Prefix (folder) inside the bucket. |
| `LOG_LEVEL` | Logging level (`INFO`, `DEBUG`, etc.). |

## Usage

### Building the Vector Store

The indexer reads the dataset, creates chunks, computes embeddings, and stores them in `models/vector_store/`.

```bash
# Make sure your .env is set (especially HF_* and EMBEDDING_* variables)
python scripts/build_index.py
```

**Optional arguments** (if you want to limit data for quick testing):

```bash
python scripts/build_index.py \
    --metadata-limit 10000 \   # only first 10k metadata rows
    --content-limit 10000      # only first 10k content rows
```

The script will:

1. Stream metadata into a temporary SQLite file.
2. Iterate over content in batches, joining with metadata.
3. Chunk each document.
4. Generate embeddings in batches (`EMBEDDING_BATCH_SIZE`).
5. Insert into the vector store, committing every `commit_interval` chunks (default 100) to keep RAM low.
6. Finally call `store.save()` to write metadata (`store_meta.json`).

> **Note:** The first run may take considerable time depending on dataset size and your hardware. Subsequent runs are fast if you reuse the existing vector store (delete the folder to force a rebuild).

### Running the API Locally

```bash
# Option A: via main.py (thin wrapper)
python main.py

# Option B: via the dedicated runner (same effect)
python scripts/run_api.py
```

The API will start on `http://0.0.0.0:8000`. Open `http://localhost:8000/docs` to see the interactive Swagger UI and test the `/ask` endpoint.

**Example request (via curl):**

```bash
curl -X POST "http://localhost:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "Luật đất đai Việt Nam có quy định gì về quyền sử dụng đất?", "top_k": 5}'
```

Response format:

```json
{
  "answer": "... generated answer ...",
  "retrieved_chunks": [
    {
      "chunk_id": "doc123::chunk_0",
      "document_id": "doc123",
      "text": "... chunk text ...",
      "score": 0.842,
      "metadata": { ... }
    },
    ...
  ]
}
```

### Using Docker

```bash
# Build the image
docker build -t law-chatbot:latest .

# Run (make sure to mount or provide .env)
docker run --rm -p 8000:8000 \
   --env-file .env \
   law-chatbot:latest
```

If you prefer docker‑compose (useful for adding a reverse proxy or a local S3 mock):

```bash
docker-compose up --build
```

The `docker-compose.yml` defines a service `app` that mounts the current folder as `/app` and passes through the `.env` file.

### Syncing Artefacts to AWS S3

After building the vector store locally, upload it to S3 so other environments (CI, staging, production) can reuse it without rebuilding:

```bash
python scripts/sync_to_s3.py \
    --bucket my-ml-artifacts \
    --prefix law-chatbot/v1
```

To **download** the artefacts (useful for fresh clones or production containers):

```bash
python scripts/sync_to_s3.py \
    --bucket my-ml-artifacts \
    --prefix law-chatbot/v1 \
    --download-only   # you may need to add this flag; see script for details
```

The script will upload/download everything under `models/vector_store/` preserving the folder structure.

### Running Evaluation

The evaluation suite computes standard retrieval metrics (e.g., Recall@k, MRR) on a predefined set of test questions (`src/evaluation/test_cases.json`).

```bash
python scripts/eval.py
```

You can adjust the number of questions or the `top_k` via command‑line arguments (see `scripts/eval.py --help`).

## Environment Variables

A complete list of variables used throughout the project:

| Variable | Where it’s used | Default / Example |
|----------|----------------|-------------------|
| `HF_DATASET_NAME` | `DatasetReader` | `th1nhng0/vietnamese-legal-documents` |
| `HF_METADATA_CONFIG` | `DatasetReader` | `metadata` |
| `HF_CONTENT_PARQUET_URL` | `DatasetReader` | URL to content parquet |
| `EMBEDDING_MODEL_NAME` | `EmbeddingService` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `EMBEDDING_BATCH_SIZE` | `EmbeddingService` | `32` |
| `CHUNK_SIZE_CHARS` | `chunking.split_text` | `1200` |
| `CHUNK_OVERLAP_CHARS` | `chunking.split_text` | `200` |
| `VECTOR_STORE_DIR` | `VectorStore.__init__` | `models/vector_store` |
| `COMMIT_INTERVAL` (hardcoded in `pipeline.py`) | `build_index_pipeline` | `100` |
| `DOCUMENT_BATCH_SIZE` (argument to `build_index_pipeline`) | `build_index.py` | `32` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | `boto3` client in `sync_to_s3.py` | – |
| `VECTOR_S3_BUCKET` | `sync_to_s3.py` | – |
| `VECTOR_S3_PREFIX` | `sync_to_s3.py` | – |
| `LOG_LEVEL` | `monitoring/logging_config.py` | `INFO` |
| `PORT` (if you want to override) | `uvicorn` entrypoint | `8000` |

Create or edit `.env` based on `.env.sample` to set these values.

## Testing

Unit tests live in the `test/` directory and can be run with `pytest`:

```bash
pytest -q
```

Ensure you have the test dependencies installed (`pip install -r requirements.txt` already includes `pytest`).

## Project Structure (short)

```
Law-Chatbot/
│
├─ .gitignore               # excludes .env, __pycache__, models/, etc.
├─ .env.sample              # template for local env
├─ README.md                # this file
├─ requirements.txt
├─ main.py
│
├─ src/
│   ├─ rag_core/            # core RAG logic
│   ├─ api/                 # FastAPI service
│   ├─ evaluation/          # offline metrics & test cases
│   └─ monitoring/          # logging & feedback
│
├─ scripts/
│   ├─ build_index.py       # create vector store
│   ├─ sync_to_s3.py        # upload/download to/from S3
│   ├─ eval.py              # run evaluation
│   └─ run_api.py           # alternative API launcher
│
├─ configs/
│   ├─ dev.yaml
│   ├─ prod.yaml
│   ├─ logging.yaml
│   └─ aws.yaml
│
├─ deploy/
│   ├─ Dockerfile
│   ├─ docker-compose.yml
│   └─ entrypoint.sh
│
├─ models/                  # ← generated vector store (gitignored)
│   └─ vector_store/
│
└─ test/                    # unit tests
```

## Contributing

1. Fork the repository and create your feature branch (`git checkout -b feature/awesome-thing`).
2. Make sure your changes follow the existing code style (PEP8, type hints where appropriate).
3. Add or update tests as needed.
4. Run the full test suite locally: `pytest`.
5. Commit with a clear message and push to your fork.
6. Open a Pull Request describing the changes and any relevant performance or security impact.

> **Please never commit `.env` or any file under `models/`** – add them to `.gitignore` if they appear accidentally.

## License

This project is licensed under the MIT License – see the `LICENSE` file for details.

--- 

*Happy coding and may your legal queries always find the right answer!* 🚀