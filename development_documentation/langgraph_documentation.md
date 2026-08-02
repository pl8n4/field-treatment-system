# LangGraph Implementation Documentation

## Purpose and audience

This document explains how LangGraph is currently implemented in the Field Treatment Review project. The implementation is a working MVP (minimum viable product). Several nodes currently use mock data so the complete workflow can run while the Streamlit, RAG, and Tools portions are developed.

## Important terms and abbreviations

### Agricultural and compliance terms

- **REI (Restricted-Entry Interval)**: The amount of time that must pass after a pesticide application before workers may re-enter a treated area without the protective measures required for early entry. In this project, it is stored as `rei_hours`.
- **PHI (Pre-Harvest Interval)**: The minimum number of days that must pass between a pesticide application and harvest. In this project, it is stored as `phi_days`.
- **Buffer**: A required untreated distance between an application area and a sensitive location, such as neighboring property, water, or another protected site.
- **Trait package**: A set of crop characteristics, often including genetically engineered herbicide or pest resistance. Product compatibility can depend on the field's trait package.
- **Growth stage**: A code describing the crop's current development. For soybeans, `R2` means full bloom. Product labels may restrict applications to particular growth stages.
- **Seasonal maximum rate**: The maximum total amount of a product that may be applied during one growing season. Previous applications must be included in this calculation.
- **EPA registration number**: An identifier assigned by the United States Environmental Protection Agency to a registered pesticide product. It helps connect a product record to the correct label.

## Relevant files

```text
field-treatment-system/
|-- src/
|   |-- config.py       Model-provider configuration
|   |-- graph.py        LangGraph state, nodes, routes, and workflow API
|   |-- main.py         Command-line demonstration interface
|   `-- schemas.py      Pydantic integration models
|-- system-spec.md      Proposed overall architecture
`-- langgraph_integration_guide.md
                        Contracts shared with other workstreams
```

Most of the LangGraph implementation is currently contained in `src/graph.py`.

## LangGraph concepts used in this project

### State

LangGraph state is the shared data object passed from one node to the next. A node reads values from state and returns a dictionary containing state updates.

The project defines state with a `TypedDict`:

```python
class AgriculturalState(TypedDict, total=False):
    ...
```

`TypedDict` documents the expected keys and their Python types. `total=False` means a state instance does not need to contain every key at every point in the workflow. For example, `work_order` will not exist before human approval.

### Nodes

A node is a Python function registered as one step in the graph. Each node receives the current state and returns updates.

Example shape:

```python
def example_node(state: AgriculturalState) -> dict:
    return {
        "some_state_field": new_value,
        "audit_log": ["Example node completed."],
    }
```

### Edges and conditional edges

An edge connects one node to the next. A normal edge always follows the same path. A conditional edge calls a routing function, which returns a route name based on state.

For example, intake can route to clarification, context gathering, or controlled failure.

### Checkpointing

A checkpointer saves graph state under a `thread_id`. This is required for the human-review pause because the application must restore the same state when the reviewer responds.

The current implementation uses `InMemorySaver`. Its checkpoints exist only while the Python process is running. Restarting the application clears them. A persistent checkpointer would be needed for a production system.

### Interrupt and resume

The `interrupt()` function pauses graph execution and returns control to the interface. The graph later resumes when it receives a `Command(resume=...)` using the same `thread_id`.

This is how the project implements human approval without automatically performing the simulated side effect.

## Shared graph state

`AgriculturalState` groups state fields by purpose.

### Request and intake state

```python
question: str
request: TreatmentRequest
intake: IntakeDecision
```

- `question` is the latest user message.
- `request` is the normalized treatment request extracted from the conversation.
- `intake` contains the LLM's structured intake response.

### Operational context

```python
field_record: FieldRecord
product_record: ProductRecord
application_history: list[ApplicationRecord]
weather: WeatherForecast
```

These fields hold farm, product, prior-application, and weather data. They are currently produced by mock logic in `_gather_context_node`.

### Retrieved knowledge

```python
evidence: list[EvidenceChunk]
context_sources: list[str]
```

`evidence` contains relevant label passages. `context_sources` contains unique source names for display and human review. The current `_retrieve_node` returns mock evidence until the RAG implementation is connected.

### Plan and review state

```python
plan: TreatmentPlan
rule_result: RuleEngineResult
review: CriticDecision
```

