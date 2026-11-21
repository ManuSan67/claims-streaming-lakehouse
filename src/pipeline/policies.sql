CREATE OR REFRESH STREAMING TABLE policy_changes (
  CONSTRAINT valid_op EXPECT (op IN ('INSERT', 'UPDATE', 'DELETE')) ON VIOLATION FAIL UPDATE,
  CONSTRAINT has_policy_id EXPECT (policy_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT positive_premium EXPECT (annual_premium > 0)
)
AS SELECT
  policy_id,
  customer_id,
  plan,
  CAST(vehicle_year AS INT) AS vehicle_year,
  CAST(vehicle_value AS DECIMAL(14, 2)) AS vehicle_value,
  CAST(annual_premium AS DECIMAL(14, 2)) AS annual_premium,
  state,
  city,
  CAST(start_date AS DATE) AS start_date,
  op,
  CAST(change_ts AS TIMESTAMP) AS change_ts
FROM STREAM(${catalog}.bronze.policies_cdc);

CREATE OR REFRESH STREAMING TABLE policies;

CREATE FLOW policies_scd2 AS AUTO CDC INTO policies
FROM STREAM(policy_changes)
KEYS (policy_id)
APPLY AS DELETE WHEN op = 'DELETE'
SEQUENCE BY change_ts
COLUMNS * EXCEPT (op, change_ts)
STORED AS SCD TYPE 2;