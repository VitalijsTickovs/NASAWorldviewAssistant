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

## Setting up the project
  1. Install python 3.12
  2. Install poetry
  3. Use `poetry install`

## Running the project locally
  Run `poetry run uvicorn src.nasaworldviewassistant.main:app --host 0.0.0.0 --port 8000 --reload`
  You can run `curl -X POST "http://0.0.0.0:8000/api/agent"      -H "Content-Type: application/json"      -d '{"input": "Hello agent!", "thread_id": "thread-001"}'`
  or go to `http://localhost:8000/docs#/` and run the api command from there
  
