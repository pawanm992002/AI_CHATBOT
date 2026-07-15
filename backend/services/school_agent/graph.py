import os
from typing import Annotated, Sequence, TypedDict, Literal
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from services.llm.factory import get_llm_raw
from services.school_agent.tools import ALL_TOOLS, WRITE_TOOL_NAMES, tools_by_name

# Define graph state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    tenant_id: str
    school_session_id: str
    original_question: str

def get_system_prompt() -> str:
    return """You are an AI assistant for a school ERP system.
You help tenants query and update school records including students, classes, sections, routes, bus stops, fees, payments, and hostel assignments.

Rules for using tools:
1. You MUST only use the provided tools to query or update data.
2. NEVER assume or invent IDs or names. Use the resolver tools to look up IDs from names.
3. Every tool invocation automatically scopes queries to the current tenant. You do NOT need to supply tenant_id (the system handles this internally).
4. For fees, status values are exactly 'Paid', 'Pending', or 'Partial'. Use status='Pending' or status='Partial' for due fees. Do NOT use 'due' as a status.
5. For counts, totals, summaries, dues, and financial answers, use deterministic tools (`count_school_entities` or `get_school_report`). Do NOT calculate totals from limited row lists.
6. For due fee totals, students with due fees, pending/partial fee lists, or "with due amount" follow-ups, call `get_school_report(report_id="due_fees_by_student")`. This report returns total_due and rows from the same calculation.
7. If a tool result has `has_more=true`, clearly say the answer is limited and include returned_count and total_count.
8. Do not invent missing rows, fee amounts, or totals. Format the structured tool result only.

SCALABLE GENERIC TOOLS:
- `search_school_entity` safely searches registered entities such as student, class, section, applied_fee, payment, route, stop, transport_assignment, hostel_assignment, and teacher.
- `get_school_entity_detail` fetches one record by primary key.
- `get_school_related_entities` follows registry relationships, for example student -> fees/payments/transport/hostel.
- `count_school_entities` answers count questions.
- `get_school_report` answers deterministic business reports. Use it for due fees and financial totals.
- `explain_school_schema` explains available entities, fields, relationships, and reports.

RESOLVE-THEN-QUERY PATTERN:
If a query references an entity by name (e.g., student name, class name, route name, stop name) rather than an ID, you MUST resolve the name to an ID first before running any queries that filter by ID.
- To lookup student IDs from a student's name, use `resolve_student_id(name)`.
- To lookup class IDs from a class name, use `resolve_class_id(class_name, school_id)`.

MULTI-HOP QUERY CHAINS:
When answering queries that span multiple collections, execute tools step-by-step.
Example 1: "transport status for student John Doe"
Step 1: Call `resolve_student_id(name="John Doe")`.
Step 2: From the returned student(s), find the matching student's `student_id` (e.g. 5).
Step 3: Call `query_transport_assign(student_id=5)`.
Step 4: From the transport assignment, find the `route_id` (e.g. 2) and `status` (e.g. 'Active').
Step 5: Call `query_routes(route_id=2)` to get the route name.
Step 6: Formulate the final answer containing the route name, vehicle_no, and status.

Example 2: "Show outstanding fees for student Ansh"
Step 1: Call `resolve_student_id(name="Ansh")`.
Step 2: Using the returned `student_id` (e.g. 1), call `query_applied_fees(student_id=1)`.
Step 3: Call `query_payments(student_id=1)`.
Step 4: Formulate the fee summary.

Example 3: "How many students are in UKG?"
Step 1: Call `resolve_class_id(class_name="UKG")`.
Step 2: From the class record, get `class_id` (e.g. 3).
Step 3: Call `count_school_entities(entity="student", filters=[{"field": "class_id", "op": "$eq", "value": 3}])`.
Step 4: Use the returned `total_count`.

Example 4: "Total due fees and student list with due amount"
Step 1: Call `get_school_report(report_id="due_fees_by_student", filters={"statuses": ["Pending", "Partial"]})`.
Step 2: Use `total_due`, `student_count`, `fee_record_count`, and `rows`.
Step 3: If `has_more` is true, tell the user the list is limited.

WRITE ACTIONS:
For any action that modifies data (e.g. change transport status, vacate hostel room, update fee status), you MUST immediately call the corresponding update tool (`update_transport_status`, `update_hostel_status`, or `update_fee_status`). Do NOT ask the user for permission, verification, or confirmation first. Output the tool call immediately.

IMPORTANT: Multi-tenant safety is critical. The tools automatically inject the tenant_id from the session context, ensuring you only access data belonging to the current tenant. Never attempt to guess, fetch, or expose data from other tenants.
"""

