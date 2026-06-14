import json
import logging

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)


def _get_deepseek_client():
    if not DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY not configured")
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    except ImportError:
        logger.error("openai package not installed")
        return None


def _call_deepseek(prompt, temp=0.3):
    client = _get_deepseek_client()
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=temp,
            max_tokens=2048,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error("DeepSeek API call failed: %s", e)
        return None


def _extract_pdf_text(filepath):
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(filepath)
    except ImportError:
        logger.error("PyPDF2 not installed")
        return []
    except Exception as e:
        logger.error("Failed to open PDF: %s", e)
        return []

    lines = []
    for page in reader.pages:
        try:
            t = page.extract_text()
        except Exception:
            continue
        if t:
            for line in t.split("\n"):
                s = line.strip()
                if s and len(s) > 2:
                    lines.append(s)
    return lines


def _empty_result(error=""):
    return {
        "skills": [],
        "error": error,
        "role": "",
        "experience_level": "mid",
        "meta": {"name": "", "email": "", "phone": "", "social_media": [], "location": ""},
        "work_experience": [],
        "education": [],
        "leadership": [],
        "projects": [],
        "personality_traits": [],
    }


def extract_cv(filepath):
    lines = _extract_pdf_text(filepath)
    full_text = "\n".join(lines)

    if not full_text.strip():
        return _empty_result("Could not extract text from PDF. The file may be scanned/image-based or empty.")

    result = _call_deepseek(f"""Extract structured data from this CV/resume as JSON only.
Use null for missing fields, empty arrays for lists with no items.

Schema:
{{
  "meta": {{
    "name": "Full name",
    "email": "email address",
    "phone": "phone number",
    "social_media": ["LinkedIn URL", "GitHub URL", ...],
    "location": "City, Country"
  }},
  "skills": ["skill1", "skill2", ...],
  "experience_level": "entry|mid|senior|lead",
  "years_experience": number,
  "top_skills": ["top 5 most relevant"],
  "role": "current or most recent job title",
  "industry": "industry name",
  "work_experience": [
    {{
      "organisation": "Company name",
      "role": "Job title",
      "achievements": "Key accomplishments",
      "skills_obtained": ["skill1", "skill2"],
      "location": "City, Country",
      "duration": "Start - End"
    }}
  ],
  "education": [
    {{
      "institution": "School/University name",
      "course": "Degree / course name",
      "results": "Grades / GPA / classification",
      "subjects": ["subject1", "subject2"],
      "activities": ["club", "sport", "volunteer", ...],
      "location": "City, Country",
      "duration": "Start - End"
    }}
  ],
  "leadership": [
    {{
      "place": "Organization / event name",
      "role": "Position held",
      "notes": "What was done",
      "duration": "Start - End"
    }}
  ],
  "projects": [
    {{
      "certifications": ["cert name"],
      "project_name": "Project title",
      "project_type": "personal|academic|professional|open_source",
      "notes": "Description",
      "duration": "Start - End",
      "proof_link": "URL or reference ID"
    }}
  ],
  "personality_traits": ["trait1", "trait2"]
}}

CV:
{full_text[:8000]}""")

    if result and isinstance(result, dict):
        return result

    return _empty_result("AI extraction unavailable. Set DEEPSEEK_API_KEY in .env.")


def process_text_entry(text):
    if not text.strip():
        return {"section_type": "projects", "entry": {}, "skills_extracted": []}

    result = _call_deepseek(f"""Classify this text and extract structured data as JSON only.

Rules:
- Classify into exactly one section: "work_experience", "education", "leadership", or "projects"
- "projects" is the default if unclear (includes certifications, open source, side projects)
- Extract fields matching the section type
- Also extract any skill keywords mentioned

Output schema:
{{
  "section_type": "work_experience|education|leadership|projects",
  "entry": {{
    "organisation": "",
    "role": "",
    "achievements": "",
    "skills_obtained": [],
    "location": "",
    "duration": ""
  }},
  "skills_extracted": ["skill1", "skill2"]
}}

Text: {text[:4000]}""")

    if result and isinstance(result, dict) and "section_type" in result:
        return result

    return {"section_type": "projects", "entry": {"notes": text[:500]}, "skills_extracted": []}


def validate_cv_proof(entry_text, proof_text):
    if not proof_text.strip():
        return None
    try:
        result = _call_deepseek(
            "You are a CV entry validator for CareerOS.\n\n"
            "A user submitted this CV entry and proof. Determine if the proof credibly supports the claim.\n"
            "- Pass: proof is specific and credible (link, cert name, real detail)\n"
            "- Fail: proof is vague, irrelevant, or absent of real evidence\n\n"
            f"CV Entry: {entry_text[:1500]}\n"
            f"Proof: {proof_text[:1500]}\n\n"
            'Return JSON only: {"pass": true/false, "reason": "brief explanation"}'
        )
        if result and isinstance(result, dict) and "pass" in result:
            return result
    except Exception:
        logger.exception("validate_cv_proof failed")
    return None


