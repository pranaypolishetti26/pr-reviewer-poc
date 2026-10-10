import copy
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr


spec = importlib.util.spec_from_file_location(
    "publisher", Path(__file__).resolve().parents[1] / "scripts/publish_pr_review.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


SHA = "a" * 40
NEW_SHA = "b" * 40


def review(exit_code=0):
    return {
        "head_sha": SHA,
        "verdict": "NEEDS_CHANGES" if exit_code else "APPROVE",
        "build_tests": {"command": "gradle clean build", "exit_code": exit_code,
                        "build_result": "FAIL" if exit_code else "PASS",
                        "test_result": "NOT_RUN" if exit_code else "PASS",
                        "details": "Compilation failed" if exit_code else "All tests passed"},
        "requirement_alignment": {"requested": "Feature", "implemented": "Feature", "match": "YES"},
        "test_coverage": "No relevant gaps found",
        "findings": [],
        "evidence": ["PR diff", "Knowledge Base", "CodeBuild log"],
    }


class ReviewTests(unittest.TestCase):
    def test_structured_logs_use_only_safe_metadata(self):
        secret = 'secret-do-not-print'
        with tempfile.TemporaryDirectory() as directory:
            stream, result = Path(directory) / 'stream', Path(directory) / 'review'
            events = self.stream_events(json.dumps(review()))
            # Untrusted text and credentials must never be echoed by observability.
            events[0]['update']['rawInput'] = {'token': secret}
            stream.write_text('\n'.join(json.dumps(event) for event in events))
            payload = review()
            payload['build_tests']['details'] = secret
            result.write_text(json.dumps(payload))
            output = io.StringIO()
            with patch.dict('os.environ', {'PR_NUMBER': '42', 'PR_HEAD_SHA': SHA,
                                          'GRADLE_EXIT_CODE': '0', 'WORKFLOW_STAGE': 'publish',
                                          'REVIEW_STARTED_AT': '100', 'STAGE_STARTED_AT': '101',
                                          'KIRO_STREAM_PATH': str(stream), 'REVIEW_JSON': str(result),
                                          'KIRO_API_KEY': secret, 'GITHUB_PERSONAL_ACCESS_TOKEN': secret}), \
                    patch.object(publisher.time, 'time', return_value=105), redirect_stderr(output):
                publisher.log_event('workflow_finished')
            logged = output.getvalue()
            self.assertNotIn(secret, logged)
            event = json.loads(logged)
            self.assertEqual(event['pr_number'], 42)
            self.assertEqual(event['commit_sha'], SHA)
            self.assertEqual(event['duration_seconds'], 5)
            self.assertEqual(event['review_verdict'], 'APPROVE')
            self.assertEqual(event['build_status'], 'PASS')
            self.assertEqual(event['test_status'], 'PASS')
            self.assertTrue(event['github_mcp_used'])
            self.assertTrue(event['knowledge_base_mcp_used'])

    def stream_events(self, output):
        events = []
        for index, name in enumerate(("@github/pull_request_read",
                                     "@project-knowledge/ProjectDocsLambdaTarget___search_project_docs")):
            events.extend([{"update": {"sessionUpdate": "tool_call", "toolCallId": str(index),
                                       "name": name, "status": "pending"}},
                           {"update": {"sessionUpdate": "tool_call_update", "toolCallId": str(index),
                                       "status": "completed"}}])
        # Exercise JSON-RPC notification envelopes and chunked assistant output.
        for chunk in (output[:20], output[20:]):
            events.append({"method": "session/update", "params": {"update": {
                "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": chunk}}}})
        return events

    def test_extract_review_without_file_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / "stream", Path(directory) / "review"
            source.write_text('\n'.join(json.dumps(event) for event in self.stream_events(json.dumps(review()))))
            publisher.extract_review(source, dest)
            publisher.validate_review(json.loads(dest.read_text()), 0, SHA)

    def test_failed_unauthorized_or_missing_tools_prevent_extraction(self):
        cases = [self.stream_events(json.dumps(review())) + [{"update": {
                    "sessionUpdate": "tool_call_update", "toolCallId": "issue", "status": "failed"}}],
                 self.stream_events(json.dumps(review())) + [{"method": "session/request_permission"}],
                 self.stream_events(json.dumps(review())) + [{"update": {
                    "sessionUpdate": "tool_call_update", "rawOutput": {"isError": True}}}],
                 self.stream_events(json.dumps(review()))[4:],
                 self.stream_events(json.dumps(review())) + [{"result": {"stopReason": "cancelled"}}],
                 self.stream_events(json.dumps(review())) + [{"update": {
                    "sessionUpdate": "tool_call", "toolCallId": "issue", "status": "pending"}}],
                 self.stream_events(json.dumps({"error": "REVIEW_TOOL_ERROR: issue_read unauthorized"})),
                 self.stream_events('not JSON')]
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / "stream", Path(directory) / "review"
            for events in cases:
                source.write_text('\n'.join(json.dumps(event) for event in events))
                with self.assertRaises(ValueError):
                    publisher.extract_review(source, dest)
                self.assertFalse(dest.exists())

    def test_agent_exposes_and_preapproves_only_required_mcp_tools(self):
        root = Path(__file__).resolve().parents[1]
        agent = json.loads((root / '.kiro/agents/pr-reviewer.json').read_text())
        approved = {"@github/pull_request_read", "@github/issue_read",
                    "@project-knowledge/ProjectDocsLambdaTarget___search_project_docs"}
        self.assertEqual(set(agent['tools']), approved)
        self.assertEqual(set(agent['allowedTools']), approved)
        rules = agent['permissions']['rules']
        self.assertIn({'capability': 'builtin', 'effect': 'deny'}, rules)
        patterns = approved | {tool.removeprefix('@') for tool in approved}
        self.assertEqual(set(rules[1]['match']), patterns)
        self.assertEqual(set(rules[2]['exclude']), patterns)
        self.assertNotIn('--trust-all-tools', (root / 'buildspec.yml').read_text())

    def test_valid_success_and_failure(self):
        for code in (0, 7):
            publisher.validate_review(review(code), code, SHA)
            body = publisher.render_comment(review(code))
            self.assertTrue(body.startswith(publisher.MARKER))
            self.assertIn(f"Exit code: {code}", body)

    def test_invalid_or_contradictory_reviews(self):
        invalid = [[], {}, {**review(), "verdict": "MAYBE"},
                   {**review(), "findings": ["bad"]}, {**review(), "evidence": []},
                   {**review(), "build_tests": {}},
                   {**review(), "requirement_alignment": {}},
                   {**review(7), "verdict": "APPROVE"}]
        mismatch = review()
        mismatch["build_tests"]["exit_code"] = 7
        invalid.append(mismatch)
        for field in ("test_result", "build_result"):
            item = copy.deepcopy(review())
            item["build_tests"][field] = "FAIL"
            invalid.append(item)
        item = review()
        item["requirement_alignment"]["match"] = "NO"
        invalid.append(item)
        item = review()
        item["findings"] = [{"severity": "BLOCKING", "title": "Missing test",
                             "requirement": "Test the feature", "implementation": "No test",
                             "why_it_matters": "Required coverage is missing", "file": ""}]
        invalid.append(item)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                publisher.validate_review(item, 0, SHA)
        with self.assertRaises(ValueError):
            publisher.validate_review({**review(7), "verdict": "APPROVE"}, 7, SHA)

    def test_invalid_json_makes_no_github_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            with patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo", "PR_NUMBER": "42",
                                             "GITHUB_PERSONAL_ACCESS_TOKEN": "token"}), \
                    patch.object(publisher, "github_request") as api:
                for content in ('not json', '{}', json.dumps({**review(7), "verdict": "APPROVE"})):
                    path.write_text(content)
                    with patch('sys.argv', ['publish', str(path), '7', SHA]), self.assertRaises(ValueError):
                        publisher.main()
                api.assert_not_called()

    def test_create_ignores_other_authors_and_unrelated_comments(self):
        comments = [{"id": 1, "user": {"id": 9}, "body": publisher.MARKER},
                    {"id": 2, "user": {"id": 4}, "body": "Other comment"}]
        with patch.object(publisher, "github_request", side_effect=[{"id": 4}, comments, {"head": {"sha": SHA}}, {"id": 3}]) as api:
            publisher.publish_comment("owner/repo", "42", "token", "new review", SHA)
            self.assertEqual(api.call_args.args[:2], ("POST", "/repos/owner/repo/issues/42/comments"))

    def test_update_existing_and_legacy_comments(self):
        for body in (publisher.MARKER + "\nold", "## Kiro PR Review\nold"):
            with patch.object(publisher, "github_request", side_effect=[
                {"id": 4}, [{"id": 12, "user": {"id": 4}, "body": body}], {"head": {"sha": SHA}}, {"id": 12}
            ]) as api:
                publisher.publish_comment("owner/repo", "42", "token", "updated review", SHA)
                self.assertEqual(api.call_args.args[:2], ("PATCH", "/repos/owner/repo/issues/comments/12"))

    def test_existing_comment_on_second_page(self):
        first_page = [{"id": i, "user": {"id": 9}, "body": "Other"} for i in range(100)]
        with patch.object(publisher, "github_request", side_effect=[
            {"id": 4}, first_page,
            [{"id": 101, "user": {"id": 4}, "body": publisher.MARKER}], {"head": {"sha": SHA}}, {"id": 101}
        ]) as api:
            publisher.publish_comment("owner/repo", "42", "token", "updated", SHA)
            self.assertIn("page=2", api.call_args_list[2].args[1])
            self.assertEqual(api.call_args.args[0], "PATCH")

    def test_api_failure_does_not_fall_back_to_create(self):
        with patch.object(publisher, "github_request", side_effect=[{"id": 4}, OSError("unavailable")]) as api:
            with self.assertRaises(OSError):
                publisher.publish_comment("owner/repo", "42", "token", "review", SHA)
            self.assertEqual([call.args[0] for call in api.call_args_list], ["GET", "GET"])

    def test_stale_review_never_creates_or_updates_comment(self):
        for comments in ([], [{"id": 12, "user": {"id": 4}, "body": publisher.MARKER}]):
            with patch.object(publisher, "github_request", side_effect=[
                {"id": 4}, comments, {"head": {"sha": NEW_SHA}}
            ]) as api:
                with self.assertRaisesRegex(publisher.StaleReviewError, "STALE_REVIEW"):
                    publisher.publish_comment("owner/repo", "42", "token", "review", SHA)
                self.assertTrue(all(call.args[0] == "GET" for call in api.call_args_list))

    def test_stale_review_file_is_discarded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps(review()))
            with patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo", "PR_NUMBER": "42",
                                          "GITHUB_PERSONAL_ACCESS_TOKEN": "token"}), \
                    patch('sys.argv', ['publish', str(path), '0', SHA]), \
                    patch.object(publisher, "github_request", side_effect=[
                        {"id": 4}, [], {"head": {"sha": NEW_SHA}}
                    ]):
                with self.assertRaises(publisher.StaleReviewError):
                    publisher.main()
                self.assertFalse(path.exists())

    def test_review_sha_must_match_saved_sha(self):
        with self.assertRaisesRegex(ValueError, "head SHA"):
            publisher.validate_review({**review(), "head_sha": NEW_SHA}, 0, SHA)

    def test_initial_head_sha_lookup(self):
        with patch.object(publisher, "github_request", return_value={"head": {"sha": SHA}}) as api:
            self.assertEqual(publisher.get_head_sha("owner/repo", "42", "token"), SHA)
            self.assertEqual(api.call_args.args, ("GET", "/repos/owner/repo/pulls/42", "token"))
        with patch.object(publisher, "github_request", return_value={"head": {"sha": "invalid"}}):
            with self.assertRaises(ValueError):
                publisher.get_head_sha("owner/repo", "42", "token")


if __name__ == "__main__":
    unittest.main()