- `plan` is generated by the Specialist agent.
- `rule_result` comes from deterministic Python checks.
- `review` is the validated Critic decision.

### Revision state

```python
revision_count: int
max_revisions: int
```

These values prevent an unlimited Specialist-Critic loop. `MAX_REVISIONS` is currently initialized to `1`, so the Specialist gets a limited opportunity to correct a fixable plan.

### Human-review and result state

```python
human_decision: Literal["approved", "rejected"]
work_order: WorkOrderResult
final_status: str
final_message: str
error: str | None
missing_information: list[str]
```

`Literal` restricts a value to the listed strings. The work order is only created after `human_decision` is `"approved"`.

### Append-only state

```python
audit_log: Annotated[list[str], add]
messages: Annotated[list[AnyMessage], add_messages]
```

`Annotated` attaches a reducer to a state field. A reducer tells LangGraph how to combine an existing value with a node's update.

- `add` appends new audit entries rather than replacing the existing list.
- `add_messages` adds conversation messages using LangGraph's message-handling behavior.

Because these fields accumulate, a new treatment request should receive a new `thread_id` after the previous request reaches a terminal status. Reusing an old completed thread would also reuse its checkpointed history.

## Workflow initialization

Creating `AgriculturalWorkflow()` performs these steps:

1. Validate environment settings.
2. Select an Ollama or Gemini chat model.
3. Build the Intake, Specialist, and Critic structured-output chains.
4. Configure serialization for the Pydantic models stored in checkpoints.
5. Create the in-memory checkpointer.
6. Build and compile the graph.

### Model selection

`config.py` reads `MODEL_PROVIDER` from the environment. The supported values are:

```text
ollama
gemini
```

Ollama is the current default and supports local testing without consuming Gemini quota. `OLLAMA_MODEL` defaults to `gemma3`, and `OLLAMA_BASE_URL` defaults to `http://localhost:11434`.

Gemini requires `GOOGLE_API_KEY`. Both providers use temperature `0` to encourage more consistent output. Temperature controls response randomness; a lower value generally makes responses more repeatable, although it does not guarantee identical or perfectly accurate output.

### Structured-output chains

The helper `_build_structured_chain` connects a prompt to a chat model configured with a Pydantic output schema:

```text
Prompt -> chat model -> validated Pydantic object
```

The schemas are:

| Chain | Output schema |
|---|---|
| Intake | `IntakeDecision` |
| Specialist | `TreatmentPlan` |
| Critic | `CriticDecision` |

`method="json_schema"` asks the model provider to follow the schema's JSON structure. The chain also retries failed calls. Retries help with temporary model or parsing failures, but they may consume provider quota.

### Checkpoint serialization

`JsonPlusSerializer` is configured with the project's Pydantic models in `allowed_msgpack_modules`. This permits the checkpointer to serialize and restore those structured values without unregistered-type warnings.

Serialization means converting Python objects into a form that can be stored and later reconstructed. MessagePack is a compact serialization format used internally by the checkpointer.

## Graph construction

`_build_graph` creates a `StateGraph(AgriculturalState)`, registers nodes, connects routes, and compiles the result with the checkpointer.

The normal successful path is:

```text
START
  -> intake
  -> gather_context
  -> retrieve
  -> specialist
  -> rules
  -> critic
  -> human_review
  -> write_work_order or rejected
  -> END
```

Other paths allow clarification, revision, escalation, and controlled failure.

## Node-by-node implementation

### 1. Intake node

Method: `_intake_node`

The Intake agent reads the full available conversation and converts free text into a `TreatmentRequest`. Relative dates such as "today" are resolved using the current date.

The model extracts information, but deterministic Python code determines whether the user omitted a required field. The currently user-required fields are:

```text
field_id
observed_issue
proposed_product
proposed_date
```

The system may obtain `crop`, `acres`, and `requested_rate` from records or label evidence. This separation prevents an inconsistent model-provided route from controlling the graph.

Routing:

- Missing user-required fields -> `clarify`
- All required fields present -> `gather_context`
- Exception -> `failure`

### 2. Clarification node

Method: `_clarify_node`

This node builds a readable message from `missing_information`, records the message in conversation state, and ends the current graph invocation with `final_status="needs_information"`.

The interface should keep the same `thread_id` when submitting the user's follow-up answer. That lets Intake combine the new answer with earlier conversation messages.

### 3. Context-gathering node

Method: `_gather_context_node`

