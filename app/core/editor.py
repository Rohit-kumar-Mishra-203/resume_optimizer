import json
import copy
from typing import List, Dict
from app.core.schema import ResumeFacts, ResumeCritique, CritiqueItem, EditorOutput
from app.core.groq_client import invoke_structured

EDITOR_PROMPT = """You are revising specific resume bullet points based on feedback,
to better match a job description - WITHOUT ever inventing new facts.

Respond with ONLY a valid JSON object matching this schema:

{schema}

CRITICAL RULES:
1. You may ONLY revise the exact bullets listed below by their id.
2. You may ONLY rephrase/reframe what is ALREADY stated - NEVER add a new
   tool, technology, metric, number, or claim not already present.
3. If the suggestion implies adding something not in the original, revise
   as close as honestly possible without fabricating, note the limitation.
4. Keep each revised bullet a similar length to the original.
5. justification must state which part of the ORIGINAL bullet grounds it.

Bullets to revise:
{bullets_to_revise}
"""


def _format_bullets_for_editing(facts: ResumeFacts, items: List[CritiqueItem]) -> str:
    id_to_text: Dict[str, str] = {}
    for exp in facts.experience:
        for b in exp.bullets:
            id_to_text[b.id] = b.text
    for proj in facts.projects:
        for b in proj.bullets:
            id_to_text[b.id] = b.text

    lines = []
    for item in items:
        if item.target_bullet_id and item.target_bullet_id in id_to_text:
            original = id_to_text[item.target_bullet_id]
            lines.append(
                f"- id: {item.target_bullet_id}\n"
                f"  original: \"{original}\"\n"
                f"  suggestion: \"{item.suggestion}\""
            )
    return "\n".join(lines)


def generate_revisions(facts: ResumeFacts, critique: ResumeCritique) -> EditorOutput:
    actionable_items = [
        item for item in critique.items
        if not item.is_genuine_gap and item.target_bullet_id
    ]
    if not actionable_items:
        return EditorOutput(revisions=[])

    schema_json = json.dumps(EditorOutput.model_json_schema(), indent=2)
    bullets_text = _format_bullets_for_editing(facts, actionable_items)
    prompt = EDITOR_PROMPT.format(schema=schema_json, bullets_to_revise=bullets_text)
    return invoke_structured(EditorOutput, prompt)


def apply_revisions(facts: ResumeFacts, editor_output: EditorOutput) -> ResumeFacts:
    updated = copy.deepcopy(facts)
    revision_map = {r.bullet_id: r.revised_text for r in editor_output.revisions}

    for exp in updated.experience:
        for b in exp.bullets:
            if b.id in revision_map:
                b.text = revision_map[b.id]
    for proj in updated.projects:
        for b in proj.bullets:
            if b.id in revision_map:
                b.text = revision_map[b.id]

    return updated

if __name__ == "__main__":
    from app.core.scorer import score_resume
    from app.core.critic import generate_critique
    from app.core.schema import JDRequirements

    with open("data/resume_facts.json", "r", encoding="utf-8") as f:
        facts = ResumeFacts.model_validate_json(f.read())

    sample_jd = JDRequirements(
        job_title="Machine Learning Engineer",
        company=None,
        seniority_level="Mid-Level",
        must_have_skills=["Python", "PyTorch", "Transformer architectures", "LLM fine-tuning"],
        nice_to_have_skills=["LangChain/LangGraph", "RAG systems"],
        responsibilities=[
            "Build and deploy production NLP pipelines",
            "Collaborate with product team",
            "Optimize model performance",
        ],
        tools_and_tech=["Python", "PyTorch", "LangChain", "LangGraph"],
        raw_text="",
    )

    score_result = score_resume(sample_jd, facts)
    critique = generate_critique(sample_jd, facts, score_result)
    editor_output = generate_revisions(facts, critique)

    print("--- Revisions ---")
    print(editor_output.model_dump_json(indent=2))

    updated_facts = apply_revisions(facts, editor_output)

    new_score = score_resume(sample_jd, updated_facts)
    print(f"\nOriginal score: {score_result['overall_score']}")
    print(f"New score:      {new_score['overall_score']}")