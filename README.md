# SAP Order-to-Cash Graph Explorer

> A context graph system with an LLM-powered natural language query interface, built on SAP Order-to-Cash data.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Live Demo](#live-demo)
3. [Tech Stack & Reasoning](#tech-stack--reasoning)
4. [Architecture Decisions](#architecture-decisions)
5. [Graph Schema](#graph-schema)
6. [LLM Prompting Strategy](#llm-prompting-strategy)
7. [Guardrails](#guardrails)
8. [Project Structure](#project-structure)
9. [Setup & Installation](#setup--installation)
10. [API Endpoints](#api-endpoints)
11. [Daily Work Report](#daily-work-report)
12. [AI Coding Sessions](#ai-coding-sessions)

---

## Project Overview

Real-world SAP business data is fragmented across multiple tables — sales orders, deliveries, billing documents, payments, and journal entries — with no clear way to trace how they connect end-to-end.

This project unifies 19 SAP Order-to-Cash (O2C) entity types from a raw JSONL dataset into a **property graph** in Neo4j, then exposes that graph through:

- An **interactive visualization** where users can explore nodes and relationships
- A **conversational LLM interface** where users ask questions in plain English and receive data-backed answers
- **Pre-built analytical endpoints** for the most valuable O2C queries (flow trace, broken flow detection, top products)

The system is not a static Q&A bot. Every answer is grounded in live graph data — the LLM generates Cypher queries dynamically, executes them against Neo4j, and summarizes the results.

---

## Live Demo

| Service  | URL |
|----------|-----|
| Frontend | https://your-app.vercel.app |
| Backend API | https://your-api.onrender.com |
| API Docs | https://your-api.onrender.com/docs |

---

## Tech Stack & Reasoning

### Database — Neo4j AuraDB (Free Tier)

**Why Neo4j over PostgreSQL or MongoDB?**

The O2C flow is fundamentally a graph problem. A single transaction touches 6+ entity types:

```
Customer → SalesOrder → Delivery → BillingDocument → JournalEntry → Payment
```

In a relational database, answering "trace the full flow of billing document 90504248" requires 5 JOINs across 5 tables. In Neo4j, it is a single path query:

```cypher
MATCH path = (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
             -[:BILLED_AS]->(bd:BillingDocument {billingDocument: '90504248'})
             -[:RECORDED_IN]->(je:JournalEntry)-[:CLEARED_BY]->(pay:Payment)
RETURN path
```

Neo4j also makes "broken flow" detection trivial — finding delivered orders that were never billed is one line:

```cypher
MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
WHERE NOT (od)-[:BILLED_AS]->()
RETURN so.salesOrder, od.deliveryDocument
```

**AuraDB specifically** was chosen because it provides a managed, cloud-hosted Neo4j instance with a free 512MB tier — zero infrastructure setup, accessible from any deployed backend.

---

### Backend — FastAPI (Python)

**Why FastAPI over Flask or Django?**

- **Async-native**: Neo4j queries and LLM API calls benefit from async I/O
- **Auto-generated docs**: Swagger UI at `/docs` with zero configuration
- **Pydantic validation**: Request/response models are validated automatically
- **Speed**: FastAPI is one of the fastest Python web frameworks, matching Node.js performance in benchmarks

---

### LLM — Groq + Llama 3.3 70B

**Why Groq over OpenAI or Gemini?**

| Provider | Free Tier | Speed | Cypher Quality |
|----------|-----------|-------|----------------|
| OpenAI GPT-4o | No | Medium | Excellent |
| Google Gemini Flash | Yes (quota limited) | Fast | Good |
| **Groq Llama 3.3 70B** | **Yes (generous)** | **Very Fast** | **Excellent** |

Groq's inference hardware (LPU chips) delivers sub-second response times even for 70B parameter models. The free tier provides 14,400 requests/day — sufficient for a demo without spending money.

Llama 3.3 70B was chosen specifically for its strong code generation capability — it produces valid Cypher on the first attempt for most O2C queries.

---

### Frontend — React + Vite

**Why Vite over Create React App?**

Vite uses native ES modules for development, resulting in near-instant hot module replacement (HMR). A change to a component reflects in the browser in under 100ms.

**Why React Flow for graph visualization?**

React Flow is purpose-built for node-edge graph UIs in React. It provides:
- Drag, zoom, pan out of the box
- Custom node rendering (our color-coded dots)
- `useNodesState` / `useEdgesState` hooks for React-idiomatic state management
- MiniMap component for overview navigation

---

### Styling — Tailwind CSS

Utility-first CSS eliminates the need for separate stylesheet files. All styling is co-located with the component, making it easy to read and maintain. The dark theme is enforced consistently via Tailwind's gray-900/950 palette.

---

## Architecture Decisions

### Graph as a Logical Layer over Data

The graph is not just a visualization — it IS the query engine. Every answer the LLM gives is backed by a Cypher query executed against Neo4j. This means:

1. Answers are always grounded in real data
2. The LLM cannot hallucinate facts (it can only hallucinate Cypher, which fails loudly)
3. New data loaded into Neo4j is immediately queryable without retraining

### Two-Stage LLM Pipeline

The pipeline makes two separate LLM calls per question:

```
Stage 1 — generate_cypher():
  Input:  natural language question + schema
  Output: Cypher query only (temperature=0.0 for determinism)

Stage 2 — generate_answer():
  Input:  original question + Cypher + raw result rows
  Output: natural language summary (temperature=0.3)
```

Separating these concerns produces better results than a single combined prompt. The Cypher generator focuses purely on syntax correctness. The answer generator focuses purely on clear communication.

### Idempotent Ingestion

The ingestion pipeline uses `MERGE` instead of `CREATE` throughout. This means running `ingest_graph.py` multiple times produces the same result — no duplicate nodes or relationships. Safe to re-run after schema changes.

### Node Highlighting via Element IDs

When the LLM returns an answer, the pipeline attempts to resolve referenced document IDs back to Neo4j element IDs. These are passed to the frontend, which highlights the corresponding dots on the canvas — creating a visual connection between the conversation and the graph.

---

## Graph Schema

### Nodes (13 types)

| Label | Primary Key | Description |
|-------|-------------|-------------|
| BusinessPartner | businessPartner | Customer master data |
| SalesOrder | salesOrder | Order header |
| SalesOrderItem | itemId (composite) | Order line items |
| SalesOrderScheduleLine | scheduleId (composite) | Delivery date commitments |
| OutboundDelivery | deliveryDocument | Shipment header |
| OutboundDeliveryItem | deliveryItemId (composite) | Shipment line items |
| BillingDocument | billingDocument | Invoice header |
| BillingDocumentItem | billingItemId (composite) | Invoice line items |
| JournalEntry | journalEntryId (composite) | Accounting entry |
| Payment | paymentId (composite) | AR clearing document |
| Product | product | Material master |
| Plant | plant | Warehouse/factory |
| Address | addressId | Physical address |

### Relationships (14 types)

```
(BusinessPartner) -[:PLACED]->          (SalesOrder)
(SalesOrder)      -[:HAS_ITEM]->         (SalesOrderItem)
(SalesOrder)      -[:HAS_SCHEDULE_LINE]-> (SalesOrderScheduleLine)
(SalesOrder)      -[:FULFILLED_BY]->     (OutboundDelivery)
(SalesOrderItem)  -[:FOR_PRODUCT]->      (Product)
(OutboundDelivery)-[:HAS_ITEM]->         (OutboundDeliveryItem)
(OutboundDeliveryItem)-[:SHIPPED_FROM]-> (Plant)
(OutboundDelivery)-[:BILLED_AS]->        (BillingDocument)
(BillingDocument) -[:HAS_ITEM]->         (BillingDocumentItem)
(BillingDocumentItem)-[:FOR_PRODUCT]->   (Product)
(BillingDocument) -[:BILLED_TO]->        (BusinessPartner)
(BillingDocument) -[:RECORDED_IN]->      (JournalEntry)
(JournalEntry)    -[:CLEARED_BY]->       (Payment)
(Product)         -[:AVAILABLE_AT]->     (Plant)
```

### Graph Statistics

| Metric | Value |
|--------|-------|
| Total Nodes | 1,397 |
| Total Relationships | 5,024 |
| Complete O2C Flows | 76 |
| Broken Flows (no delivery) | 14 |
| Broken Flows (no billing) | 3 |
| Cancelled Billing Docs | 80 |

---

## LLM Prompting Strategy

### System Prompt Design

The Cypher generation prompt includes:

1. **Full schema** — exact node labels, property names, and relationship types. Without this, the LLM guesses field names and generates invalid Cypher.

2. **Strict output rules** — "Return ONLY valid Cypher. No explanation, no markdown." This prevents the LLM from wrapping the query in prose.

3. **Few-shot examples** — three representative Q&A pairs covering the three most common query patterns (aggregation, path traversal, negative pattern matching).

4. **Temperature = 0.0** — Cypher must be deterministic. Creative variation in SQL/Cypher is a bug, not a feature.

### Answer Generation Prompt

The summarization prompt:

1. Receives the original question, the Cypher used, and the raw result rows
2. Is instructed to avoid mentioning Cypher, Neo4j, or technical details
3. Is constrained to 150 words — forces concise, business-focused answers
4. Uses temperature = 0.3 — slight variation for natural language variety

### Error Recovery

If the generated Cypher fails execution, the error is caught and returned to the user with a suggestion to rephrase — rather than crashing or returning a generic error. The failed Cypher is also returned for transparency.

---

## Guardrails

The system uses a two-layer guardrail to prevent off-topic usage:

### Layer 1 — Off-Topic Pattern Detection (fast, no LLM call)

Immediate rejection if the question contains patterns like:
- "poem", "song", "story", "joke"
- "write me", "tell me a"
- "capital of", "weather", "recipe"

### Layer 2 — Domain Keyword Requirement

After passing Layer 1, the question must contain at least one domain keyword:
- Entity names: "sales order", "delivery", "billing", "payment", "product", "customer", "plant"
- Actions: "shipped", "billed", "fulfilled", "cleared", "cancelled"
- SAP terms: "o2c", "sap", "journal", "document", "account"

Questions that fail both layers receive a standard refusal:

> "This system is designed to answer questions about the SAP Order-to-Cash dataset only — including sales orders, deliveries, billing documents, payments, products, and customers."

---

## Project Structure

```
order-to-cash-graph/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app, CORS, lifespan hooks
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Pydantic settings from .env
│   │   │   └── database.py             # Neo4j singleton driver
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── graph.py                # GET /api/graph/* endpoints
│   │   │   ├── chat.py                 # POST /api/chat/ + memory
│   │   │   └── analytics.py            # Flow trace + broken flows
│   │   │
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── reader.py               # JSONL file reader utility
│   │   │   └── ingest.py               # Neo4j ingestion functions
│   │   │
│   │   └── llm/
│   │       ├── __init__.py
│   │       └── pipeline.py             # Guardrail → Cypher → Execute → Answer
│   │
│   ├── data/
│   │   └── raw/
│   │       └── sap-order-to-cash-dataset/
│   │           └── sap-o2c-data/
│   │               ├── sales_order_headers/        # part-*.jsonl
│   │               ├── sales_order_items/
│   │               ├── sales_order_schedule_lines/
│   │               ├── outbound_delivery_headers/
│   │               ├── outbound_delivery_items/
│   │               ├── billing_document_headers/
│   │               ├── billing_document_items/
│   │               ├── billing_document_cancellations/
│   │               ├── journal_entry_items_accounts_receivable/
│   │               ├── payments_accounts_receivable/
│   │               ├── business_partners/
│   │               ├── business_partner_addresses/
│   │               ├── customer_company_assignments/
│   │               ├── customer_sales_area_assignments/
│   │               ├── products/
│   │               ├── product_descriptions/
│   │               ├── product_plants/
│   │               ├── product_storage_locations/
│   │               └── plants/
│   │
│   ├── scripts/
│   │   ├── inspect_data.py             # Dataset field inspection tool
│   │   └── ingest_graph.py             # Full ingestion pipeline runner
│   │
│   ├── .env                            # Secrets (never committed)
│   ├── .env.example                    # Safe template
│   ├── render.yaml                     # Render deployment config
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # Root component + layout
│   │   │
│   │   ├── api/
│   │   │   ├── client.js               # Axios instance + interceptors
│   │   │   └── graph.js                # API function wrappers
│   │   │
│   │   ├── components/
│   │   │   ├── GraphCanvas.jsx         # React Flow canvas + interactions
│   │   │   ├── GraphNode.jsx           # Custom dot node component
│   │   │   ├── NodeSidebar.jsx         # Node detail + neighbour panel
│   │   │   ├── ChatPanel.jsx           # LLM chat interface
│   │   │   └── StatsBar.jsx            # Graph statistics header
│   │   │
│   │   ├── utils/
│   │   │   ├── graphConfig.js          # Node colors + schema mapping
│   │   │   └── layout.js               # Force-directed layout engine
│   │   │
│   │   ├── index.css                   # Tailwind + global styles
│   │   └── main.jsx                    # React entry point
│   │
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── package.json
│
├── .gitignore
└── README.md
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Neo4j AuraDB account (free at console.neo4j.io)
- Groq API key (free at console.groq.com)

### Backend Setup

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env`:

```env
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
```

### Load Data into Neo4j

```bash
# Inspect your dataset first
python scripts/inspect_data.py

# Run full ingestion pipeline
python scripts/ingest_graph.py
```

### Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

App available at: `http://localhost:5173`

---

## API Endpoints

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check |

### Graph
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/graph/stats` | Node and relationship counts |
| GET | `/api/graph/overview` | Sample nodes + edges for visualization |
| GET | `/api/graph/node/{id}` | Single node + all neighbours |
| GET | `/api/graph/search?q=` | Search nodes by name/ID |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat/` | Send NL question, get data-backed answer |
| GET | `/api/chat/history/{session_id}` | Get conversation history |
| DELETE | `/api/chat/history/{session_id}` | Clear conversation |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/flow-trace/{billing_doc_id}` | Full O2C chain for a document |
| GET | `/api/analytics/broken-flows?flow_type=all` | Incomplete flow detection |
| GET | `/api/analytics/top-products?limit=10` | Products by billing volume |

---

## Daily Work Report

### Day 1 — Data, Graph, and Backend

**Morning: Dataset Inspection & Graph Design**
- Downloaded SAP O2C dataset (19 entity types, partitioned JSONL files)
- Built `inspect_data.py` to scan all 19 folders and surface field names, record counts, and FK relationships
- Discovered key FK bridges:
  - `outbound_delivery_items.referenceSdDocument` → `SalesOrder`
  - `billing_document_items.referenceSdDocument` → `OutboundDelivery`
- Designed complete graph schema: 13 node types, 14 relationship types
- Created Neo4j AuraDB free instance

**Afternoon: Data Ingestion Pipeline**
- Built `reader.py` — JSONL reader with generator pattern for memory efficiency
- Built `ingest.py` — batched UNWIND ingestion using MERGE for idempotency
- Ingested all 13 node types in dependency order (root nodes first, then relationships)
- Created uniqueness constraints before ingestion for O(log n) MERGE performance
- Validated graph: 1,397 nodes, 5,024 relationships, 76 complete O2C chains

**Evening: FastAPI Backend**
- Set up FastAPI app with lifespan hooks and CORS middleware
- Built Neo4j singleton driver with connection pooling
- Built Pydantic settings with `.env` loading
- Implemented 4 graph query endpoints (`/stats`, `/overview`, `/node/{id}`, `/search`)
- Implemented 3 analytics endpoints (flow trace, broken flows, top products)

---

### Day 2 — LLM Pipeline, Frontend, and Deployment

**Morning: LLM Pipeline**
- Integrated Groq API with Llama 3.3 70B
- Designed two-stage pipeline (Cypher generation + answer summarization)
- Engineered Cypher generation prompt with full schema + 3 few-shot examples
- Implemented two-layer guardrail (off-topic patterns + domain keyword check)
- Implemented conversation memory using session-keyed deques
- Built `/api/chat/` endpoint with history tracking
- Tested all example queries from the assignment specification

**Midday: React Frontend**
- Scaffolded Vite + React project with Tailwind CSS
- Built `graphConfig.js` — centralized node color and schema mapping
- Built force-directed layout engine (pure JS, no external dependency)
- Built `GraphNode.jsx` — colored dot nodes with hover tooltips
- Built `GraphCanvas.jsx` — React Flow canvas with click/double-click interactions
- Built `NodeSidebar.jsx` — node property inspector with neighbour expansion
- Built `ChatPanel.jsx` — chat interface with session memory and Cypher viewer
- Built `StatsBar.jsx` — live graph statistics header

**Afternoon: Integration & Polish**
- Connected chat answers to graph highlighting via node ID lookup
- Added Product nodes to overview query for chat highlighting to work
- Tested all 3 example queries from the assignment
- Verified guardrails reject: poems, general knowledge, creative writing
- Verified guardrails accept: all O2C domain questions

**Evening: Deployment**
- Added `render.yaml` for Render backend deployment
- Pushed to public GitHub repository
- Deployed backend on Render (free tier)
- Deployed frontend on Vercel (free tier)
- Verified end-to-end flow on production URLs

---

## AI Coding Sessions

This project was built entirely using Claude (Anthropic) as the AI coding assistant via claude.ai.

### How AI Was Used

**Prompt Strategy:**
- Each step was broken into a single, focused request: "write only this function, stop, wait for confirmation"
- Schema design was validated by providing the actual inspect output and asking Claude to derive relationships from real field names — not assumed ones
- Every code snippet was tested before the next was written
- Errors were shared verbatim with Claude for diagnosis

**Workflow Pattern:**
1. Run → get output/error
2. Paste exact output to Claude
3. Claude diagnoses and provides targeted fix
4. Repeat

**AI Session Logs:**
Full conversation transcripts are available in the GitHub repository under `/ai-session-logs/`.

---

## Example Queries

The system can answer questions such as:

| Question | What it demonstrates |
|----------|---------------------|
| Which products have the most billing documents? | Aggregation across graph relationships |
| Trace the full flow of billing document 90504248 | Multi-hop path traversal |
| Find sales orders delivered but never billed | Negative pattern matching (broken flows) |
| Which customers have the highest total order value? | Aggregation with relationship traversal |
| Show me all cancelled billing documents | Property-based filtering |
| How many orders were fulfilled last month? | Date-range filtering |

---

## License

MIT License — see LICENSE file for details.