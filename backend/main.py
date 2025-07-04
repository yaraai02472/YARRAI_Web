# backend/main.py
from dotenv import load_dotenv
import os, uuid, json

# .env 로드 (프로젝트 루트의 .env)
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai
from services.analysis import analyze_file

# OpenAI 키 설정
openai.api_key = os.getenv("OPENAI_API_KEY")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
META_DIR   = os.path.join(BASE_DIR, "meta_json")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)

app = FastAPI(title="YARAAI Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # 프론트 dev 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptRequest(BaseModel):
    prompt: str

@app.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...)):
    # 지원 확장자 확인
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("exe", "dll"):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # 고유 이름으로 저장
    unique_name = f"{uuid.uuid4()}.{ext}"
    dest_path   = os.path.join(UPLOAD_DIR, unique_name)
    data = await file.read()
    with open(dest_path, "wb") as f:
        f.write(data)

    # 분석 수행
    try:
        report = analyze_file(dest_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    # JSON 메타 저장
    base      = os.path.splitext(unique_name)[0]
    meta_path = os.path.join(META_DIR, f"{base}.json")
    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(report, mf, ensure_ascii=False, indent=2)

    return {"filename": unique_name}

@app.get("/reports")
def list_reports():
    files = [
        f for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    ]
    return {"reports": files}

@app.get("/reports/{filename}")
def get_report(filename: str):
    base      = os.path.splitext(filename)[0]
    meta_path = os.path.join(META_DIR, f"{base}.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail="Report not found")

    with open(meta_path, "r", encoding="utf-8") as mf:
        return json.load(mf)

# ──────────────────────────────────────────────────────────────────────────────
# 여기에 AI 리포트용 엔드포인트 추가
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/report/section/{section_id}")
async def report_section(
    section_id: int = Path(..., ge=1, le=9),
    body: PromptRequest = None
):
    if not body or not body.prompt:
        raise HTTPException(status_code=400, detail="`prompt` is required in body")
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",    # 원하는 모델로 변경
            messages=[{"role": "user", "content": body.prompt}],
            max_tokens=1024,
            temperature=0.7,
        )
        text = resp.choices[0].message.content.strip()
        return {"text": text}
    except Exception as e:
        print("OpenAI API error:", e)
        raise HTTPException(status_code=500, detail="OpenAI API error")
