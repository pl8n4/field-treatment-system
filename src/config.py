import os
from dotenv import load_dotenv

load_dotenv()

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

    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Add it to the .env file."
        )
    