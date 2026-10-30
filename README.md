# AI Cloud Cost Detective

An AI-powered tool that investigates Azure cloud costs automatically. It scans resources in an Azure Resource Group, detects cost issues like over-provisioning and misconfigurations, and provides actionable suggestions with fixes.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite + TypeScript + Tailwind) |
| Backend | Python (FastAPI) |
| Auth | Custom JWT Auth (bcrypt + PyJWT) |
| Cloud Data | Azure CLI |
| Cloud | Azure |
| AI Analysis | OpenAI API |
| Database | Azure Managed PostgreSQL |
| Live Updates | FastAPI WebSocket |

## Architecture

```
                              ┌──────────────┐
                              │     USER     │
                              └──────┬───────┘
                                     │
                                     ▼
                           ┌───────────────────┐
                           │  REACT FRONTEND   │
                           └────────┬──────────┘
                                    :
                                    : Login / Signup
                                    ▼
                           ┌───────────────────┐
                           │  PYTHON BACKEND   │
                           │    (FastAPI)      │
                           │                   │
                           │  · Custom JWT Auth│
                           └───┬───────┬───┬───┘
                               :       :   :
                ┌──────────────┘       :   └──────────────┐
                :                      :                  :
                ▼                      ▼                  ▼
         ┌─────────────┐     ┌──────────────┐    ┌──────────────┐
         │  AZURE CLI  │     │   FASTAPI    │    │   OPENAI     │
         │             │     │  WEBSOCKET   │    │    API       │
         │ az resource │     │  (Progress)  │    │              │
         │ list --rg   │     └──────┬───────┘    │ Cost Analysis│
         └──────┬──────┘            :            └──────┬───────┘
                :                   : Live updates      :
                ▼                   ▼                   :
         ┌─────────────┐   ┌───────────────┐            :
         │   AZURE     │   │    REACT      │            :
         │ (Resource   │   │  (Progress    │            :
         │   Group)    │   │   Tracker)    │            :
         └─────────────┘   └───────────────┘            :
                                                        ▼
                                                 ┌──────────────┐
                                                 │    AZURE     │
                                                 │  POSTGRESQL  │
                                                 │  (Managed)   │
                                                 │              │
                                                 │ · users      │
                                                 │ · analyses   │
                                                 └──────┬───────┘
                                                        :
                                                        : Stored results
                                                        ▼
                                                 ┌───────────────┐
                                                 │    REACT      │
                                                 │ (Final Report │
                                                 │  + Suggestions│
                                                 │  + Fixes)     │
                                                 └───────────────┘
```

## Request Flow

```
①  User ─·─·─► React ─·─·─► FastAPI Auth ─·─·─► JWT (Azure PostgreSQL)

②  User selects Resource Group ─·─·─► Python Backend

③  Python ─·─·─► Azure CLI ─·─·─► Fetches all resources in RG

④  Python ─·─·─► FastAPI WebSocket ─·─·─► React (live progress)

⑤  Python ─·─·─► OpenAI API ─·─·─► Cost analysis

⑥  Python ─·─·─► Azure PostgreSQL ─·─·─► Stores analysis history

⑦  React ◄·─·─·─ Final report with suggestions & fixes
```

## What It Detects

- **Over-provisioned resources** — VMs, App Services, or databases sized larger than needed
- **Unused resources** — Orphaned disks, unattached public IPs, idle load balancers
- **Misconfigurations** — Wrong pricing tiers, missing auto-shutdown, no reserved instances
- **Storage & logging costs** — Excessive log retention, no lifecycle policies on blob storage

## Prerequisites

- Azure CLI installed and logged in (`az login`)
- An active Azure subscription with at least one resource group
- An Azure Managed PostgreSQL instance
- An OpenAI API key
- Python 3.10+
- Node.js 18+

## How to Run

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your credentials
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## How It Works

1. User signs up / logs in via custom JWT auth (credentials stored in Azure PostgreSQL)
2. Selects an Azure Resource Group to analyze
3. Python backend fetches all resources using Azure CLI
4. Live progress is streamed to the UI via FastAPI WebSocket
5. Resource data is sent to OpenAI API for cost analysis
6. Analysis results are stored in Azure PostgreSQL
7. Final report with cost breakdown, suggestions, and fix commands is displayed
