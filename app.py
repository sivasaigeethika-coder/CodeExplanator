import os
import requests
import base64
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sarvamai import SarvamAI
import time
from datetime import datetime

app = FastAPI(title="Next-Gen Code Explainer")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sarvam AI setup
SARVAM_KEY = os.getenv("SARVAM_API_KEY", "sk_n57hfs7t_e5CqgICSvwUxlwW3ZicAgCnx")
try:
    ai_client = SarvamAI(api_subscription_key=SARVAM_KEY)
except Exception as e:
    ai_client = None
    print(f"⚠️ Sarvam AI Client initialization warning: {e}")

# ---------------- MODELS ----------------
class CodeRequest(BaseModel):
    language: str
    explanation_language: str
    level: str
    code: str
    cross: str
    visualization: str

class FeedbackRequest(BaseModel):
    code: str
    feedback: str
    customStyle: str | None = None

# ---------------- ROUTES ----------------
@app.get("/")
def home():
    # Corrected pathing: points to the same directory as this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "demo.html")
    return FileResponse(html_path)

@app.get("/favicon.ico")
async def favicon():
    # Corrected pathing: points to the same directory as this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    favicon_path = os.path.join(current_dir, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return {"status": "no favicon"}

# ---------------- JUDGE0 CONFIG ----------------
LANGUAGE_IDS = {"python": 71, "c": 50, "cpp": 54, "java": 62, "javascript": 63}

def compile_code(code, language):
    lid = LANGUAGE_IDS.get(language)
    if not lid:
        return {"error": "Language not supported"}
    url = "https://ce.judge0.com/submissions?base64_encoded=true&wait=true"
    payload = {"language_id": lid, "source_code": base64.b64encode(code.encode()).decode()}
    return requests.post(url, json=payload).json()

def extract_error(result):
    if result.get("compile_output"):
        return base64.b64decode(result["compile_output"]).decode()
    if result.get("stderr"):
        return base64.b64decode(result["stderr"]).decode()
    return None

def decode_stdout(result):
    if result.get("stdout"):
        return base64.b64decode(result["stdout"]).decode()
    return ""

# ---------------- SARVAM AI HELPER ----------------
def ask_sarvam(prompt: str) -> str:
    if not ai_client or not SARVAM_KEY:
        return "AI Error: Please configure your environment with a valid SARVAM_API_KEY."
    try:
        response = ai_client.chat.completions(
            model="sarvam-30b",
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort=None
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Failed to generate Sarvam AI response: {str(e)}"

# ---------------- EXPLAIN ENDPOINT ----------------
@app.post("/explain")
def explain(request: CodeRequest):
    start_time = time.time()
    result = compile_code(request.code, request.language.lower())
    error = extract_error(result)

    lang_instruction = f"\n\nCRITICAL: Provide the entire response output strictly in the {request.explanation_language} language."

    now = datetime.now()
    day_name = now.strftime("%A")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    if error:
        correction_prompt = (
            f"The following code has errors:\n{request.code}\n\nError: {error}\n"
            "Identify the exact line(s) with errors, correct them, and provide ONE corrected version. "
            "Explain each correction briefly line by line."
        )
        correction_prompt += lang_instruction
        corrected = ask_sarvam(correction_prompt)
        end_time = time.time()
        return {
            "status": "error",
            "message": error,
            "corrected_code": corrected,
            "execution_seconds": round(end_time - start_time, 2),
            "day": day_name, "date": date_str, "time": time_str
        }

    program_output = decode_stdout(result)
    level = request.level.lower()

    if level == "beginner":
        explanation_prompt = f"Explain this {request.language} code line by line for a beginner with some theory and syntax:\n{request.code}"
    elif level == "intermediate":
        explanation_prompt = f"Explain this {request.language} code line by line for an intermediate level programmer:\n{request.code}"
    elif level == "advanced":
        explanation_prompt = (
            f"Explain this {request.language} code by logic for an advanced programmer. Focus on its logic explaination rather than syntax"
            f"Include analysis of efficiency and time complexity:\n{request.code}"
        )
    else:
        explanation_prompt = f"Explain this {request.language} code clearly:\n{request.code}"

    explanation_prompt += lang_instruction
    ai_explanation = ask_sarvam(explanation_prompt)

    vis_choice = request.visualization.lower()
    if vis_choice == "flowchart":
        vis_prompt = (
            f"Generate one well formatted flowchart that shows the flow of this code:\n{request.code}\n\n"
            f"Represent this strictly as a step-by-step algorithmic flowchart mapping out data flow, conditions, and loops."
        )
        vis_prompt += lang_instruction
        ai_visualization = ask_sarvam(vis_prompt)
    elif vis_choice == "analogy":
        vis_prompt = f"Give one short real-world analogy for this {request.language} code:\n{request.code}"
        vis_prompt += lang_instruction
        ai_visualization = ask_sarvam(vis_prompt)
    else:
        ai_visualization = "None requested."

    if request.cross.lower() == "yes":
        cross_prompt = f"Explain how this logic looks in Java, Python, C, and C++:\n{request.code}"
        cross_prompt += lang_instruction
        cross_text = ask_sarvam(cross_prompt)
        ai_explanation += f"\n\n--- Cross-Language Insights ---\n{cross_text}"

    end_time = time.time()
    return {
        "status": "success",
        "program_output": program_output,
        "explanation": ai_explanation,
        "visualization_text": ai_visualization,
        "execution_seconds": round(end_time - start_time, 2),
        "day": day_name, "date": date_str, "time": time_str
    }

# ---------------- FEEDBACK ENDPOINT ----------------
FEEDBACK_STORE = {}

@app.post("/feedback")
def feedback(request: FeedbackRequest):
    previous_feedback = FEEDBACK_STORE.get(request.code, "")
    FEEDBACK_STORE[request.code] = previous_feedback + "\n" + request.feedback
    
    feedback_prompt = (
        f"Here is the code:\n{request.code}\n\n"
        f"User feedback history:\n{FEEDBACK_STORE[request.code]}\n\n"
        f"Custom explanation request: {request.customStyle}\n\n"
        f"Please refine the explanation again based on all feedback above."
    )
    refined_explanation = ask_sarvam(feedback_prompt)
    
    now = datetime.now()
    return {
        "status": "success",
        "refined_explanation": refined_explanation,
        "day": now.strftime("%A"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S")
    }

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
