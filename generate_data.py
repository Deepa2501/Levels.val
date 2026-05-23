import pandas as pd
import numpy as np
import random
import os

# Set random seed for reproducibility
np.random.seed(42)
random.seed(42)

def generate_sample_data(num_records=500):
    companies = {
        "Google": "tier_1",
        "Microsoft": "tier_1",
        "Amazon": "tier_1",
        "Meta": "tier_1",
        "UnicornX": "tier_2",
        "StartupA": "tier_2",
        "StartupB": "tier_2",
        "TCS": "tier_3",
        "Infosys": "tier_3",
        "Wipro": "tier_3"
    }

    roles = {
        "Software Engineer": 1.0,
        "Senior Software Engineer": 1.6,
        "Tech Lead": 2.2,
        "Product Manager": 2.0,
        "Data Scientist": 1.4,
        "Engineering Manager": 2.8
    }

    locations = {
        "Bengaluru": 1.2,
        "SF Bay Area": 1.4,
        "Seattle": 1.3,
        "Hyderabad": 1.0,
        "Pune": 0.95,
        "Chennai": 0.9,
        "Remote": 1.0
    }

    data = []
    
    # Define salary multipliers
    base_salaries = {
        "tier_1": 1500000.0,
        "tier_2": 800000.0,
        "tier_3": 350000.0
    }
    
    exp_multipliers = {
        "tier_1": 350000.0,
        "tier_2": 180000.0,
        "tier_3": 50000.0
    }

    for _ in range(num_records):
        company = random.choice(list(companies.keys()))
        tier = companies[company]
        
        role = random.choice(list(roles.keys()))
        role_mult = roles[role]
        
        location = random.choice(list(locations.keys()))
        loc_mult = locations[location]
        
        # Years of experience: exponential distribution or truncated normal to favor 1-10 YOE
        yoe = round(max(0, min(20, np.random.normal(6, 4.5))), 1)
        
        # Year of offer: 2021 to 2026
        year = random.choice([2021, 2022, 2023, 2024, 2025, 2026])
        
        # Base calculation
        base = base_salaries[tier]
        exp_addition = yoe * exp_multipliers[tier]
        
        # Year-on-year inflation/trend (e.g. +4% per year after 2021)
        year_mult = 1.0 + (year - 2021) * 0.05
        
        # Expected compensation
        expected_tc = (base + exp_addition) * role_mult * loc_mult * year_mult
        
        # Apply US salary premium
        if location in ["SF Bay Area", "Seattle"]:
            expected_tc *= 2.25
        
        # Add random noise (normal distribution with 12% standard deviation)
        noise = np.random.normal(0, 0.12)
        total_compensation = round(expected_tc * (1.0 + noise))
        
        # Generate Level based on role and YOE
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
        else: # Engineering Manager
            level = "M1" if yoe < 12 else "M2"

        # Determine currency
        if location in ["SF Bay Area", "Seattle"] or (location == "Remote" and random.random() < 0.3):
            currency = "USD"
            # Normalize to USD (1 USD = 83 INR)
            total_compensation = round(total_compensation / 83.0)
            user_currency = "USD"
            exchange_rate = 83.0
        else:
            currency = "INR"
            user_currency = "INR"
            exchange_rate = 1.0

        # Component breakdown based on tier
        if tier == "tier_1":
            base_pct = random.uniform(0.55, 0.65)
            stock_pct = random.uniform(0.20, 0.30)
        elif tier == "tier_2":
            base_pct = random.uniform(0.75, 0.85)
            stock_pct = random.uniform(0.05, 0.15)
        else: # tier_3
            base_pct = random.uniform(0.85, 0.95)
            stock_pct = 0.0
            
        base_salary = round(total_compensation * base_pct)
        stock_val = round(total_compensation * stock_pct)
        bonus_val = total_compensation - base_salary - stock_val
        
        # Set individual currencies
        base_currency = currency
        stock_currency = "USD" if tier == "tier_1" else currency
        bonus_currency = currency

        # Format offerDate
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        offer_date = f"{year}-{month:02d}-{day:02d}"
        
        # Generate fake IP address
        ip_address = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        
        data.append({
            "company": company,
            "role": role,
            "location": location,
            "yearsOfExperience": yoe,
            "offerDate": offer_date,
            "totalCompensation": total_compensation,
            "currency": currency,
            "level": level,
            "baseSalary": base_salary,
            "baseSalaryCurrency": base_currency,
            "avgAnnualStockGrantValue": stock_val,
            "stockGrantCurrency": stock_currency,
            "avgAnnualBonusValue": bonus_val,
            "bonusCurrency": bonus_currency,
            "userCurrency": user_currency,
            "exchangeRate": exchange_rate,
            "ipAddress": ip_address
        })
        
    # Inject some explicit anomalies/spam to test validation
    # Anomaly 1: junior role with extremely high salary
    data.append({
        "company": "TCS",
        "role": "Software Engineer",
        "location": "Pune",
        "yearsOfExperience": 1.0,
        "offerDate": "2026-03-15",
        "totalCompensation": 45000000,
        "currency": "INR",
        "level": "IC1",
        "baseSalary": 40000000,
        "baseSalaryCurrency": "INR",
        "avgAnnualStockGrantValue": 0,
        "stockGrantCurrency": "INR",
        "avgAnnualBonusValue": 5000000,
        "bonusCurrency": "INR",
        "userCurrency": "INR",
        "exchangeRate": 1.0,
        "ipAddress": "10.0.0.1"
    })
    
    # Anomaly 2: senior role with extremely low salary
    data.append({
        "company": "Google",
        "role": "Engineering Manager",
        "location": "Bengaluru",
        "yearsOfExperience": 15.0,
        "offerDate": "2026-01-10",
        "totalCompensation": 12000,
        "currency": "INR",
        "level": "M2",
        "baseSalary": 10000,
        "baseSalaryCurrency": "INR",
        "avgAnnualStockGrantValue": 1000,
        "stockGrantCurrency": "USD",
        "avgAnnualBonusValue": 1000,
        "bonusCurrency": "INR",
        "userCurrency": "INR",
        "exchangeRate": 1.0,
        "ipAddress": "10.0.0.2"
    })
    
    # Anomaly 3: duplicate entries / spam from same IP
    spam_ip = "198.51.100.42"
    for i in range(4):
        data.append({
            "company": "UnicornX",
            "role": "Senior Software Engineer",
            "location": "Remote",
            "yearsOfExperience": 8.0,
            "offerDate": f"2026-05-{20+i}",
            "totalCompensation": 3200000,
            "currency": "INR",
            "level": "IC3",
            "baseSalary": 2600000,
            "baseSalaryCurrency": "INR",
            "avgAnnualStockGrantValue": 300000,
            "stockGrantCurrency": "INR",
            "avgAnnualBonusValue": 300000,
            "bonusCurrency": "INR",
            "userCurrency": "INR",
            "exchangeRate": 1.0,
            "ipAddress": spam_ip
        })

    df = pd.DataFrame(data)
    df.to_csv("sample_data.csv", index=False)
    print(f"Generated sample_data.csv with {len(df)} records.")

if __name__ == "__main__":
    generate_sample_data()
