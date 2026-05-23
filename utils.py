import time
from datetime import datetime, timedelta
import threading
from typing import Dict, List, Tuple

# Conversion rate: 1 USD = 83 INR (Fixed rate for demo/production stability)
USD_TO_INR_RATE = 83.0

class CurrencyConverter:
    """Normalizes compensation figures into Indian Rupees (INR)."""
    
    @staticmethod
    def convert_to_inr(amount: float, currency: str) -> float:
        """Converts base and total compensation to INR.
        
        Args:
            amount (float): The compensation amount.
            currency (str): The currency identifier (e.g. 'USD', 'INR').
            
        Returns:
            float: Normalized amount in INR.
        """
        curr = currency.strip().upper()
        if curr == "USD":
            return amount * USD_TO_INR_RATE
        elif curr == "INR":
            return float(amount)
        else:
            # Default to INR if unknown or unsupported, in production raise Exception or log warning
            return float(amount)

class IPSpamTracker:
    """Thread-safe tracker to detect spam submission behaviors per IP address."""
    
    def __init__(self, window_seconds: int = 120, max_submissions: int = 3):
        self.window_seconds = window_seconds
        self.max_submissions = max_submissions
        # Store mapping of IP -> list of timestamps (float epochs)
        self.ips: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def check_spam_and_record(self, ip_address: str) -> bool:
        """Records a submission timestamp and checks if the IP exceeded request limits.
        
        Args:
            ip_address (str): Submitter's IP address.
            
        Returns:
            bool: True if IP is flagged as spam, False otherwise.
        """
        now = time.time()
        with self.lock:
            # Initialize if not present
            if ip_address not in self.ips:
                self.ips[ip_address] = []
            
            # Prune old timestamps outside the sliding window
            cutoff = now - self.window_seconds
            self.ips[ip_address] = [ts for ts in self.ips[ip_address] if ts > cutoff]
            
            # Record current timestamp
            self.ips[ip_address].append(now)
            
            # Check if threshold is breached
            # If submissions in the window exceed max_submissions, flag as spam
            is_spam = len(self.ips[ip_address]) > self.max_submissions
            return is_spam

