-- Billing Dispute Mock Data — Schema
-- Works as-is in SQLite; for Postgres/MySQL, swap TEXT/REAL for VARCHAR/NUMERIC as needed.

CREATE TABLE contracts (
    contract_id TEXT PRIMARY KEY,
    product_name TEXT,
    base_mrc REAL,
    promo_name TEXT,
    promo_end_date TEXT,
    min_term_months INTEGER,
    notes TEXT
);

CREATE TABLE billing (
    customer_id TEXT PRIMARY KEY,
    baseline_avg_daily_spend REAL,
    current_cycle_start TEXT,
    current_mrc_billed_last_cycle REAL
);

CREATE TABLE crm (
    customer_id TEXT PRIMARY KEY,
    name TEXT,
    tenure_months INTEGER,
    contract_id TEXT,
    prior_disputes_12mo INTEGER,
    prior_goodwill_credits_12mo INTEGER,
    vulnerable_customer INTEGER DEFAULT 0,
    FOREIGN KEY (contract_id) REFERENCES contracts(contract_id)
);

CREATE TABLE ocs_events (
    event_id TEXT PRIMARY KEY,
    customer_id TEXT,
    timestamp TEXT,
    event_type TEXT,
    amount REAL,
    description TEXT,
    FOREIGN KEY (customer_id) REFERENCES crm(customer_id)
);

-- "Answer key" for evaluating an AI agent's triage decisions.
-- Keep this table out of anything the agent itself is allowed to query directly.
CREATE TABLE scenario_labels (
    customer_id TEXT PRIMARY KEY,
    scenario_id TEXT,
    category TEXT,
    difficulty TEXT,
    expected_verdict TEXT,       -- valid_dispute_credit_due | valid_charge_no_credit | needs_human_review
    expected_credit_amount REAL, -- NULL when the correct action isn't a fixed credit
    eval_notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES crm(customer_id)
);
