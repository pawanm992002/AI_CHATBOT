# School Data Service Architecture

This document explains the current School ERP chat/data architecture. The
system is designed to support many school tables without creating one LangGraph
tool per table.

## Current Design

The active school-mode flow is:

```text
chat_service.py
  -> SchoolDataService.query()
  -> school_agent.graph
  -> school_agent.tools
  -> SchoolDataEngine
  -> School Entity Registry
  -> MongoDB
```

The key idea is simple: the LLM chooses a safe tool and structured parameters,
but the backend validates the entity, fields, operators, relationships,
projections, sorting, limits, and `tenant_id` before MongoDB is queried.

```mermaid
flowchart TD
    User[School admin question] --> Chat[chat_service.py]
    Chat --> Mode{School mode active?}
    Mode -->|No| Normal[Normal RAG chat]
    Mode -->|Yes| Service[SchoolDataService.query]

    Service --> Graph[LangGraph school agent]
    Graph --> Choice{Agent tool choice}

    Choice -->|Search/list| Search[search_school_entity]
    Choice -->|Single record| Detail[get_school_entity_detail]
    Choice -->|Related rows| Related[get_school_related_entities]
    Choice -->|Count| Count[count_school_entities]
    Choice -->|Financial/reporting| Report[get_school_report]
    Choice -->|Schema help| Explain[explain_school_schema]
    Choice -->|Write action| Approval[Approval interrupt]

    Search --> Engine[SchoolDataEngine]
    Detail --> Engine
    Related --> Engine
    Count --> Engine
    Report --> Engine
    Explain --> Registry[school_data_registry.py]

    Engine --> Registry
    Registry --> Validate[Validate entity metadata]
    Validate --> Guard[Inject tenant_id server-side]
    Guard --> Query{Query type}
    Query -->|Generic query| Mongo[(MongoDB)]
    Query -->|Deterministic report| ReportHandler[Report handler]
    ReportHandler --> Mongo
    Mongo --> Structured[Structured result]
    Structured --> Graph
    Graph --> Answer[Final answer]
    Approval --> Service
```

## Main Files

| File | Role |
|---|---|
| `backend/services/school_data_service.py` | Entry point from chat service; invokes LangGraph and handles approval interrupts. |
| `backend/services/school_agent/graph.py` | LangGraph agent, routing, prompt rules, read-tool node, approval node. |
| `backend/services/school_agent/tools.py` | Registry-backed generic read/report tools, resolvers, and guarded write tools exposed to the agent. |
| `backend/services/school_data_registry.py` | Metadata registry for entities, fields, operators, projections, sort fields, and relationships. |
| `backend/services/school_data_engine.py` | Safe generic query engine and deterministic report engine. |
| `backend/tests/test_school_data_engine.py` | Tests for registry validation, tenant isolation, limit metadata, and due-fee report arithmetic. |
| `backend/tests/test_school_query_safety.py` | Registry-backed query safety tests for tenant isolation, fields, and operators. |

## Why This Supports 200 Tables

Do not add one tool per collection. Add metadata for each new table in
`school_data_registry.py`.

```mermaid
flowchart LR
    NewTable[New school table] --> Metadata[Add EntitySpec metadata]
    Metadata --> Fields[Fields and allowed operators]
    Metadata --> Projection[Default projection]
    Metadata --> Sort[Sortable fields]
    Metadata --> Relations[Relationships]
    Relations --> ExistingTools[Same generic tools keep working]
```

The agent keeps a small tool surface:

```mermaid
mindmap
  root((School Agent Tools))
    Generic Tools
      search_school_entity
      get_school_entity_detail
      get_school_related_entities
      count_school_entities
      get_school_report
      explain_school_schema
    Deterministic Reports
      due_fees_by_student
    Resolver Tools
      resolve_student_id
      resolve_class_id
```

## Registry Model

`school_data_registry.py` defines:

- `FieldSpec`: field type, allowed operators, searchable flag, sortable flag.
- `RelationshipSpec`: target entity, local key, foreign key, relationship type.
- `EntitySpec`: entity name, collection, primary key, display name, fields,
  default projection, and relationships.

