from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
import os
import uvicorn
import pandas as pd
from sqlalchemy.orm import Session

from model import SalaryValidationModel
from utils import CurrencyConverter, IPSpamTracker, calculate_trust_score
from database import get_db, init_db, SalarySubmissionDB


# =========================
# APP INIT
# =========================
app = FastAPI(
    title="AI-Powered Salary Validation API",
    description="Production-ready validation engine",
    version="1.0.0"
)


# =========================
# CORS (FIXED FOR VERCEL + RENDER)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# GLOBALS
# =========================
model_engine = SalaryValidationModel()
ip_tracker = IPSpamTracker(window_seconds=120, max_submissions=3)
DATA_PATH = "sample_data.csv"


# =========================
# STARTUP
# =========================
@app.on_event("startup")
def startup_event():
    print("Initializing DB...")
    init_db()

    print("Loading model...")
    success = model_engine.load()

    if not success:
        print("Training model from scratch...")
        if os.path.exists(DATA_PATH):
            model_engine.train(DATA_PATH)


# =========================
# SCHEMAS
# =========================
class SalarySubmission(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = None
    jobFamily: Optional[str] = None
    location: Optional[str] = None
    yearsOfExperience: float = 0.0
    offerDate: Optional[str] = None
    totalCompensation: float
    currency: str = "INR"
    level: Optional[str] = None
    baseSalary: Optional[float] = None
    avgAnnualStockGrantValue: Optional[float] = None
    avgAnnualBonusValue: Optional[float] = None
    ipAddress: Optional[str] = "127.0.0.1"

    @model_validator(mode="after")
    def fix_role(self):
        if not self.role:
            self.role = self.title or self.jobFamily
        if not self.role:
            raise ValueError("role/title/jobFamily required")
        return self


class PredictedRange(BaseModel):
    min: float
    avg: float
    max: float


class ValidationResponse(BaseModel):
    predicted_range: PredictedRange
    submitted_salary: float
    deviation_percent: float
    anomaly: bool
    ip_flag: bool
    trust_score: float
    status: str
    reasons: List[str]


# =========================
# HEALTH
# =========================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_trained": model_engine.is_trained
    }


# =========================
# TRAIN
# =========================
@app.post("/train")
def train(background_tasks: BackgroundTasks):
    def task():
        model_engine.train(DATA_PATH)

    background_tasks.add_task(task)
    return {"status": "training_started"}


# =========================
# VALIDATE (MAIN API)
# =========================
@app.post("/validate-submission", response_model=ValidationResponse)
def validate(submission: SalarySubmission, db: Session = Depends(get_db)):

    if not model_engine.is_trained:
        raise HTTPException(status_code=503, detail="Model not trained")

    from utils import normalize_payload

    payload = submission.model_dump()
    norm = normalize_payload(payload)

    salary = norm["totalCompensationINR"]
    ip = norm["ipAddress"]

    ip_flag = ip_tracker.check_spam_and_record(ip)

    predicted_range, is_anomaly, _ = model_engine.predict(payload)

    avg = predicted_range["avg"]
    deviation = ((salary - avg) / avg) * 100 if avg else 0

    trust_score, status_result, reasons = calculate_trust_score(
        submitted_salary=salary,
        predicted_min=predicted_range["min"],
        predicted_avg=predicted_range["avg"],
        predicted_max=predicted_range["max"],
        is_anomaly=is_anomaly,
        ip_flag=ip_flag,
        base_salary_inr=norm["baseSalaryINR"],
        stock_inr=norm["stockINR"],
        bonus_inr=norm["bonusINR"]
    )

    return ValidationResponse(
        predicted_range=PredictedRange(**predicted_range),
        submitted_salary=salary,
        deviation_percent=round(deviation, 2),
        anomaly=is_anomaly,
        ip_flag=ip_flag,
        trust_score=trust_score,
        status=status_result,
        reasons=reasons
    )


# =========================
# MODEL INSIGHTS
# =========================
@app.get("/model-insights")
def insights(db: Session = Depends(get_db)):

    db_count = db.query(SalarySubmissionDB).count() if db else 0
    csv_count = len(pd.read_csv(DATA_PATH)) if os.path.exists(DATA_PATH) else 0

    return {
        "total_training_records": db_count + csv_count,
        "db_accepted_records": db_count,
        "feature_importances": model_engine.get_feature_importances()[:12]
    }


# =========================
# SUBMISSIONS
# =========================
@app.get("/submissions")
def submissions(db: Session = Depends(get_db)):
    rows = db.query(SalarySubmissionDB).order_by(SalarySubmissionDB.id.desc()).limit(20).all()

    return [
        {
            "id": r.id,
            "company": r.company,
            "role": r.role,
            "level": r.level,
            "location": r.location,
            "yearsOfExperience": r.yearsOfExperience,
            "totalCompensation": r.totalCompensation,
            "currency": r.currency,
            "trust_score": r.trust_score,
            "status": r.status
        }
        for r in rows
    ]


# =========================
# DELETE
# =========================
@app.delete("/submissions/{id}")
def delete(id: int, db: Session = Depends(get_db)):
    row = db.query(SalarySubmissionDB).filter(SalarySubmissionDB.id == id).first()

    if not row:
        raise HTTPException(404, "Not found")

    db.delete(row)
    db.commit()

    return {"deleted": id}


# =========================
# STATIC FRONTEND
# =========================
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/index.html")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
