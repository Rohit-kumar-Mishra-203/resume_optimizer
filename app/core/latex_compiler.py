import subprocess
import re
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader
from app.core.schema import ResumeFacts

TEMPLATE_DIR = Path("data")
TEMPLATE_NAME = "template.tex.jinja"
BUILD_DIR = Path("data/generated")

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    block_start_string="((*",
    block_end_string="*))",
    variable_start_string="(((",
    variable_end_string=")))",
    comment_start_string="((=",
    comment_end_string="=))",
    trim_blocks=True,
    autoescape=False,
)


def escape_latex(text: str) -> str:
    if not text:
        return ""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
        ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _extract_slug(value: str) -> str:
    if not value:
        return ""
    if "://" in value or value.startswith("www."):
        path = urlparse(value if "://" in value else f"//{value}").path
        segments = [s for s in path.split("/") if s]
        return segments[-1] if segments else value
    return value


def _slug_label(name: str) -> str:
    return name.upper().replace(" ", "-")


def build_render_context(facts: ResumeFacts) -> dict:
    p = facts.personal_info
    linkedin_slug = _extract_slug(p.linkedin or "")
    github_slug = _extract_slug(p.github or "")
    phone_tel = re.sub(r"[^\d+]", "", p.phone or "")

    return {
        "personal_info": {
            "name": escape_latex(p.name),
            "phone": escape_latex(p.phone or ""),
            "phone_tel": phone_tel,
            "email": p.email or "",
            "linkedin_url": f"https://www.linkedin.com/in/{linkedin_slug}" if linkedin_slug else "",
            "linkedin_label": escape_latex(linkedin_slug),
            "github_url": f"https://github.com/{github_slug}" if github_slug else "",
            "github_label": escape_latex(github_slug),
        },
        "summary": escape_latex(facts.summary or ""),
        "experience": [
            {
                "company": escape_latex(exp.company),
                "role": escape_latex(exp.role),
                "start_date": escape_latex(exp.start_date),
                "end_date": escape_latex(exp.end_date or "Present"),
                "location": escape_latex(exp.location or ""),
                "bullets": [{"text": escape_latex(b.text)} for b in exp.bullets],
            }
            for exp in facts.experience
        ],
        "education": [
            {
                "institution": escape_latex(edu.institution),
                "degree": escape_latex(edu.degree),
                "start_date": escape_latex(edu.start_date),
                "end_date": escape_latex(edu.end_date),
            }
            for edu in facts.education
        ],
        "skills": [
            {"category": escape_latex(cat.category), "items_joined": escape_latex(", ".join(cat.items))}
            for cat in facts.skills
        ],
        "projects": [
            {
                "name": escape_latex(proj.name),
                "tech_stack_joined": escape_latex(", ".join(proj.tech_stack)),
                "link": proj.link or "",
                "link_label": escape_latex(proj.link) if proj.link else _slug_label(proj.name),
                "bullets": [{"text": escape_latex(b.text)} for b in proj.bullets],
            }
            for proj in facts.projects
        ],
        "certifications": [
            {
                "name": escape_latex(cert.name),
                "issuer": escape_latex(cert.issuer),
                "date": escape_latex(cert.date or ""),
                "instructor_line": escape_latex(f"Instructor: {cert.instructor}") if cert.instructor else "",
            }
            for cert in facts.certifications
        ],
    }


def render_latex(facts: ResumeFacts) -> str:
    template = jinja_env.get_template(TEMPLATE_NAME)
    return template.render(**build_render_context(facts))


def compile_to_pdf(tex_source: str, output_filename: str = "resume") -> Path:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = BUILD_DIR / f"{output_filename}.tex"
    pdf_path = BUILD_DIR / f"{output_filename}.pdf"
    tex_path.write_text(tex_source, encoding="utf-8")

    result = subprocess.run(
        ["tectonic", str(tex_path), "--outdir", str(BUILD_DIR)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tectonic failed to compile {tex_path}:\n{result.stdout}\n{result.stderr}")

    return pdf_path