# AI-Powered Salary Validation System

A complete production-ready machine learning backend system built with **FastAPI**, **Scikit-learn**, **Pandas**, and **NumPy**. This system simulates a production validation engine for user-submitted salary/compensation data to detect spam, statistical anomalies, and potential frauds (similar to Levels.fyi).

---

## 🛠️ Tech Stack & Features

- **API Layer**: [FastAPI](https://fastapi.tiangolo.com) for high performance, standard JSON validation, and automatic Swagger docs.
- **ML Predictor**: `RandomForestRegressor` to estimate expected compensation ranges (minimum: 10th percentile, average: mean, maximum: 90th percentile) using bootstrap tree prediction distribution.
- **Anomaly Detection**: `IsolationForest` trained on joint preprocessed feature space (categoricals + experience) and standardized compensation values.
- **Spam Control**: In-memory, thread-safe IP submission frequency tracker (flags if >3 submissions occur within 2 minutes).
- **Integrated Scoring**: A unified scoring engine converting deviation, statistical outlier status, and spam flags into a numeric `trust_score` (0-100) and final acceptance status (`accepted` or `flagged`).

---

## 📁 Project Structure

```
├── main.py            # FastAPI endpoints, validation schemas, and startup lifecycle hooks
├── model.py           # RandomForestRegressor and IsolationForest pipeline training and prediction
├── utils.py           # Currency normalization, IP spam tracker, and scoring logic
├── requirements.txt   # Python dependencies
├── sample_data.csv    # Synthetic realistic historical salary data (with injected outliers and spam)
├── test_api.py        # Automated validation test script
└── README.md          # Project instructions and documentation
```

---

## 🚀 Setup & Execution

### 1. Prerequisites

Ensure you have **Python 3.8+** installed.

### 2. Create and Activate a Virtual Environment

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the Application

Execute the FastAPI app using Uvicorn. The engine automatically checks for trained model artifacts (`model_artifacts.pkl`) and, if missing, auto-trains using the `sample_data.csv` historical dataset.

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🔌 API Endpoints

Once the server is running, you can access the interactive documentation at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### 1. Health Check
- **URL**: `GET /health`
- **Response**:
  ```json
  {
    "status": "healthy",
    "model_trained": true,
    "sample_data_present": true
  }
  ```

### 2. Validate Submission
- **URL**: `POST /validate-submission`
- **Payload Schema**:
  ```json
  {
    "company": "Google",
    "role": "Software Engineer",
    "location": "Bengaluru",
    "yearsOfExperience": 3.0,
    "offerDate": "2026-05-23",
    "totalCompensation": 2200000.0,
    "currency": "INR",
    "ipAddress": "192.168.1.10"
  }
  ```
- **Example Response (Accepted)**:
  ```json
  {
    "predicted_range": {
      "min": 1782000.0,
      "avg": 2185000.0,
      "max": 2510000.0
    },
    "submitted_salary": 2200000.0,
    "deviation_percent": 0.69,
    "anomaly": false,
    "ip_flag": false,
    "trust_score": 100.0,
    "status": "accepted",
    "reasons": []
  }
  ```

- **Example Response (Flagged - Outlier)**:
  ```json
  {
    "predicted_range": {
      "min": 380000.0,
      "avg": 445000.0,
      "max": 512000.0
    },
    "submitted_salary": 45000000.0,
    "deviation_percent": 10012.36,
    "anomaly": true,
    "ip_flag": false,
    "trust_score": 25.0,
    "status": "flagged",
    "reasons": [
      "Submitted compensation is 8689.1% above the maximum expected threshold of 512,000 INR (-40.0 trust score)",
      "Statistical anomaly detected by the Isolation Forest model (-35.0 trust score)"
    ]
  }
  ```

### 3. Model Training
- **URL**: `POST /train`
- **Description**: Triggers a background job to retrain the regression and isolation forest models using `sample_data.csv`.
- **Response**:
  ```json
  {
    "status": "training_started",
    "message": "Model retraining has been triggered in the background."
  }
  ```

---

## 🧪 Validation & Testing

To test the system automatedly, run the verification script `test_api.py` while the server is active:
```bash
python test_api.py
```
This tests:
1. Normal submissions mapping within expectations.
2. Positive and negative statistical anomalies.
3. Multi-currency translation validation (e.g. USD values conversion).
4. Submissions exceeding frequency thresholds from the same IP (Spam mitigation).
