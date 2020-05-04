"""
# NCI Database Backup and Upload to S3

"""
from textwrap import dedent

from airflow import DAG
from airflow.contrib.hooks.aws_hook import AwsHook
from airflow.contrib.operators.ssh_operator import SSHOperator

from datetime import datetime, timedelta

import pendulum

local_tz = pendulum.timezone("Australia/Canberra")

default_args = {
    'owner': 'dayers',
    'depends_on_past': False,
    'retries': 0,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2020, 5, 1, 1, tzinfo=local_tz),
    'timeout': 60*60*2,  # For running SSH Commands
    'ssh_conn_id': 'lpgs_gadi',
    'email_on_failure': True,
    'email': 'damien.ayers@ga.gov.au',
}

with DAG('nci_db_backup',
         default_args=default_args,
         catchup=False,
         schedule_interval="@daily",
         concurrency=1,
         ) as dag:

    COMMON = dedent('''
        # Load dea module to ensure that pg_dump version and the server version
        # matches, when the cronjob is run from an ec2 instance
        module use /g/data/v10/public/modules/modulefiles
        module load dea/20191127

        cd /g/data/v10/agdc/backup/archive

        host=105
        file_prefix="105-{{ ds_nodash }}"
        
    ''')

    run_backup = SSHOperator(
        task_id='run_backup',
        command=COMMON + dedent("""
            args="-U agdc_backup -h 130.56.244.${host} -p 5432"

            set -x

            # Cleanup previous failures
            rm -rf "105"*-datacube-partial.pgdump

            # Dump
            pg_dump ${args} guest > "${file_prefix}-guest.sql"
            pg_dump ${args} datacube -n agdc -T 'agdc.dv_*' -F c -f "${file_prefix}-datacube-partial.pgdump"
            mv -v "${file_prefix}-datacube-partial.pgdump" "${file_prefix}-datacube.pgdump"

            # The globals technically contain (weakly) hashed pg user passwords, so we'll
            # tighten permissions.  (This shouldn't really matter, as users don't choose
            # their own passwords and they're long random strings, but anyway)
            umask 066
            pg_dumpall ${args} --globals-only > "${file_prefix}-globals.sql"

        """),
    )

    aws_conn = AwsHook(aws_conn_id='aws_nci_db_backup')
    upload_to_s3 = SSHOperator(
        task_id='upload_to_s3',
        params={
            'aws_conn': aws_conn.get_credentials(),
        },
        command=COMMON + dedent('''
            export AWS_ACCESS_KEY_ID={{params.aws_conn.access_key}}
            export AWS_SECRET_ACCESS_KEY={{params.aws_conn.secret_key}}
            
            s3_dump_file=s3://nci-db-dump/prod/"${file_prefix}-datacube.pgdump"
            aws s3 cp "${file_prefix}-datacube.pgdump" "${s3_dump_file}"

        ''')

    )

    run_backup >> upload_to_s3