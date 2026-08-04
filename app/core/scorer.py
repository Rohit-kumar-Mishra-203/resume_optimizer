from typing import List, Tuple, Dict, Optional
from app.core.schema import ResumeFacts, JDRequirements
from app.core.embeddings import embed_text, embed_batch
from sentence_transformers.util import cos_sim
import numpy as np

SEMANTIC_MATCH_CEILING = 0.55
KEYWORD_FALLBACK_THRESHOLD = 0.35

KEYWORD_WEIGHT = 0.40
SEMANTIC_WEIGHT = 0.40
STRUCTURAL_WEIGHT = 0.20

MUST_HAVE_WEIGHT = 0.70
NICE_TO_HAVE_WEIGHT = 0.30


def _flatten_resume_text(facts: ResumeFacts) -> List[str]:
    chunks = []
    for skill_cat in facts.skills:
        chunks.extend(skill_cat.items)
    for exp in facts.experience:
        chunks.extend(b.text for b in exp.bullets)
    for proj in facts.projects:
        chunks.extend(b.text for b in proj.bullets)
    return chunks


def _flatten_bullets_only(facts: ResumeFacts) -> List[Tuple[str, str]]:
    chunks = []
    for exp in facts.experience:
        chunks.extend((b.id, b.text) for b in exp.bullets)
    for proj in facts.projects:
        chunks.extend((b.id, b.text) for b in proj.bullets)
    return chunks


def _keyword_covered(skill: str, resume_chunks: List[str], resume_embeddings: np.ndarray) -> bool:
    skill_lower = skill.lower()
    for chunk in resume_chunks:
        if skill_lower in chunk.lower():
            return True
    skill_emb = embed_text(skill)
    sims = cos_sim(skill_emb, resume_embeddings)[0]
    return float(sims.max()) >= KEYWORD_FALLBACK_THRESHOLD


def _keyword_coverage_score(jd: JDRequirements, facts: ResumeFacts) -> Tuple[float, Dict]:
    resume_chunks = _flatten_resume_text(facts)
    resume_embeddings = embed_batch(resume_chunks)

    must_have_matched = [s for s in jd.must_have_skills if _keyword_covered(s, resume_chunks, resume_embeddings)]
    must_have_missing = [s for s in jd.must_have_skills if s not in must_have_matched]

    nice_to_have_matched = [s for s in jd.nice_to_have_skills if _keyword_covered(s, resume_chunks, resume_embeddings)]
    nice_to_have_missing = [s for s in jd.nice_to_have_skills if s not in nice_to_have_matched]

    must_have_score = (len(must_have_matched) / len(jd.must_have_skills)) if jd.must_have_skills else 1.0
    nice_to_have_score = (len(nice_to_have_matched) / len(jd.nice_to_have_skills)) if jd.nice_to_have_skills else 1.0

    combined = (must_have_score * MUST_HAVE_WEIGHT) + (nice_to_have_score * NICE_TO_HAVE_WEIGHT)

    details = {
        "must_have_matched": must_have_matched,
        "must_have_missing": must_have_missing,
        "nice_to_have_matched": nice_to_have_matched,
        "nice_to_have_missing": nice_to_have_missing,
    }
    return combined, details


def _semantic_similarity_score(jd: JDRequirements, facts: ResumeFacts) -> Tuple[float, Dict]:
    resume_bullets = _flatten_bullets_only(facts)
    if not resume_bullets or not jd.responsibilities:
        return 0.0, {"per_responsibility": []}

    bullet_ids = [b[0] for b in resume_bullets]
    bullet_texts = [b[1] for b in resume_bullets]
    resume_embeddings = embed_batch(bullet_texts)

    per_responsibility = []
    raw_scores = []
    for resp in jd.responsibilities:
        resp_emb = embed_text(resp)
        sims = cos_sim(resp_emb, resume_embeddings)[0]
        best_idx = int(sims.argmax())
        best_score = float(sims[best_idx])
        raw_scores.append(best_score)
        per_responsibility.append({
            "responsibility": resp,
            "best_matching_bullet_id": bullet_ids[best_idx],
            "best_matching_bullet_text": bullet_texts[best_idx],
            "raw_similarity": round(best_score, 3),
        })

    rescaled = [min(s / SEMANTIC_MATCH_CEILING, 1.0) for s in raw_scores]
    avg_score = sum(rescaled) / len(rescaled)

    return avg_score, {"per_responsibility": per_responsibility}


def _structural_score(template_checklist: Optional[Dict[str, bool]] = None) -> Tuple[float, Dict]:
    if template_checklist is None:
        template_checklist = {
            "standard_section_headers": True,
            "no_tables_or_columns": True,
            "no_images_or_graphics": True,
            "parseable_fonts": True,
        }
    passed = sum(1 for v in template_checklist.values() if v)
    total = len(template_checklist)
    score = passed / total if total else 1.0
    return score, {"checklist": template_checklist}


def score_resume(jd: JDRequirements, facts: ResumeFacts) -> Dict:
    keyword_score, keyword_details = _keyword_coverage_score(jd, facts)
    semantic_score, semantic_details = _semantic_similarity_score(jd, facts)
    structural_score, structural_details = _structural_score()

    overall = (
        keyword_score * KEYWORD_WEIGHT
        + semantic_score * SEMANTIC_WEIGHT
        + structural_score * STRUCTURAL_WEIGHT
    ) * 100

    return {
        "overall_score": round(overall, 1),
        "keyword_score": round(keyword_score * 100, 1),
        "semantic_score": round(semantic_score * 100, 1),
        "structural_score": round(structural_score * 100, 1),
        "keyword_details": keyword_details,
        "semantic_details": semantic_details,
        "structural_details": structural_details,
    }