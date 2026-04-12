# The Brain — Deployment & Operations Guide

The Brain is the standalone AI/ML service (`apps/ai`) that powers all intelligence in Replica AI. It handles LLM inference, vector search, knowledge ingestion, embeddings, and RAG — with zero database dependency. This guide covers how to deploy, configure, and connect to the Brain anywhere.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Hardware Requirements](#hardware-requirements)
4. [Deployment Options](#deployment-options)
   - [Same Machine (Co-located)](#same-machine-co-located)
   - [Dedicated Local Machine](#dedicated-local-machine)
   - [Cloud VPS (DigitalOcean, Hetzner, Linode)](#cloud-vps)
   - [AWS](#aws)
   - [GCP](#gcp)
5. [Configuration Reference](#configuration-reference)
6. [Connecting the Brain to Any App](#connecting-the-brain-to-any-app)
7. [Using the Brain from a Terminal](#using-the-brain-from-a-terminal)
8. [Storage Planning](#storage-planning)
9. [Scaling & Performance Tuning](#scaling--performance-tuning)
10. [Monitoring & Health Checks](#monitoring--health-checks)
11. [Backup & Recovery](#backup--recovery)
12. [Security](#security)

---

## Architecture Overview

The Brain runs as an independent FastAPI service on port **8100**. It depends on three infrastructure services and nothing else:

```
┌─────────────────────────────────────────────────────┐
│                    THE BRAIN                         │
│              FastAPI (port 8100)                     │
│                                                     │
│  Endpoints:                                         │
│  /health, /models, /generate, /generate/stream,     │
│  /summarize, /embeddings, /vectors/search,          │
│  /ingest/text, /ingest/audio, /ingest/video,        │
│  /ingest/document, /tasks/{id},                     │
│  /rag/search, /rag/generate, /rag/stream            │
└──────────┬──────────┬──────────┬────────────────────┘
           │          │          │
     ┌─────▼────┐ ┌───▼────┐ ┌──▼──────────┐
     │  Ollama  │ │ Qdrant │ │    Redis     │
     │  :11434  │ │ :6333  │ │    :6379     │
     │  (LLM)   │ │(vectors)│ │(task status) │
     └──────────┘ └────────┘ └─────────────┘
```

**No PostgreSQL. No user auth. No web framework coupling.**

The Brain is stateless except for:
- **Qdrant** — stores embedding vectors and content previews
- **Redis** — tracks background task status (24h TTL)
- **Filesystem** — stores uploaded files (audio, video, documents)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API framework** | FastAPI + Uvicorn | HTTP server, async request handling |
| **LLM runtime** | Ollama | Local model inference (mistral:7b-instruct default) |
| **Vector database** | Qdrant | Embedding storage and similarity search |
| **Task queue** | Redis | Background task tracking |
| **Transcription** | faster-whisper (base, int8) | Audio-to-text (CPU) |
| **Document parsing** | PyPDF2, python-docx | PDF and DOCX text extraction |
| **Language detection** | langdetect | Auto-detect content language |
| **Streaming** | sse-starlette | Server-Sent Events for token streaming |
| **Video processing** | ffmpeg (system) | Audio extraction, keyframe capture |
| **Python** | 3.11+ | Runtime |

### System Dependencies

These must be installed on the host (not Python packages):

- **ffmpeg** — required for audio/video processing
- **Python 3.11+** — runtime

---

## Hardware Requirements

### Minimum (Light Use — text only, 1-2 users)

| Resource | Spec |
|----------|------|
| CPU | 4 cores |
| RAM | 8 GB |
| Storage | 50 GB SSD |
| GPU | Not required |

This handles text ingestion, embeddings, and basic chat. Inference will be slow (10-30 tokens/sec on CPU for 7B models).

### Recommended (Moderate Use — text + audio, 5-10 users)

| Resource | Spec |
|----------|------|
| CPU | 8 cores (Intel i7/Ryzen 7 or equivalent) |
| RAM | 16 GB |
| Storage | 200 GB NVMe SSD |
| GPU | Optional — NVIDIA GPU with 8+ GB VRAM dramatically speeds inference |

### Heavy Use (All media types, lots of video, 10+ users)

| Resource | Spec |
|----------|------|
| CPU | 16+ cores |
| RAM | 32+ GB |
| Storage | 1-2 TB NVMe SSD (see [Storage Planning](#storage-planning)) |
| GPU | NVIDIA GPU with 12+ GB VRAM (RTX 3060/4060 or better) |

### What Eats Resources

| Operation | CPU | RAM | Disk I/O | GPU (if present) |
|-----------|-----|-----|----------|-------------------|
| LLM inference (Ollama) | Heavy | 4-8 GB per 7B model | Low | Offloads entirely |
| Embedding generation | Medium | 2-4 GB | Low | Helps |
| Audio transcription (faster-whisper) | Heavy | 1-2 GB | Low | Helps significantly |
| Video processing (ffmpeg) | Heavy | Low | High (temp files) | Not used |
| Vector search (Qdrant) | Low | Depends on index size | Medium | Not used |
| Document parsing | Low | Low | Low | Not used |

---

## Deployment Options

### Same Machine (Co-located)

The simplest setup — the Brain runs alongside the main API on the same machine.

```bash
# 1. Install system dependencies
# macOS
brew install ffmpeg python@3.11

# Ubuntu/Debian
sudo apt update && sudo apt install -y ffmpeg python3.11 python3.11-venv

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 3. Start infrastructure (Qdrant + Redis)
# If you already run docker-compose for the main app, these are already running.
docker compose up -d qdrant redis

# 4. Pull the default model
ollama pull mistral:7b-instruct

# 5. Set up the Brain
cd apps/ai
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# 6. Configure
cp .env.example .env
# Edit .env if defaults are fine (localhost for Ollama, Qdrant, Redis)

# 7. Run
uvicorn app.main:app --host 0.0.0.0 --port 8100

# 8. Verify
curl http://localhost:8100/health
```

**In the main API's `.env`:**
```
AI_SERVICE_URL=http://localhost:8100
```

### Dedicated Local Machine

The Brain runs on a separate machine on your local network (e.g., a powerful desktop or a NAS).

**On the Brain machine:**

```bash
# 1. Install system deps + Ollama (same as above)
# 2. Start Qdrant and Redis
docker run -d --name qdrant -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant:latest
docker run -d --name redis -p 6379:6379 -v redis_data:/data redis:7-alpine

# 3. Pull model
ollama pull mistral:7b-instruct

# 4. Clone repo and set up
git clone <your-repo> && cd replica-ai/apps/ai
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .

# 5. Configure .env
cat > .env << 'EOF'
OLLAMA_BASE_URL=http://localhost:11434
QDRANT_HOST=localhost
QDRANT_PORT=6333
REDIS_URL=redis://localhost:6379/0
STORAGE_BASE_PATH=./storage
CORS_ORIGINS=["http://<main-app-ip>:3000","http://<main-app-ip>:8000"]
EOF

# 6. Run (bind to 0.0.0.0 so it's reachable from other machines)
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

**On the main app machine, set:**
```
AI_SERVICE_URL=http://<brain-machine-ip>:8100
```

> **Shared Redis note:** If the main API and the Brain need to share Redis (for task status polling), either point both to the same Redis instance or run Redis on the Brain machine and configure the main API's `REDIS_URL` to reach it.

### Cloud VPS

Works with any VPS provider (DigitalOcean, Hetzner, Linode, Vultr, OVH, etc.).

**Recommended VPS specs:**
- 8+ vCPUs, 16+ GB RAM, 200+ GB NVMe
- GPU VPS (Hetzner GX, Lambda, etc.) for fast inference — optional but impactful

```bash
# SSH into your VPS
ssh user@your-vps-ip

# 1. System deps
sudo apt update && sudo apt install -y ffmpeg python3.11 python3.11-venv docker.io docker-compose-plugin curl
sudo systemctl enable docker && sudo systemctl start docker

# 2. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral:7b-instruct

# 3. Infrastructure
docker compose -f - up -d << 'EOF'
version: "3.9"
services:
  qdrant:
    image: qdrant/qdrant:latest
    restart: unless-stopped
    ports: ["6333:6333"]
    volumes: [qdrant_data:/qdrant/storage]
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports: ["6379:6379"]
    volumes: [redis_data:/data]
volumes:
  qdrant_data:
  redis_data:
EOF

# 4. Deploy the Brain
git clone <your-repo> && cd replica-ai/apps/ai
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env

# Edit .env — update CORS_ORIGINS to include your app's domain

# 5. Run with process manager
pip install gunicorn
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8100 --timeout 600
```

**Production hardening:**

```bash
# Use systemd for auto-restart
sudo tee /etc/systemd/system/brain.service << 'EOF'
[Unit]
Description=Replica AI Brain
After=network.target docker.service

[Service]
User=deploy
WorkingDirectory=/home/deploy/replica-ai/apps/ai
Environment=PATH=/home/deploy/replica-ai/apps/ai/.venv/bin
ExecStart=/home/deploy/replica-ai/apps/ai/.venv/bin/gunicorn app.main:app \
  -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8100 --timeout 600
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable brain && sudo systemctl start brain
```

**Put it behind a reverse proxy (nginx):**

```nginx
server {
    listen 443 ssl;
    server_name brain.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/brain.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/brain.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 600s;  # Long timeout for generation

        # SSE support
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### AWS

**Option A: EC2 instance (simplest)**

1. Launch an EC2 instance:
   - **Instance type:** `c6i.2xlarge` (8 vCPU, 16 GB) for CPU-only, or `g5.xlarge` (4 vCPU, 16 GB, NVIDIA A10G) for GPU
   - **AMI:** Ubuntu 22.04 LTS
   - **Storage:** 200+ GB gp3 EBS volume
   - **Security group:** Open ports 8100 (Brain), 6333 (Qdrant internal), 6379 (Redis internal)
2. Follow the [Cloud VPS](#cloud-vps) instructions above
3. For persistent storage, use an EBS volume mounted at `/data` and set `STORAGE_BASE_PATH=/data/brain-storage`

**Option B: ECS/Fargate (containerized)**

Create a `Dockerfile` for the Brain:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ app/

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

Run Qdrant and Redis as separate ECS services or use **ElastiCache** (Redis) and host Qdrant on EC2.

Ollama does not run in a small container — for AWS, consider:
- Running Ollama on a GPU EC2 instance and pointing `OLLAMA_BASE_URL` at it
- Using **Amazon Bedrock** or another hosted LLM API (would require modifying `llm_engine.py`)

**Option C: EC2 + S3 for file storage**

For heavy media workloads, store processed files in S3 instead of local disk. This requires modifying `app/core/storage.py` to use boto3 for uploads/downloads.

### GCP

**Option A: Compute Engine (simplest)**

1. Create a VM:
   - **Machine type:** `c2-standard-8` (8 vCPU, 32 GB) or `g2-standard-4` (4 vCPU, 16 GB, NVIDIA L4 GPU)
   - **Boot disk:** Ubuntu 22.04, 200+ GB SSD persistent disk
   - **Firewall:** Allow TCP 8100
2. Follow the [Cloud VPS](#cloud-vps) instructions

**Option B: Cloud Run (serverless)**

Cloud Run can host the FastAPI service, but:
- Ollama needs a persistent GPU instance (use a GCE VM)
- Qdrant needs persistent storage (use Qdrant Cloud or a GCE VM)
- Redis: use **Memorystore for Redis**
- File storage: use **Cloud Storage** (requires modifying `storage.py`)

Cloud Run is best for the Brain only if you externalize Ollama to a dedicated inference server.

**Option C: GKE (Kubernetes)**

Deploy the Brain, Qdrant, and Redis as Kubernetes workloads. Ollama runs as a DaemonSet on GPU node pools. This is production-grade but adds operational complexity.

---

## Configuration Reference

All config is via environment variables (or `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_DEFAULT_MODEL` | `mistral:7b-instruct` | Default model for generation |
| `OLLAMA_REQUEST_TIMEOUT` | `300.0` | Max seconds to wait for Ollama response |
| `QDRANT_HOST` | `localhost` | Qdrant server hostname |
| `QDRANT_PORT` | `6333` | Qdrant HTTP port |
| `QDRANT_COLLECTION_NAME` | `knowledge` | Qdrant collection for embeddings |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `STORAGE_BASE_PATH` | `./storage` | Root directory for uploaded files |
| `CORS_ORIGINS` | `["http://localhost:3000","http://localhost:8000"]` | Allowed CORS origins |

### Connecting the Main API to the Brain

In the main API's `.env`:
```
AI_SERVICE_URL=http://<brain-host>:8100
```

If behind a reverse proxy with TLS:
```
AI_SERVICE_URL=https://brain.yourdomain.com
```

---

## Connecting the Brain to Any App

The Brain exposes a standard REST + SSE API. Any application that can make HTTP requests can use it.

### From Any Backend (Python example)

```python
import httpx

BRAIN_URL = "http://brain-host:8100"

async def ask_brain(owner_id: str, message: str, context: str = ""):
    async with httpx.AsyncClient(timeout=300) as client:
        # Generate a response with RAG
        resp = await client.post(f"{BRAIN_URL}/rag/generate", json={
            "owner_id": owner_id,
            "query": message,
            "context": context,
            "model": "mistral:7b-instruct",
        })
        return resp.json()

async def ingest_knowledge(owner_id: str, text: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BRAIN_URL}/ingest/text", json={
            "owner_id": owner_id,
            "text": text,
        })
        return resp.json()

async def stream_response(owner_id: str, query: str):
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{BRAIN_URL}/rag/stream", json={
            "owner_id": owner_id,
            "query": query,
        }) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    print(line[6:], end="", flush=True)
```

### From Node.js / TypeScript

```typescript
const BRAIN_URL = "http://brain-host:8100";

// Generate with RAG
const response = await fetch(`${BRAIN_URL}/rag/generate`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    owner_id: "owner-123",
    query: "What's my favorite food?",
  }),
});
const data = await response.json();

// Stream tokens via SSE
const stream = await fetch(`${BRAIN_URL}/rag/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ owner_id: "owner-123", query: "Tell me about myself" }),
});
const reader = stream.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  process.stdout.write(decoder.decode(value));
}
```

---

## Using the Brain from a Terminal

Every Brain endpoint is accessible with `curl`.

### Health Check

```bash
curl http://localhost:8100/health
```

### Pull a Model

```bash
curl -X POST http://localhost:8100/models/pull \
  -H "Content-Type: application/json" \
  -d '{"name": "mistral:7b-instruct"}'
```

### List Models

```bash
curl http://localhost:8100/models
```

### Generate Text

```bash
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing in simple terms",
    "model": "mistral:7b-instruct",
    "temperature": 0.7
  }'
```

### Stream Text (SSE)

```bash
curl -N -X POST http://localhost:8100/generate/stream \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a short poem about the ocean",
    "model": "mistral:7b-instruct"
  }'
```

### Generate Embeddings

```bash
curl -X POST http://localhost:8100/embeddings \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!", "model": "mistral:7b-instruct"}'
```

### Ingest Text Knowledge

```bash
curl -X POST http://localhost:8100/ingest/text \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "owner-123",
    "text": "My favorite food is sushi. I especially love salmon nigiri."
  }'
```

### Ingest Audio File

```bash
curl -X POST http://localhost:8100/ingest/audio \
  -F "owner_id=owner-123" \
  -F "file=@recording.mp3"
```

### Ingest Video File

```bash
curl -X POST http://localhost:8100/ingest/video \
  -F "owner_id=owner-123" \
  -F "file=@interview.mp4"
```

### Ingest Document

```bash
curl -X POST http://localhost:8100/ingest/document \
  -F "owner_id=owner-123" \
  -F "file=@diary.pdf"
```

### Check Background Task Status

```bash
curl http://localhost:8100/tasks/<task-id>
```

### Vector Search

```bash
curl -X POST http://localhost:8100/vectors/search \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "owner-123",
    "query": "What food do I like?",
    "limit": 5
  }'
```

### RAG Search (search only, no generation)

```bash
curl -X POST http://localhost:8100/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "owner-123",
    "query": "Tell me about my hobbies"
  }'
```

### RAG Generate (search + answer)

```bash
curl -X POST http://localhost:8100/rag/generate \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "owner-123",
    "query": "What do I like to eat?",
    "model": "mistral:7b-instruct"
  }'
```

### RAG Stream (search + stream answer via SSE)

```bash
curl -N -X POST http://localhost:8100/rag/stream \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "owner-123",
    "query": "What are my favorite memories?"
  }'
```

### Delete Vectors for an Entry

```bash
curl -X DELETE http://localhost:8100/vectors/entry-abc-123
```

---

## Storage Planning

The Brain stores three types of data. Plan your disk accordingly.

### 1. Uploaded Files (Filesystem)

Raw files saved under `STORAGE_BASE_PATH` (`./storage` by default).

| Content Type | Avg Size | Example |
|-------------|----------|---------|
| Text | < 1 KB | Short personal notes |
| Audio | 1-50 MB | Voice recordings, interviews |
| Video | 50-500 MB | Life moments, vlogs |
| Documents | 0.1-20 MB | PDFs, journal entries |

**Estimation for heavy video usage:**

| Scenario | Storage Needed |
|----------|---------------|
| 100 videos (avg 200 MB) | ~20 GB |
| 500 videos (avg 200 MB) | ~100 GB |
| 1,000 videos (avg 300 MB) | ~300 GB |
| 2,000 videos + 500 audio + docs | ~700 GB |

Rule of thumb: **allocate 1 GB per 3-5 videos** as a planning baseline. If users share daily video diaries (5-10 min each, ~150-300 MB), one user generates ~5-10 GB/month of raw video alone.

### 2. Qdrant Vectors

Each embedding is ~15 KB in Qdrant (3840 dimensions x float32 + payload metadata).

| Entries | Qdrant Disk | Qdrant RAM |
|---------|-------------|------------|
| 10,000 | ~200 MB | ~500 MB |
| 100,000 | ~2 GB | ~4 GB |
| 1,000,000 | ~20 GB | ~30 GB |

A single video generates multiple chunks (transcript is split into 2000-char segments), so 1 video may produce 5-50 embeddings depending on length.

### 3. Ollama Models

Models are stored in `~/.ollama/models/`.

| Model | Disk Size |
|-------|-----------|
| mistral:7b-instruct | ~4 GB |
| llama3:8b | ~4.7 GB |
| mistral:7b (multiple quantizations) | 4-7 GB each |
| Per-owner custom models | ~50 KB each (Modelfile only, shares base weights) |

### Total Storage Recommendation

| Use Case | Recommended Disk |
|----------|-----------------|
| Light (text + some audio, 1-5 users) | 50 GB |
| Moderate (mixed media, 5-20 users) | 200 GB |
| Heavy (lots of video, 20-50 users) | 500 GB - 1 TB |
| Very heavy (thousands of videos, 50+ users) | 2+ TB, consider object storage (S3/GCS) |

> For very heavy workloads, modify `app/core/storage.py` to write files to S3 / GCS / MinIO instead of local disk. Qdrant vectors and Ollama models still need local fast storage.

---

## Scaling & Performance Tuning

### Increase Inference Speed

1. **Use a GPU** — Ollama automatically uses NVIDIA GPUs. A single RTX 3060 (12 GB VRAM) gives 5-10x speedup for 7B models.
2. **Use a smaller/quantized model** — `mistral:7b-instruct-q4_0` uses less RAM and runs faster than the full model.
3. **Increase Ollama parallelism** — set `OLLAMA_NUM_PARALLEL=4` in the Ollama environment to handle concurrent requests.

### Run Multiple Workers

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8100 --timeout 600
```

More workers handle more concurrent requests but don't speed up Ollama (which is the bottleneck). 2-4 workers is usually enough.

### Qdrant Performance

- For < 100K vectors, default settings are fine.
- For > 100K vectors, consider enabling on-disk storage in Qdrant config:
  ```yaml
  storage:
    on_disk_payload: true
  ```
- Use payload indexes (already configured for `owner_id` and `content_type`).

### Separate Heavy Services

For best performance on a single machine, pin services to specific CPU cores:
- Ollama: gets the most cores (it's CPU-bound during inference)
- Qdrant: 1-2 cores
- Redis: 1 core
- Brain API: 2-4 cores

Or, on a cloud setup, run Ollama on a GPU instance and everything else on a cheaper CPU instance.

---

## Monitoring & Health Checks

### Health Endpoint

```bash
# Returns status of Ollama and Qdrant connectivity
curl http://localhost:8100/health

# Response:
# {"status": "healthy", "ollama": "connected", "qdrant": "connected"}
```

Use this for load balancer health checks, uptime monitoring (UptimeRobot, Healthchecks.io), and container orchestration liveness probes.

### Logs

Uvicorn logs all requests to stdout. For production, redirect to a file or log aggregator:

```bash
# Log to file
uvicorn app.main:app --host 0.0.0.0 --port 8100 2>&1 | tee /var/log/brain.log

# Or with systemd, logs go to journald
journalctl -u brain -f
```

### Key Metrics to Watch

- **Response time on `/generate`** — if > 30s consistently, you need more CPU or a GPU
- **Qdrant collection size** — `curl http://localhost:6333/collections/knowledge`
- **Redis memory** — `redis-cli info memory`
- **Disk usage** — `du -sh ./storage/` for uploaded files

---

## Backup & Recovery

### What to Back Up

| Data | Location | Backup Method |
|------|----------|---------------|
| Uploaded files | `STORAGE_BASE_PATH` (default `./storage/`) | rsync, S3 sync, tar |
| Qdrant vectors | Docker volume `qdrant_data` | Qdrant snapshots API |
| Redis task data | Docker volume `redis_data` | Not critical (ephemeral, 24h TTL) |
| Ollama models | `~/.ollama/models/` | Can be re-pulled, backup optional |
| .env config | `apps/ai/.env` | Version control or secrets manager |

### Qdrant Snapshot

```bash
# Create snapshot
curl -X POST http://localhost:6333/collections/knowledge/snapshots

# List snapshots
curl http://localhost:6333/collections/knowledge/snapshots

# Download snapshot
curl http://localhost:6333/collections/knowledge/snapshots/<snapshot-name> --output backup.snapshot
```

### File Storage Backup

```bash
# Sync to a backup location
rsync -av ./storage/ /backup/brain-storage/

# Or to S3
aws s3 sync ./storage/ s3://your-bucket/brain-storage/
```

---

## Security

The Brain has **no built-in authentication**. It trusts whatever sends it requests. This is by design — auth is handled by the main API which proxies requests.

### When Exposing to the Internet

If the Brain is accessible from the public internet (cloud deployment), you **must** add a security layer:

1. **Reverse proxy with auth** — Use nginx with basic auth or API key validation:
   ```nginx
   location / {
       if ($http_x_api_key != "your-secret-key") {
           return 401;
       }
       proxy_pass http://127.0.0.1:8100;
   }
   ```

2. **Firewall rules** — Only allow connections from your main API's IP:
   ```bash
   # UFW example
   sudo ufw allow from <main-api-ip> to any port 8100
   sudo ufw deny 8100
   ```

3. **VPN / Private network** — Run the Brain on a private subnet (AWS VPC, GCP VPC) and only expose the main API publicly.

4. **CORS** — Already configured via `CORS_ORIGINS`. Set this to only your app's domain in production.

### Data Isolation

The Brain uses `owner_id` to isolate data between users:
- Qdrant searches are always filtered by `owner_id`
- File storage is namespaced: `storage/{owner_id}/{content_type}/{entry_id}/`
- No cross-owner data leakage is possible through the API

Ensure the calling application always passes the correct `owner_id` — the Brain does not verify ownership.
