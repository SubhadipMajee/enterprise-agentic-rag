from langgraph.graph import StateGraph, END
from app.agents.state import AgentState
from app.agents.nodes.planner import planner_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.nodes.responder import generate_node
from app.agents.checkpointer import build_checkpointer


workflow = StateGraph(AgentState)
workflow.add_node("planner", planner_node)
workflow.add_node("retriever", retrieve_node)
workflow.add_node("responder", generate_node)


def route_planner(state: AgentState):
    if state["current_query"] == "CONVERSATIONAL":
        return "responder"
    return "retriever"


workflow.set_entry_point("planner")
workflow.add_conditional_edges(
    "planner",
    route_planner,
    {
        "retriever": "retriever",
        "responder": "responder",
    },
)
workflow.add_edge("retriever", "responder")
workflow.add_edge("responder", END)

rag_agent = None


def compile_agent():
    global rag_agent
    rag_agent = workflow.compile(checkpointer=build_checkpointer())
    return rag_agent


def get_agent():
    if rag_agent is None:
        compile_agent()
    return rag_agent
