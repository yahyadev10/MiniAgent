import os
from datetime import datetime

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

API_URL = os.getenv("API_URL", "http://api:8000/tasks")


def prepare_task() -> None:
    print("Preparing mini agent workflow...")


def call_agent() -> dict:
    """Call the FastAPI agent once and return its JSON response."""
    response = requests.post(
        API_URL,
        json={"message": "Send an email to John and generate a report"},
        timeout=180,
    )
    response.raise_for_status()

    result = response.json()
    print(f"Agent action: {result.get('action')}")
    print(f"Agent final: {result.get('final')}")
    return result


def summarize(**context) -> None:
    result = context["ti"].xcom_pull(task_ids="call_agent")
    print(f"Workflow finished. Action={result.get('action')}")
    print(result.get("final", ""))


with DAG(
    dag_id="task_workflow",
    description="Minimal Airflow orchestration for the mini AI agent",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["mini-ai-agent"],
) as dag:
    prepare = PythonOperator(task_id="prepare", python_callable=prepare_task)
    call = PythonOperator(task_id="call_agent", python_callable=call_agent)
    summarize_task = PythonOperator(task_id="summarize", python_callable=summarize)

    prepare >> call >> summarize_task