Example shape:

```python
"student": EntitySpec(
    entity="student",
    collection="school_students",
    primary_key="student_id",
    display_name="Student",
    fields={
        "student_id": FieldSpec("number", ("$eq", "$in")),
        "student_name": FieldSpec("string", ("$eq", "$regex", "$in")),
        "class_id": FieldSpec("number", ("$eq", "$in")),
    },
    default_projection=("student_id", "admission_no", "student_name", "class_id"),
    relationships={
        "fees": RelationshipSpec("applied_fee", "student_id", "student_id"),
        "payments": RelationshipSpec("payment", "student_id", "student_id"),
    },
)
```

Current registered entities:

```mermaid
mindmap
  root((SCHOOL_ENTITY_REGISTRY))
    school
    class
    section
    student
      fees
      payments
      transport
      hostel
      class
      section
    route
      stops
      transport_assignments
    stop
      route
      transport_assignments
    transport_assignment
      student
      route
      stop
    hostel_assignment
      student
    applied_fee
      student
      payments
    payment
      student
      applied_fee
    teacher
```

## Generic Query Engine

`SchoolDataEngine` runs all generic reads through registry validation.

```mermaid
flowchart TD
    Start[Generic tool call] --> Spec[get_entity_spec]
    Spec --> EntityValid{Known entity?}
    EntityValid -->|No| Error[Raise ValueError]
    EntityValid -->|Yes| Filters[Validate filters]

    Filters --> FieldValid{Fields allowed?}
    FieldValid -->|No| Error
    FieldValid -->|Yes| OpValid{Operators allowed?}
    OpValid -->|No| Error
    OpValid -->|Yes| RegexCheck{Regex value?}
    RegexCheck -->|Yes| RegexLimit{Length <= 200?}
    RegexLimit -->|No| Error
    RegexLimit -->|Yes| Projection
    RegexCheck -->|No| Projection[Validate projection]

    Projection --> Sort[Validate sort fields]
    Sort --> Limit[Clamp limit between 1 and 200]
    Limit --> Tenant[Build filter with server tenant_id]
    Tenant --> Count[count_documents]
    Tenant --> Find[find with projection/sort/limit]
    Count --> Result[Structured result]
    Find --> Result
```

Generic search result shape:

```json
{
  "entity": "student",
  "collection": "school_students",
  "filter": {
    "$and": [
      {"tenant_id": "tenant_abc"},
      {"class_id": {"$eq": 10}}
    ]
  },
  "total_count": 25,
  "returned_count": 20,
  "has_more": true,
  "limit": 20,
  "rows": []
}
```

The important metadata is `has_more`. If `has_more` is true, the agent is
instructed to tell the user the list is limited.

## Due Fees Report

Financial totals should not be calculated by the LLM from limited rows. The
due-fee report is deterministic:

```text
get_school_report(report_id="due_fees_by_student")
```

It calculates:

```text
due_amount = max(amount - concession - payments recorded against the same applied fee, 0)
```

from `school_applied_fees` and `school_payments`. Payments are matched by
`applied_fee_id`; an overpayment cannot make an individual fee record negative.
By default the report includes:

```text
Pending + Partial
```

Statuses can be safely filtered, for example:

```json
{"statuses": ["Pending"]}
```

```mermaid
sequenceDiagram
    autonumber
    participant Agent as LangGraph Agent
    participant Tool as get_school_report
    participant Engine as SchoolDataEngine
    participant Fees as school_applied_fees
    participant Payments as school_payments
    participant Students as school_students

    Agent->>Tool: report_id="due_fees_by_student"
    Tool->>Engine: get_report(...)
    Engine->>Engine: Validate statuses and filters
    Engine->>Fees: Find fee rows scoped by tenant_id
    Fees-->>Engine: Pending/Partial fee rows
    Engine->>Payments: Sum payments by applied_fee_id, scoped by tenant_id
    Payments-->>Engine: Paid totals for matching fee records
    Engine->>Engine: Group by student_id
    Engine->>Engine: Sum max(amount - concession - paid, 0)
    Engine->>Students: Fetch matching students scoped by tenant_id
    Students-->>Engine: Student names/admission/class/section
    Engine-->>Tool: total_due + student rows + metadata
    Tool-->>Agent: JSON result
```

