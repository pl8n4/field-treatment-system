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

The workflow-owned models are located in `src/workflow/schemas.py`. Farm,
product, weather, and retrieval models are located in
`src/data_layer/schemas.py`.

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

The current graph returns its raw state dictionary. Structured values inside
that dictionary, such as `request`, `plan`, and `review`, are Pydantic model
objects. `WorkflowResponse` exists as a possible normalized response model but
is not currently returned by `start()` or `resume_human_review()`.

Please let me know if Streamlit would benefit from a normalized response or
plain dictionaries. That boundary can be adapted without changing the graph's
internal state.

## RAG integration

### What the graph supplies

The retrieval step currently has access to:

```python
state["request"]
state["field_record"]
state["product_record"]
```

The most important retrieval filter is the proposed product. Results should come from that product's label rather than mixing evidence from all product labels.

### Current retrieval call

The graph calls:

```python
search(query, product=product.name, k=2)
```

It runs several focused queries covering the observed issue, application
rates, growth stage, wind and buffer restrictions, temperature inversions,
REI, and PHI. The product filter keeps evidence inside the selected product's
label.

The graph expects a `list[LabelChunk]`. Each chunk contains:

```python
class LabelChunk(BaseModel):
    text: str
    product: str
    epa_reg_no: str
    page: int
    source: str
```

Example:

```python
LabelChunk(
    text="Do not apply when wind exceeds 15 mph.",
    product="Delaro Complete",
    epa_reg_no="264-1207",
    page=7,
    source="000264-01207-20260611.pdf",
)
```

### Current assumptions

- Retrieval returns only evidence relevant to the proposed product.
- Every chunk includes a source.
- Every chunk includes a page number.
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

Context gathering can resolve:

```text
crop
acres
requested_rate
```

The precedence rules are:

```text
User acreage -> FarmField.acres fallback
User rate -> ProductLimits.default_rate_fl_oz_per_acre fallback
```

Context gathering writes these resolved values back into `TreatmentRequest`
before retrieval and specialist planning. Both values must be greater than
zero. User-supplied acreage may describe a partial-field treatment, but it may
not exceed the resolved field's acreage. An oversized request routes to
clarification before a plan is drafted.

If neither the user nor the product record supplies a rate, the workflow also
routes to clarification rather than allowing the Specialist to invent one.

### Expected context results

The graph currently expects four results:

```python
FarmField
ProductLimits
list[Application]
WeatherForecast
```

#### Field lookup

```python
FarmField(
    id=...,
    name=...,
    acres=...,
    crop=...,
    trait_package=...,
    growth_stage=...,
    expected_harvest_date=...,
    latitude=...,
    longitude=...,
    feet_to_sensitive_site=...,
)
```

#### Product lookup

```python
ProductLimits(
    name=...,
    epa_reg_no=...,
    supported_crops=...,
    allowed_traits=...,
    earliest_growth_stage=...,
    latest_growth_stage=...,
    default_rate_fl_oz_per_acre=...,
    max_rate_fl_oz_per_acre=...,
    max_seasonal_fl_oz_per_acre=...,
    max_applications_per_season=...,
    rei_hours=...,
    phi_days=...,
    wind_min_mph=...,
    wind_max_mph=...,
    downwind_buffer_ft=...,
)
```

For optional product limits, `None` means the label sets no such restriction.
It does not mean that retrieval failed.

#### Application history

```python
Application(
    id=...,
    field_id=...,
    product=...,
    applied_on=...,
    rate_fl_oz_per_acre=...,
)
```

The graph expects a list because a field may have multiple prior applications.

#### Weather lookup

```python
WeatherForecast(
    latitude=...,
    longitude=...,
    target_date=...,
    high_temp_f=...,
    wind_speed_mph=...,
    wind_direction_deg=...,
    precipitation_probability_pct=...,
)
```

### Tool behavior

Current assumptions:

- Lookup tools are read-only.
- They return Pydantic models rather than raw JSON.
- Dates are converted to Python `date` values before entering graph state.
- `find_field()` and `find_product()` return `None` for missing or ambiguous
  matches. The graph routes that result to clarification.
- Tools do not decide whether a treatment is approved.
- `get_forecast()` raises `WeatherUnavailable` when the live Open-Meteo
  forecast cannot be obtained or the date is outside its forecast horizon.

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

The graph currently owns the deterministic rule engine. It runs after the
Specialist drafts a plan and checks 16 conditions:

```text
field identity
product identity
requested treatment date
resolved requested or default rate
resolved requested or field acreage
maximum individual application rate
seasonal cumulative rate
maximum applications per season
crop compatibility
trait compatibility
growth-stage window
maximum wind speed
minimum wind speed
downwind buffer distance
PHI before harvest
REI recording
```

REI means restricted-entry interval: the time workers must wait before
re-entering a treated area. PHI means pre-harvest interval: the minimum time
between treatment and harvest. REI is recorded as informational; PHI is checked
against the expected harvest date.

The current product records do not contain a numeric maximum temperature. The
labels instead discuss temperature inversions, which the MVP weather model does
not represent as a deterministic rule.

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
