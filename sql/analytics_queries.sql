-- =============================================================================
-- analytics_queries.sql
-- Specialty Pharmacy Claims Analytics — Core KPI & Reporting Queries
-- Compatible with PostgreSQL
-- =============================================================================


-- =============================================================================
-- 1. EXECUTIVE SUMMARY KPIs
-- =============================================================================

-- Total claims volume, approval rate, total billed vs paid, avg copay
SELECT
    COUNT(*)                                                   AS total_claims,
    COUNT(*) FILTER (WHERE claim_status = 'Approved')         AS approved_claims,
    COUNT(*) FILTER (WHERE claim_status = 'Denied')           AS denied_claims,
    COUNT(*) FILTER (WHERE claim_status = 'Pending')          AS pending_claims,
    ROUND(
        COUNT(*) FILTER (WHERE claim_status = 'Approved')::NUMERIC
        / COUNT(*) * 100, 2)                                   AS approval_rate_pct,
    ROUND(SUM(billed_amount_usd), 2)                           AS total_billed_usd,
    ROUND(SUM(paid_amount_usd), 2)                             AS total_paid_usd,
    ROUND(AVG(patient_copay_usd) FILTER
         (WHERE claim_status = 'Approved'), 2)                 AS avg_patient_copay_usd,
    ROUND(SUM(paid_amount_usd) / NULLIF(SUM(billed_amount_usd), 0) * 100, 2)
                                                               AS payment_ratio_pct
FROM claims;


-- =============================================================================
-- 2. CLAIMS BY THERAPY AREA (Monthly Trend)
-- =============================================================================

SELECT
    DATE_TRUNC('month', c.service_date)::DATE                  AS month,
    d.therapy_area,
    COUNT(*)                                                    AS claim_count,
    ROUND(SUM(c.billed_amount_usd), 2)                         AS total_billed,
    ROUND(SUM(c.paid_amount_usd), 2)                           AS total_paid,
    ROUND(AVG(c.billed_amount_usd), 2)                         AS avg_claim_value
FROM claims c
JOIN drugs d ON c.drug_id = d.drug_id
GROUP BY DATE_TRUNC('month', c.service_date), d.therapy_area
ORDER BY month, d.therapy_area;


-- =============================================================================
-- 3. TOP 10 DRUGS BY PAID AMOUNT
-- =============================================================================

SELECT
    d.brand_name,
    d.generic_name,
    d.therapy_area,
    d.manufacturer,
    COUNT(c.claim_id)                           AS total_claims,
    COUNT(*) FILTER (WHERE c.claim_status = 'Approved')
                                                AS approved_claims,
    ROUND(SUM(c.paid_amount_usd), 2)            AS total_paid_usd,
    ROUND(AVG(c.paid_amount_usd)
          FILTER (WHERE c.claim_status = 'Approved'), 2)
                                                AS avg_paid_per_claim,
    ROUND(SUM(c.paid_amount_usd) * 100.0
        / SUM(SUM(c.paid_amount_usd)) OVER (), 2)
                                                AS pct_of_total_spend
FROM claims c
JOIN drugs d ON c.drug_id = d.drug_id
GROUP BY d.drug_id, d.brand_name, d.generic_name, d.therapy_area, d.manufacturer
ORDER BY total_paid_usd DESC
LIMIT 10;


-- =============================================================================
-- 4. DENIAL ANALYSIS — Denial Rate by Drug and Reason
-- =============================================================================

SELECT
    d.brand_name,
    c.denial_reason,
    COUNT(*)                                    AS denial_count,
    ROUND(COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (PARTITION BY d.brand_name), 2)
                                                AS pct_of_drug_denials
FROM claims c
JOIN drugs d ON c.drug_id = d.drug_id
WHERE c.claim_status = 'Denied'
GROUP BY d.brand_name, c.denial_reason
ORDER BY d.brand_name, denial_count DESC;


-- =============================================================================
-- 5. PAYER MIX ANALYSIS
-- =============================================================================

SELECT
    p.payer_name,
    p.payer_type,
    COUNT(c.claim_id)                           AS total_claims,
    ROUND(SUM(c.billed_amount_usd), 2)          AS total_billed,
    ROUND(SUM(c.paid_amount_usd), 2)            AS total_paid,
    ROUND(AVG(c.patient_copay_usd)
          FILTER (WHERE c.claim_status = 'Approved'), 2)
                                                AS avg_copay,
    ROUND(COUNT(*) FILTER (WHERE c.claim_status = 'Denied')::NUMERIC
        / COUNT(*) * 100, 2)                    AS denial_rate_pct
FROM claims c
JOIN payers p ON c.payer_id = p.payer_id
GROUP BY p.payer_id, p.payer_name, p.payer_type
ORDER BY total_paid DESC;


-- =============================================================================
-- 6. DISPENSING PERFORMANCE — Days to Ship & Deliver
-- =============================================================================

SELECT
    d.delivery_method,
    COUNT(*)                                    AS dispense_count,
    ROUND(AVG(d.days_to_ship), 2)              AS avg_days_to_ship,
    ROUND(AVG(d.days_to_deliver), 2)           AS avg_days_to_deliver,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
         (ORDER BY d.days_to_deliver), 1)       AS median_days_to_deliver,
    COUNT(*) FILTER (WHERE d.days_to_deliver > 7)
                                                AS late_deliveries,
    ROUND(COUNT(*) FILTER (WHERE d.days_to_deliver > 7)::NUMERIC
        / COUNT(*) * 100, 2)                    AS late_delivery_rate_pct
