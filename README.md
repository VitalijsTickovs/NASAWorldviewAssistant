# AI Assistant for NASA's Worldview - Luma

**Luma** is an AI-powered Earth observation assistant built with **LangGraph**, **FastAPI**, and **NASA Worldview/GIBS APIs**.  
It lets users request imagery layers (e.g., MODIS, VIIRS, fires, true color) and automatically generates shareable NASA Worldview links or static satellite snapshots — all through a conversational agent interface.

---

## 🚀 Features

- 🤖 **LangGraph Agent** — interprets natural-language prompts (“show me wildfires in California yesterday”).
- 🛰️ **NASA Worldview Integration** — builds interactive map links or retrieves static imagery via Worldview Snapshots.
- 📡 **Layer Metadata Lookup** — fetches layer descriptions via NASA’s CMR Visualizations API or `wv.json`.
- 🌐 **FastAPI Backend** — clean JSON API + streaming (SSE / WebSocket).
- 🔌 **Frontend Ready** — CORS-enabled; connect via Fetch, SSE, or WebSocket.
- 🧠 **Modular Graph** — easily extend agent nodes for RAG, reasoning, or analysis.
- ☁️ **Deploy Anywhere** — runs locally via Uvicorn or in production on AWS (Lambda, ECS, App Runner, or EC2).

---

## 🧩 Architecture Overview

```mermaid
flowchart LR
  U[User / Frontend] -->|JSON / SSE / WS| A[FastAPI API]
  A -->|invoke| G[LangGraph Agent]
  G -->|build request| N[NASA APIs]
  N -->|Worldview Snapshots / GIBS / CMR / EONET| G
  A -->|return| U
  subgraph "Optional Infra"
    R[(Redis / Cache)]
    L[(Logging / CloudWatch)]
  end
  G <-->|checkpoint| R
  A --> L
