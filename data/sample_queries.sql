-- =========================================================
-- FETCH — pull a scenario (or a batch) for an agent to evaluate
-- =========================================================

-- Full joined "case file" for one customer, the way you'd hand it to an LLM agent
SELECT
    b.customer_id, r.name, r.tenure_months, r.vulnerable_customer,
    r.prior_disputes_12mo, r.prior_goodwill_credits_12mo,
    c.product_name, c.base_mrc, c.promo_name, c.promo_end_date, c.min_term_months, c.notes,
    b.baseline_avg_daily_spend, b.current_cycle_start, b.current_mrc_billed_last_cycle
FROM billing b
JOIN crm r        ON r.customer_id = b.customer_id
JOIN contracts c   ON c.contract_id = r.contract_id
WHERE b.customer_id = 'CUST-1007';

-- All OCS/usage events tied to that same case
SELECT * FROM ocs_events WHERE customer_id = 'CUST-1007' ORDER BY timestamp;

-- Pull a random batch of N untested scenarios (e.g. for a regression run)
SELECT customer_id FROM billing ORDER BY RANDOM() LIMIT 5;

-- Filter scenarios by category or difficulty, e.g. only "hard" cases
SELECT s.customer_id, s.category, s.difficulty, s.expected_verdict
FROM scenario_labels s
WHERE s.difficulty = 'hard';

-- Compare an agent's verdict against the ground truth (after you log agent output
-- into a table of your own, e.g. agent_results(customer_id, agent_verdict, agent_credit_amount))
-- SELECT s.customer_id, s.expected_verdict, a.agent_verdict,
--        s.expected_verdict = a.agent_verdict AS is_correct
-- FROM scenario_labels s
-- JOIN agent_results a ON a.customer_id = s.customer_id;


-- =========================================================
-- ADD — insert a brand-new scenario (all 5 tables, one case)
-- =========================================================

INSERT INTO contracts (contract_id, product_name, base_mrc, promo_name, promo_end_date, min_term_months, notes)
VALUES ('CT-1027', 'Fibre 500', 42.00, NULL, NULL, 18,
        'New scenario: customer billed for a set-top box rental fee after returning the box, per courier tracking on file.');

INSERT INTO crm (customer_id, name, tenure_months, contract_id, prior_disputes_12mo, prior_goodwill_credits_12mo, vulnerable_customer)
VALUES ('CUST-1027', 'A. Test Customer', 12, 'CT-1027', 0, 0, 0);

INSERT INTO billing (customer_id, baseline_avg_daily_spend, current_cycle_start, current_mrc_billed_last_cycle)
VALUES ('CUST-1027', 0.10, '2026-09-01', 45.00);

INSERT INTO ocs_events (event_id, customer_id, timestamp, event_type, amount, description)
VALUES ('EVT-047', 'CUST-1027', '2026-09-01T00:05:00', 'EQUIPMENT_RENTAL_FEE', 3.00,
        'Set-top box rental fee charged after box was returned (tracking confirms delivery 2026-08-25)');

INSERT INTO scenario_labels (customer_id, scenario_id, category, difficulty, expected_verdict, expected_credit_amount, eval_notes)
VALUES ('CUST-1027', 'SC-27', 'equipment_fee_after_return', 'medium', 'valid_dispute_credit_due', 3.00,
        'Courier tracking proves the equipment was returned before the cycle started; refund the rental fee.');


-- =========================================================
-- DELETE — remove a scenario cleanly (respect FK order: children first)
-- =========================================================

DELETE FROM scenario_labels WHERE customer_id = 'CUST-1027';
DELETE FROM ocs_events      WHERE customer_id = 'CUST-1027';
DELETE FROM billing         WHERE customer_id = 'CUST-1027';
DELETE FROM crm             WHERE customer_id = 'CUST-1027';
DELETE FROM contracts       WHERE contract_id = 'CT-1027';


-- =========================================================
-- UPDATE — mutate a scenario in place (e.g. to test a "resolved" state)
-- =========================================================

UPDATE billing
SET current_mrc_billed_last_cycle = current_mrc_billed_last_cycle - 5.00
WHERE customer_id = 'CUST-1015';   -- after crediting the disputed add-on

INSERT INTO ocs_events (event_id, customer_id, timestamp, event_type, amount, description)
VALUES ('EVT-048', 'CUST-1015', '2026-09-08T10:00:00', 'GOODWILL_CREDIT', -5.00,
        'Refund issued for unauthorized Static IP add-on, per agent resolution');
