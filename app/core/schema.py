from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class PersonalInfo(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    location: Optional[str] = None


class SkillCategory(BaseModel):
    category: str
    items: List[str]


class ExperienceBullet(BaseModel):
    id: str
    text: str
    keywords: List[str] = []


class Experience(BaseModel):
    id: str
    company: str
    role: str
    start_date: str
    end_date: Optional[str] = None
    location: Optional[str] = None
    bullets: List[ExperienceBullet]


class Project(BaseModel):
    id: str
    name: str
    tech_stack: List[str]
    bullets: List[ExperienceBullet]
    link: Optional[str] = None


class Education(BaseModel):
    degree: str
    institution: str
    start_date: str
    end_date: str
    coursework: List[str] = []
    gpa: Optional[str] = None


class Certification(BaseModel):
    name: str
    issuer: str
    date: Optional[str] = None
    instructor: Optional[str] = None


class JDRequirements(BaseModel):
    job_title: str
    company: Optional[str] = None
    seniority_level: Optional[str] = None
    must_have_skills: List[str]
    nice_to_have_skills: List[str] = []
    responsibilities: List[str]
    tools_and_tech: List[str]
    raw_text: str


class CritiqueItem(BaseModel):
    gap_type: Literal["missing_keyword", "weak_semantic_match", "phrasing"]
    description: str
    target_bullet_id: Optional[str] = None
    suggestion: str
    is_genuine_gap: bool


class ResumeCritique(BaseModel):
    items: List[CritiqueItem]
    overall_assessment: str


class BulletRevision(BaseModel):
    bullet_id: str
    revised_text: str
    justification: str


class EditorOutput(BaseModel):
    revisions: List[BulletRevision]


class ResumeFactsPart1(BaseModel):
    personal_info: PersonalInfo
    summary: Optional[str] = None
    skills: List[SkillCategory]
    education: List[Education]
    certifications: List[Certification] = []


class ResumeFactsPart2(BaseModel):
    experience: List[Experience]
    projects: List[Project]


class ResumeFacts(BaseModel):
    """
    The single source of truth for everything downstream.
    Every generated/tailored resume must trace its content back to this object.
    Nothing here is ever invented by the LLM during tailoring - only
    selected, reordered, or rephrased.
    """
    personal_info: PersonalInfo
    summary: Optional[str] = None
    skills: List[SkillCategory]
    experience: List[Experience]
    projects: List[Project]
    education: List[Education]
    certifications: List[Certification] = []