This is currently a mock integration point. It constructs example `FieldRecord`, `ProductRecord`, `ApplicationRecord`, and `WeatherForecast` objects.

Eventually, this node should call teammate-provided read-only tools for:

- Field lookup
- Product lookup
- Application-history lookup
- Weather lookup

Routing:

- Successful context -> `retrieve`
- Exception -> `failure`

### 4. Retrieval node

Method: `_retrieve_node`

This is currently a mock RAG integration point. It returns two example `EvidenceChunk` objects with source, page, product, and registration metadata.

The final RAG implementation should retrieve evidence from the proposed product's label and preserve enough metadata for citations.

Routing:

- Evidence returned -> `specialist`
- No evidence -> `clarify`
- Exception -> `failure`

### 5. Specialist node

Method: `_specialist_node`

The Specialist agent receives:

- Structured treatment request
- Field record
- Product record
- Application history
- Weather forecast
- Retrieved label evidence
- Previous Critic review, when revising

It returns a `TreatmentPlan` containing the treatment date, rate, acres, summaries, citations, assumptions, and the requirement for human review.

The Specialist proposes a plan. It does not approve a real application.

Routing:

- Plan created -> `rules`
- Exception or structured-output failure -> `failure`

### 6. Rule-engine node

Method: `_rule_engine_node`

The rule engine uses ordinary Python rather than an LLM. This makes comparisons and calculations deterministic: the same inputs produce the same results.

The current checks are:

| Rule | Purpose | Current failure severity |
|---|---|---|
| `maximum_rate` | Plan rate does not exceed the single-application maximum | Fixable |
| `seasonal_maximum_rate` | Prior rate plus proposed rate stays within the seasonal maximum | Fixable |
| `crop_compatibility` | Product supports the field's crop | Hard violation |
| `trait_compatibility` | Product supports the crop trait package | Hard violation |
| `growth_stage` | Application is allowed at the current crop stage | Hard violation |
| `wind` | Forecast wind does not exceed the product maximum | Fixable |
| `temperature` | Forecast high does not exceed the product maximum | Fixable |
| `buffer` | Sensitive-site distance meets the required buffer | Hard violation |
| `phi_before_harvest` | PHI ends on or before expected harvest | Hard violation |

The PHI deadline is calculated as:

```python
phi_deadline = treatment_date + timedelta(days=phi_days)
```

The check passes when `phi_deadline <= expected_harvest_date`.

The current rule engine is marked as a mock integration point because the team may refine the final rules and structured product data.

### 7. Critic node

Method: `_critic_node`

The Critic agent receives the plan, deterministic rule result, and evidence. It returns one verdict:

- `clean`: Continue to human review.
- `fixable`: Send the plan back to the Specialist for revision.
- `insufficient_info`: Ask for more information.
- `hard_violation`: Escalate for manual compliance handling.

Local models can sometimes describe passing checks as failed. The implementation therefore validates the model's verdict against the deterministic rule results.

- Actual hard-rule failures override an incorrect model verdict.
- Actual fixable failures override an incorrect model verdict.
- If all checks pass, a contradictory `fixable` or `hard_violation` verdict is replaced with `clean`.

This safeguard does not approve a treatment. A `clean` result only allows the plan to proceed to required human review.

### 8. Human-review node

Method: `_human_review_node`

This node calls `interrupt()` with the plan, validated review, and evidence sources. LangGraph saves the checkpoint and pauses.

When the interface resumes the graph, the node records either:

```text
approved
rejected
```

Routing:

- Approved -> `write_work_order`
- Rejected -> `rejected`

### 9. Work-order node

Method: `_work_order_node`

This is a mock side effect. A side effect is an operation that changes something outside the graph, such as writing a database record.

The node creates a demonstration ID such as `DEMO-4D4EF9F4` and clearly states that no real treatment was scheduled. It must remain behind human approval.

Final status: `simulated_work_order_created`.

### 10. Rejected node

Method: `_rejected_node`

This is the terminal path for a human rejection. It does not create a work order.

Final status: `rejected`.

### 11. Escalation node

Method: `_escalation_node`

This terminal path indicates that the request requires manual compliance review, usually because of a hard violation or an exhausted revision limit.

Final status: `escalated`.

### 12. Failure node

Method: `_failure_node`

Most processing nodes catch exceptions and write a readable `error` value into state. Routing functions detect that value and send the request to this controlled terminal node instead of crashing the application.

