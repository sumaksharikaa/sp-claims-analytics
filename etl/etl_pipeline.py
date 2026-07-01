"""
etl_pipeline.py
Specialty Pharmacy Claims Analytics — ETL Pipeline
Extracts from CSV → Transforms (validates, cleans) → Loads into PostgreSQL
"""

import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
import logging
import os
import sys
from datetime import datetime

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("etl_pipeline.log"),
    ],
)
log = logging.getLogger(__name__)

# ── config ───────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "dbname":   os.getenv("DB_NAME",     "sp_claims_db"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ── validation rules ─────────────────────────────────────────────────────────
VALID_STATUSES      = {"Approved", "Denied", "Pending", "Reversed"}
VALID_DAYS_SUPPLY   = {30, 60, 90}
VALID_GENDERS       = {"M", "F", "Other"}
VALID_INS_TYPES     = {"Commercial", "Medicare", "Medicaid"}
VALID_PAYER_TYPES   = {"Commercial", "Government", "Managed Medicaid"}


class ETLPipeline:
    def __init__(self):
        self.conn      = None
        self.cursor    = None
        self.errors    = []
        self.stats     = {}

    # ── connection ────────────────────────────────────────────────────────────
    def connect(self):
        log.info("Connecting to PostgreSQL...")
        self.conn   = psycopg2.connect(**DB_CONFIG)
        self.cursor = self.conn.cursor()
        log.info("Connected ✓")

    def disconnect(self):
        if self.cursor: self.cursor.close()
        if self.conn:   self.conn.close()
        log.info("Disconnected.")

    # ── extract ───────────────────────────────────────────────────────────────
    def extract(self, filename: str) -> pd.DataFrame:
        path = os.path.join(DATA_DIR, filename)
        log.info(f"Extracting {filename} ...")
        df = pd.read_csv(path, low_memory=False)
        log.info(f"  → {len(df)} rows, {len(df.columns)} columns")
        return df

    # ── transform helpers ─────────────────────────────────────────────────────
    def _flag_issues(self, df, col, condition, label):
        issues = df[condition].shape[0]
        if issues:
            log.warning(f"  ⚠ {label}: {issues} rows flagged")
            self.errors.append({"check": label, "count": issues})
        return df[~condition].copy()

    def transform_payers(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming payers...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["payer_id"])
        df = self._flag_issues(df, "payer_id", df["payer_id"].isna(), "payers: missing payer_id")
        df["payer_name"] = df["payer_name"].str.strip()
        df["payer_type"] = df["payer_type"].str.strip()
        invalid = ~df["payer_type"].isin(VALID_PAYER_TYPES)
        df.loc[invalid, "payer_type"] = "Commercial"
        return df

    def transform_drugs(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming drugs...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["drug_id"])
        df = self._flag_issues(df, "drug_id", df["drug_id"].isna(), "drugs: missing drug_id")
        df["avg_monthly_cost_usd"] = pd.to_numeric(df["avg_monthly_cost_usd"], errors="coerce").fillna(0)
        df = self._flag_issues(df, "drug_id", df["avg_monthly_cost_usd"] <= 0, "drugs: invalid cost")
        df["formulary_tier"]      = 4
        df["requires_prior_auth"] = True
        df["is_cold_chain"]       = df["brand_name"].isin(["Humira", "Enbrel", "Stelara"])
        return df

    def transform_prescribers(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming prescribers...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["prescriber_id"])
        df["npi"]       = df["npi"].astype(str).str.strip().str.zfill(10)
        df["specialty"] = df["specialty"].str.strip()
        df["state"]     = df["state"].str.upper().str.strip()
        df["is_active"] = True
        return df

    def transform_patients(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming patients...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["patient_id"])
        df["gender"]          = df["gender"].str.strip()
        df["insurance_type"]  = df["insurance_type"].str.strip()
        df["state"]           = df["state"].str.upper().str.strip()
        df["enrollment_date"] = pd.to_datetime(df["enrollment_date"]).dt.date
        df = self._flag_issues(df, "patient_id",
                               ~df["gender"].isin(VALID_GENDERS),
                               "patients: invalid gender")
        df = self._flag_issues(df, "patient_id",
                               ~df["insurance_type"].isin(VALID_INS_TYPES),
                               "patients: invalid insurance type")
        df["is_active"] = True
        return df

    def transform_claims(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming claims...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["claim_id"])
        df["service_date"]        = pd.to_datetime(df["service_date"]).dt.date
        df["billed_amount_usd"]   = pd.to_numeric(df["billed_amount_usd"], errors="coerce").fillna(0)
        df["paid_amount_usd"]     = pd.to_numeric(df["paid_amount_usd"],   errors="coerce").fillna(0)
        df["patient_copay_usd"]   = pd.to_numeric(df["patient_copay_usd"], errors="coerce").fillna(0)
        df["claim_status"]        = df["claim_status"].str.strip()
        df["days_supply"]         = pd.to_numeric(df["days_supply"], errors="coerce").fillna(30).astype(int)
        df["quantity_dispensed"]  = pd.to_numeric(df["quantity_dispensed"], errors="coerce").fillna(1).astype(int)
        df["denial_reason"]       = df["denial_reason"].where(pd.notna(df["denial_reason"]), None)

        # Validate statuses
        df = self._flag_issues(df, "claim_id",
                               ~df["claim_status"].isin(VALID_STATUSES),
                               "claims: invalid status")
        # Business rule: denied must have reason
        missing_reason = (df["claim_status"] == "Denied") & df["denial_reason"].isna()
        df.loc[missing_reason, "denial_reason"] = "Unspecified"

        # Validate days supply
        invalid_days = ~df["days_supply"].isin(VALID_DAYS_SUPPLY)
        df.loc[invalid_days, "days_supply"] = 30

        log.info(f"  Claims by status:\n{df['claim_status'].value_counts().to_string()}")
        return df

    def transform_dispensing(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Transforming dispensing events...")
        df.columns = df.columns.str.lower().str.strip()
        df = df.drop_duplicates(subset=["dispense_id"])
        for col in ["dispense_date", "ship_date", "delivery_date"]:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        df["refill_number"]    = pd.to_numeric(df["refill_number"], errors="coerce").fillna(0).astype(int)
        df["days_to_ship"]     = pd.to_numeric(df["days_to_ship"],    errors="coerce").fillna(0).astype(int)
        df["days_to_deliver"]  = pd.to_numeric(df["days_to_deliver"], errors="coerce").fillna(0).astype(int)
        df["pharmacist_notes"] = df["pharmacist_notes"].where(pd.notna(df["pharmacist_notes"]), None)
        return df

    # ── load helpers ──────────────────────────────────────────────────────────
    def _upsert(self, table: str, df: pd.DataFrame, pk: str, cols: list):
        if df.empty:
            log.warning(f"  No rows to load for {table}.")
            return 0
        rows = [tuple(row) for _, row in df[cols].iterrows()]
        col_str     = ", ".join(cols)
        update_str  = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != pk)
        sql = f"""
            INSERT INTO {table} ({col_str})
            VALUES %s
            ON CONFLICT ({pk}) DO UPDATE SET {update_str}
        """
        execute_values(self.cursor, sql, rows)
        self.conn.commit()
        log.info(f"  ✓ {table}: {len(rows)} rows loaded.")
        self.stats[table] = len(rows)
        return len(rows)

    # ── load ──────────────────────────────────────────────────────────────────
    def load_payers(self, df):
        return self._upsert("payers", df, "payer_id",
                            ["payer_id","payer_name","payer_type"])

    def load_drugs(self, df):
        return self._upsert("drugs", df, "drug_id",
                            ["drug_id","brand_name","generic_name","therapy_area",
                             "manufacturer","avg_monthly_cost_usd",
                             "formulary_tier","requires_prior_auth","is_cold_chain"])

    def load_prescribers(self, df):
        return self._upsert("prescribers", df, "prescriber_id",
                            ["prescriber_id","npi","specialty","state","is_active"])

    def load_patients(self, df):
        return self._upsert("patients", df, "patient_id",
                            ["patient_id","gender","age","state",
                             "insurance_type","enrollment_date","is_active"])

    def load_claims(self, df):
        return self._upsert("claims", df, "claim_id",
                            ["claim_id","patient_id","drug_id","prescriber_id",
                             "payer_id","service_date","claim_status",
                             "billed_amount_usd","paid_amount_usd","patient_copay_usd",
                             "diagnosis_code","denial_reason","days_supply","quantity_dispensed"])

    def load_dispensing(self, df):
        return self._upsert("dispensing_events", df, "dispense_id",
                            ["dispense_id","claim_id","dispense_date","ship_date",
                             "delivery_date","delivery_method","refill_number",
                             "days_to_ship","days_to_deliver","pharmacist_notes"])

    # ── run full pipeline ─────────────────────────────────────────────────────
    def run(self):
        start = datetime.now()
        log.info("=" * 60)
        log.info("SP CLAIMS ETL PIPELINE — STARTING")
        log.info("=" * 60)

        try:
            self.connect()

            # Dimension tables first (FK order)
            self.load_payers(     self.transform_payers(     self.extract("payers.csv")))
            self.load_drugs(      self.transform_drugs(      self.extract("drugs.csv")))
            self.load_prescribers(self.transform_prescribers(self.extract("prescribers.csv")))
            self.load_patients(   self.transform_patients(   self.extract("patients.csv")))

            # Fact tables
            self.load_claims(     self.transform_claims(     self.extract("claims.csv")))
            self.load_dispensing( self.transform_dispensing( self.extract("dispensing_events.csv")))

        except Exception as e:
            log.error(f"Pipeline failed: {e}")
            if self.conn: self.conn.rollback()
            raise
        finally:
            self.disconnect()

        elapsed = (datetime.now() - start).seconds
        log.info("=" * 60)
        log.info(f"ETL COMPLETE in {elapsed}s")
        log.info(f"Rows loaded: {self.stats}")
        if self.errors:
            log.warning(f"Data quality issues: {self.errors}")
        log.info("=" * 60)


if __name__ == "__main__":
    ETLPipeline().run()
