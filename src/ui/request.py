"""Turn the intake form's values into the workflow's inputs.

The workflow's intake agent parses natural language, so the form's structured
fields are rendered back into a sentence rather than passed as a record. Every
function here is pure, which is what makes the form's rules directly testable.
"""

from __future__ import annotations

REQUIRED_FIELD_LABELS = (
    ("crop", "crop"),
    ("product", "product"),
    ("field_id", "field ID"),
    ("question", "treatment request"),
)


def build_request(
    *,
    crop: str,
    product: str,
    state: str,
    field_id: str,
    acreage: float | None,
    application_rate: float | None,
    treatment_date: str,
    question: str,
) -> str:
    """Translate the structured UI fields into the workflow's intake message.

    Acreage and rate are optional: left empty they are omitted from the message
    entirely, which is what lets the workflow fall back to the field's recorded
    acreage and the label's default rate.
    """
    parts = [
        question.strip(),
        f"The field ID is {field_id.strip()}.",
        f"The crop is {crop.strip()}.",
        f"The proposed product is {product.strip()}.",
        f"The proposed treatment date is {treatment_date}.",
    ]
    if state.strip():
        parts.append(f"The field is located in {state.strip()}.")
    if acreage:
        parts.append(f"Treat {acreage:g} acres.")
    if application_rate:
        parts.append(
            f"The requested application rate is {application_rate:g} fl oz per acre."
        )
    return " ".join(parts)


def missing_fields(
    *,
    crop: str,
    product: str,
    field_id: str,
    question: str,
) -> dict[str, str]:
    """Field key -> message, for each required field left blank.

    Keyed by field so the form can place each message under the input it is
    about rather than collecting them into one warning at the bottom.
    """
    values = {
        "crop": crop,
        "product": product,
        "field_id": field_id,
        "question": question,
    }
    return {
        key: f"Enter the {label}."
        for key, label in REQUIRED_FIELD_LABELS
        if not values[key].strip()
    }