Final status: `failed`.

## Routing and safety hierarchy

The workflow uses this authority order:

```text
Deterministic Python rules
        before
Validated Critic verdict
        before
Human decision
        before
Simulated side effect
```

The agents propose and explain. Python validates encoded compliance rules and selects safe routes. A human makes the final operational decision.

The Critic router behaves as follows:

```text
Error
-> controlled failure

Failed hard rule
-> escalation

Failed fixable rule and revisions remain
-> Specialist revision

Failed fixable rule and revision limit reached
-> escalation

Insufficient information
-> clarification

Otherwise
-> human review
```

## Public workflow methods

### Starting a request

```python
workflow.start(
    question="Field F001 has a fungal disease. Use Example Product today.",
    thread_id=thread_id,
)
```

`start` initializes conversation messages, audit state, revision state, error state, and missing-information state before invoking the graph.

### Resuming human review

```python
workflow.resume_human_review(
    decision="approved",
    thread_id=thread_id,
)
```

The same `thread_id` must be used so LangGraph can load the interrupted checkpoint. `resume_human_review` sends a `Command` containing the human decision.

## Command-line interface behavior

`src/main.py` is a demonstration interface, not the final Streamlit UI. It:

1. Creates the workflow.
2. Generates a thread ID.
3. Accepts a treatment request.
4. Displays an interrupted plan and review.
5. Collects a `yes` or `no` human decision.
6. Resumes the graph.
7. Displays the final status, plan, review, work order, and trace.
8. Creates a new thread after a terminal result but preserves the thread while clarification is needed.

The Streamlit implementation should preserve these checkpoint rules even though its presentation will be different.

## Current mock boundaries

The following behavior is intentionally temporary:

- `_gather_context_node` creates mock farm, product, application, and weather records.
- `_retrieve_node` creates mock label evidence.
- `_rule_engine_node` contains a working draft of deterministic rules that may be refined.
- `_work_order_node` creates only a simulated work order.
- `InMemorySaver` does not persist checkpoints after application restart.

The mock boundaries allow the complete graph to be tested before teammate implementations are connected.

## Audit trail

Every node appends short events to `audit_log`. The trace currently records activities such as:

- Intake route selection
- Context loading
- Evidence retrieval
- Specialist revision number
- Number of rule checks passed
- Original and validated Critic verdicts
- Human decision
- Final work-order, rejection, escalation, or failure action

The audit trail is useful for demonstrations, debugging, and explaining why the graph selected a route. It is not yet a production compliance log.

## Known implementation considerations

- Local Ollama models may be less consistent than Gemini when interpreting large structured inputs.
- Deterministic validation prevents known Critic contradictions from controlling routing.
- Model retries may increase API usage and should be considered when using a limited free tier.
- `InMemorySaver` is suitable for an MVP demonstration but not durable storage.
- The graph currently returns its state dictionary directly. A normalized response object may be added for a cleaner Streamlit contract.
- The implementation currently initializes the model with `self.llm = self.llm = self._build_chat_model()`. This behaves like a normal assignment but contains a duplicate `self.llm =` that can be cleaned up later.
- Agricultural label rules in the MVP are simplified and must not be treated as authorization for a real pesticide application.

## Working with teammates

The graph depends on contracts shared with Streamlit, RAG, and Tools. Those contracts are documented in `langgraph_integration_guide.md`.

The current interfaces are working assumptions, not unchangeable requirements. Teammates should ask questions or request changes when:

- A schema is missing a needed field.
- A return type is difficult to produce.
- Streamlit needs a clearer status or plain dictionary response.
- RAG needs additional metadata for filtering or citations.
- Tools need different inputs or error behavior.
- A proposed change would make integration, testing, or safety clearer.

Changes to shared schemas should be communicated to the team because multiple parts of the application depend on them.

## Suggested learning path through the code

For a first review of the implementation, read in this order:

1. `src/schemas.py` to understand the structured data.
2. `AgriculturalState` in `src/graph.py` to see what the workflow stores.
3. `_build_graph` to understand the nodes and routes.
4. `_intake_node`, `_specialist_node`, and `_critic_node` to see the agent roles.
5. `_rule_engine_node` to see deterministic validation.
6. `_human_review_node` and `resume_human_review` to understand interrupt and resume.
7. `src/main.py` to see how an interface calls the workflow.