def calculate_trust_score(
    submitted_salary: float,
    predicted_min: float,
    predicted_avg: float,
    predicted_max: float,
    is_anomaly: bool,
    ip_flag: bool,
    base_salary_inr: float = 0.0,
    stock_inr: float = 0.0,
    bonus_inr: float = 0.0
) -> Tuple[float, str, List[str]]:
    """Calculates a validation trust score (0-100), accepts/flags the submission, 
    and generates granular reasons for the evaluation.
    
    Args:
        submitted_salary (float): Normalized submitted salary in INR.
        predicted_min (float): Expected minimum (P10) in INR.
        predicted_avg (float): Expected average (Mean) in INR.
        predicted_max (float): Expected maximum (P90) in INR.
        is_anomaly (bool): True if flagged as a statistical outlier by Isolation Forest.
        ip_flag (bool): True if flagged for spamming submissions.
        base_salary_inr (float): Normalized base salary in INR.
        stock_inr (float): Normalized stock grant in INR.
        bonus_inr (float): Normalized bonus in INR.
        
    Returns:
        Tuple[float, str, List[str]]: (trust_score, status, reasons)
    """
    trust_score = 100.0
    reasons = []
    
    # 1. Check IP spam first
    if ip_flag:
        trust_score -= 50.0
        reasons.append("High rate of submissions from this IP address within 2 minutes (-50.0 trust score)")
        
    # 2. Check deviation from expected ranges
    if predicted_avg > 0:
        # Calculate signed percentage deviation from average salary
        deviation_percent = ((submitted_salary - predicted_avg) / predicted_avg) * 100.0
    else:
        deviation_percent = 0.0

    # Apply range-based deductions
    if submitted_salary > predicted_max:
        # Over expected P90 range
        excess_ratio = (submitted_salary - predicted_max) / predicted_max
        deduction = min(40.0, excess_ratio * 50.0) # Deduct up to 40 points
        trust_score -= deduction
        reasons.append(
            f"Submitted compensation is {excess_ratio * 100.0:.1f}% above the maximum expected threshold of "
            f"{predicted_max:,.0f} INR (-{deduction:.1f} trust score)"
        )
    elif submitted_salary < predicted_min:
        # Under expected P10 range
        deficit_ratio = (predicted_min - submitted_salary) / predicted_min
        deduction = min(40.0, deficit_ratio * 50.0) # Deduct up to 40 points
        trust_score -= deduction
        reasons.append(
            f"Submitted compensation is {deficit_ratio * 100.0:.1f}% below the minimum expected threshold of "
            f"{predicted_min:,.0f} INR (-{deduction:.1f} trust score)"
        )
        
    # 3. Check ML model anomaly
    if is_anomaly:
        trust_score -= 35.0
        reasons.append("Statistical anomaly detected by the Isolation Forest model (-35.0 trust score)")

    # 4. Check component sum alignment
    if base_salary_inr > 0 or stock_inr > 0 or bonus_inr > 0:
        sum_components = base_salary_inr + stock_inr + bonus_inr
        if submitted_salary > 0:
            pct_diff = abs(sum_components - submitted_salary) / submitted_salary * 100.0
            if pct_diff > 5.0:
                deduction = 20.0
                trust_score -= deduction
                reasons.append(
                    f"Compensation components (Base + Stock + Bonus = {sum_components:,.0f} INR) "
                    f"do not match Total Compensation ({submitted_salary:,.0f} INR) "
                    f"by {pct_diff:.1f}% (-{deduction:.1f} trust score)"
                )
        
    # Standardize boundaries
    trust_score = max(0.0, min(100.0, trust_score))
    
    # Status evaluation:
    # A submission is automatically flagged if trust score is low or if it represents an active spam vector
    if trust_score >= 70.0 and not ip_flag:
        status = "accepted"
    else:
        status = "flagged"
        if not reasons:
            reasons.append("Trust score is below acceptable validation standards.")
            
    return round(trust_score, 1), status, reasons


