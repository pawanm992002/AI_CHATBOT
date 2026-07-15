# School ERP Agent (LangGraph Architecture)

This directory contains the migrated **School ERP Module**, which uses a LangGraph-based tool-calling workflow instead of the legacy single-shot NL-to-query architecture.

## Overview

The agent is compiled as a state graph (`StateGraph`) using LangGraph. It is designed to handle complex, multi-hop natural language requests from users inside the school mode of the chatbot widget (e.g., `/school`).

```mermaid
graph TD
    START --> Agent[Agent Node]
    Agent --> Route{Route Decision}
    Route -->|Read Tool Called| ReadTools[Read Tools Node]
    Route -->|Write Tool Called| Approval[Approval Node (Interrupt)]
    Route -->|Final Answer| END
    ReadTools --> Agent
    Approval -->|Resumed w/ Approval| Agent
```

## Core Modules

### 1. `tools.py`
Defines the atomic operations the agent can perform. 
- **Generic Read Tools**: Safely search any entity registered in `school_data_registry.py`, fetch one entity by ID, follow declared relationships, count records, and run deterministic reports. Adding a new table means registering it, not adding another tool.
- **Resolver Tools**: Help resolve fuzzy/partial names (e.g., student name, class name) to exact database IDs.
  - `resolve_student_id`
  - `resolve_class_id`
- **Write Tools**: Update fields in the ERP.
  - `update_transport_status`
  - `update_hostel_status`
  - `update_fee_status`
- **Audit Logging**: Every tool execution is captured in `school_data_query_log` and `school_audit_log` for security and operational compliance.

### 2. `graph.py`
Constructs the `StateGraph` and defines the state structure, routing logic, and system prompt.
- **System Prompt**: Instructs the model to use the **Resolve-Then-Query** pattern and execute multi-hop reasoning step-by-step.
- **State**: The graph passes the conversation history, `tenant_id`, `school_session_id`, and the `original_question`.

### 3. Human-in-the-Loop (HITL) Write Approvals
To protect sensitive school ERP records from unauthorized or accidental modifications:
1. Write actions are gated behind a feature flag: `SCHOOL_WRITE_ACTIONS_ENABLED` (disabled by default).
2. When the LLM calls a write tool (e.g., `update_transport_status`), the conditional edge routes to the `approval` node.
3. The `approval` node raises a LangGraph `interrupt()`, which halts graph execution.
4. No change is made to the database during the interrupt state.
5. The caller can inspect the interrupt payload, present an approval prompt to the user, and resume execution by sending a `Command(resume={"approved": True})` or `Command(resume={"approved": False})`.

## Integration

The entry point to the ERP module remains `SchoolDataService.query()` in `backend/services/school_data_service.py`. It constructs the initial state and invokes the graph, returning the final answer or handling the approval state.

## Testing

Comprehensive unit tests are located in `backend/tests/test_school_agent.py` covering:
- Entity resolvers (`resolve_student_id`, `resolve_class_id`).
- Name resolution followed by a related transport lookup.
- Write interception and resumption via the interrupt mechanism.
- Security and audit log generation.
