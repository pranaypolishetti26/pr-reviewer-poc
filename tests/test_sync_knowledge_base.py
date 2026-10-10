import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('docs_sync', Path(__file__).resolve().parents[1] / 'scripts/sync_knowledge_base.py')
docs_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs_sync)

ENV = {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
       'S3_BUCKET': 'existing-docs-bucket', 'KNOWLEDGE_BASE_ID': 'ABCDEFGHIJ',
       'DATA_SOURCE_ID': '0123456789', 'S3_PREFIX': 'docs/knowledge-base/'}
SOURCE = {'dataSource': {'dataSourceConfiguration': {'type': 'S3', 's3Configuration': {
    'bucketArn': 'arn:aws:s3:::existing-docs-bucket', 'inclusionPrefixes': ['docs/knowledge-base/']}}}}
START = {'ingestionJob': {'ingestionJobId': 'job1234567'}}
COMPLETE = {'ingestionJob': {'status': 'COMPLETE', 'statistics': {'numberOfDocumentsFailed': 0}}}


class SyncTests(unittest.TestCase):
    def run_sync(self, responses, env=None):
        output = io.StringIO()
        with patch.dict(os.environ, env or ENV, clear=True), \
                patch.object(docs_sync, 'aws', side_effect=responses) as api, redirect_stdout(output):
            result = docs_sync.sync()
        return result, api, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_sync_uploads_and_deletes_before_ingestion(self):
        result, api, logs = self.run_sync([SOURCE, {}, START, COMPLETE])
        self.assertEqual(result, 0)
        commands = [call.args for call in api.call_args_list]
        self.assertEqual(commands[1][:2], ('s3', 'sync'))
        self.assertIn('--delete', commands[1])
        self.assertIn('s3://existing-docs-bucket/docs/knowledge-base/', commands[1])
        self.assertEqual(commands[2][:2], ('bedrock-agent', 'start-ingestion-job'))
        self.assertEqual(logs[-1]['event'], 'docs_sync_completed')

    def test_unmerged_pr_and_feature_push_never_touch_aws(self):
        for overrides in ({'GITHUB_EVENT_NAME': 'pull_request'}, {'GITHUB_REF': 'refs/heads/feature'}):
            result, api, logs = self.run_sync([], {**ENV, **overrides})
            self.assertEqual(result, 1)
            api.assert_not_called()
            self.assertEqual(logs[-1]['stage'], 'configuration')

    def test_mismatched_data_source_prevents_s3_writes(self):
        for config in (
            {'type': 'S3', 's3Configuration': {'bucketArn': 'arn:aws:s3:::other-bucket'}},
            {'type': 'S3', 's3Configuration': {'bucketArn': 'arn:aws:s3:::existing-docs-bucket', 'inclusionPrefixes': ['other/']}}
        ):
            result, api, _ = self.run_sync([{'dataSource': {'dataSourceConfiguration': config}}])
            self.assertEqual(result, 1)
            self.assertEqual(api.call_count, 1)

    def test_s3_failure_does_not_start_ingestion(self):
        result, api, logs = self.run_sync([SOURCE, RuntimeError('aws_command_failed')])
        self.assertEqual(result, 1)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(logs[-1]['stage'], 's3_sync')

    def test_ingestion_failures_fail_workflow(self):
        for job in ({'status': 'FAILED'}, {'status': 'STOPPED'},
                    {'status': 'COMPLETE', 'statistics': {'numberOfDocumentsFailed': 1}}):
            result, _, logs = self.run_sync([SOURCE, {}, START, {'ingestionJob': job}])
            self.assertEqual(result, 1)
            self.assertEqual(logs[-1]['stage'], 'wait_ingestion')

    def test_waits_for_ingestion_completion(self):
        with patch.object(docs_sync.time, 'sleep') as sleep:
            result, _, logs = self.run_sync([SOURCE, {}, START,
                {'ingestionJob': {'status': 'IN_PROGRESS'}}, COMPLETE])
            self.assertEqual(result, 0)
            sleep.assert_called_once_with(10)
            self.assertIn('ingestion_pending', [entry['event'] for entry in logs])

    def test_deleting_last_document_uses_empty_source(self):
        def api(*args):
            if args[:2] == ('bedrock-agent', 'get-data-source'):
                return SOURCE
            if args[:2] == ('s3', 'sync'):
                self.assertEqual(list(Path(args[2]).iterdir()), [])
                self.assertIn('--delete', args)
                return {}
            return START if args[1] == 'start-ingestion-job' else COMPLETE
        with patch.dict(os.environ, ENV, clear=True), patch.object(Path, 'is_dir', return_value=False), \
                patch.object(docs_sync, 'aws', side_effect=api), redirect_stdout(io.StringIO()):
            self.assertEqual(docs_sync.sync(), 0)

    def test_aws_cli_region_and_no_raw_error_logging(self):
        import subprocess
        with patch.object(docs_sync.subprocess, 'run', return_value=subprocess.CompletedProcess(
            [], 1, '', 'secret-token-should-not-be-logged')) as run:
            with self.assertRaisesRegex(RuntimeError, '^aws_command_failed$'):
                docs_sync.aws('s3', 'sync')
            self.assertIn('us-east-2', run.call_args.args[0])
