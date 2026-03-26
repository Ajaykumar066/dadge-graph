## Overview

**Order-to-Cash Graph Explorer** is an end-to-end demo project that:

- **Ingests** SAP Order-to-Cash (O2C) JSONL datasets into a **Neo4j property graph**
- Exposes a **FastAPI** backend for:
  - **Graph exploration** (overview, node expansion, search, stats)
  - **Analytics** (flow trace, broken flows, top products)
  - **Chat** (natural language → Cypher → data-backed answer, with node highlighting)
- Provides a **React** frontend that visualizes the graph with **React Flow** and runs layouts with **Dagre**

At a high level you can:

- Load the graph once via an ingestion pipeline
- Explore relationships interactively in the browser (click/double-click to expand)
- Ask O2C questions in chat; the response can highlight referenced nodes

---

## Demo features

### Graph exploration (UI + API)

- **Overview graph**: fetch a meaningful subset of the graph for the initial canvas
- **Node drilldown**: click a node to fetch its properties + immediate neighbors
- **Expand neighbors**: double-click a node to merge its neighborhood into the canvas
- **Search**: find nodes by key identifiers (sales order, billing doc, delivery doc, product description, etc.)
- **Stats**: counts by label and relationship type

Backend routes live in `backend/app/api/graph.py`.

### Analytics (fast Cypher endpoints)

Analytics endpoints avoid LLM latency and return in milliseconds:

- **Flow trace**: trace a billing document across SalesOrder → Delivery → Billing → JournalEntry → Payment
- **Broken flows**: detect missing deliveries/billing/payments, and cancelled billing documents
- **Top products**: rank by billing volume and revenue

Backend routes live in `backend/app/api/analytics.py`.

### Chat (Natural Language → Cypher → Answer)

Chat accepts a question and returns:

- A concise natural-language answer
- The generated Cypher (for debugging/visibility)
- Returned rows (capped)
- A list of **Neo4j element IDs** to highlight on the canvas
- Session history (in-memory)

Backend routes live in `backend/app/api/chat.py` and the pipeline is in `backend/app/llm/pipeline.py`.

---

## Architecture

### Backend

- **FastAPI** app: `backend/app/main.py`
- **Neo4j driver singleton**: `backend/app/core/database.py`
- **Settings**: `backend/app/core/config.py` (reads `.env`)
- **Graph ingestion**: `backend/app/graph/ingest.py` + entry script `backend/scripts/ingest_graph.py`
- **Dataset reader**: `backend/app/graph/reader.py` (reads partitioned `part-*.jsonl`)

### Frontend

- **React + Vite**: `frontend/`
- **React Flow** graph canvas: `frontend/src/components/GraphCanvas.jsx`
- **Node sidebar**: `frontend/src/components/NodeSidebar.jsx`
- **Auto-layout**: `frontend/src/utils/layout.js` (Dagre + grid fallback)
- **API client**: `frontend/src/api/client.js` (Axios) and `frontend/src/api/graph.js`
- **Styling**: TailwindCSS config in `frontend/tailwind.config.js`

---

## Tech stack (and why this stack)

### Neo4j (Graph database)

**Why Neo4j**:

- O2C is naturally a **relationship-heavy flow** (Order → Delivery → Billing → Payment)
- Graph queries like “trace end-to-end flow” are simpler and faster as a **path query** than joining many tables
- Cypher is expressive for missing-link detection (e.g. `WHERE NOT (x)-[:REL]->()`)

Used via the official **Neo4j Python Driver** in `backend/app/core/database.py`.

### FastAPI (Backend API)

**Why FastAPI**:

- Fast iteration, automatic OpenAPI docs, great developer UX
- Async-friendly request handling
- Pydantic-based validation for request/response models

### React + React Flow (Interactive graph UI)

**Why React Flow**:

- Purpose-built for interactive node-edge graphs
- Easy to support click/double-click interactions, minimap, zoom/pan, and custom node components

### Dagre (Graph layout)

**Why Dagre**:

- Directed graphs need a readable layout; Dagre produces stable hierarchical layouts
- The code includes a **grid fallback** for cases where edges are too sparse and Dagre stacks nodes

### LLM integration (Groq / Llama)

The chat pipeline in `backend/app/llm/pipeline.py` uses:

- **Groq** client with `LLM_MODEL = "llama-3.3-70b-versatile"` to:
  - Generate Cypher
  - Summarize results into a business-facing answer

**Why LLM here**:

- Enables non-technical users to query the graph without writing Cypher
- The pipeline uses a **schema prompt** + rule constraints to improve query reliability

---

## Repository structure

```text
order-to-cash-graph/
  README.md
  backend/
    app/
      api/
        analytics.py
        chat.py
        graph.py
      core/
        config.py
        database.py
      graph/
        ingest.py
        reader.py
      llm/
        pipeline.py
    scripts/
      ingest_graph.py
      inspect_data.py
    requirements.txt
    .env              # DO NOT commit real secrets
    data/
      raw/
        sap-order-to-cash-dataset/
          sap-o2c-data/
            <entity folders>/
              part-*.jsonl
  frontend/
    src/
      api/
        client.js
        graph.js
      components/
        GraphCanvas.jsx
        GraphNode.jsx
        NodeSidebar.jsx
      utils/
        graphConfig.js
        layout.js
    package.json
```