def normalize_payload(payload: dict) -> dict:
    """Normalizes a raw submission payload into standard fields in INR currency."""
    import pandas as pd
    
    def get_val(key, default=None):
        val = payload.get(key)
        # Check for pandas NaN, None, or empty string (for text fields)
        if pd.isnull(val) or val is None or val == "":
            return default
        return val

    # 1. Company name resolution
    company = get_val("company")
    if not company:
        company_info = get_val("companyInfo")
        if isinstance(company_info, dict):
            company = company_info.get("name")
    if not company:
        company = "Unknown"
    company = str(company).strip()

    # 2. Role/Title resolution
    role = get_val("role") or get_val("title") or get_val("jobFamily") or "Software Engineer"
    role = str(role).strip()

    # 3. Location cleanup
    location = get_val("location", "Remote")
    location = str(location).strip()
    known_locations = ["Bengaluru", "Hyderabad", "Pune", "Chennai", "SF Bay Area", "Seattle", "Remote"]
    matched = False
    for loc in known_locations:
        if loc.lower() in location.lower():
            location = loc
            matched = True
            break
    if not matched:
        location = location.split(",")[0].strip()

    # 4. Experience
    yoe = float(get_val("yearsOfExperience") or 0.0)

    # 5. Offer date parsing to extract offer year
    offer_date = get_val("offerDate")
    year_val = 2026
    if offer_date:
        try:
            year_val = int(pd.to_datetime(offer_date).year)
        except Exception:
            year_val = int(get_val("year") or 2026)
    else:
        year_val = int(get_val("year") or 2026)

    # 6. Resolve currency normalization rate
    user_currency = str(get_val("userCurrency") or get_val("currency") or "INR").strip().upper()
    exchange_rate = float(get_val("exchangeRate") or 83.0)

    is_usd = user_currency == "USD"
    rate = exchange_rate if is_usd else 1.0

    total_comp = float(get_val("totalCompensation") or 0.0)
    base_sal = float(get_val("baseSalary") or 0.0)
    
    stock_val = float(get_val("avgAnnualStockGrantValue") or 0.0)
    if stock_val == 0.0:
        total_stock = get_val("totalStockGrantValue")
        if total_stock is not None:
            stock_val = float(total_stock) / 4.0
        
    bonus_val = float(get_val("avgAnnualBonusValue") or 0.0)

    # DB Fallbacks if loading from database records
    if total_comp == 0.0:
        total_comp = float(get_val("totalCompensationINR") or 0.0)
        user_currency = "INR"
        rate = 1.0
    if base_sal == 0.0:
        base_sal = float(get_val("baseSalaryINR") or 0.0)
    if stock_val == 0.0:
        stock_val = float(get_val("stockINR") or 0.0)
    if bonus_val == 0.0:
        bonus_val = float(get_val("bonusINR") or 0.0)

    # Convert to INR
    total_comp_inr = total_comp * rate
    base_sal_inr = base_sal * rate
    stock_val_inr = stock_val * rate
    bonus_val_inr = bonus_val * rate

    # Check if component values were provided; if not, use company tier default ratios
    if base_sal_inr == 0.0 and stock_val_inr == 0.0 and bonus_val_inr == 0.0:
        companies_tier = {
            "Google": "tier_1",
            "Microsoft": "tier_1",
            "Amazon": "tier_1",
            "Meta": "tier_1",
            "ServiceNow": "tier_1",
            "UnicornX": "tier_2",
            "StartupA": "tier_2",
            "StartupB": "tier_2",
            "TCS": "tier_3",
            "Infosys": "tier_3",
            "Wipro": "tier_3"
        }
        tier = companies_tier.get(company, "tier_2")
        if tier == "tier_1":
            base_ratio = 0.60
            stock_ratio = 0.25
            bonus_ratio = 0.15
        elif tier == "tier_2":
            base_ratio = 0.80
            stock_ratio = 0.10
            bonus_ratio = 0.10
        else: # tier_3
            base_ratio = 0.90
            stock_ratio = 0.0
            bonus_ratio = 0.10
            
        base_sal_inr = total_comp_inr * base_ratio
        stock_val_inr = total_comp_inr * stock_ratio
        bonus_val_inr = total_comp_inr * bonus_ratio
    else:
        # Calculate actual ratios
        if total_comp_inr > 0:
            base_ratio = base_sal_inr / total_comp_inr
            stock_ratio = stock_val_inr / total_comp_inr
            bonus_ratio = bonus_val_inr / total_comp_inr
        else:
            base_ratio = 1.0
            stock_ratio = 0.0
            bonus_ratio = 0.0

    # Level
    level = str(get_val("level") or "").strip()
    if not level:
        if role == "Software Engineer":
            level = "IC1" if yoe < 3 else "IC2"
        elif role == "Senior Software Engineer":
            level = "IC3"
        elif role == "Tech Lead":
            level = "IC4"
        elif role == "Data Scientist":
            level = "IC2" if yoe < 4 else "IC3"
        elif role == "Product Manager":
            level = "IC3" if yoe < 6 else "IC4"
        else:
            level = "M1" if yoe < 12 else "M2"

    # Client IP
    ip_address = str(get_val("ipAddress") or "127.0.0.1").strip()

    return {
        "company": company,
        "role": role,
        "location": location,
        "yearsOfExperience": yoe,
        "offerDate": str(offer_date) if offer_date else f"{year_val}-01-01",
        "year": year_val,
        "totalCompensation": total_comp,
        "currency": user_currency,
        "totalCompensationINR": total_comp_inr,
        "level": level,
        "baseSalaryINR": base_sal_inr,
        "stockINR": stock_val_inr,
        "bonusINR": bonus_val_inr,
        "base_ratio": base_ratio,
        "stock_ratio": stock_ratio,
        "bonus_ratio": bonus_ratio,
        "ipAddress": ip_address
    }

