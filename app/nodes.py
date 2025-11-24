from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from typing import List, Optional
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import json


with open("llm_config.json") as f:
    LLM_CONFIG = json.load(f)

load_dotenv()


# ---------------- Helper ---------------- #
def get_llm_config(key: str):
    return LLM_CONFIG.get(key, LLM_CONFIG["chat_followup"])

# ---------------- Models ---------------- #
class ExperienceEntry(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    description: Optional[str] = None

class EducationEntry(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None

class ResumeData(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    skills: List[str] = []
    experience: List[ExperienceEntry] = []
    education: List[EducationEntry] = []
    certifications: List[str] = []

class JobDescriptionData(BaseModel):
    title: Optional[str] = None
    skills_required: List[str] = []
    experience_required: Optional[str] = None
    education_required: Optional[str] = None
    responsibilities: List[str] = []

class MatchState(BaseModel):
    resume_text: str
    jd_text: str
    resume_summary: Optional[dict] = None
    jd_summary: Optional[dict] = None
    missing_skills: List[str] = []
    skills_matching: List[str] = []
    bullet_summary: Optional[List[str]] = None
    match_percentage: Optional[float] = None
    reasoning: Optional[str] = None

class ChatState(BaseModel):
    thread_id: str
    question: str
    resume_summary: Optional[dict] = None
    history: List[dict] = []    # list of {sender, message}
    jd_summary: Optional[dict] = None
    answer: Optional[str] = None

# ---------------- LLM Chains ---------------- #

def parse_resume_text(state: MatchState):
    """Parse resume text using GPT"""
    cfg = get_llm_config("resume_parser")
    prompt = PromptTemplate(
        input_variables=["resume_text", "schema"],
        template=(
            "You are an expert resume parser. Extract structured information from this resume:\n\n"
            "{resume_text}\n\n"
        ),
    )

    model = ChatOpenAI(
        model_name=cfg["model"], temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"]
    ).with_structured_output(ResumeData)

    formatted_prompt = prompt.format(resume_text=state.resume_text)
    response = model.invoke(formatted_prompt)
    try:
        data = response.dict()
    except Exception as e:
        data = {
            "name": None,
            "email": None,
            "phone": None,
            "skills": [],
            "experience": [],
            "education": [],
            "certifications": []
        }
    return {"resume_summary": data}


def parse_job_description_text(state: MatchState):
    """Parse job description text using GPT"""
    cfg = get_llm_config("jd_parser")
    prompt = PromptTemplate(
        input_variables=["jd_text", "schema"],
        template=(
            "You are an expert job description parser. Extract structured details from this JD:\n\n"
            "{jd_text}\n\n"
        ),
    )

    model = ChatOpenAI(
        model_name=cfg["model"], temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"]
    ).with_structured_output(JobDescriptionData)
    formatted_prompt = prompt.format(jd_text=state.jd_text)
    response = model.invoke(formatted_prompt)

    try:
        data = response.dict()
    except Exception:
        data = {
            "title": None,
            "skills_required": [],
            "experience_required": None,
            "education_required": None,
            "responsibilities": []
        }

    return {"jd_summary": data}


def get_skill_matching_missing_chain(state: MatchState):
    """Use LLM to identify matched and missing skills (semantic-aware)"""
    cfg = get_llm_config("skill_matcher")
    class ResumeMatchResponse(BaseModel):
        matched_skills: List[str]
        missing_skills: List[str]
    resume_skills = state.resume_summary.get("skills", []) if state.resume_summary else []
    jd_skills = state.jd_summary.get("skills_required", []) if state.jd_summary else []

    prompt = PromptTemplate(
        input_variables=["resume_skills", "jd_skills"],
        template="""
        You are an AI assistant specialized in comparing technical skills.

        Resume skills: {resume_skills}
        Job description skills: {jd_skills}

        Compare them semantically, not just exact words.
        For example:
          - "React" ≈ "React.js"
          - "Node" ≈ "Node.js"
          - "Python" ≈ "Python 3"
          - "Django" ≈ "Django Framework"
        """
    )

    llm = ChatOpenAI(
        model=cfg["model"], temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"]
    ).with_structured_output(ResumeMatchResponse)
    formatted_prompt = prompt.format(resume_skills=resume_skills, jd_skills=jd_skills)
    response = llm.invoke(formatted_prompt)

    try:
        result = response.dict()
    except Exception:
        result = {"matched_skills": [], "missing_skills": []}

    return {
        "skills_matching": result.get("matched_skills", []),
        "missing_skills": result.get("missing_skills", []),
    }


def get_reasoning_chain(state: MatchState):
    cfg = get_llm_config("reasoning_chain")
    class MatchAnalysisResponse(BaseModel):
        bullet_summary: Optional[List[str]] = None
        match_percentage: Optional[float] = None
        reasoning: Optional[str] = None
    """Generate reasoning, bullet points, and match percentage"""
    matched_count = len(state.skills_matching)
    total_count = matched_count + len(state.missing_skills)
    match_percentage = (matched_count / total_count * 100) if total_count > 0 else 0

    prompt = PromptTemplate(
        input_variables=["resume_summary", "jd_summary", "matched_skills", "missing_skills"],
        template=(
            "Based on this resume summary: {resume_summary}\n\n"
            "And this job description: {jd_summary}\n\n"
            "Matched skills: {matched_skills}\n"
            "Missing skills: {missing_skills}\n\n"
        ),
    )

    model = ChatOpenAI(
        model=cfg["model"], temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"]
    ).with_structured_output(MatchAnalysisResponse)
    formatted_prompt = prompt.format(
        resume_summary=state.resume_summary or {},
        jd_summary=state.jd_summary or {},
        matched_skills=state.skills_matching,
        missing_skills=state.missing_skills,
    )

    response = model.invoke(formatted_prompt)

    try:
        result = response.dict()
    except Exception:
        result = {
            "reasoning": f"Candidate matches {match_percentage:.1f}% of skills.",
            "bullet_summary": [
                "Good alignment with core technical skills.",
                "Needs improvement in missing areas.",
                "Overall fair fit."
            ],
            "match_percentage": match_percentage
        }

    return result

def answer_node(state: ChatState):
    cfg = get_llm_config("chat_followup")
    model = ChatOpenAI(
        model=cfg["model"], temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"]
    )
    ctx = (
        f"Resume Summary: {state.resume_summary}\n"
        f"JD Summary: {state.jd_summary}\n\n"
        f"User Question: {state.question}\n"
        "Answer precisely using only the above context."
    )
    resp = model.invoke(ctx)
    return {"answer": resp.content}
