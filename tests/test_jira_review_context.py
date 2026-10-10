import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_review_context as setup
import publish_pr_review as publisher
from test_publish_pr_review import SHA, review


class JiraReviewTests(unittest.TestCase):
    def context(self, title='', body='', repository='owner/repo'):
        return setup.context_for({'head': {'sha': SHA}, 'title': title, 'body': body}, repository, SHA)

    def test_no_jira_requires_no_jira_credentials_or_server(self):
        context = self.context(body='Implements #12')
        config = setup.configure_mcp(json.loads((ROOT / '.kiro/settings/mcp.json').read_text()), context)
        agent = setup.configure_agent(json.loads((ROOT / '.kiro/agents/pr-reviewer.json').read_text()), context)
        self.assertNotIn('atlassian', config['mcpServers'])
        self.assertTrue(context['github_issue_linked'])
        self.assertEqual(context['documentation_source'], 'knowledge-base')
        self.assertIn('@github/issue_read', agent['tools'])
        self.assertEqual(len(agent['tools']), 3)

    def test_jira_keys_are_deduplicated_and_require_credentials(self):
        context = self.context('SCRUM-5: Fix masking', 'SCRUM-5 and BANK-12')
        self.assertEqual(context['jira_keys'], ['BANK-12', 'SCRUM-5'])
        config = json.loads((ROOT / '.kiro/settings/mcp.json').read_text())
        with self.assertRaisesRegex(ValueError, 'JIRA_TOKEN'):
            setup.configure_mcp(copy.deepcopy(config), context)
        with self.assertRaisesRegex(ValueError, 'JIRA_EMAIL'):
            setup.configure_mcp(copy.deepcopy(config), context, 'token')
        result = setup.configure_mcp(config, context, 'token', 'user@example.com')
        self.assertEqual(result['mcpServers']['atlassian']['headers']['Authorization'],
                         'Basic dXNlckBleGFtcGxlLmNvbTp0b2tlbg==')

    def test_fineract_disables_unrelated_knowledge_base(self):
        context = self.context('SCRUM-5', repository='pranaypolishetti26/fineract')
        config = setup.configure_mcp(json.loads((ROOT / '.kiro/settings/mcp.json').read_text()),
                                     context, 'token', 'user@example.com')
        agent = setup.configure_agent(json.loads((ROOT / '.kiro/agents/pr-reviewer.json').read_text()), context)
        self.assertTrue(config['mcpServers']['project-knowledge']['disabled'])
        self.assertNotIn('@project-knowledge/ProjectDocsLambdaTarget___search_project_docs', agent['tools'])
        self.assertIn('get_file_contents', config['mcpServers']['github']['headers']['X-MCP-Tools'])
        self.assertEqual(context['build_command'], setup.FINERACT_COMMAND)
        self.assertNotIn('doc', context['build_command'])

    def extract(self, context, calls):
        events = []
        for index, (name, args) in enumerate(calls):
            events.append({'update': {'sessionUpdate': 'tool_call', 'toolCallId': str(index),
                                      'name': name, 'rawInput': args, 'status': 'completed'}})
        events.append({'update': {'sessionUpdate': 'agent_message_chunk',
                                  'content': {'type': 'text', 'text': json.dumps(review())}}})
        with tempfile.TemporaryDirectory() as directory:
            ctx, stream, output = [Path(directory) / name for name in ('context', 'stream', 'output')]
            ctx.write_text(json.dumps(context))
            stream.write_text('\n'.join(json.dumps(event) for event in events))
            with patch.dict(os.environ, {'REVIEW_CONTEXT_PATH': str(ctx)}):
                publisher.extract_review(stream, output)
            self.assertTrue(output.exists())

    def test_jira_and_pinned_docs_must_actually_be_read(self):
        context = self.context('SCRUM-5', repository='pranaypolishetti26/fineract')
        calls = [('@github/pull_request_read', {}), ('@atlassian/getAccessibleAtlassianResources', {}),
                 ('@atlassian/getJiraIssue', {'issueIdOrKey': 'SCRUM-5'})]
        calls += [('@github/get_file_contents', {'path': path, 'ref': SHA})
                  for path in context['documentation_paths']]
        self.extract(context, calls)
        for invalid in (calls[:2] + calls[3:], calls[:-1],
                        calls + [('@project-knowledge/ProjectDocsLambdaTarget___search_project_docs', {})],
                        [(name, {**args, 'ref': 'develop'} if 'path' in args else args) for name, args in calls],
                        [(name, {'issueIdOrKey': 'SCRUM-99'} if 'getJiraIssue' in name else args) for name, args in calls]):
            with self.assertRaisesRegex(ValueError, 'REVIEW_TOOL_ERROR'):
                self.extract(context, invalid)

    def test_github_issue_fallback_cannot_skip_issue_read(self):
        context = self.context(body='Refs #12')
        calls = [('@github/pull_request_read', {}),
                 ('@project-knowledge/ProjectDocsLambdaTarget___search_project_docs', {})]
        with self.assertRaisesRegex(ValueError, 'issue_read'):
            self.extract(context, calls)
        self.extract(context, calls + [('@github/issue_read', {'issue_number': 12})])

    def test_sha_change_during_setup_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'STALE_REVIEW'):
            setup.context_for({'head': {'sha': 'b' * 40}}, 'owner/repo', SHA)

    def test_focused_command_validation_and_rest_comment(self):
        payload = review()
        payload['build_tests']['command'] = setup.FINERACT_COMMAND
        with patch.dict(os.environ, {'REVIEW_BUILD_COMMAND': setup.FINERACT_COMMAND}):
            publisher.validate_review(payload, 0, SHA)
        self.assertIn(setup.FINERACT_COMMAND, publisher.render_comment(payload))
        with self.assertRaisesRegex(ValueError, 'Incorrect build command'):
            publisher.validate_review(payload, 0, SHA)