async def agent_node(state: AgentState, config: RunnableConfig):
    configurable = config.get("configurable", {})
    provider = configurable.get("llm_provider", "openai")
    model = configurable.get("llm_model", "gpt-4o-mini")
    
    llm = get_llm_raw(provider, model)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    
    sys_prompt = get_system_prompt()
    messages = [SystemMessage(content=sys_prompt)] + list(state["messages"])
    
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}

async def read_tools_node(state: AgentState, config: RunnableConfig):
    messages = state["messages"]
    last_message = messages[-1]
    
    tool_outputs = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        if tool_name not in tools_by_name:
            tool_outputs.append(
                ToolMessage(
                    content=f"Error: Tool {tool_name} not found.",
                    tool_call_id=tool_call["id"],
                )
            )
            continue
            
        tool_fn = tools_by_name[tool_name]
        try:
            res = await tool_fn.ainvoke(tool_call["args"], config=config)
            tool_outputs.append(
                ToolMessage(
                    content=str(res),
                    tool_call_id=tool_call["id"],
                )
            )
        except Exception as e:
            tool_outputs.append(
                ToolMessage(
                    content=f"Error running tool {tool_name}: {str(e)}",
                    tool_call_id=tool_call["id"],
                )
            )
            
    return {"messages": tool_outputs}

async def approval_node(state: AgentState, config: RunnableConfig):
    messages = state["messages"]
    last_message = messages[-1]
    
    write_tool_calls = [tc for tc in last_message.tool_calls if tc["name"] in WRITE_TOOL_NAMES]
    if not write_tool_calls:
        return {"messages": []}
        
    # We call interrupt to get human approval
    decision = interrupt({
        "message": f"Write action approval requested for: {write_tool_calls}",
        "write_tool_calls": write_tool_calls
    })
    
    # Once resumed, decision will contain the resume value.
    if decision.get("approved"):
        tool_outputs = []
        for tool_call in write_tool_calls:
            tool_name = tool_call["name"]
            tool_fn = tools_by_name[tool_name]
            try:
                res = await tool_fn.ainvoke(tool_call["args"], config=config)
                tool_outputs.append(
                    ToolMessage(
                        content=str(res),
                        tool_call_id=tool_call["id"],
                    )
                )
            except Exception as e:
                tool_outputs.append(
                    ToolMessage(
                        content=f"Error executing write tool {tool_name}: {str(e)}",
                        tool_call_id=tool_call["id"],
                    )
                )
        return {"messages": tool_outputs}
    else:
        tool_outputs = []
        for tool_call in write_tool_calls:
            tool_outputs.append(
                ToolMessage(
                    content=f"Write action rejected by user: {decision.get('reason', 'No reason provided')}",
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": tool_outputs}

def route_after_agent(state: AgentState) -> Literal["read_tools", "approval", "final_answer"]:
    messages = state["messages"]
    last_message = messages[-1]
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return "final_answer"
        
    has_write_calls = any(tc["name"] in WRITE_TOOL_NAMES for tc in last_message.tool_calls)
    if has_write_calls:
        return "approval"
    else:
        return "read_tools"

# Compile the graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("read_tools", read_tools_node)
workflow.add_node("approval", approval_node)

workflow.add_edge(START, "agent")

workflow.add_conditional_edges(
    "agent",
    route_after_agent,
    {
        "read_tools": "read_tools",
        "approval": "approval",
        "final_answer": END
    }
)

workflow.add_edge("read_tools", "agent")
workflow.add_edge("approval", "agent")

# TODO: Configure Mongo/Redis-backed checkpointer for production.
# checkpointer = RedisSaver(redis_client) or MongoSaver(db)
checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)
