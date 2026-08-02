import os
from dotenv import load_dotenv

load_dotenv()

MODEL_PROVIDER = os.getenv(
    "MODEL_PROVIDER",
    "ollama",
).lower()

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "gemma3",
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
)


GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash",
)

MODEL_MAX_TOKENS = int(
    os.getenv(
        "MODEL_MAX_TOKENS",
        "800"
    )
)

def validate_settings() -> None:
    """
    Fail early when required application settings are missing.
    """
    valid_providers = {
        "gemini",
        "ollama",
    }

    if MODEL_PROVIDER not in valid_providers:
        raise RuntimeError(
            "MODEL_PROVIDER must be 'gemini' or 'ollama'."
        )

    if (MODEL_PROVIDER == "gemini" and not os.getenv("GOOGLE_API_KEY")):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to the .env file."
        )
    