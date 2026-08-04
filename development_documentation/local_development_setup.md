# Local Development Setup

## Prerequisites

- Python 3.10+
- Git
- One model provider:
  - [Ollama](https://ollama.com/download), or
  - Gemini with a Google API key

Run commands from the `field-treatment-system` directory.

## Environment setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it for the current shell:

| Platform or shell | Command |
|---|---|
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| macOS or Linux | `source .venv/bin/activate` |

Install runtime dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create the local environment file:

```bash
cp .sample.env .env
```

PowerShell equivalent:

```powershell
Copy-Item .sample.env .env
```

`.env` is ignored by Git and must not be committed.

## Model provider configuration

### Ollama

Install Ollama, start its service, and pull the configured model:

```bash
ollama pull gemma3
ollama list
```

Configure `.env`:

```dotenv
MODEL_PROVIDER=ollama
OLLAMA_MODEL=gemma3
OLLAMA_BASE_URL=http://localhost:11434
MODEL_MAX_TOKENS=800
```

Use the full model tag from `ollama list` when applicable, for example `gemma3:4b`.

On Windows, terminals opened before Ollama was installed may not see the updated `PATH`. Restart the terminal or editor. The application only requires the Ollama service to be reachable at the configured base URL.

### Gemini

Configure `.env`:

```dotenv
MODEL_PROVIDER=gemini
GOOGLE_API_KEY=<api-key>
GEMINI_MODEL=gemini-3.5-flash
MODEL_MAX_TOKENS=800
```

Gemini usage is subject to the quota associated with the configured API key.

## Run the CLI

```bash
python src/main.py
```

Example request:

```text
Field F001 has a fungal disease. Use Example Product today.
```

The current implementation uses mock context, retrieval, rule-engine, and work-order integration points. An approved request creates only a simulated work order.

## Development dependencies

Install the development toolchain:

```bash
python -m pip install -r dev-requirements.txt
```

Run the current checks:

```bash
black --check src tests
ruff check src tests
mypy src
pytest
```

Apply formatting and safe lint fixes:

```bash
black src tests
ruff check --fix src tests
```

The automated suite includes unit and provider-independent workflow integration
tests. See `manual_workflow_testing.md` for live CLI scenarios using the seeded
records, configured model, label retrieval, and weather service.

## Optional pre-commit hook

The pre-commit hook is opt-in per local clone.

Enable it:

```bash
pre-commit install
```

Run hooks without installing the Git hook:

```bash
pre-commit run --all-files
```

Remove the local hook:

```bash
pre-commit uninstall
```

Committing `.pre-commit-config.yaml` does not activate hooks for other developers.

## Troubleshooting

### Ollama is unreachable

Confirm the service, model name, and endpoint:

```bash
ollama list
```

```dotenv
MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=<installed-model-name>
```

### Gemini returns `RESOURCE_EXHAUSTED`

The configured quota or rate limit has been reached. Wait for it to reset or switch `MODEL_PROVIDER` to `ollama`.

### Imports fail

Verify that the active interpreter belongs to `.venv` and reinstall runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

### PowerShell blocks activation

Use another shell or temporarily allow scripts for the current process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Related documentation

- `development_documentation/langgraph_documentation.md`
- `development_documentation/langgraph_integration_guide.md`
- `development_documentation/manual_workflow_testing.md`
- `development_documentation/system-spec.md`
- `development_documentation/project-requirements.md`
