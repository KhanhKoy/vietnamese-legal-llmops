# EC2 deploy (Streamlit UI + RAG /ask API)

## Architecture

- Container `api` — FastAPI `api.main:app` on port **8000** (`POST /ask`)
- Container `streamlit` — UI on port **8501**, calls `API_URL=http://api:8000/ask`
- App users/chat + RAG vectors — **existing RDS Postgres** (no `legal_chat.db` on disk)

EC2 only needs Docker. Do not mount SQLite into the container.

## EC2 prerequisites

1. Instance in a subnet that can reach RDS (`PGHOST`) and Bedrock (or public egress).
2. Security groups:
   - Inbound EC2: `8501` (UI), optionally `8000` (API) from your IP / ALB
   - RDS inbound `5432` from the EC2 security group
3. IAM instance role preferred for Bedrock (and S3 if used). Avoid long-lived access keys when possible.
4. Size: embedding on CPU is heavy — prefer **≥8 GB RAM** and **≥20 GB disk** (e.g. `t3.large`). Default `torch` CUDA wheels will fill a small root volume; the Dockerfile installs **CPU-only torch**.

## Deploy steps

```bash
# on EC2
sudo yum install -y docker git   # or apt equivalent
sudo systemctl enable --now docker
sudo usermod -aG docker $USER    # re-login after this

git clone <your-repo-url> vietnamese-legal-llmops
cd vietnamese-legal-llmops

# put production secrets here (never commit real keys)
nano .env

# ensure these are set for cloud
# USE_PGVECTOR=true
# APP_DB_BACKEND=postgres
# PGHOST=...
# LLM_PROVIDER=bedrock   # or gemini + GEMINI_API_KEY

cd deploy
docker compose up -d --build
```

Open `http://<ec2-public-ip>:8501`.

Init / migrate app tables (once, from laptop or EC2):

```bash
python scripts/init_app_db.py
```

## Useful commands

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
docker compose -f deploy/docker-compose.yml logs -f streamlit
docker compose -f deploy/docker-compose.yml down
```

## Notes

- First API start may download the embedding model — healthcheck `start-period` is 120s.
- For ALB: target group → Streamlit `:8501`; keep API internal on the Docker network.
- Cognito/`api.app` is not required for this Streamlit path; `/ask` on `api.main` has no JWT.
