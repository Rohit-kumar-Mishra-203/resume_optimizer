from app.core.schema import JDRequirements
from app.core.groq_client import invoke_structured

EXTRACTION_PROMPT = """You are extracting structured requirements from a job description.

Respond with ONLY a valid JSON object matching the required structure. Do not
include any explanation, markdown formatting, or text outside the JSON.

Your output MUST match this exact JSON schema - use these EXACT field names,
nothing else:

{schema}

Rules:
1. Separate "must_have_skills" from "nice_to_have_skills" - do not mix these.
2. "tools_and_tech" should list only concrete named technologies.
3. "responsibilities" should be short phrases, not copied verbatim sentences.
4. Infer "seniority_level" only if there's a clear signal. If unclear, null.
5. Do not add skills or requirements that aren't stated or clearly implied.
6. "raw_text" can be left as an empty string - filled in automatically after.

Job description:
---
{jd_text}
---
"""


def parse_jd(jd_text: str) -> JDRequirements:
    import json
    schema_json = json.dumps(JDRequirements.model_json_schema(), indent=2)
    prompt = EXTRACTION_PROMPT.format(schema=schema_json, jd_text=jd_text)
    result = invoke_structured(JDRequirements, prompt)
    result.raw_text = jd_text
    return result


if __name__ == "__main__":
    sample_jd = """
    We are hiring a Machine Learning Engineer to join our NLP team.
    Requirements: 2+ years experience with Python and PyTorch, strong
    understanding of Transformer architectures, experience with LLM
    fine-tuning. Familiarity with LangChain/LangGraph and RAG systems
    is a plus. You will build and deploy production NLP pipelines,
    collaborate with the product team, and optimize model performance.
    """
    result = parse_jd(sample_jd)
    print(result.model_dump_json(indent=2))