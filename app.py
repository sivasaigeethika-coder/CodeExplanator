import os
import requests
import base64
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
# Ensure you have 'pip install sarvam-ai' in your requirements.txt
from sarvamai import SarvamAI
import time
from datetime import datetime

app = FastAPI(title="Next-Gen Code Explainer")

# Enable CORS - Crucial for web communication
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
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, "demo.html")
    return FileResponse(html_path)

@app.get("/favicon.ico")
async def favicon():
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
            messages=[{"role": "user", "content": prompt}]
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
    if error:
        correction_prompt = f"The following code has errors:\n{request.code}\n\nError: {error}\nCorrect it and explain line by line." + lang_instruction
        corrected = ask_sarvam(correction_prompt)
        return {"status": "error", "message": error, "corrected_code": corrected}

    program_output = decode_stdout(result)
    
    # Prompting logic
    explanation_prompt = f"Explain this {request.language} code ({request.level} level):\n{request.code}" + lang_instruction
    ai_explanation = ask_sarvam(explanation_prompt)

    # Visualization
    ai_visualization = ask_sarvam(f"Generate an analogy or flowchart for this code:\n{request.code}" + lang_instruction) if request.visualization != "none" else "None"

    return {
        "status": "success",
        "program_output": program_output,
        "explanation": ai_explanation,
        "visualization_text": ai_visualization,
        "execution_seconds": round(time.time() - start_time, 2)
    }

# ---------------- FEEDBACK ENDPOINT ----------------
@app.post("/feedback")
def feedback(request: FeedbackRequest):
    feedback_prompt = f"Refine the explanation for this code:\n{request.code}\n\nFeedback: {request.feedback}"
    refined = ask_sarvam(feedback_prompt)
    return {"status": "success", "refined_explanation": refined}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
