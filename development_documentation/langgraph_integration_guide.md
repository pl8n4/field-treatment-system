# LangGraph Integration Guide

## Purpose

This document explains what the current LangGraph workflow expects from the Streamlit, RAG, and Tools portions of the project.

These interfaces are a working draft. Please ask questions, suggest improvements, or request changes if an assumption makes your portion unnecessarily difficult. The goal is to agree on simple contracts that let everyone work independently and integrate cleanly.

## Current workflow

```text
User request
-> Intake agent
-> Farm, product, and weather tools
-> Label retriever
-> Specialist agent
-> Deterministic rule engine
-> Critic agent
-> Human review
-> Simulated work order or rejection
```

LangGraph coordinates this sequence and maintains the shared state.

## Shared schemas

The workflow models are located in `src/workflow/schemas.py`. Farm, product,
weather, and retrieval models are located in `src/data_layer/schemas.py`.

These models are the proposed interfaces between our workstreams. They can be changed if a teammate identifies missing fields or a difficult assumption, but changes should be discussed so downstream code stays synchronized.

## Streamlit integration

### Starting and resuming a request

Start a request with:

```python
state = workflow.start(
    question=user_input,
    thread_id=thread_id,
)
```

Resume a human-review interruption with:

```python
state = workflow.resume_human_review(
    decision="approved",
    thread_id=thread_id,
)
```

Valid decisions are `"approved"` and `"rejected"`.

### Thread behavior

A `thread_id` identifies one treatment-review conversation.

Streamlit should:

- Create a thread ID when a new treatment request begins.
- Keep the same ID while gathering follow-up information.
- Keep the same ID while resuming human review.
- Create a new ID after the request reaches a terminal outcome.
- Store the active ID in `st.session_state`.

### Human-review interruption

When the graph pauses for approval, the returned state currently contains:

```python
state.get("__interrupt__")
```

The state also contains:

```python
state["plan"]
state["review"]
state["context_sources"]
```

The UI can display the proposed plan, review, citations, and approve/reject controls.

This interrupt format is open for discussion. If Streamlit would benefit from a normalized status such as `awaiting_human_review`, please request it.

### Current terminal statuses

| Status | Meaning |
|---|---|
| `needs_information` | User-required details are missing |
| `simulated_work_order_created` | A human approved and a mock work order was created |
| `rejected` | A human rejected the proposed plan |
| `escalated` | Automated review found a condition requiring manual compliance handling |
| `failed` | A model, tool, validation, or workflow operation failed safely |

### Useful state fields

```python
state.get("final_status")
state.get("final_message")
state.get("missing_information", [])
state.get("request")
state.get("plan")
state.get("rule_result")
state.get("review")
state.get("work_order")
state.get("context_sources", [])
state.get("audit_log", [])
```

The current graph returns Pydantic model objects for structured fields. Please let me know if Streamlit would benefit from receiving plain dictionaries instead.

## RAG integration

### What the graph supplies

The retrieval step currently has access to:

```python
state["request"]
state["field_record"]
state["product_record"]
```

The most important retrieval filter is the proposed product. Results should come from that product's label rather than mixing evidence from all product labels.

### Expected return type

The graph expects a `list[EvidenceChunk]`.

Each chunk currently contains:

```python
class EvidenceChunk(BaseModel):
    content: str
    source: str
    page: int | None = None
    product_name: str | None = None
    registration_number: str | None = None
```

Example:

```python
EvidenceChunk(
    content="Do not apply when wind exceeds 15 mph.",
    source="000264-01207-20260611.pdf",
    page=7,
    product_name="Example Product",
    registration_number="000264-01207",
)
```

### Current assumptions

- Retrieval returns only evidence relevant to the proposed product.
- Every chunk includes a source.
- Page numbers are included when available.
- Product name and registration number support filtering and citation.
- An empty evidence list causes the workflow to request more information instead of inventing requirements.

These assumptions are open to improvement. Please suggest additional metadata if it would make filtering or citation easier. Potential additions include `chunk_id`, `section_heading`, `document_date`, `label_topic`, and `relevance_score`. Before adding them, we should agree on which fields the graph actually needs.

## Tools integration

### Context-gathering input

The Tools portion receives a parsed `TreatmentRequest` with these fields:

```text
field_id
crop
observed_issue
proposed_product
proposed_date
acres
requested_rate
```

The user must currently supply:

```text
field_id
observed_issue
proposed_product
proposed_date
```

The tools may fill:

```text
crop
acres
requested_rate
```

### Expected context results

The graph currently expects four results:

```python
FieldRecord
ProductRecord
list[ApplicationRecord]
WeatherForecast
```

#### Field lookup

```python
FieldRecord(
    field_id=...,
    crop=...,
    acres=...,
    trait_package=...,
    growth_stage=...,
    expected_harvest_date=...,
    latitude=...,
    longitude=...,
    sensitive_site_distance_feet=...,
)
```

#### Product lookup

```python
ProductRecord(
    product_name=...,
    supported_crops=...,
    compatible_traits=...,
    allowed_growth_stages=...,
    minimum_rate=...,
    maximum_rate=...,
    seasonal_maximum_rate=...,
    maximum_wind_mph=...,
    maximum_temperature_f=...,
    required_buffer_feet=...,
    rei_hours=...,
    phi_days=...,
)
```

#### Application history

```python
ApplicationRecord(
    field_id=...,
    product_name=...,
    application_date=...,
    rate=...,
)
```

The graph expects a list because a field may have multiple prior applications.

#### Weather lookup

```python
WeatherForecast(
    forecast_date=...,
    high_temperature_f=...,
    wind_speed_mph=...,
    wind_direction=...,
    precipitation_probability=...,
    source=...,
    cached=...,
)
```

### Tool behavior

Current assumptions:

- Lookup tools are read-only.
- They return Pydantic models rather than raw JSON.
- Dates are converted to Python `date` values before entering graph state.
- Missing records raise or return a clearly identifiable error.
- Tools do not decide whether a treatment is approved.
- Weather results identify their source and whether they were cached.

If returning raw dictionaries is easier, let me know. I can adapt them at the LangGraph boundary instead of requiring every tool to construct Pydantic objects.

### Work-order integration

The work-order operation is the only side-effecting tool. It must only run after explicit human approval.

The current mock returns:

```python
WorkOrderResult(
    work_order_id=...,
    status="simulated",
    message=...,
)
```

For the MVP, the UI and result should clearly state that no real treatment was scheduled.

## Rule engine boundary

The graph currently contains a mock deterministic rule engine. It checks:

```text
crop compatibility
trait compatibility
growth stage
individual application rate
seasonal cumulative rate
wind speed
temperature
buffer distance
PHI before harvest
```

The graph owns when the engine runs and how results are routed. Whether the final rule implementation belongs with LangGraph or Tools can be decided as a group.

The required return contract is:

```python
RuleEngineResult(
    checks=[
        RuleCheck(
            rule_name=...,
            passed=...,
            severity=...,
            explanation=...,
        )
    ],
    all_passed=...,
)
```

## Collaboration and change requests

Please contact me when:

- A schema lacks a field your portion needs.
- A current field is difficult to produce reliably.
- You need a different input or output format.
- The graph's status names are inconvenient for the UI.
- You need additional metadata for citations or filtering.
- An error should be represented differently.
- You have an idea that simplifies integration or improves safety.
- You want help testing your component through the complete graph.

The current interfaces are intended to help us integrate, not prevent improvements. If we agree on a change, I will update the LangGraph state, routing, and agent inputs and communicate any downstream impact.
