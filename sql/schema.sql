-- =============================================================================
-- schema.sql
-- Specialty Pharmacy Claims Analytics — PostgreSQL Schema
-- ER Model: patients → claims ← drugs, prescribers, payers
--           claims → dispensing_events
-- =============================================================================

-- ── extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── drop existing tables (safe re-run) ────────────────────────────────────────
DROP TABLE IF EXISTS dispensing_events CASCADE;
DROP TABLE IF EXISTS claims            CASCADE;
DROP TABLE IF EXISTS patients          CASCADE;
DROP TABLE IF EXISTS drugs             CASCADE;
DROP TABLE IF EXISTS prescribers       CASCADE;
DROP TABLE IF EXISTS payers            CASCADE;
DROP TABLE IF EXISTS audit_log         CASCADE;

-- =============================================================================
-- DIMENSION TABLES
-- =============================================================================

CREATE TABLE payers (
    payer_id        VARCHAR(10)  PRIMARY KEY,
    payer_name      VARCHAR(100) NOT NULL,
    payer_type      VARCHAR(30)  NOT NULL CHECK (payer_type IN ('Commercial','Government','Managed Medicaid'))
);

CREATE TABLE drugs (
    drug_id                 VARCHAR(10)  PRIMARY KEY,
    brand_name              VARCHAR(100) NOT NULL,
    generic_name            VARCHAR(100) NOT NULL,
    therapy_area            VARCHAR(60)  NOT NULL,
    manufacturer            VARCHAR(100) NOT NULL,
    avg_monthly_cost_usd    NUMERIC(10,2) NOT NULL CHECK (avg_monthly_cost_usd > 0),
    formulary_tier          SMALLINT     DEFAULT 4 CHECK (formulary_tier BETWEEN 1 AND 5),
    requires_prior_auth     BOOLEAN      DEFAULT TRUE,
    is_cold_chain           BOOLEAN      DEFAULT FALSE,
    created_at              TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prescribers (
    prescriber_id   VARCHAR(10)  PRIMARY KEY,
    npi             CHAR(10)     NOT NULL UNIQUE,
    specialty       VARCHAR(80)  NOT NULL,
    state           CHAR(2)      NOT NULL,
    is_active       BOOLEAN      DEFAULT TRUE
);

CREATE TABLE patients (
    patient_id       VARCHAR(10)  PRIMARY KEY,
    gender           CHAR(6)      CHECK (gender IN ('M','F','Other')),
    age              SMALLINT     CHECK (age BETWEEN 0 AND 120),
    state            CHAR(2)      NOT NULL,
    insurance_type   VARCHAR(20)  NOT NULL CHECK (insurance_type IN ('Commercial','Medicare','Medicaid')),
    enrollment_date  DATE         NOT NULL,
    is_active        BOOLEAN      DEFAULT TRUE,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- FACT TABLES
-- =============================================================================

CREATE TABLE claims (
    claim_id             VARCHAR(12)   PRIMARY KEY,
    patient_id           VARCHAR(10)   NOT NULL REFERENCES patients(patient_id),
    drug_id              VARCHAR(10)   NOT NULL REFERENCES drugs(drug_id),
    prescriber_id        VARCHAR(10)   NOT NULL REFERENCES prescribers(prescriber_id),
    payer_id             VARCHAR(10)   NOT NULL REFERENCES payers(payer_id),
    service_date         DATE          NOT NULL,
    claim_status         VARCHAR(20)   NOT NULL CHECK (claim_status IN ('Approved','Denied','Pending','Reversed')),
    billed_amount_usd    NUMERIC(10,2) NOT NULL CHECK (billed_amount_usd >= 0),
    paid_amount_usd      NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (paid_amount_usd >= 0),
    patient_copay_usd    NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (patient_copay_usd >= 0),
    diagnosis_code       VARCHAR(10),
    denial_reason        VARCHAR(100),
    days_supply          SMALLINT      CHECK (days_supply IN (30, 60, 90)),
    quantity_dispensed   SMALLINT      CHECK (quantity_dispensed > 0),
    created_at           TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    -- business rule: denied claims must have a reason
    CONSTRAINT chk_denial_reason CHECK (
        claim_status != 'Denied' OR denial_reason IS NOT NULL
    )
);

CREATE INDEX idx_claims_patient    ON claims(patient_id);
CREATE INDEX idx_claims_drug       ON claims(drug_id);
CREATE INDEX idx_claims_payer      ON claims(payer_id);
CREATE INDEX idx_claims_status     ON claims(claim_status);
CREATE INDEX idx_claims_svc_date   ON claims(service_date);
CREATE INDEX idx_claims_therapy    ON claims(drug_id, claim_status);

CREATE TABLE dispensing_events (
    dispense_id       VARCHAR(12)  PRIMARY KEY,
    claim_id          VARCHAR(12)  NOT NULL REFERENCES claims(claim_id),
    dispense_date     DATE         NOT NULL,
    ship_date         DATE,
    delivery_date     DATE,
    delivery_method   VARCHAR(40)  NOT NULL,
    refill_number     SMALLINT     DEFAULT 0 CHECK (refill_number >= 0),
    days_to_ship      SMALLINT,
    days_to_deliver   SMALLINT,
    pharmacist_notes  TEXT,
    created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_ship_after_dispense   CHECK (ship_date >= dispense_date),
    CONSTRAINT chk_deliver_after_ship    CHECK (delivery_date >= ship_date)
);

CREATE INDEX idx_disp_claim        ON dispensing_events(claim_id);
CREATE INDEX idx_disp_date         ON dispensing_events(dispense_date);
CREATE INDEX idx_disp_method       ON dispensing_events(delivery_method);

-- =============================================================================
-- AUDIT LOG (Data Governance)
-- =============================================================================

CREATE TABLE audit_log (
    log_id        SERIAL        PRIMARY KEY,
    table_name    VARCHAR(50)   NOT NULL,
    record_id     VARCHAR(20)   NOT NULL,
    action        VARCHAR(10)   NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
    changed_by    VARCHAR(50)   DEFAULT current_user,
    changed_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    old_values    JSONB,
    new_values    JSONB
);

-- =============================================================================
-- TRIGGER: auto-update updated_at on claims
-- =============================================================================

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_claims_updated_at
    BEFORE UPDATE ON claims
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- =============================================================================
-- TRIGGER: audit log on claims changes
-- =============================================================================

CREATE OR REPLACE FUNCTION log_claims_audit()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_log(table_name, record_id, action, new_values)
        VALUES ('claims', NEW.claim_id, 'INSERT', row_to_json(NEW)::jsonb);
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_log(table_name, record_id, action, old_values, new_values)
        VALUES ('claims', NEW.claim_id, 'UPDATE', row_to_json(OLD)::jsonb, row_to_json(NEW)::jsonb);
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log(table_name, record_id, action, old_values)
        VALUES ('claims', OLD.claim_id, 'DELETE', row_to_json(OLD)::jsonb);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_claims_audit
    AFTER INSERT OR UPDATE OR DELETE ON claims
    FOR EACH ROW EXECUTE FUNCTION log_claims_audit();
