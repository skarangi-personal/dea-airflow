"""
# Sentinel-2_nrt Indexing from SQS

DAG to periodically index Sentinel-2 NRT data.

This DAG uses k8s executors and in cluster with relevant tooling
and configuration installed.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.kubernetes.secret import Secret
from airflow.contrib.operators.kubernetes_pod_operator import KubernetesPodOperator

from sqs_processing_workflow.images import INDEXER_IMAGE
from env_var.infra import (
    DB_DATABASE,
    DB_HOSTNAME,
    SECRET_ODC_WRITER_NAME,
    SECRET_AWS_NAME,
    INDEXING_ROLE,
    SQS_QUEUE_NAME,
)
from sqs_processing_workflow.env_cfg import (
    INDEXING_PRODUCTS,
    PRODUCT_RECORD_PATHS,
    NODE_AFFINITY,
)

# DAG CONFIGURATION
DEFAULT_ARGS = {
    "owner": "Pin Jin",
    "depends_on_past": False,
    "start_date": datetime(2020, 6, 14),
    "email": ["pin.jin@ga.gov.au"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "env_vars": {
        # TODO: Pass these via templated params in DAG Run
        "DB_HOSTNAME": DB_HOSTNAME,
        "DB_DATABASE": DB_DATABASE,
    },
    # Lift secrets into environment variables
    "secrets": [
        Secret("env", "DB_USERNAME", SECRET_ODC_WRITER_NAME, "postgres-username"),
        Secret("env", "DB_PASSWORD", SECRET_ODC_WRITER_NAME, "postgres-password"),
        Secret("env", "AWS_DEFAULT_REGION", SECRET_AWS_NAME, "AWS_DEFAULT_REGION"),
    ],
}

record_path_list_with_prefix = [
    "--record-path " + path for path in PRODUCT_RECORD_PATHS
]
index_product_string = " ".join(INDEXING_PRODUCTS)
record_path_string = " ".join(record_path_list_with_prefix)

INDEXING_BASH_COMMAND = [
    "bash",
    "-c",
    f'sqs-to-dc {SQS_QUEUE_NAME} "{index_product_string}" {record_path_string} --skip-lineage --allow-unsafe',
]


# THE DAG
dag = DAG(
    "sentinel_2_nrt_streamline_indexing",
    doc_md=__doc__,
    default_args=DEFAULT_ARGS,
    schedule_interval="0 */1 * * *",  # hourly
    catchup=False,
    tags=["k8s", "sentinel-2", "streamline-indexing"],
)

with dag:
    INDEXING = KubernetesPodOperator(
        namespace="processing",
        image=INDEXER_IMAGE,
        image_pull_policy="IfNotPresent",
        annotations={"iam.amazonaws.com/role": INDEXING_ROLE},
        arguments=INDEXING_BASH_COMMAND,
        labels={"step": "sqs-to-rds"},
        name="datacube-index",
        task_id="indexing-task",
        get_logs=True,
        affinity=NODE_AFFINITY,
        is_delete_operator_pod=True,
    )
