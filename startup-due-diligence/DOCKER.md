# Docker Setup — Startup Due Diligence

## 1. Install Docker Desktop (Windows)

1. Go to **https://www.docker.com/products/docker-desktop/**
2. Click **Download for Windows** and run the installer.
3. During install, keep **"Use WSL 2 instead of Hyper-V"** checked (recommended).
4. Restart your machine when prompted.
5. Launch **Docker Desktop** from the Start menu and wait for the whale icon in the
   taskbar to show a green "Running" status.

Verify the install:
```
docker --version
docker compose version
```
Both should print version numbers.

---

## 2. Prerequisites

Your root `.env` file (at `POCs - Qubrid/.env`) must contain:

```
QUBRID_BASE_URL=https://...
QUBRID_API_KEY=your_key_here

# Optional — for LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT_DD=startup-due-diligence
```

The `docker-compose.yml` loads this file automatically via `env_file: ../.env`.

---

## 3. Build and Run

From the `startup-due-diligence/` folder:

```bash
# Build the image and start the container
docker compose up --build

# Or run in the background (detached)
docker compose up --build -d
```

The app will be available at **http://localhost:8003**

---

## 4. Common Commands

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild after code changes | `docker compose up --build` |
| View live logs | `docker compose logs -f` |
| Open a shell inside the container | `docker compose exec due-diligence sh` |
| Check container status | `docker compose ps` |

---

## 5. Persistent Memory

The `due_diligence_memory.json` file is stored in a Docker **named volume**
(`due_diligence_data`), so past reports survive container restarts and rebuilds.

To inspect or clear it:
```bash
# List volumes
docker volume ls

# Remove persisted data (clears all past reports)
docker volume rm startup-due-diligence_due_diligence_data
```

---

## 6. Running Without Docker (local dev)

If you prefer to run locally without Docker:

```bash
# From the repo root
pip install -r startup-due-diligence/requirements.txt

# Then start the server
uvicorn due_diligence.main:app --reload --port 8003
```

Open **http://localhost:8003** in your browser.

---

## 7. Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Frontend UI |
| `POST` | `/evaluate` | Run full due diligence → JSON report |
| `POST` | `/pitch-deck` | Generate pitch deck → JSON + base64 .pptx |
| `POST` | `/pitch-deck/download` | Generate pitch deck → direct .pptx file download |
| `GET` | `/memory` | List all persisted reports |
