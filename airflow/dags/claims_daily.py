from datetime import datetime

from airflow.providers.databricks.operators.databricks import DatabricksRunNowOperator
from airflow.sdk import DAG, Param

with DAG(
    dag_id="claims_daily",
    start_date=datetime(2026, 11, 1),
    schedule="0 7 * * *",
    catchup=False,
    params={
        "through": Param("2026-06-30", type="string"),
        "retrain": Param("false", enum=["false", "true"]),
    },
    tags=["databricks", "claims"],
) as dag:
    DatabricksRunNowOperator(
        task_id="run_claims_daily",
        databricks_conn_id="databricks_default",
        job_name="claims_daily_prod",
        job_parameters={
            "through": "{{ params.through }}",
            "retrain": "{{ params.retrain }}",
        },
    )