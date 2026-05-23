import json
from fastapi.testclient import TestClient
from main import app, model_engine, DATA_PATH
from database import engine, SalarySubmissionDB
from sqlalchemy.orm import Session

client = TestClient(app)

def test_api():
    print("==================================================")
    print("STARTING SALARY VALIDATION INTEGRATION TESTS")
    print("==================================================")

    # 0. Force database initialization and retraining
    print("\n[Step 0] Initializing DB and training model on sample_data.csv...")
    from database import init_db
    init_db()
    model_engine.train(DATA_PATH)

    # 1. Health check test
    print("\n[Step 1] Testing /health endpoint...")
    response = client.get("/health")
    print(f"Health Response: {response.json()}")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["model_trained"] is True

    # 2. Normal salary validation (INR) & DB Persistence Check
    print("\n[Step 2] Testing normal submission (within expected range) and DB persistence...")
    payload_normal = {
        "company": "Google",
        "role": "Software Engineer",
        "location": "Bengaluru",
        "yearsOfExperience": 3.0,
        "offerDate": "2026-05-23",
        "totalCompensation": 2200000.0,
        "currency": "INR",
        "ipAddress": "192.168.1.10"
    }
    response = client.post("/validate-submission", json=payload_normal)
    res_data = response.json()
    print(f"Normal Submission Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert res_data["status"] == "accepted"
    assert res_data["anomaly"] is False
    assert res_data["ip_flag"] is False
    assert res_data["trust_score"] >= 80.0

    # Query DB directly to verify persistence
    session = Session(bind=engine)
    db_records = session.query(SalarySubmissionDB).filter(
        SalarySubmissionDB.company == "Google",
        SalarySubmissionDB.role == "Software Engineer",
        SalarySubmissionDB.location == "Bengaluru",
        SalarySubmissionDB.totalCompensation == 2200000.0
    ).all()
    assert len(db_records) > 0, "Record was not persisted to the SQLite database on acceptance"
    print(f"  Verified Database Persistence! Found {len(db_records)} records matching in SQL database.")
    session.close()

    # 3. Anomaly detection: Extremely high salary
    print("\n[Step 3] Testing extreme positive salary anomaly...")
    payload_high = {
        "company": "TCS",
        "role": "Software Engineer",
        "location": "Pune",
        "yearsOfExperience": 1.0,
        "offerDate": "2026-05-23",
        "totalCompensation": 45000000.0, # 45,000,000 INR
        "currency": "INR",
        "ipAddress": "192.168.1.11"
    }
    response = client.post("/validate-submission", json=payload_high)
    res_data = response.json()
    print(f"Extreme High Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert res_data["status"] == "flagged"
    assert res_data["anomaly"] is True
    assert "above the maximum expected threshold" in "".join(res_data["reasons"])
    assert "Statistical anomaly detected" in "".join(res_data["reasons"])

    # 4. Anomaly detection: Extremely low salary
    print("\n[Step 4] Testing extreme negative salary anomaly...")
    payload_low = {
        "company": "Google",
        "role": "Engineering Manager",
        "location": "Bengaluru",
        "yearsOfExperience": 15.0,
        "offerDate": "2026-05-23",
        "totalCompensation": 12000.0, # 12,000 INR
        "currency": "INR",
        "ipAddress": "192.168.1.12"
    }
    response = client.post("/validate-submission", json=payload_low)
    res_data = response.json()
    print(f"Extreme Low Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert res_data["status"] == "flagged"
    assert res_data["anomaly"] is True
    assert "below the minimum expected threshold" in "".join(res_data["reasons"])
    assert "Statistical anomaly detected" in "".join(res_data["reasons"])

    # 5. Currency normalization: USD conversion
    print("\n[Step 5] Testing USD currency normalization...")
    payload_usd = {
        "company": "Google",
        "role": "Senior Software Engineer",
        "location": "SF Bay Area",
        "yearsOfExperience": 6.0,
        "offerDate": "2026-05-23",
        "totalCompensation": 250000.0, # 250k USD -> ~20.75M INR
        "currency": "USD",
        "ipAddress": "192.168.1.13"
    }
    response = client.post("/validate-submission", json=payload_usd)
    res_data = response.json()
    print(f"USD Submission Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert res_data["status"] == "accepted"
    # Target should be converted to INR
    assert abs(res_data["submitted_salary"] - (250000.0 * 83.0)) < 1e-2

    # Verify that the USD accepted record was also saved to DB
    session = Session(bind=engine)
    db_usd_records = session.query(SalarySubmissionDB).filter(
        SalarySubmissionDB.company == "Google",
        SalarySubmissionDB.currency == "USD",
        SalarySubmissionDB.totalCompensation == 250000.0
    ).all()
    assert len(db_usd_records) > 0, "USD Accepted record was not saved to SQL database"
    print(f"  Verified USD Record DB Persistence! Found {len(db_usd_records)} USD records in SQLite.")
    session.close()

    # 6. IP Spam detection test
    print("\n[Step 6] Testing IP Spam Rate Limiting...")
    spam_ip = "198.51.100.99"
    payload_spam = {
        "company": "Amazon",
        "role": "Software Engineer",
        "location": "Bengaluru",
        "yearsOfExperience": 3.0,
        "offerDate": "2026-05-23",
        "totalCompensation": 2000000.0,
        "currency": "INR",
        "ipAddress": spam_ip
    }
    
    # Send 3 submissions (should succeed)
    for i in range(1, 4):
        print(f"  Sending submission {i} for IP {spam_ip}...")
        response = client.post("/validate-submission", json=payload_spam)
        assert response.status_code == 200
        assert response.json()["ip_flag"] is False
        assert response.json()["status"] == "accepted"
        
    # Send 4th submission (should trigger spam threshold)
    print(f"  Sending 4th submission from IP {spam_ip} (expected spam trigger)...")
    response = client.post("/validate-submission", json=payload_spam)
    res_data = response.json()
    print(f"4th Submission Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert res_data["ip_flag"] is True
    assert res_data["status"] == "flagged"
    assert "High rate of submissions from this IP" in "".join(res_data["reasons"])

    # 7. Model Insights Endpoint Test
    print("\n[Step 7] Testing /model-insights endpoint...")
    response = client.get("/model-insights")
    insights_data = response.json()
    print(f"Insights Response: {json.dumps(insights_data, indent=2)}")
    assert response.status_code == 200
    assert "total_training_records" in insights_data
    assert "csv_baseline_records" in insights_data
    assert "db_accepted_records" in insights_data
    assert "feature_importances" in insights_data
    assert len(insights_data["feature_importances"]) > 0
    assert "weight" in insights_data["feature_importances"][0]
    print("  Verified Model Insights output!")

    # 8. Query and Delete DB records Test
    print("\n[Step 8] Testing GET and DELETE /submissions endpoints...")
    # Get all submissions
    response = client.get("/submissions")
    submissions_list = response.json()
    assert response.status_code == 200
    assert len(submissions_list) > 0
    sub_id = submissions_list[0]["id"]
    print(f"  Retrieved {len(submissions_list)} database submissions. Latest ID is #{sub_id}.")

    # Delete the latest submission
    del_response = client.delete(f"/submissions/{sub_id}")
    assert del_response.status_code == 200
    assert del_response.json()["status"] == "success"
    print(f"  Successfully deleted submission #{sub_id} from SQLite DB.")

    # Confirm deletion
    response_after = client.get("/submissions")
    submissions_after = response_after.json()
    assert not any(s["id"] == sub_id for s in submissions_after), f"Submission #{sub_id} was not deleted"
    print("  Verified record deletion audit trail!")

    # 9. Rich levels.fyi ServiceNow JSON payload validation test
    print("\n[Step 9] Testing rich levels.fyi ServiceNow JSON payload...")
    payload_rich = {
      "uuid": "8199449f-7a0d-4f83-9427-bdaeae2d507a",
      "company": "ServiceNow",
      "title": "Software Engineer",
      "jobFamily": "Software Engineer",
      "jobFamilySlug": "software-engineer",
      "level": "IC1",
      "focusTag": "Software Engineer",
      "yearsOfExperience": 1.0,
      "yearsAtCompany": 0,
      "offerDate": "Mon Sep 09 2024 09:15:00 GMT+0000 (Coordinated Universal Time)",
      "location": "Pune, MH, India",
      "exchangeRate": 83.94,
      "baseSalary": 19000.0,
      "baseSalaryCurrency": "INR",
      "totalCompensation": 27600.0,
      "avgAnnualStockGrantValue": 5000.0,
      "stockGrantCurrency": "USD",
      "avgAnnualBonusValue": 3500.0,
      "bonusCurrency": "INR",
      "userCurrency": "USD",
      "ipAddress": "192.168.1.110"
    }
    response = client.post("/validate-submission", json=payload_rich)
    res_data = response.json()
    print(f"Rich Submission Response: {json.dumps(res_data, indent=2)}")
    assert response.status_code == 200
    assert "submitted_salary" in res_data
    # Should convert total compensation to INR: 27600 * 83.94 = 2,316,744
    expected_salary_inr = 27600.0 * 83.94
    assert abs(res_data["submitted_salary"] - expected_salary_inr) < 1.0
    print("  Verified rich payload normalization and total compensation in INR!")

    print("\n==================================================")
    print("ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    test_api()
