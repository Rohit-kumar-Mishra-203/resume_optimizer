from app.graph.state import LoopState
from app.core.scorer import score_resume
from app.core.critic import generate_critique
from app.core.editor import generate_revisions, apply_revisions

PLATEAU_THRESHOLD = 0.5


def score_node(state: LoopState) -> LoopState:
    breakdown = score_resume(state["jd"], state["facts"])
    state["score_breakdown"] = breakdown
    state["score_history"] = state["score_history"] + [breakdown["overall_score"]]

    current_score = breakdown["overall_score"]

    if current_score >= state["target_score"]:
        state["status"] = "success"
    elif state["iteration"] >= state["max_iterations"]:
        state["status"] = "max_iterations_reached"
    elif len(state["score_history"]) >= 2 and (
        state["score_history"][-1] - state["score_history"][-2] < PLATEAU_THRESHOLD
    ):
        state["status"] = "plateaued"
    else:
        state["status"] = "in_progress"

    return state


def critique_node(state: LoopState) -> LoopState:
    assert state["score_breakdown"] is not None
    critique = generate_critique(state["jd"], state["facts"], state["score_breakdown"])
    state["critique"] = critique
    return state


def edit_node(state: LoopState) -> LoopState:
    assert state["critique"] is not None
    editor_output = generate_revisions(state["facts"], state["critique"])
    state["facts"] = apply_revisions(state["facts"], editor_output)
    state["iteration"] = state["iteration"] + 1
    return state


def route_after_score(state: LoopState) -> str:
    return "stop" if state["status"] != "in_progress" else "continue"