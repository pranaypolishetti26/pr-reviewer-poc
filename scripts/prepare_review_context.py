"""Select requirements and MCP servers from the pinned PR, before application checkout."""

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from publish_pr_review import github_request, require


FINERACT_COMMAND = ("./gradlew --no-daemon --console=plain :fineract-core:test "
                    "--tests org.apache.fineract.infrastructure.core.service.StringUtilTest")
JIRA_SITE = "https://pranaypspk26.atlassian.net"


def context_for(pr, repository, expected_sha):
    require(pr['head']['sha'] == expected_sha, 'STALE_REVIEW: PR head changed during setup')
    content = (pr.get('title') or '') + '\n' + (pr.get('body') or '')
    # Resolve referenced keys only on the configured site; never follow arbitrary Jira hosts.
    keys = sorted(set(re.findall(r'\b[A-Z][A-Z0-9_]*-[1-9][0-9]*\b', content)))
    fineract = repository == 'pranaypolishetti26/fineract'
    return {'head_sha': expected_sha, 'jira_keys': keys, 'jira_site': JIRA_SITE,
            'github_issue_linked': bool(re.search(
                r'(?:(?<![\w/])#\d+\b|'
                r'https://github\.com/[^/\s]+/[^/\s]+/issues/\d+)', content, re.I)),
            'documentation_source': 'repository' if fineract else 'knowledge-base',
            'documentation_paths': ['README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'SECURITY.md'] if fineract else [],
            'build_command': FINERACT_COMMAND if fineract else 'gradle clean build'}


def configure_mcp(config, context, jira_token=None, jira_email=None):
    servers = config['mcpServers']
    if context['documentation_source'] == 'repository':
        servers['project-knowledge']['disabled'] = True
        servers['github']['headers']['X-MCP-Tools'] = 'pull_request_read,issue_read,get_file_contents'
        servers['github']['autoApprove'] = ['pull_request_read', 'issue_read', 'get_file_contents']
    if not context['jira_keys']:
        servers.pop('atlassian', None)
    else:
        require(bool(jira_token), 'JIRA_AUTH_SETUP_REQUIRED: JIRA_TOKEN is missing')
        require(bool(jira_email), 'JIRA_AUTH_SETUP_REQUIRED: JIRA_EMAIL is missing')
        encoded = base64.b64encode(f'{jira_email}:{jira_token}'.encode()).decode()
        servers['atlassian'] = {
            'url': 'https://mcp.atlassian.com/v2/mcp',
            'headers': {'Authorization': 'Basic ' + encoded},
            'disabled': False,
            'autoApprove': ['getAccessibleAtlassianResources', 'getJiraIssue'],
        }
    return config


def configure_agent(agent, context):
    tools = ['@github/pull_request_read', '@github/issue_read']
    tools.append('@github/get_file_contents' if context['documentation_source'] == 'repository'
                 else '@project-knowledge/ProjectDocsLambdaTarget___search_project_docs')
    if context['jira_keys']:
        tools.extend(['@atlassian/getAccessibleAtlassianResources', '@atlassian/getJiraIssue'])
    agent['tools'] = tools
    agent['allowedTools'] = tools
    patterns = tools + [tool.removeprefix('@') for tool in tools]
    agent['permissions']['rules'] = [
        {'capability': 'builtin', 'effect': 'deny'},
        {'capability': 'mcp', 'match': patterns, 'effect': 'allow'},
        {'capability': 'mcp', 'exclude': patterns, 'effect': 'deny'},
    ]
    return agent


def main():
    repository = os.environ['GITHUB_REPOSITORY']
    pr = github_request('GET', f"/repos/{repository}/pulls/{os.environ['PR_NUMBER']}",
                        os.environ['GITHUB_PERSONAL_ACCESS_TOKEN'])
    context = context_for(pr, repository, os.environ['PR_HEAD_SHA'])
    token = None
    if context['jira_keys']:
        # Conditional lookup preserves no-Jira builds even if no Jira secret exists.
        result = subprocess.run(['aws', 'secretsmanager', 'get-secret-value',
                                 '--secret-id', 'poc/kiro-pr-reviewer',
                                 '--query', 'SecretString', '--output', 'text'],
                                capture_output=True, text=True)
        require(result.returncode == 0, 'JIRA_AUTH_SETUP_REQUIRED: CodeBuild cannot read the Jira secret')
        token = json.loads(result.stdout).get('JIRA_TOKEN')
    config_path = Path(sys.argv[1])
    config = configure_mcp(json.loads(config_path.read_text()), context, token, os.environ.get('JIRA_EMAIL'))
    config_path.chmod(0o600)
    config_path.write_text(json.dumps(config, indent=2) + '\n')
    agent_path = Path(sys.argv[3])
    agent_path.write_text(json.dumps(configure_agent(json.loads(agent_path.read_text()), context), indent=2) + '\n')
    Path(sys.argv[2]).write_text(json.dumps(context) + '\n')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        # Never print credential-bearing config or service responses.
        print(str(error) if str(error).startswith(('STALE_REVIEW:', 'JIRA_AUTH_SETUP_REQUIRED:'))
              else 'REVIEW_CONTEXT_SETUP_FAILED', file=sys.stderr)
        sys.exit(1)
