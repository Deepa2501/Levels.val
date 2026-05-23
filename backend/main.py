from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pandas as pd
from sqlalchemy.orm import Session
from model import SalaryValidationModel
from utils import CurrencyConverter, IPSpamTracker, calculate_trust_score
from database import get_db, init_db, SalarySubmissionDB

# Initialize FastAPI application
app = FastAPI(
    title="AI-Powered Salary Validation API",
    description="A production-ready validation engine to check compensation submissions, identify anomalies, and detect spam.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://levels-val.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables/services
model_engine = SalaryValidationModel()
ip_tracker = IPSpamTracker(window_seconds=120, max_submissions=3)
DATA_PATH = "sample_data.csv"

# Pydantic Schemas
class SalarySubmission(BaseModel):
    company: Optional[str] = Field(None, description="Name of the company", example="Google")
    companyInfo: Optional[dict] = Field(None, description="Detailed company info mapping")
    role: Optional[str] = Field(None, description="Job role/title", example="Software Engineer")
    title: Optional[str] = Field(None, description="Alternative job role/title key", example="Software Engineer")
    jobFamily: Optional[str] = Field(None, description="Alternative job role/family key", example="Software Engineer")
    location: Optional[str] = Field(None, description="Office location", example="Bengaluru")
    yearsOfExperience: float = Field(0.0, ge=0.0, description="Total years of professional experience", example=4.5)
    offerDate: Optional[str] = Field(None, description="Offer date in YYYY-MM-DD format", example="2026-05-23")
    year: Optional[int] = Field(None, description="Direct year of offer, extracted from offerDate if not provided", example=2026)
    totalCompensation: float = Field(..., gt=0.0, description="Total compensation value", example=2800000.0)
    currency: str = Field("INR", description="Three-letter currency code (e.g. INR, USD)", example="INR")
    level: Optional[str] = Field(None, description="Level / Grade of the employee", example="IC1")
    baseSalary: Optional[float] = Field(None, description="Base salary component")
    baseSalaryCurrency: Optional[str] = Field(None, description="Base salary currency")
    avgAnnualStockGrantValue: Optional[float] = Field(None, description="Annual stock grant component")
    stockGrantCurrency: Optional[str] = Field(None, description="Stock currency")
    avgAnnualBonusValue: Optional[float] = Field(None, description="Annual bonus component")
    bonusCurrency: Optional[str] = Field(None, description="Bonus currency")
    userCurrency: Optional[str] = Field(None, description="User currency preference")
    exchangeRate: Optional[float] = Field(None, description="Exchange rate against USD")
    ipAddress: Optional[str] = Field("127.0.0.1", description="IP address of the submitter", example="192.168.1.100")

    @model_validator(mode='after')
    def verify_role_exists(self) -> 'SalarySubmission':
        """Ensures that either 'role', 'title' or 'jobFamily' is supplied."""
        if not self.role and not self.title and not self.jobFamily:
            raise ValueError("Either 'role', 'title' or 'jobFamily' must be provided.")
        # Normalize to role
        if not self.role:
            self.role = self.title or self.jobFamily
        return self

class PredictedRange(BaseModel):
    min: float = Field(..., description="10th percentile expected compensation in INR")
    avg: float = Field(..., description="Mean expected compensation in INR")
    max: float = Field(..., description="90th percentile expected compensation in INR")

class ValidationResponse(BaseModel):
    predicted_range: PredictedRange
    submitted_salary: float = Field(..., description="Normalized submitted salary in INR")
    deviation_percent: float = Field(..., description="Signed percentage deviation from average salary")
    anomaly: bool = Field(..., description="Flag indicating if isolation forest detected a statistical outlier")
    ip_flag: bool = Field(..., description="Flag indicating if submissions from this IP exceed limits")
    trust_score: float = Field(..., description="Submissions trust score (0 - 100)")
    status: str = Field(..., description="Validation resolution (accepted or flagged)")
    reasons: List[str] = Field(..., description="List of reasons for validation status deductions")


@app.on_event("startup")
def startup_event():
    """Startup routine to initialize SQLite database and load model artifacts."""
    print("Initializing Database...")
    init_db()
    
    print("Initializing Salary Validation Engine...")
    success = model_engine.load()
    if success:
        print("Model loaded successfully from local storage.")
    else:
        print("Model files not found or corrupted. Triggering automatic model training from sample_data.csv...")
        if os.path.exists(DATA_PATH):
            try:
                model_engine.train(DATA_PATH)
            except Exception as e:
                print(f"Failed to auto-train model: {e}")
        else:
            print(f"Error: {DATA_PATH} not found. Model cannot be auto-trained.")


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Returns the API health and ML model training state."""
    return {
        "status": "healthy",
        "model_trained": model_engine.is_trained,
        "sample_data_present": os.path.exists(DATA_PATH)
    }


@app.post("/train", status_code=status.HTTP_202_ACCEPTED)
def train_model(background_tasks: BackgroundTasks):
    """Triggers an asynchronous model retraining cycle on the sample dataset."""
    if not os.path.exists(DATA_PATH):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Training dataset {DATA_PATH} not found."
        )
    
    def run_training():
        model_engine.train(DATA_PATH)
        
    background_tasks.add_task(run_training)
    return {
        "status": "training_started",
        "message": "Model retraining has been triggered in the background."
    }


@app.post("/validate-submission", response_model=ValidationResponse, status_code=status.HTTP_200_OK)
def validate_submission(submission: SalarySubmission, db: Session = Depends(get_db)):
    """Validates user compensation details against market data to flag spam or fraud.
    
    Performs:
    1. Rich payload normalization and currency conversion to INR
    2. IP submission frequency check (spam rate limit)
    3. RandomForestRegressor salary range prediction with levels
    4. IsolationForest anomaly score evaluation with component ratios
    5. Integrated scoring logic with component checks
    6. Persists accepted submissions to SQLite DB.
    """
    if not model_engine.is_trained:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Machine learning validation model is currently untrained. Call /train or seed sample_data.csv."
        )

    try:
        from utils import normalize_payload

        # 1. Normalize payload using utility helper (handles levels, currencies, conversions)
        submission_dict = submission.model_dump()
        norm_submission = normalize_payload(submission_dict)
        
        submitted_salary_inr = norm_submission["totalCompensationINR"]
        ip_address = norm_submission["ipAddress"]

        # 2. IP rate limiting / Spam check
        ip_flag = ip_tracker.check_spam_and_record(ip_address)

        # 3. Get predictions from ML engine (using the normalized payload)
        predicted_range, is_anomaly, anomaly_score = model_engine.predict(submission_dict)

        # 4. Calculate deviation percentage
        pred_avg = predicted_range["avg"]
        if pred_avg > 0:
            deviation_percent = ((submitted_salary_inr - pred_avg) / pred_avg) * 100.0
        else:
            deviation_percent = 0.0

        # 5. Process Scoring Engine
        trust_score, status_result, reasons = calculate_trust_score(
            submitted_salary=submitted_salary_inr,
            predicted_min=predicted_range["min"],
            predicted_avg=predicted_range["avg"],
            predicted_max=predicted_range["max"],
            is_anomaly=is_anomaly,
            ip_flag=ip_flag,
            base_salary_inr=norm_submission["baseSalaryINR"],
            stock_inr=norm_submission["stockINR"],
            bonus_inr=norm_submission["bonusINR"]
        )

        # 6. Persist all submissions to the SQLite DB for auditing
        db_submission = SalarySubmissionDB(
            company=norm_submission["company"],
            role=norm_submission["role"],
            location=norm_submission["location"],
            yearsOfExperience=norm_submission["yearsOfExperience"],
            offerDate=norm_submission["offerDate"],
            year=norm_submission["year"],
            totalCompensation=norm_submission["totalCompensation"],
            currency=norm_submission["currency"],
            totalCompensationINR=submitted_salary_inr,
            level=norm_submission["level"],
            baseSalaryINR=norm_submission["baseSalaryINR"],
            stockINR=norm_submission["stockINR"],
            bonusINR=norm_submission["bonusINR"],
            ipAddress=ip_address,
            trust_score=trust_score,
            status=status_result,
            reasons=reasons
        )
        db.add(db_submission)
        db.commit()

        return ValidationResponse(
            predicted_range=PredictedRange(
                min=predicted_range["min"],
                avg=predicted_range["avg"],
                max=predicted_range["max"]
            ),
            submitted_salary=round(submitted_salary_inr, 2),
            deviation_percent=round(deviation_percent, 2),
            anomaly=is_anomaly,
            ip_flag=ip_flag,
            trust_score=trust_score,
            status=status_result,
            reasons=reasons
        )
        
    except Exception as e:
        import traceback
        print(f"Exception encountered during validation: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during submission validation: {str(e)}"
        )


@app.get("/model-insights", status_code=status.HTTP_200_OK)
def get_model_insights(db: Session = Depends(get_db)):
    """Exposes statistics on training datasets and ML model feature importances."""
    # Count database accepted records
    try:
        db_count = db.query(SalarySubmissionDB).filter(SalarySubmissionDB.status == "accepted").count()
    except Exception:
        db_count = 0
        
    # Count base CSV records
    try:
        csv_count = len(pd.read_csv(DATA_PATH))
    except Exception:
        csv_count = 0
        
    total_training_records = csv_count + db_count
    
    # Retrieve feature importances from model
    feature_importances = model_engine.get_feature_importances()
    
    return {
        "total_training_records": total_training_records,
        "csv_baseline_records": csv_count,
        "db_accepted_records": db_count,
        "feature_importances": feature_importances[:12]  # Limit to top 12 features for visualization clarity
    }


@app.get("/submissions", status_code=status.HTTP_200_OK)
def get_submissions(db: Session = Depends(get_db)):
    """Retrieves the recent submissions from the SQLite database."""
    try:
        submissions = db.query(SalarySubmissionDB).order_by(SalarySubmissionDB.id.desc()).limit(20).all()
        result = []
        for s in submissions:
            result.append({
                "id": s.id,
                "company": s.company,
                "role": s.role,
                "level": s.level,
                "location": s.location,
                "yearsOfExperience": s.yearsOfExperience,
                "offerDate": s.offerDate,
                "totalCompensation": s.totalCompensation,
                "currency": s.currency,
                "totalCompensationINR": s.totalCompensationINR,
                "baseSalaryINR": s.baseSalaryINR or 0.0,
                "stockINR": s.stockINR or 0.0,
                "bonusINR": s.bonusINR or 0.0,
                "trust_score": s.trust_score,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None
            })
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query submissions: {str(e)}"
        )


@app.delete("/submissions/{submission_id}", status_code=status.HTTP_200_OK)
def delete_submission(submission_id: int, db: Session = Depends(get_db)):
    """Deletes a specific submission record from the database."""
    try:
        record = db.query(SalarySubmissionDB).filter(SalarySubmissionDB.id == submission_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Submission with ID {submission_id} not found."
            )
        db.delete(record)
        db.commit()
        return {"status": "success", "message": f"Submission {submission_id} deleted."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete submission: {str(e)}"
        )


# Mount the static files directory
# Ensure the "static" folder exists on disk
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_root():
    """Serves the main Glassmorphic Web Dashboard HTML interface."""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
