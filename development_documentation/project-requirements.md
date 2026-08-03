# Project 2 - Multi-Agent Business Workflow Application

**Project presentation:** August 7th ~2PM EST 
**Primary technologies:** Python, LangChain, RAG, vector database, LangGraph, and a user interface  
**Optional stretch:** AWS SageMaker integration

## Project objective

Design and implement an AI-assisted business workflow that moves a request from intake to a justified outcome.

The project must be more than a general chatbot. It should represent a process with:

- Organizational knowledge
- Multiple responsibilities or agent roles
- Structured shared information
- Decisions and branches
- At least one controlled revision, retry, or validation loop
- Tools
- A clear completion, escalation, or human-review outcome

## Challenge statement

Create a system that accepts a realistic business request and coordinates several specialized responsibilities to produce a grounded result.

The system should be able to:

1. Understand or classify the request.
2. Retrieve relevant business documents or records.
3. Decide which workflow route is appropriate.
4. Use tools to gather information or perform mocked actions.
5. Share structured information across roles.
6. Validate the proposed outcome.
7. Revise, request missing information, or escalate when necessary.
8. Display the final result and supporting evidence.

## Approved project domains

Teams may choose one of the following or submit a comparable workflow for approval.

### Option A — Vendor onboarding and risk review

Possible roles:

- Intake or document-completeness agent
- Onboarding planner
- Risk/compliance reviewer

Possible tools:

- Vendor lookup
- Policy retriever
- Required-document checklist
- Mock approval-request creator

Possible routes:

- Missing documents
- Standard onboarding
- High-risk vendor
- Policy exception
- Human approval

### Option B — Customer support resolution and escalation

Possible roles:

- Triage agent
- Resolution specialist
- Quality reviewer

Possible tools:

- Customer lookup
- Order lookup
- Knowledge-base retriever
- Mock ticket or escalation creator

Possible routes:

- Shipping issue
- Technical issue
- Account issue
- Refund or policy exception
- Missing information
- Escalation

### Option C — Employee onboarding and access provisioning

Possible roles:

- Onboarding planner
- Access coordinator
- Security reviewer

Possible tools:

- Employee/role lookup
- Access matrix lookup
- Policy retriever
- Mock task creator

Possible routes:

- Standard employee
- Contractor
- Privileged access
- Missing manager approval
- Security exception

### Option D — Procurement request and exception management

Possible roles:

- Request analyst
- Procurement planner
- Policy critic

Possible tools:

- Budget lookup
- Vendor lookup
- Procurement-policy retriever
- Mock approval submission

Possible routes:

- Within policy
- Missing justification
- New vendor
- High-value purchase
- Policy exception
- Rejected request

### Option E — Team-proposed workflow

A custom workflow is allowed when it has:

- A realistic business purpose
- Enough complexity for three contributors
- Meaningful retrieval
- Meaningful branching
- At least one tool
- A validation or human-review point
- Data that can be safely created or simulated

## Required architecture

Your system should follow this general shape:

```text
User request
    ↓
Intake / triage
    ↓
Structured workflow state
    ↓
Planner, router, or supervisor
    ↓
Specialized work and tools
    ↓
Evidence-based draft
    ↓
Critic / validator
    ├── Approved → Complete
    ├── Revision required → Return to earlier node
    ├── Missing information → Ask user or pause
    └── Escalation required → Human-review outcome
```

The exact graph may differ. Every node and route must have a clear business purpose.

---

## Requirements

The project must include:

