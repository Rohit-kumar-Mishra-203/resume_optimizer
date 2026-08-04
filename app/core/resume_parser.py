import os
from typing import cast
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.schema import ResumeFacts, ResumeFactsPart1, ResumeFactsPart2

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

part1_llm = llm.with_structured_output(ResumeFactsPart1)
part2_llm = llm.with_structured_output(ResumeFactsPart2)

PART1_PROMPT = """You are extracting structured data from a resume - specifically
the personal info, summary, skills, education, and certifications ONLY.
Do NOT extract experience or projects - those are handled separately.

Rules:
1. Extract ONLY information explicitly present in the source text below.
   Do not infer, guess, or add anything that isn't there.
2. If a field genuinely isn't present, leave it null rather than guessing.
3. For certifications, if an instructor name is mentioned, extract just the
   person's name into an "instructor" field.

Resume source:
---
{resume_text}
---
"""

PART2_PROMPT = """You are extracting structured data from a resume - specifically
the work experience and projects ONLY, including every bullet point.
Do NOT extract personal info, skills, education, or certifications - those
are handled separately.

Rules:
1. Extract ONLY information explicitly present in the source text below.
   Do not infer, guess, or add anything that isn't there.
2. Preserve the original wording of bullet points exactly - do not paraphrase.
3. Assign each experience entry an id like "exp1", "exp2" in order of
   appearance. Assign each project an id like "proj1", "proj2". Assign each
   bullet an id combining its parent id and bullet number, e.g. "exp1_b1".
4. Split each bullet point into its own separate entry - do not merge
   multiple bullets into one, and do not split one bullet into multiple.
5. For a current/ongoing role with no end date stated, set end_date to the
   literal string "Present" - never null.

Resume source:
---
{resume_text}
---
"""


def parse_resume(resume_text: str) -> ResumeFacts:
    part1_prompt = PART1_PROMPT.format(resume_text=resume_text)
    part1 = cast(ResumeFactsPart1, part1_llm.invoke(part1_prompt))

    part2_prompt = PART2_PROMPT.format(resume_text=resume_text)
    part2 = cast(ResumeFactsPart2, part2_llm.invoke(part2_prompt))

    return ResumeFacts(
        personal_info=part1.personal_info,
        summary=part1.summary,
        skills=part1.skills,
        education=part1.education,
        certifications=part1.certifications,
        experience=part2.experience,
        projects=part2.projects,
    )


if __name__ == "__main__":
    try:
        with open("data/base_resume.tex", "r", encoding="utf-8") as f:
            resume_text = f.read()
    except UnicodeDecodeError:
        with open("data/base_resume.tex", "r", encoding="latin-1") as f:
            resume_text = f.read()

    facts = parse_resume(resume_text)

    with open("data/resume_facts.json", "w", encoding="utf-8") as f:
        f.write(facts.model_dump_json(indent=2))

    print("Extraction complete. Review data/resume_facts.json")
    print(f"Extracted {len(facts.experience)} experience entries, "
          f"{len(facts.projects)} projects, "
          f"{sum(len(s.items) for s in facts.skills)} skills.")