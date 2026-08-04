# Field Treatment Review

An AI-assisted agricultural field-treatment review system. The application
combines farm records, product restrictions, label evidence, weather data, and
deterministic compliance rules to draft a treatment plan for human review.

The MVP covers soybeans in Missouri using synthetic field and application data
and a limited product catalog. It does not schedule real agricultural work. An
approved request creates only a simulated work-order record.

## Workflow

1. The intake agent converts a natural-language request into structured data.
2. Missing user information is requested, while eligible values such as field
   acreage and the default product rate can be loaded from system records.
3. The data layer gathers field, product, application-history, and weather
   context.
4. The retriever supplies relevant product-label evidence.
5. The specialist agent drafts a treatment plan.
6. The deterministic rule engine evaluates label and field constraints.
7. The critic agent reviews the plan and supporting evidence.
8. LangGraph pauses for explicit human approval or rejection.
9. Approval creates a simulated work order in a local SQLite database.

REI means restricted-entry interval: the required time before people may
re-enter a treated area. PHI means pre-harvest interval: the minimum time
between treatment and harvest.

## Architecture

```text
app.py                    Streamlit entry point
src/main.py               Command-line entry point
src/workflow/             LangGraph workflow, agents, state, and schemas
src/data_layer/           Records, weather, retrieval, and work-order storage
data/                     Synthetic records and product-label source data
tests/                    Unit and provider-independent integration tests
development_documentation/  Design, integration, setup, and testing guides
```

Ollama and Gemini are supported as chat-model providers. Hugging Face sentence
transformers and Chroma provide local label-evidence retrieval. SQLite stores
simulated work orders locally; `work_orders.db` is generated at runtime and is
not tracked by Git.

## Local setup

Python 3.10 or newer is required.

```bash
python -m venv .venv
```

Activate the environment using the command for your shell, then install the
runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `.sample.env` to `.env` and select a model provider.

For Ollama:

```dotenv
MODEL_PROVIDER=ollama
OLLAMA_MODEL=gemma3
OLLAMA_BASE_URL=http://localhost:11434
MODEL_MAX_TOKENS=800
```

Ensure the configured model is installed and the Ollama service is running:

```bash
ollama pull gemma3
ollama serve
```

For Gemini:

```dotenv
MODEL_PROVIDER=gemini
GOOGLE_API_KEY=<api-key>
GEMINI_MODEL=gemini-3.5-flash
MODEL_MAX_TOKENS=800
```

## Running the application

Start the Streamlit interface from the repository root:

```bash
streamlit run app.py
```

If Streamlit's file watcher probes optional Transformers image modules and
reports a missing `torchvision` package, disable the watcher for local use:

```bash
streamlit run app.py --server.fileWatcherType none
```

The command-line interface remains available for workflow testing:

```bash
python src/main.py
```

Example request:

```text
Treat field F-02 with Enlist One on August 6, 2026.
```

## Development

Install the optional development toolchain:

```bash
python -m pip install -r dev-requirements.txt
```

Run the automated checks:

```bash
black --check src tests app.py
ruff check src tests app.py
mypy src app.py
pytest
```

The pre-commit hooks are opt-in:

```bash
pre-commit install
```

## Safety boundary

The system is a training-project MVP. Its records, recommendations, approvals,
and work orders are simulated and must not be used to authorize real pesticide
applications. Product labels and qualified human review remain authoritative.