- A vector database such as Chroma or Pinecone.
- A meaningful collection of business documents or records.
- Document loading or data preparation.
- Chunking appropriate to the source material.
- An embedding model.
- Semantic retrieval.
- Metadata stored with chunks or records.
- At least one meaningful metadata filter or metadata-based behavior.
- Source information displayed or retained for traceability.
- A LangChain chat-model integration.
- Prompt templates.
- At least one retriever.
- At least one RAG workflow.
- Structured output using Pydantic, `TypedDict`, or another validated schema.
- At least one composed chain or runnable.
- Clear separation between retrieval, generation, and application-owned logic.
- Session handling, message history, or another justified form of memory.
- A usable interface, normally Streamlit.
- A LangGraph state definition.
- At least four meaningful nodes.
- `START` and one or more clear terminal outcomes.
- At least one conditional branch.
- At least one controlled loop, retry, or revision route.
- A maximum retry or termination condition.
- At least two application tools.
- At least one read-only tool.
- A human-review or escalation path before a consequential action.
- At least three distinct responsibilities or roles.
- Structured communication through graph state.
- Error handling for at least one tool or model failure.
- A visible state or workflow trace for debugging or presentation.

### Role requirement

A role must have a distinct responsibility. Renaming the same prompt three times does not create a meaningful multi-agent system.

A common pattern is:

- **Planner or triage role:** Determines what must happen.
- **Executor or specialist role:** Uses tools and produces work.
- **Critic or compliance role:** Checks evidence, policy, and completion.

Teams may use another pattern when responsibilities remain distinct.

### Tool requirement

Examples of read-only tools:

- Search a vector store
- Look up a customer
- Check inventory
- Read order status
- Read account status
- Retrieve a policy
- Calculate a score

Examples of mocked side-effect tools:

- Create a ticket
- Submit an approval request
- Schedule a follow-up
- Update a request status
- Send a notification
- Assign a case

A side-effect tool may be simulated by writing to a local JSON file, SQLite table, or in-memory record.

##  Human review and safety

The application must identify at least one action that should not occur solely because a model requested it.

Examples:

- Refund approval
- Access change
- Vendor approval
- Security escalation
- Record update
- External notification

The project should demonstrate one of these outcomes:

```text
Recommended action awaiting approval
Approved mocked action
Rejected action
Escalated to human
```

The interface must not falsely claim that a real-world action occurred when it was only simulated.

---

## Required test scenarios

The final application must demonstrate at least four scenarios:

1. **Happy path**  
   The request contains enough information and reaches a supported outcome.

2. **Branching path**  
   A different input follows a visibly different route.

3. **Missing-information or human-review path**  
   The workflow asks for information, pauses, or produces an escalation outcome.

4. **Failure or revision path**  
   A tool fails, retrieval is insufficient, or a critic requests revision.

At least one scenario must exercise the controlled loop without exceeding the retry limit.

Teams should record expected routes before testing.

## Presentation expectations

Prepare a 12–15 minute presentation.

Every team member must speak and demonstrate technical understanding.

Include:

1. Business problem and user
2. Why the workflow benefits from AI
3. Architecture diagram
4. Vector database and retrieval strategy
5. LangChain components
6. LangGraph state, nodes, and routes
7. Agent or role responsibilities
8. Tool design and human-review boundary
9. Live happy-path demonstration
10. Live branching, failure, or escalation demonstration
11. State or workflow trace
12. Reliability, limitations, and future work
13. Team contributions

A polished chat interface without a clear workflow explanation is not sufficient.

## SageMaker stretch goal

SageMaker is optional and should extend the business workflow rather than being added only for appearance.

### Recommended stretch

Train and deploy a small classifier that predicts a useful routing signal, such as:

- Request category
- Ticket priority
- Escalation risk
- Vendor risk
- Purchase category
- Customer-churn or retention risk

Use the endpoint as a tool or node:

```text
Business request
    ↓
SageMaker classifier endpoint
    ↓
Prediction stored in graph state
    ↓
LangGraph routing decision
```

Possible additional stretch work:

- SageMaker Experiments
- Model Registry
- Endpoint versioning
- Basic training pipeline
- Compare local and hosted inference
- Fallback behavior when the endpoint is unavailable

Do not attempt to host the entire LangGraph or Streamlit application as a SageMaker model endpoint unless the team has a clear architecture and extra time.