Returned shape:

```json
{
  "report_id": "due_fees_by_student",
  "calculation_basis": "Due amount = sum(max(amount - concession - payments recorded against each applied fee, 0)) for selected statuses.",
  "statuses": ["Pending", "Partial"],
  "total_due": "243800",
  "student_count": 26,
  "fee_record_count": 36,
  "total_count": 26,
  "returned_count": 26,
  "has_more": false,
  "limit": 200,
  "rows": [
    {
      "student_id": 1,
      "student_name": "Ansh Sharma",
      "admission_no": "ADM001",
      "class_id": 4,
      "section_id": 1,
      "due_amount": "11000",
      "fee_record_count": 1,
      "breakdown": []
    }
  ]
}
```

Because `total_due` and `rows` come from the same backend calculation, answers
like "total due" and "student list with due amount" stay consistent.

## Dashboard Administration

The dashboard provides two tenant-authenticated school views. They use the
signed-in dashboard user's JWT and always query the current school data; they
do not depend on the browser widget or require the admin to enter school
credentials again.

- **School Records** searches students and loads the selected student's live
  student, fee, payment, transport, and hostel records. It presents both the
  amount on Pending/Partial fee records and the overall outstanding balance.
  Each fee's outstanding amount is `max(amount - concession - payments for the
  applied fee, 0)`.
- **School Chat** starts the same LangGraph School Agent in School Mode for the
  dashboard tenant. It stores a separate `dashboard-school-` session, reloads
  its saved conversation, and renders the agent's Markdown response.

```mermaid
flowchart LR
    Admin[Signed-in dashboard admin] --> JWT[Dashboard JWT]
    JWT --> Records[School Records API]
    JWT --> Chat[School Chat API]
    Records --> Mongo[(Tenant-scoped live MongoDB data)]
    Chat --> Mode[Activate School Mode for dashboard session]
    Mode --> Agent[LangGraph School Agent]
    Agent --> Engine[Registry-backed SchoolDataEngine]
    Engine --> Mongo
```

Endpoints:

- `GET /api/dashboard/school/students`
- `GET /api/dashboard/school/students/{student_id}`
- `POST /api/dashboard/school/chat`
- `GET /api/dashboard/school/chat/{session_id}`

## Manoj Sir Mismatch Root Cause

The earlier mismatch happened because the agent used low-level tools and the
LLM tried to combine limited/incomplete rows.

Previous problem pattern, before the registry/report migration:

```mermaid
flowchart TD
    Q1[Ask total due] --> FeesTool[Limited low-level fee query]
    FeesTool --> Limit20[Only first 20 rows possible]
    Limit20 --> LLMTotal[LLM summarizes total]

    Q2[Ask student list] --> StudentsTool[Limited low-level student query]
    StudentsTool --> NoFeeJoin[No deterministic fee join]
    NoFeeJoin --> Guess[LLM formats incomplete or wrong list]

    LLMTotal --> Mismatch[Total and student list mismatch]
    Guess --> Mismatch
```

Fixed pattern:

```mermaid
flowchart TD
    Question[Due fee total or due student list] --> Report[get_school_report]
    Report --> SamePath[Same deterministic report path]
    SamePath --> Total[total_due]
    SamePath --> Rows[student-wise rows]
    Total --> Consistent[Consistent answer]
    Rows --> Consistent
```

## `SchoolDataService.query()` Flow

`SchoolDataService.query()` remains the entry point for school mode.

```mermaid
sequenceDiagram
    autonumber
    participant Chat as chat_service.py
    participant Service as SchoolDataService.query()
    participant Graph as school_agent.graph
    participant Tools as school_agent.tools

    Chat->>Service: query(tenant_id, session_id, question, provider, model)
    Service->>Service: Build initial_state with HumanMessage
    Service->>Service: Build config.configurable
    Service->>Graph: graph.ainvoke(initial_state, config)
    Graph->>Tools: Call generic/read/write tools as needed
    Tools-->>Graph: Tool result
    alt Approval interrupt
        Graph-->>Service: __interrupt__
        Service-->>Chat: [APPROVAL_REQUIRED]: message
    else Final answer
        Graph-->>Service: messages
        Service-->>Chat: last message content
    end
