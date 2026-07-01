"""
generate_data.py
Generates synthetic Specialty Pharmacy (SP) claims data and saves to CSV.
Tables: patients, drugs, prescribers, payers, claims, dispensing_events
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

random.seed(42)
np.random.seed(42)

OUT = os.path.dirname(__file__)

# ── constants ────────────────────────────────────────────────────────────────
SPECIALTY_DRUGS = [
    ("Humira",        "adalimumab",       "Immunology",      "AbbVie",       6500),
    ("Enbrel",        "etanercept",       "Immunology",      "Pfizer",       5800),
    ("Stelara",       "ustekinumab",      "Dermatology",     "Janssen",      18000),
    ("Keytruda",      "pembrolizumab",    "Oncology",        "Merck",        22000),
    ("Revlimid",      "lenalidomide",     "Oncology",        "BMS",          19000),
    ("Copaxone",      "glatiramer",       "Neurology",       "Teva",         7200),
    ("Tecfidera",     "dimethyl fumarate","Neurology",       "Biogen",       8100),
    ("Harvoni",       "ledipasvir",       "Hepatology",      "Gilead",       31000),
    ("Truvada",       "emtricitabine",    "Infectious Dis.", "Gilead",       2700),
    ("Otezla",        "apremilast",       "Dermatology",     "Amgen",        4100),
]

PAYERS = [
    ("PAY001", "BlueCross BlueShield", "Commercial"),
    ("PAY002", "Aetna",               "Commercial"),
    ("PAY003", "Cigna",               "Commercial"),
    ("PAY004", "UnitedHealthcare",    "Commercial"),
    ("PAY005", "Medicare Part D",     "Government"),
    ("PAY006", "Medicaid",            "Government"),
    ("PAY007", "Humana",              "Commercial"),
]

STATES = ["NC","TX","CA","FL","NY","GA","OH","PA","IL","AZ"]
DIAGNOSES = {
    "Immunology":     ["M05.79","M06.9","L40.50"],
    "Dermatology":    ["L40.0","L20.9","L30.9"],
    "Oncology":       ["C90.00","C83.90","C61"],
    "Neurology":      ["G35","G43.909","G89.29"],
    "Hepatology":     ["B18.2","K74.60","K70.30"],
    "Infectious Dis.":["B20","Z21","B19.20"],
}
CLAIM_STATUSES   = ["Approved","Approved","Approved","Approved","Denied","Pending"]
DENIAL_REASONS   = ["Prior Auth Required","Not Medically Necessary",
                    "Formulary Exclusion","Benefit Limit Reached", None]
DELIVERY_METHODS = ["Mail Order","Specialty Pharmacy","In-Office","Hub Dispense"]

START = datetime(2022, 1, 1)
END   = datetime(2024, 12, 31)

def rand_date(start=START, end=END):
    return start + timedelta(days=random.randint(0, (end - start).days))

def fmt(d): return d.strftime("%Y-%m-%d")

# ── patients (500) ───────────────────────────────────────────────────────────
n_pat = 500
patient_ids = [f"PT{str(i).zfill(5)}" for i in range(1, n_pat+1)]
genders      = np.random.choice(["M","F","Other"], n_pat, p=[0.48,0.49,0.03])
ages         = np.random.randint(18, 85, n_pat)
states       = np.random.choice(STATES, n_pat)
enroll_dates = [fmt(rand_date(START, START + timedelta(days=365))) for _ in range(n_pat)]

patients = pd.DataFrame({
    "patient_id":      patient_ids,
    "gender":          genders,
    "age":             ages,
    "state":           states,
    "insurance_type":  np.random.choice(["Commercial","Medicare","Medicaid"], n_pat, p=[0.60,0.25,0.15]),
    "enrollment_date": enroll_dates,
})
patients.to_csv(f"{OUT}/patients.csv", index=False)

# ── drugs (10) ───────────────────────────────────────────────────────────────
drugs = pd.DataFrame(SPECIALTY_DRUGS,
    columns=["brand_name","generic_name","therapy_area","manufacturer","avg_monthly_cost_usd"])
drugs.insert(0, "drug_id", [f"DRG{str(i).zfill(3)}" for i in range(1, len(drugs)+1)])
drugs.to_csv(f"{OUT}/drugs.csv", index=False)

# ── prescribers (80) ─────────────────────────────────────────────────────────
n_rx = 80
specialties = ["Rheumatology","Dermatology","Oncology","Neurology","Gastroenterology","Infectious Disease"]
prescribers = pd.DataFrame({
    "prescriber_id": [f"PRX{str(i).zfill(4)}" for i in range(1, n_rx+1)],
    "specialty":     np.random.choice(specialties, n_rx),
    "state":         np.random.choice(STATES, n_rx),
    "npi":           [str(random.randint(1000000000, 9999999999)) for _ in range(n_rx)],
})
prescribers.to_csv(f"{OUT}/prescribers.csv", index=False)

# ── payers ───────────────────────────────────────────────────────────────────
payers = pd.DataFrame(PAYERS, columns=["payer_id","payer_name","payer_type"])
payers.to_csv(f"{OUT}/payers.csv", index=False)

# ── claims (2000) ────────────────────────────────────────────────────────────
n_claims = 2000
claim_records = []
for i in range(1, n_claims + 1):
    pat   = random.choice(patient_ids)
    drug  = random.choice(drugs["drug_id"].tolist())
    drg_r = drugs[drugs["drug_id"] == drug].iloc[0]
    area  = drg_r["therapy_area"]
    payer = random.choice(payers["payer_id"].tolist())
    prx   = random.choice(prescribers["prescriber_id"].tolist())
    svc_d = rand_date()
    stat  = random.choice(CLAIM_STATUSES)
    base  = drg_r["avg_monthly_cost_usd"]
    billed = round(base * random.uniform(0.90, 1.10), 2)
    paid   = round(billed * random.uniform(0.70, 0.95), 2) if stat == "Approved" else 0.0
    copay  = round(paid * random.uniform(0.05, 0.20), 2) if stat == "Approved" else 0.0
    denial = random.choice(DENIAL_REASONS[:4]) if stat == "Denied" else None
    diag   = random.choice(DIAGNOSES.get(area, ["Z00.00"]))
    claim_records.append({
        "claim_id":           f"CLM{str(i).zfill(6)}",
        "patient_id":         pat,
        "drug_id":            drug,
        "prescriber_id":      prx,
        "payer_id":           payer,
        "service_date":       fmt(svc_d),
        "claim_status":       stat,
        "billed_amount_usd":  billed,
        "paid_amount_usd":    paid,
        "patient_copay_usd":  copay,
        "diagnosis_code":     diag,
        "denial_reason":      denial,
        "days_supply":        random.choice([30, 60, 90]),
        "quantity_dispensed": random.randint(1, 4),
    })

claims = pd.DataFrame(claim_records)
claims.to_csv(f"{OUT}/claims.csv", index=False)

# ── dispensing events (for approved claims) ──────────────────────────────────
approved = claims[claims["claim_status"] == "Approved"]["claim_id"].tolist()
disp_records = []
for i, cid in enumerate(approved, 1):
    c = claims[claims["claim_id"] == cid].iloc[0]
    svc = datetime.strptime(c["service_date"], "%Y-%m-%d")
    ship_d = svc + timedelta(days=random.randint(1, 5))
    deliv_d = ship_d + timedelta(days=random.randint(1, 4))
    disp_records.append({
        "dispense_id":       f"DSP{str(i).zfill(6)}",
        "claim_id":          cid,
        "dispense_date":     fmt(svc),
        "ship_date":         fmt(ship_d),
        "delivery_date":     fmt(deliv_d),
        "delivery_method":   random.choice(DELIVERY_METHODS),
        "pharmacist_notes":  random.choice(["No issues","Patient counseled","Refrigeration required","Temp excursion flagged", None]),
        "refill_number":     random.randint(0, 5),
        "days_to_ship":      (ship_d - svc).days,
        "days_to_deliver":   (deliv_d - svc).days,
    })

dispensing = pd.DataFrame(disp_records)
dispensing.to_csv(f"{OUT}/dispensing_events.csv", index=False)

print(f"✅ Generated:")
print(f"   patients.csv          → {len(patients)} rows")
print(f"   drugs.csv             → {len(drugs)} rows")
print(f"   prescribers.csv       → {len(prescribers)} rows")
print(f"   payers.csv            → {len(payers)} rows")
print(f"   claims.csv            → {len(claims)} rows")
print(f"   dispensing_events.csv → {len(dispensing)} rows")