---

## Setup

### 1) Prerequisites

- **Python** (3.10+ recommended)
- **Node.js** (18+ recommended)
- A running **Neo4j** instance (Neo4j AuraDB or local Neo4j)

### 2) Neo4j credentials

Create `backend/.env` with:

```bash
NEO4J_URI=neo4j+s://<your-instance>.databases.neo4j.io
NEO4J_USERNAME=<username>
NEO4J_PASSWORD=<password>

# Optional (for chat)
GROQ_API_KEY=<your key>
GEMINI_API_KEY=<optional/unused unless you extend pipeline>
```

Notes:

- The backend reads `.env` via `pydantic-settings` (`backend/app/core/config.py`)
- Never commit real passwords or API keys

### 3) Dataset placement

The dataset reader expects JSONL files under:

`backend/data/raw/sap-order-to-cash-dataset/sap-o2c-data/`

Each entity should contain partitioned files like:

`part-00000-....jsonl`

You can sanity-check your dataset layout and fields with:

```bash
cd backend
python scripts/inspect_data.py
```

---

## Execution (recommended order)

### Step A — Create and populate the graph (ingestion)

Run:

```bash
cd backend
python scripts/ingest_graph.py
```

What it does (high level):

- Creates constraints / indexes
- Clears the database for a clean rerun
- Ingests nodes in phases (business partners, products, orders, deliveries, billing, journal, payments)
- Creates relationships
- Validates the final graph

This is implemented in `backend/app/graph/ingest.py` and orchestrated by `backend/scripts/ingest_graph.py`.

### Step B — Start the backend API

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

- Health: `GET http://127.0.0.1:8000/health`

### Step C — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend uses `VITE_API_URL` (optional) to point to the backend:

```bash
# frontend/.env
VITE_API_URL=http://127.0.0.1:8000
```

---

## API reference (high signal)

### Graph

- `GET /api/graph/overview?limit=80`
- `GET /api/graph/node/{node_id}`
- `GET /api/graph/search?q=<term>`
- `GET /api/graph/stats`

### Analytics

- `GET /api/analytics/flow-trace/{billing_document_id}`
- `GET /api/analytics/broken-flows?flow_type=all|no_delivery|no_billing|no_payment|cancelled`
- `GET /api/analytics/top-products?limit=10`

### Chat

- `POST /api/chat/` with JSON `{ "question": "...", "session_id": "..." }`
- `GET /api/chat/history/{session_id}`
- `DELETE /api/chat/history/{session_id}`

---

## Hard parts (what makes this project non-trivial)

### 1) Correct graph modeling and keys

SAP-like datasets often don’t have a single globally unique key for “line-item” style entities.
This project uses **composite IDs** (e.g., sales order + item number) to create stable graph keys.

If IDs are wrong, you get:

- Duplicate nodes
- Broken relationships
- “Trace flow” queries returning partial chains

### 2) Ingestion performance and reliability

Loading thousands of rows into Neo4j requires:

- Constraints/indexes first (for fast `MERGE`)
- Batching with `UNWIND` (transaction-friendly bulk inserts)
- Careful string normalization to avoid null/empty IDs

### 3) Relationship creation order

Nodes must exist before relationships are created.
The ingestion is staged into phases so that foreign keys can reliably link entities.

### 4) Frontend graph layout at scale

Graph UIs become unreadable quickly without layout and interaction patterns.
The UI uses:

- Overview sampling (don’t render everything)
- Expand-on-demand (double-click)
- Dagre layout + a grid fallback for sparse graphs

### 5) NL → Cypher correctness (LLM “sharp edge”)

Generating correct Cypher is hard because:

- Labels, properties, and relationship names must match exactly
- The model can hallucinate fields/labels if schema isn’t explicit

This project mitigates it with:

- A concise schema prompt (`GRAPH_SCHEMA`)
- Rules (no APOC, always limit, camelCase properties)
- Two-step prompting: generate query then summarize results

---

## Troubleshooting

### Backend can’t import `app` (Windows)

Run uvicorn **from the `backend/` folder**:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### Neo4j connection failures

- Confirm `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` are set
- If using AuraDB, make sure the instance is awake/ready
- The backend verifies connectivity on startup

### Frontend build/runtime issues

- Ensure backend is reachable at `VITE_API_URL` (or default `http://127.0.0.1:8000`)
- If you see a missing import for `ChatPanel`, check that `frontend/src/components/ChatPanel.jsx` exists.
  - Current code in `frontend/src/App.jsx` imports `ChatPanel`, but it is not present in `src/components/` in this workspace snapshot.

---

## Security notes

- Do **not** commit `.env` files with real credentials.
- The chat endpoint executes LLM-generated Cypher. For production you should add:
  - allowlisted query templates
  - read-only user/role in Neo4j
  - query timeouts and stricter validation

