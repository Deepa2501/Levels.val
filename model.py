import os
import pickle
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from datetime import datetime
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from utils import CurrencyConverter

MODEL_FILENAME = "model_artifacts.pkl"

class SalaryValidationModel:
    """Manages training, inference, and serialization of the salary validation models."""
    
    def __init__(self, model_dir: str = "."):
        self.model_path = os.path.join(model_dir, MODEL_FILENAME)
        self.regressor_pipeline = None
        self.salary_scaler = None
        self.iso_forest = None
        self.is_trained = False

    def train(self, data_path: str) -> None:
        """Trains the Random Forest Regressor and Isolation Forest models on historical data.
        
        Args:
            data_path (str): Path to the training CSV file.
        """
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Training data not found at {data_path}")
            
        # Load baseline data
        df = pd.read_csv(data_path)
        
        # Merge with accepted submissions in the database if any exist
        from database import engine
        try:
            db_records = pd.read_sql(
                "SELECT company, role, location, yearsOfExperience, offerDate, year, totalCompensation, currency, level, baseSalaryINR, stockINR, bonusINR, ipAddress FROM submissions WHERE status = 'accepted'",
                con=engine
            )
            if not db_records.empty:
                df = pd.concat([df, db_records], ignore_index=True)
                print(f"Merged {len(db_records)} accepted submissions from Database for training.")
        except Exception as e:
            # Table might not exist yet if no records were inserted, ignore
            pass
        
        # 1. Normalize targets and derive features using our payload normalizer
        from utils import normalize_payload
        normalized_data = [normalize_payload(row.to_dict()) for _, row in df.iterrows()]
        df = pd.DataFrame(normalized_data)
        
        categorical_features = ['company', 'role', 'location', 'level']
        numeric_features = ['yearsOfExperience', 'year']
        
        X = df[categorical_features + numeric_features]
        y_log = np.log1p(df['totalCompensationINR'])
        
        # 2. Fit Preprocessor and a baseline regressor to compute residuals (geography-independent)
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', Pipeline(steps=[
                    ('imputer', SimpleImputer(strategy='median')),
                    ('scaler', StandardScaler())
                ]), numeric_features),
                ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features)
            ]
        )
        
        X_processed = preprocessor.fit_transform(X)
        
        # Baseline model to estimate expected salary per profile
        rf_baseline = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
        rf_baseline.fit(X_processed, y_log)
        y_pred_log = rf_baseline.predict(X_processed)
        
        # Compute log-residuals (actual - expected)
        residuals = y_log.values - y_pred_log
        
        # 3. Fit Isolation Forest on [yearsOfExperience, year, residual, base_ratio, stock_ratio]
        X_iso_raw = np.column_stack((
            df['yearsOfExperience'].values,
            df['year'].values,
            residuals,
            df['base_ratio'].values,
            df['stock_ratio'].values
        ))
        
        self.salary_scaler = StandardScaler()
        X_iso_scaled = self.salary_scaler.fit_transform(X_iso_raw)
        
        # Fit Isolation Forest (expected outliers contamination ~5%)
        self.iso_forest = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
        outlier_preds = self.iso_forest.fit_predict(X_iso_scaled)
        
        # 4. Clean dataset by removing anomalies to train a robust final regression model
        inlier_mask = outlier_preds == 1
        X_clean = X[inlier_mask]
        y_clean_log = y_log[inlier_mask]
        
        # Build and fit final RandomForestRegressor pipeline on CLEAN inlier data
        self.regressor_pipeline = Pipeline(steps=[
            ('preprocessor', preprocessor),
            ('regressor', RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1))
        ])
        self.regressor_pipeline.fit(X_clean, y_clean_log)
        
        self.is_trained = True
        self.save()
        print(f"Model training successfully completed. Excluded {np.sum(~inlier_mask)} outliers from regression training.")

    def predict(self, submission: Dict[str, Any]) -> Tuple[Dict[str, float], bool, float]:
        """Validates a single salary submission against trained models.
        
        Args:
            submission (Dict[str, Any]): Dictionary of the submission input.
            
        Returns:
            Tuple[Dict[str, float], bool, float]: (predicted_range_dict, is_anomaly, anomaly_score)
        """
        if not self.is_trained:
            raise RuntimeError("Model is not trained or loaded.")
            
        from utils import normalize_payload
        
        # Normalize/clean raw submission input
        norm_submission = normalize_payload(submission)
        
        company = norm_submission["company"]
        role = norm_submission["role"]
        location = norm_submission["location"]
        yoe = norm_submission["yearsOfExperience"]
        year = norm_submission["year"]
        level = norm_submission["level"]
        submitted_salary_inr = norm_submission["totalCompensationINR"]
        base_ratio = norm_submission["base_ratio"]
        stock_ratio = norm_submission["stock_ratio"]
        
        # Format input for scikit-learn regressor
        X_new = pd.DataFrame([{
            'company': company,
            'role': role,
            'location': location,
            'level': level,
            'yearsOfExperience': yoe,
            'year': year
        }])
        
        # 1. Expected Salary Range Estimation
        # Transform features using pipeline preprocessor
        X_new_processed = self.regressor_pipeline.named_steps['preprocessor'].transform(X_new)
        
        # Retrieve estimators to compute predictions across all decision trees (in log space)
        regressor = self.regressor_pipeline.named_steps['regressor']
        tree_predictions_log = np.array([tree.predict(X_new_processed) for tree in regressor.estimators_])
        # Flatten and convert predictions back from log space to INR
        predictions = np.expm1(tree_predictions_log.ravel())
        
        # Calculate P10, Mean (avg), and P90 in INR space
        predicted_min = float(np.percentile(predictions, 10))
        predicted_avg = float(np.mean(predictions))
        predicted_max = float(np.percentile(predictions, 90))
        
        # Calculate predicted log salary using our final clean pipeline
        predicted_log_salary = float(np.mean(tree_predictions_log))
        
        # 2. Anomaly Detection
        submitted_salary_log = np.log1p(submitted_salary_inr)
        
        # Calculate residual of submitted salary from expected profile salary
        residual_new = submitted_salary_log - predicted_log_salary
        
        X_iso_new = np.array([[yoe, year, residual_new, base_ratio, stock_ratio]])
        X_iso_new_scaled = self.salary_scaler.transform(X_iso_new)
        
        # Run Isolation Forest prediction
        iso_pred = self.iso_forest.predict(X_iso_new_scaled)[0]
        anomaly_score = float(self.iso_forest.score_samples(X_iso_new_scaled)[0])
        
        is_anomaly = bool(iso_pred == -1 or anomaly_score < -0.55)
        print(f"DEBUG: company={company}, level={level}, yoe={yoe}, salary={submitted_salary_inr:,.0f}, iso_pred={iso_pred}, anomaly_score={anomaly_score:.4f}, is_anomaly={is_anomaly}")
        
        predicted_range = {
            "min": round(predicted_min, 2),
            "avg": round(predicted_avg, 2),
            "max": round(predicted_max, 2)
        }
        
        return predicted_range, is_anomaly, anomaly_score

    def save(self) -> None:
        """Serializes model objects using pickle."""
        artifacts = {
            "regressor_pipeline": self.regressor_pipeline,
            "salary_scaler": self.salary_scaler,
            "iso_forest": self.iso_forest
        }
        with open(self.model_path, "wb") as f:
            pickle.dump(artifacts, f)
            
    def load(self) -> bool:
        """Deserializes model objects. Returns True if successful, False otherwise."""
        if not os.path.exists(self.model_path):
            self.is_trained = False
            return False
            
        try:
            with open(self.model_path, "rb") as f:
                artifacts = pickle.load(f)
            self.regressor_pipeline = artifacts["regressor_pipeline"]
            self.salary_scaler = artifacts["salary_scaler"]
            self.iso_forest = artifacts["iso_forest"]
            self.is_trained = True
            return True
        except Exception as e:
            print(f"Error loading model artifacts: {e}")
            self.is_trained = False
            return False

    def get_feature_importances(self) -> list:
        """Extracts and sorts features by importance from the trained RandomForestRegressor."""
        if not self.is_trained:
            return []
            
        try:
            preprocessor = self.regressor_pipeline.named_steps['preprocessor']
            regressor = self.regressor_pipeline.named_steps['regressor']
            
            # Get feature names from the pipeline preprocessor
            feature_names = preprocessor.get_feature_names_out()
            importances = regressor.feature_importances_
            
            # Map clean name formats (e.g. removing prefixes like 'num__' or 'cat__')
            mapped_importances = []
            for name, imp in zip(feature_names, importances):
                clean_name = name
                if name.startswith("num__"):
                    col = name[5:]
                    if col == "yearsOfExperience":
                        clean_name = "Years of Experience"
                    elif col == "year":
                        clean_name = "Offer Year"
                elif name.startswith("cat__"):
                    parts = name[5:].split("_", 1)
                    if len(parts) == 2:
                        clean_name = f"{parts[0].capitalize()}: {parts[1]}"
                
                mapped_importances.append({
                    "feature": clean_name,
                    "weight": round(float(imp), 4)
                })
                
            # Sort by importance descending
            mapped_importances.sort(key=lambda x: x["weight"], reverse=True)
            return mapped_importances
        except Exception as e:
            print(f"Error extracting feature importances: {e}")
            return []