FROM dispensing_events d
GROUP BY d.delivery_method
ORDER BY avg_days_to_deliver;


-- =============================================================================
-- 7. PATIENT COHORT ANALYSIS — Refill Adherence
-- =============================================================================

WITH patient_refills AS (
    SELECT
        c.patient_id,
        d.therapy_area,
        COUNT(de.dispense_id)                   AS total_fills,
        MAX(de.refill_number)                   AS max_refill_num,
        MIN(c.service_date)                     AS first_fill_date,
        MAX(c.service_date)                     AS last_fill_date,
        SUM(c.paid_amount_usd)                  AS total_paid
    FROM claims c
    JOIN dispensing_events de ON c.claim_id = de.claim_id
    JOIN drugs d ON c.drug_id = d.drug_id
    WHERE c.claim_status = 'Approved'
    GROUP BY c.patient_id, d.therapy_area
)
SELECT
    therapy_area,
    COUNT(DISTINCT patient_id)                  AS patient_count,
    ROUND(AVG(total_fills), 2)                  AS avg_fills_per_patient,
    ROUND(AVG(max_refill_num), 2)               AS avg_max_refill,
    ROUND(AVG(total_paid), 2)                   AS avg_total_paid_per_patient,
    COUNT(*) FILTER (WHERE total_fills >= 3)    AS adherent_patients,
    ROUND(COUNT(*) FILTER (WHERE total_fills >= 3)::NUMERIC
        / COUNT(*) * 100, 2)                    AS adherence_rate_pct
FROM patient_refills
GROUP BY therapy_area
ORDER BY adherence_rate_pct DESC;


-- =============================================================================
-- 8. PRESCRIBER PERFORMANCE — Top Prescribers by Volume & Value
-- =============================================================================

SELECT
    pr.prescriber_id,
    pr.specialty,
    pr.state,
    COUNT(c.claim_id)                           AS total_claims,
    COUNT(DISTINCT c.patient_id)                AS unique_patients,
    ROUND(SUM(c.paid_amount_usd), 2)            AS total_paid_usd,
    ROUND(AVG(c.paid_amount_usd)
          FILTER (WHERE c.claim_status = 'Approved'), 2)
                                                AS avg_claim_value,
    ROUND(COUNT(*) FILTER (WHERE c.claim_status = 'Denied')::NUMERIC
        / COUNT(*) * 100, 2)                    AS denial_rate_pct
FROM claims c
JOIN prescribers pr ON c.prescriber_id = pr.prescriber_id
GROUP BY pr.prescriber_id, pr.specialty, pr.state
HAVING COUNT(c.claim_id) >= 10
ORDER BY total_paid_usd DESC
LIMIT 20;


-- =============================================================================
-- 9. GEOGRAPHIC ANALYSIS — Claims by State
-- =============================================================================

SELECT
    pt.state,
    COUNT(c.claim_id)                           AS total_claims,
    COUNT(DISTINCT c.patient_id)                AS unique_patients,
    ROUND(SUM(c.paid_amount_usd), 2)            AS total_paid_usd,
    ROUND(AVG(c.paid_amount_usd)
          FILTER (WHERE c.claim_status = 'Approved'), 2)
                                                AS avg_claim_value,
    ROUND(COUNT(*) FILTER (WHERE c.claim_status = 'Denied')::NUMERIC
        / COUNT(*) * 100, 2)                    AS denial_rate_pct
FROM claims c
JOIN patients pt ON c.patient_id = pt.patient_id
GROUP BY pt.state
ORDER BY total_claims DESC;


-- =============================================================================
-- 10. YEAR-OVER-YEAR TREND — Claims Volume and Spend
-- =============================================================================

SELECT
    EXTRACT(YEAR FROM service_date)::INT        AS year,
    EXTRACT(QUARTER FROM service_date)::INT     AS quarter,
    COUNT(*)                                    AS total_claims,
    COUNT(*) FILTER (WHERE claim_status = 'Approved')
                                                AS approved_claims,
    ROUND(SUM(billed_amount_usd), 2)            AS total_billed,
    ROUND(SUM(paid_amount_usd), 2)              AS total_paid,
    ROUND(SUM(paid_amount_usd) - LAG(SUM(paid_amount_usd))
        OVER (ORDER BY EXTRACT(YEAR FROM service_date),
                       EXTRACT(QUARTER FROM service_date)), 2)
                                                AS qoq_spend_change
FROM claims
GROUP BY year, quarter
ORDER BY year, quarter;


-- =============================================================================
-- 11. DATA QUALITY CHECK — Orphaned Records & Nulls
-- =============================================================================

SELECT 'claims_missing_diagnosis'   AS check_name,
       COUNT(*) AS issue_count
FROM claims WHERE diagnosis_code IS NULL

UNION ALL

SELECT 'claims_paid_exceeds_billed',
       COUNT(*)
FROM claims WHERE paid_amount_usd > billed_amount_usd

UNION ALL

SELECT 'dispensing_missing_delivery_date',
       COUNT(*)
FROM dispensing_events WHERE delivery_date IS NULL

UNION ALL

SELECT 'claims_approved_zero_paid',
       COUNT(*)
FROM claims WHERE claim_status = 'Approved' AND paid_amount_usd = 0

UNION ALL

SELECT 'patients_missing_state',
       COUNT(*)
FROM patients WHERE state IS NULL OR state = '';
