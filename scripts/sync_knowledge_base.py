"""Mirror merged project docs to the existing S3 data source, then ingest."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


REGION = 'us-east-2'


def log(event, **fields):
    # Fixed metadata only: do not echo CLI stderr, credentials, or document contents.
    print(json.dumps({'event': event, 'region': REGION, **fields}), flush=True)


def aws(*args):
    result = subprocess.run(['aws', *args, '--region', REGION, '--no-cli-pager'],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError('aws_command_failed')
    return json.loads(result.stdout) if result.stdout.strip() else {}


def sync():
    stage = 'configuration'
    started = time.monotonic()
    try:
        # Defense in depth: this script cannot sync a PR event or a feature branch.
        if os.environ.get('GITHUB_EVENT_NAME') != 'push' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
            raise ValueError('main_push_required')
        bucket = os.environ['S3_BUCKET']
        kb_id = os.environ['KNOWLEDGE_BASE_ID']
        source_id = os.environ['DATA_SOURCE_ID']
        prefix_value = os.environ.get('S3_PREFIX', 'docs/knowledge-base/')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
            raise ValueError('invalid_bucket')
        if not all(re.fullmatch(r'[A-Za-z0-9]{10}', value) for value in (kb_id, source_id)):
            raise ValueError('invalid_resource_id')
        # '/' explicitly selects a dedicated bucket root; never default to root.
        if not prefix_value or '..' in prefix_value.split('/') or prefix_value.startswith('s3:'):
            raise ValueError('invalid_prefix')
        prefix = prefix_value.strip('/')
        prefix = prefix + '/' if prefix else ''
        stage = 'verify_data_source'
        source = aws('bedrock-agent', 'get-data-source', '--knowledge-base-id', kb_id,
                     '--data-source-id', source_id)['dataSource']['dataSourceConfiguration']
        config = source.get('s3Configuration', {})
        if source.get('type') != 'S3' or config.get('bucketArn') != f'arn:aws:s3:::{bucket}':
            raise ValueError('data_source_bucket_mismatch')
        inclusions = config.get('inclusionPrefixes', [])
        if inclusions and not any(prefix.startswith(allowed) for allowed in inclusions):
            raise ValueError('data_source_prefix_mismatch')
        log('docs_sync_started')
        stage = 's3_sync'
        # Git removes empty directories. An empty source mirrors deletion of the last doc.
        documents = Path(__file__).resolve().parents[1] / 'docs/knowledge-base'
        with tempfile.TemporaryDirectory(prefix='empty-kb-docs-') as empty:
            aws('s3', 'sync', str(documents if documents.is_dir() else Path(empty)),
                f's3://{bucket}/{prefix}', '--delete', '--no-follow-symlinks', '--only-show-errors')
        log('s3_sync_completed')
        stage = 'start_ingestion'
        job = aws('bedrock-agent', 'start-ingestion-job', '--knowledge-base-id', kb_id,
                  '--data-source-id', source_id)['ingestionJob']
        job_id = job['ingestionJobId']
        log('ingestion_started', job_id=job_id)
        stage = 'wait_ingestion'
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            job = aws('bedrock-agent', 'get-ingestion-job', '--knowledge-base-id', kb_id,
                      '--data-source-id', source_id, '--ingestion-job-id', job_id)['ingestionJob']
            status = job['status']
            if status == 'COMPLETE':
                statistics = job.get('statistics', {})
                if statistics.get('numberOfDocumentsFailed', 0):
                    raise RuntimeError('ingestion_documents_failed')
                log('docs_sync_completed', duration_seconds=round(time.monotonic() - started, 3),
                    job_id=job_id, status=status)
                return 0
            if status in ('FAILED', 'STOPPED'):
                raise RuntimeError('ingestion_failed')
            if status not in ('STARTING', 'IN_PROGRESS', 'STOPPING'):
                raise RuntimeError('unexpected_ingestion_status')
            log('ingestion_pending', job_id=job_id, status=status)
            time.sleep(10)
        raise RuntimeError('ingestion_timeout')
    except (KeyError, ValueError, RuntimeError, OSError, TypeError) as error:
        # Error messages are fixed codes from this script, never raw AWS responses.
        reason = str(error) if isinstance(error, RuntimeError) and str(error) in (
            'aws_command_failed', 'ingestion_failed', 'ingestion_documents_failed',
            'unexpected_ingestion_status', 'ingestion_timeout'
        ) else 'invalid_configuration_or_response'
        log('docs_sync_failed', stage=stage, error=reason,
            duration_seconds=round(time.monotonic() - started, 3))
        return 1


if __name__ == '__main__':
    raise SystemExit(sync())
