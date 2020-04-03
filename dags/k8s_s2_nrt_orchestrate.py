"""DAG to periodically update explorer and ows schemas in RDS
after daily NRT has been indexed.
- Run Explorer summaries
- Run ows update ranges for NRT products
- Run ows update ranges for NRT multi-products

This DAG uses k8s executors and pre-existing pods in cluster with relevant tooling
and configuration installed

set start_date to something real, not datetime.utcnow() because that'll break things

for setting upstream and downstream, use
start >> passing
start >> failing

You can use `with dag: ` as a context manager, and not have to manually pass it as an argument
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator
from airflow.operators.dummy_operator import DummyOperator


DEFAULT_ARGS = {
    "owner": "Tisham Dhar",
    "depends_on_past": False,
    "start_date": datetime(2020, 3, 4),
    "email": ["tisham.dhar@ga.gov.au"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG("k8s_s2_nrt_orchestrate", default_args=DEFAULT_ARGS, schedule_interval=timedelta(hours=3))


with dag:
    START = DummyOperator(task_id="s3_index_publish")

    INDEXING = KubernetesPodOperator(
        namespace="processing",
        image="Python:3.6",
        cmds=["Python", "-c"],
        arguments=["print('hello world')"],
        labels={"foo": "bar"},
        name="datacube-index",
        task_id="indexing-task",
        get_logs=True,
    )

    UPDATE_RANGES = KubernetesPodOperator(
        namespace="processing",
        image="ubuntu:1604",
        cmds=["Python", "-c"],
        arguments=["print('hello world')"],
        labels={"foo": "bar"},
        name="ows-update-ranges",
        task_id="update-ranges-task",
        get_logs=True,
    )

    SUMMARY = KubernetesPodOperator(
        namespace="processing",
        image="ubuntu:1604",
        cmds=["Python", "-c"],
        arguments=["print('hello world')"],
        labels={"foo": "bar"},
        name="explorer-summary",
        task_id="explorer-summary-task",
        get_logs=True,
    )

    COMPLETE = DummyOperator(task_id="all_done")

    START >> INDEXING
    INDEXING >> UPDATE_RANGES
    INDEXING >> SUMMARY
    UPDATE_RANGES >> COMPLETE
    SUMMARY >> COMPLETE
