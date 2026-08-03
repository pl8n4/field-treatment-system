# Manual Workflow Testing

This guide exercises the integrated CLI, LangGraph workflow, JSON records,
label retrieval, weather client, configured chat model, human-review interrupt,
and simulated work-order path.

Run these tests from the project root with the virtual environment active:

```bash
python src/main.py
```

The configured model provider must be available. Ollama must be running when
`MODEL_PROVIDER=ollama`; Gemini requires `GOOGLE_API_KEY` when
`MODEL_PROVIDER=gemini`. Weather and initial Hugging Face model downloads
require network access.

## Test-date selection

Open-Meteo normally provides approximately 16 days of forecast data. Replace
`<TEST_DATE>` in the examples with a date within that horizon. Use the same date
throughout one test conversation.

The first retrieval may download the local sentence-transformer model and
build the Chroma collection. Later runs should use the cached model and vector
store. The Hugging Face unauthenticated-request warning is not a workflow
failure; an `HF_TOKEN` is optional for this MVP.

## Thread and session isolation

Follow-up answers for one request should be entered in the same CLI session so
LangGraph can reuse its checkpoint thread.

Restart the CLI before beginning a logically separate scenario after a
`needs_information` result. The CLI intentionally retains that thread for
follow-up information, so starting an unrelated request in it can preserve
state from the previous request.

Terminal results such as `rejected`, `escalated`, and
`simulated_work_order_created` automatically cause the CLI to create a new
thread for the next request.

## 1. Compliant request and approval

Enter:

```text
Field F-02 has weeds. Apply Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

F-02 is planted with the Enlist E3 trait at growth stage V3. The structured
product record permits Enlist One for that trait and growth stage.

Expected behavior, provided the forecast satisfies the label limits:

- Field, product, application history, and weather context load.
- Retrieval returns evidence only from the Enlist One label.
- The rule trace reports 16 checks.
- The workflow pauses for human review.
- Entering `yes` returns `simulated_work_order_created`.
- The result clearly states that no real treatment was scheduled.

Inspect the plan before approving. The plan should preserve:

```text
field_id: F-02
product_name: Enlist One
proposed_rate: 32
treated_acres: 80
```

If the plan changes one of those values, the corresponding deterministic
identity or request-consistency rule should fail and request a revision.

## Fallback acreage and rate

Start a fresh CLI session and omit acreage and rate:

```text
Field F-02 has weeds. Apply Enlist One on <TEST_DATE>.
```

Expected behavior:

- Context gathering resolves acreage from F-02's `FarmField.acres` value of
  `96.5`.
- Context gathering resolves rate from Enlist One's
  `default_rate_fl_oz_per_acre` value of `32.0`.
- The resolved values are written into the structured request before the
  Specialist runs.
- The plan preserves `treated_acres=96.5` and `proposed_rate=32.0`.
- The `requested_acres` and `requested_rate` consistency checks pass.

## Field acreage validation

Start a fresh CLI session and request more than F-02's 96.5 acres:

```text
Field F-02 has weeds. Apply Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 100 acres.
```

Expected behavior:

- Final status is `needs_information`.
- The message reports both the requested 100 acres and the field's 96.5 acres.
- Retrieval and specialist planning do not run.
- No plan or work order is created for the oversized request.

## 2. Human rejection

Run the compliant F-02 request again. At the human-review prompt, enter:

```text
no
```

Expected behavior:

- Final status is `rejected`.
- The final message says the human reviewer rejected the plan.
- No work order is created.

## 3. Multi-turn clarification

Enter:

```text
Field F-02 has weeds.
```

Expected first result:

- Final status is `needs_information`.
- Missing information includes `proposed_product` and `proposed_date`.

In the same session, enter:

```text
Use Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

Expected behavior:

- Intake combines the follow-up with the earlier field and issue.
- The structured request retains F-02.
- The workflow continues through context gathering and retrieval.

## 4. Unknown field

Start a fresh CLI session and enter:

```text
Field F-99 has weeds. Apply Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

Expected behavior:

- Final status is `needs_information`.
- Missing information explains that F-99 could not be resolved.
- No new treatment plan or work order should be produced for F-99.

## 5. Trait incompatibility

Enter:

```text
Field F-01 has weeds. Apply Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

F-01 uses the XtendFlex trait, while Enlist One requires the Enlist trait.

Expected behavior:

- `trait_compatibility` fails as a hard violation.
- The critic cannot override the deterministic failure with a clean verdict.
- Final status is `escalated`.
- Human approval is not requested.

## 6. Growth-stage violation

Enter:

```text
Field F-08 has weeds. Apply Roundup PowerMax 3 on <TEST_DATE> at 20 fluid ounces per acre across 80 acres.
```

F-08 is at R5, beyond Roundup PowerMax 3's R2 application window.

Expected behavior:

- `growth_stage_window` fails as a hard violation.
- Final status is `escalated`.

## 7. Seasonal-rate conflict and revision limit

Enter:

```text
Field F-01 has weeds. Apply Roundup PowerMax 3 on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

F-01 already has 32 fluid ounces per acre of Roundup PowerMax 3 recorded. A
second 32-fluid-ounce application would exceed the 60-fluid-ounce seasonal
maximum.

Expected behavior:

- `seasonal_maximum_rate` fails as fixable.
- The workflow gives the Specialist one revision opportunity.
- A lower rate conflicts with the explicitly requested 32-fluid-ounce rate.
- The workflow escalates if it cannot satisfy both constraints within the
  revision limit.

## 8. PHI violation

Enter:

```text
Field F-10 has weeds. Apply Enlist One on <TEST_DATE> at 32 fluid ounces per acre across 80 acres.
```

Choose a test date for which the 50-day Enlist One pre-harvest interval extends
past F-10's expected harvest date of September 15, 2026.

Expected behavior:

- `phi_before_harvest` fails as a hard violation.
- F-10's R4 growth stage also exceeds Enlist One's R1 limit.
- Final status is `escalated`.

## 9. Nonpositive request values

Enter:

```text
Field F-02 has weeds. Apply Enlist One on <TEST_DATE> at -5 fluid ounces per acre across -20 acres.
```

Expected behavior:

- Pydantic rejects the nonpositive rate and acreage.
- The workflow fails safely or asks for corrected values.
- It does not create a treatment plan eligible for approval.

## What to inspect in every result

The workflow trace should show only nodes appropriate to the route. A complete
review path normally includes:

```text
Intake
Context gathering
Retrieval
Specialist
Rule engine
Critic
Human review or another terminal route
```

Also verify:

- The field and product match the request.
- The treatment date and resolved rate and acreage are preserved.
- Product evidence comes from the selected product's PDF.
- REI means restricted-entry interval.
- PHI means pre-harvest interval and is calculated against expected harvest.
- A hard deterministic failure never reaches human approval.
- Only explicit human approval creates a simulated work order.
- No output implies that a real treatment was scheduled.

Model-generated summaries and citations should be reviewed for grounding even
when all deterministic rules pass. A passing rule result confirms structured
compliance checks; it does not independently prove that every sentence written
by the chat model is accurate.

## Recording unexpected behavior

When reporting a manual-test issue, include:

- The exact request and follow-up messages.
- The configured model provider and model name.
- The final status and message.
- The plan, review, and rule results.
- The complete workflow trace.
- Whether the Chroma collection and embedding model were being built for the
  first time.
- Whether the test reused a thread after `needs_information`.

Do not include API keys or the contents of `.env` in test reports.
