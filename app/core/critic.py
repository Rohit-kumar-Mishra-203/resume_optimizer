import os
import json
from typing import cast
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import SecretStr
from app.core.schema import ResumeFacts, JDRequirements, ResumeCritique

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=cast(SecretStr, os.getenv("GROQ_API_KEY")),
)

structured_llm = llm.with_structured_output(ResumeCritique, method="json_mode")

CRITIQUE_PROMPT = """You are a career coach reviewing how well a resume matches a job description,
using a scoring breakdown that has already been computed.

Respond with ONLY a valid JSON object matching the required structure.

Your output MUST match this exact JSON schema:

{schema}

Your job is to produce SPECIFIC, ACTIONABLE feedback.

CRITICAL RULES:
1. You may ONLY reference bullets by their real id, taken from the resume data
   below. Never invent a bullet or claim content that isn't there.
2. target_bullet_id MUST be the exact same bullet you discuss in description.
3. gap_type must be exactly one of: "missing_keyword", "weak_semantic_match",
   or "phrasing".
4. When a gap is GENUINE (real experience doesn't support it even with
   better phrasing), set is_genuine_gap=True and don't suggest a misleading rewrite.
5. When experience exists but is under-emphasized, set is_genuine_gap=False
   with a specific suggestion referencing the exact bullet id.
6. Never suggest adding a skill/tool/claim not already present in the resume.
7. Prioritize must-have skill gaps and the weakest semantic matches first.

Job description requirements:
{jd_requirements}

Score breakdown:
{score_breakdown}

Candidate's real resume data (only reference these ids):
{resume_bullets}
"""


def _format_resume_bullets(facts: ResumeFacts) -> str:
    lines = []
    for exp in facts.experience:
        lines.append(f"\n{exp.company} - {exp.role}:")
        for b in exp.bullets:
            lines.append(f"  [{b.id}] {b.text}")
    for proj in facts.projects:
        lines.append(f"\nProject: {proj.name}:")
        for b in proj.bullets:
            lines.append(f"  [{b.id}] {b.text}")
    return "\n".join(lines)


def generate_critique(jd: JDRequirements, facts: ResumeFacts, score_breakdown: dict) -> ResumeCritique:
    schema_json = json.dumps(ResumeCritique.model_json_schema(), indent=2)
    prompt = CRITIQUE_PROMPT.format(
        schema=schema_json,
        jd_requirements=jd.model_dump_json(indent=2),
        score_breakdown=score_breakdown,
        resume_bullets=_format_resume_bullets(facts),
    )
    result = cast(ResumeCritique, structured_llm.invoke(prompt))
    return result