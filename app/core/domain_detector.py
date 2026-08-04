import os
from typing import cast, List
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import SecretStr, BaseModel
from app.core.schema import ResumeFacts

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=cast(SecretStr, os.getenv("GROQ_API_KEY")),
    temperature=0,
)


class SearchKeywords(BaseModel):
    keywords: List[str]  # e.g. ["Machine Learning Engineer", "NLP Engineer", "Computer Vision"]


structured_llm = llm.with_structured_output(SearchKeywords)

PROMPT = """Based on this candidate's resume summary, roles, and skills, generate
3-5 job title search terms that would find genuinely relevant open roles for them.

Use real, common job title phrasing (e.g. "Machine Learning Engineer", not
"AI Wizard"). Base this only on what's actually in their background below -
don't guess at aspirational roles they have no evidence for.

Summary: {summary}

Most recent roles: {roles}

Top skills: {skills}
"""


def detect_search_keywords(facts: ResumeFacts) -> List[str]:
    roles = ", ".join(exp.role for exp in facts.experience[:3])
    skills = ", ".join(
        item for cat in facts.skills[:4] for item in cat.items[:5]
    )
    prompt = PROMPT.format(summary=facts.summary or "", roles=roles, skills=skills)
    result = cast(SearchKeywords, structured_llm.invoke(prompt))
    return result.keywords


if __name__ == "__main__":
    with open("data/resume_facts.json", "r", encoding="utf-8") as f:
        facts = ResumeFacts.model_validate_json(f.read())

    keywords = detect_search_keywords(facts)
    print("Detected search keywords:", keywords)