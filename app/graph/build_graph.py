from langgraph.graph import StateGraph, END
from app.graph.state import LoopState
from app.graph.nodes import score_node, critique_node, edit_node, route_after_score


def build_graph():
    graph = StateGraph(LoopState)
    graph.add_node("score", score_node)
    graph.add_node("critique", critique_node)
    graph.add_node("edit", edit_node)
    graph.set_entry_point("score")
    graph.add_conditional_edges("score", route_after_score, {"stop": END, "continue": "critique"})
    graph.add_edge("critique", "edit")
    graph.add_edge("edit", "score")
    return graph.compile()


def run_optimization_loop(jd, base_facts, target_score: float = 93.0, max_iterations: int = 6):
    app = build_graph()
    initial_state: LoopState = {
        "jd": jd,
        "original_facts": base_facts,
        "facts": base_facts,
        "score_breakdown": None,
        "critique": None,
        "iteration": 0,
        "max_iterations": max_iterations,
        "target_score": target_score,
        "score_history": [],
        "status": "in_progress",
    }
    return app.invoke(initial_state)