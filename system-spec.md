# System Components

Field Treatment Review: what the system is made of, and what each piece is responsible for.

**Tentative idea for overall system specification**

---

## How they connect

```
Agronomist (free text)
        │
        ▼
   [9] Intake parser ──uses──▶ [8] Schemas
        │
        ▼
   [6] Read-only tools ──▶ [4] Farm DB   [5] Weather client
        │
        ▼
   [3] Retriever ──▶ [2] Vector store ──▶ [1] Label corpus
        │
        ▼
   [10] Specialist ──▶ draft plan
        │
        ▼
   [12] Critic ──runs──▶ [11] Rule engine
        │
        ├─ clean ──▶ human review ──▶ [7] Work order writer
        ├─ fixable ──▶ back to [10]  (capped)
        ├─ insufficient ──▶ ask user
        └─ violation ──▶ escalate

  All of the above orchestrated by [14] LangGraph over [13] Graph state,
  recorded in [15] Trace log, surfaced through [16] Streamlit.
```

---

## Data & knowledge

### 1. Label corpus
The five official label PDFs, stored and split into chunks Each chunk carries that metadata, attached at ingest time.

### 2. Vector store
Chroma, holding the embedded chunks. Built once from the corpus, either persisted to disk or rebuilt at startup.

### 3. Retriever
Semantic search over the store. The important part is the metadata filter: when checking a temperature restriction you search *one product's label*, not all five. Returns chunks with their source attached, since everything downstream has to cite.

### 4. Farm records
Three JSON files loaded at startup: fields.json (~10 fields — trait package, growth stage, expected harvest date, lat/lon, distance to nearest sensitive site), applications.json (spray history — what went on which field, when, at what rate), products.json (each label's limits as structured numbers, for the rule engine). Everything reads through a thin accessor layer returning Pydantic objects.

### 5. Weather client
Wraps Open-Meteo. Given a lat/lon and target date, returns forecast high, wind speed and direction, and precipitation probability. Label rules are written directly against forecast values, so its output becomes part of the compliance record.

---

### Starting points

**Labels — [EPA Pesticide Product and Label System (PPLS)](https://ordspub.epa.gov/ords/pesticides/f?p=PPLS:1)**
Search by product name, company, active ingredient, or EPA registration number. <cite index="11-1">EPA has converted its collection of over 170,000 current and historical labels to text-searchable PDFs</cite>

There's also a **[JSON API](https://epa.gov/pesticide-labels/pesticide-product-label-system-ppls-application-program-interface-api)** if you want to pull programmatically: <cite index="18-1">query by EPA registration number at `https://ordspub.epa.gov/ords/pesticides/ppls/[Company-Product]`, or by product name at `.../pplstxt/[Product_Name]`. Output is JSON, and the database refreshes every 12 hours.</cite> <cite index="11-1">Direct PDF links follow the pattern `www3.epa.gov/pesticides/chem_search/ppls/[Company]-[Product]-[Date].pdf`.</cite>

Manufacturer sites and agronomy label databases (CDMS, Agrian) carry the same labels in a friendlier layout — sometimes easier to read, but PPLS is the authoritative source and the one to cite.

**Weather — [Open-Meteo](https://open-meteo.com/en/docs)**
<cite index="23-1">Free, no API key, no signup, plain JSON over HTTP GET. Up to 16-day hourly and daily forecasts from coordinates.</cite> <cite index="28-1">Roughly 10,000 requests/day on the free tier, non-commercial.</cite>

---

## Tools layer

### 6. Read-only tools
Field lookup, product lookup, application history, weather. Thin typed wrappers over the farm DB and weather client. Some are called unconditionally by the graph rather than chosen by the model.

### 7. Side-effect tool
Writes a work order row. The only thing in the system that "does" anything, which is exactly why it sits behind human approval. The UI has to state plainly that it's simulated.

---

## Intelligence

### 8. Schemas
Pydantic models for the parsed request, the treatment plan, and the compliance review. These are the integration contract between all four workstreams, which is why they get frozen on day one.

### 9. Intake parser
LLM with structured output. Free text — *"Hartley North has waterhemp, let's get XtendiMax on it Thursday"* — becomes a typed object with field, product, date, pest, rate. Also flags what's missing, and distinguishes gaps the system can fill from gaps that require going back to the user.

### 10. Specialist
LLM. Takes the retrieved label chunks plus field, weather, and history context, and drafts a treatment plan: rate, timing, tank mix, nozzle, buffer, computed REI/PHI dates. Every element traces back to a chunk.

### 11. Rule engine
Plain Python, no LLM. Rate vs. label max, cumulative seasonal rate, trait compatibility, growth stage window, PHI vs. harvest date, wind range, temperature threshold, buffer distance.

### 12. Critic
Runs the rule engine, then uses the LLM to explain any failures in plain language with citations, and emits a verdict: **clean / fixable / insufficient info / hard violation**. The verdict is what the graph routes on.

---

## Orchestration

### 13. Graph state
The single object every node reads and writes: the request, gathered context, retrieved chunks, current draft, latest review, revision count, outcome, trace. Passing structured state between roles is how the "multi-agent" requirement is actually satisfied.

### 14. LangGraph state machine
Wires the nodes together, routes on the critic's verdict, sends fixable failures back to the specialist with a hard cap on retries, and pauses at human review via a checkpointer so the graph can resume after the manager clicks approve.

### 15. Trace log
Accumulates in state as the graph runs: nodes hit, each routing decision with its reason, chunks retrieved, retry count, every rule check with pass/fail.

---

## Interface

### 16. Streamlit app
Two screens plus a panel: **submit** (agronomist), **review queue** (compliance manager — plan, checks, citations, approve/reject), and the **trace panel**. graph state lives in the checkpointer, not in local variables.