```

## Write Actions

Write tools are still guarded by the approval node and feature flag.

```mermaid
flowchart TD
    User[Admin asks update/change] --> Agent[Agent]
    Agent --> WriteTool[Write tool call]
    WriteTool --> Route{Tool is write tool?}
    Route -->|Yes| Approval[LangGraph approval interrupt]
    Approval --> Decision{Approved?}
    Decision -->|No| Reject[Return rejected message]
    Decision -->|Yes| Flag{SCHOOL_WRITE_ACTIONS_ENABLED?}
    Flag -->|No| Disabled[Return write disabled]
    Flag -->|Yes| Update[(MongoDB update scoped by tenant_id)]
```

## Registry Query Safety

Every generic tool uses `SchoolDataEngine` and `school_data_registry.py`.
The registry declares the only allowed fields and operators for each entity;
the engine injects `tenant_id` server-side. Invalid entities, fields, and
operators raise an error instead of being silently ignored.

```mermaid
flowchart TD
    Input[Structured entity/filter request] --> Entity[Resolve EntitySpec]
    Entity --> Field{"Field registered?"}
    Field -->|No| Error[Reject request]
    Field -->|Yes| Operator{"Operator allowed for field?"}
    Operator -->|No| Error
    Operator -->|Yes| Regex{"Regex length within limit?"}
    Regex -->|No| Error
    Regex -->|Yes| Tenant[Inject tenant_id server-side]
    Tenant --> Mongo[(Tenant-scoped MongoDB query)]
```

## Real Query Example

Admin asks:

```text
Class 5 ke students dikhao
```

Agent should call:

```json
{
  "tool": "search_school_entity",
  "args": {
    "entity": "student",
    "filters": [
      {"field": "class_id", "op": "$eq", "value": 5}
    ],
    "limit": 50
  }
}
```

Backend builds:

```python
{
    "$and": [
        {"tenant_id": "current_school_tenant"},
        {"class_id": {"$eq": 5}}
    ]
}
```

Admin asks:

```text
Pure school ki due fees aur student-wise amount batao
```

Agent should call:

```json
{
  "tool": "get_school_report",
  "args": {
    "report_id": "due_fees_by_student",
    "filters": {
      "statuses": ["Pending", "Partial"]
    },
    "limit": 200
  }
}
```

The backend returns the total and student rows from the same calculation.

## Adding A New Table

To add a new ERP table:

1. Add an `EntitySpec` to `SCHOOL_ENTITY_REGISTRY`.
2. Define safe fields and operators.
3. Define `default_projection`.
4. Mark sortable/searchable fields.
5. Add relationships to other entities if needed.
6. Add a deterministic report only if the table needs business-critical
   calculations.
7. Add tests for validation and any new report logic.

You do not need to add a new LangGraph tool unless the capability is truly new.

## Tests

Run the backend tests with:

```bash
PYTHONPATH=backend uv run python -m unittest discover -s backend/tests -p "test_*.py" -v
```

Important test coverage:

- `test_school_query_safety.py`: registry field/operator validation and tenant
  isolation safety.
- `test_school_data_engine.py`: registry validation, tenant isolation, due-fee
  report totals, and limit metadata.
- `test_school_agent.py`: LangGraph agent behavior, resolver tools, write
  approval flow, and audit logging.

## Security Invariants

```mermaid
flowchart LR
    LLM[LLM suggested args] --> Backend[Backend validation]
    Tenant[Session tenant_id] --> Backend
    Backend --> Safe[Safe query/report plan]
    Safe --> Mongo[(MongoDB)]
    LLM -. cannot provide .-> Tenant
```

- The LLM never sends raw MongoDB queries.
- `tenant_id` is always injected from server/session context.
- Unknown entities, fields, operators, projections, sort fields, and
  relationships are rejected.
- Generic query limits are clamped.
- Financial totals are calculated by deterministic backend reports.