def generate_tasks(cv_data):
    skills = cv_data.get("skills", [])
    if not skills:
        return []

    result = _call_deepseek(f"""You are a career coach for CareerOS.

Generate 3-5 career development tasks for this professional profile.
Each task must be specific, actionable, and help advance their career.

Profile:
{json.dumps({
    "role": cv_data.get("role", ""),
    "experience_level": cv_data.get("experience_level", "mid"),
    "skills": skills,
    "top_skills": cv_data.get("top_skills", []),
    "industry": cv_data.get("industry", ""),
    "has_work_experience": len(cv_data.get("work_experience", [])) > 0,
    "has_education": len(cv_data.get("education", [])) > 0,
    "has_projects": len(cv_data.get("projects", [])) > 0,
    "has_leadership": len(cv_data.get("leadership", [])) > 0,
}, indent=2)}

Output JSON:
{{
  "tasks": [
    {{
      "id": "t_0",
      "category": "skill_gap|profile_completion|career_advancement|certification|networking",
      "priority": "high|medium|low",
      "title": "Short task title (max 60 chars)",
      "description": "Detailed actionable description (max 300 chars)"
    }}
  ]
}}

Rules:
- Each id unique: t_0, t_1, t_2...
- Max 5 tasks
- Prioritize filling gaps in the profile
- Focus on concrete actions: learn a skill, earn a certification, build a project, network, add missing profile sections""")

    if result and isinstance(result, dict) and "tasks" in result:
        tasks = []
        for i, t in enumerate(result["tasks"][:5]):
            cat = t.get("category", "career_advancement")
            if cat not in ("skill_gap", "profile_completion", "career_advancement", "certification", "networking"):
                cat = "career_advancement"
            prio = t.get("priority", "medium")
            if prio not in ("high", "medium", "low"):
                prio = "medium"
            tasks.append({
                "id": t.get("id", f"t_{i}"),
                "category": cat,
                "priority": prio,
                "title": (t.get("title") or f"Task {i}")[:60],
                "description": (t.get("description") or "")[:300],
                "status": "active",
            })
        return tasks

    return []


def process_task_completion(task, proof_text):
    if not proof_text.strip():
        return None

    result = _call_deepseek(f"""You are a career coach for CareerOS.

Validate and extract achievements from a task completion proof.

Task: {task.get('title', 'Unknown')}
Category: {task.get('category', 'career_advancement')}
Description: {task.get('description', '')}

Proof submitted: {proof_text[:2000]}

Return JSON:
{{
  "valid": true/false,
  "reason": "brief explanation of validation result",
  "skills_found": ["skill1", "skill2"],
  "section_type": "projects|work_experience|education|leadership",
  "entry": {{
    "project_name": "",
    "certifications": [],
    "notes": "",
    "organisation": "",
    "role": "",
    "achievements": "",
    "skills_obtained": [],
    "institution": "",
    "course": "",
    "results": "",
    "place": "",
    "location": "",
    "duration": ""
  }}
}}

Rules:
- valid: true if proof is credible and specific (link, cert name, real detail)
- valid: false if proof is vague, irrelevant, or no real evidence
- section_type: where this achievement belongs in a CV
- skills_found: any new skills demonstrated by this proof
- Populate only the fields relevant to the section_type""")

    if result and isinstance(result, dict) and "valid" in result:
        return result
    return None


def analyze_candidate_fit(candidate_cv, job_data):
    result = _call_deepseek(f"""You are an AI hiring advisor for CareerOS.

Analyze how well this candidate fits the job requirements.

Candidate Profile:
{json.dumps({
    "role": candidate_cv.get("role", ""),
    "experience_level": candidate_cv.get("experience_level", "mid"),
    "skills": candidate_cv.get("skills", []),
    "top_skills": candidate_cv.get("top_skills", []),
    "industry": candidate_cv.get("industry", ""),
    "years_experience": candidate_cv.get("years_experience"),
    "work_experience": candidate_cv.get("work_experience", []),
    "education": candidate_cv.get("education", []),
    "projects": candidate_cv.get("projects", []),
}, indent=2)}

Job Requirements:
{json.dumps({
    "title": job_data.get("title", ""),
    "description": job_data.get("description", ""),
    "skills_required": job_data.get("skills_required", []),
    "location": job_data.get("location", ""),
    "salary_range": job_data.get("salary_range", ""),
}, indent=2)}

Return JSON:
{{
  "match_score": 0-100,
  "summary": "1-2 sentence assessment of overall fit",
  "skill_gaps": ["missing skill 1", "missing skill 2"],
  "trajectory_assessment": "brief assessment of career trajectory fit",
  "recommendation": "shortlist|consider|pass",
  "risk_factors": ["potential concern 1", "potential concern 2"]
}}""")

    if result and isinstance(result, dict) and "match_score" in result:
        return result
    return {
        "match_score": 0,
        "summary": "AI analysis unavailable.",
        "skill_gaps": [],
        "trajectory_assessment": "",
        "recommendation": "consider",
        "risk_factors": [],
    }
