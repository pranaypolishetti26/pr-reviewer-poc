"""Read-only, noninteractive Atlassian MCP probe; logs no credentials or ticket body."""

import base64
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = 'https://mcp.atlassian.com/v2/mcp'


def rpc(method, params, auth, session=None, request_id=1):
    headers = {'Authorization': auth, 'Content-Type': 'application/json',
               'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-03-26'}
    if session:
        headers['Mcp-Session-Id'] = session
    request = Request(URL, data=json.dumps({'jsonrpc': '2.0', 'id': request_id,
                                          'method': method, 'params': params}).encode(), headers=headers)
    with urlopen(request, timeout=30) as response:
        session = response.headers.get('Mcp-Session-Id', session)
        if 'text/event-stream' in response.headers.get('Content-Type', ''):
            for line in response:
                if line.startswith(b'data: '):
                    data = json.loads(line[6:])
                    if data.get('id') == request_id:
                        return data, session
            raise ValueError('MCP_EMPTY_RESPONSE')
        return json.load(response), session


def check(data, step):
    if data.get('error') or data.get('result', {}).get('isError'):
        # Print only bounded diagnostic classifications; raw responses are not logs.
        message = json.dumps(data).lower()
        reason = next((word for word in ('explicitly granted', 'scope', 'permission', 'unauthorized', 'disabled', 'invalid token')
                       if word in message), 'mcp_error')
        if reason == 'explicitly granted':
            reason = "requested cloudId isn't explicitly granted by the user"
        if reason == 'scope':
            scopes = sorted(set(re.findall(r'\bread:[a-z][a-z0-9:-]*', message)))
            reason = 'insufficient scopes; required: ' + ', '.join(scopes)
        if 'failed to fetch accessible products: 401' in message:
            reason = 'Failed to fetch accessible products: 401'
        raise ValueError(f'JIRA_MCP_BLOCKED: {step}: {reason}')
    return data['result']


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--config':
        servers = json.loads(Path(sys.argv[2]).read_text())['mcpServers']
        if 'atlassian' not in servers:
            print(json.dumps({'event': 'jira_mcp_probe', 'status': 'SKIPPED', 'reason': 'no Jira reference'}))
            return
        auth = servers['atlassian']['headers']['Authorization']
    else:
        encoded = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_TOKEN']}".encode()).decode()
        auth = 'Basic ' + encoded
    data, session = rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                     'clientInfo': {'name': 'codebuild-jira-probe', 'version': '1'}}, auth)
    check(data, 'initialize')
    headers = {'Authorization': auth, 'Content-Type': 'application/json',
               'Accept': 'application/json, text/event-stream'}
    if session:
        headers['Mcp-Session-Id'] = session
    with urlopen(Request(URL, headers=headers, data=json.dumps(
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'}).encode()), timeout=30):
        pass
    data, session = rpc('tools/list', {}, auth, session, 2)
    result = check(data, 'tools/list')
    names = {t['name'] for t in result.get('tools', [])}
    for name in ('getAccessibleAtlassianResources', 'getJiraIssue'):
        if name not in names:
            raise ValueError(f'JIRA_MCP_BLOCKED: required tool unavailable: {name}')
    data, session = rpc('tools/call', {'name': 'getAccessibleAtlassianResources', 'arguments': {}}, auth, session, 3)
    check(data, 'getAccessibleAtlassianResources')
    data, session = rpc('tools/call', {'name': 'getJiraIssue', 'arguments': {
        'cloudId': '888ba0e5-a89b-430c-ae7b-9d9c22c629d0',
        'issueIdOrKey': os.environ.get('JIRA_PROBE_ISSUE', 'SCRUM-5')}}, auth, session, 4)
    result = check(data, 'getJiraIssue')
    if os.environ.get('JIRA_PROBE_ISSUE', 'SCRUM-5') not in json.dumps(result):
        raise ValueError('JIRA_MCP_BLOCKED: ticket was not returned')
    print(json.dumps({'event': 'jira_mcp_probe', 'status': 'PASS', 'headless': True,
                      'issue': os.environ.get('JIRA_PROBE_ISSUE', 'SCRUM-5')}))


if __name__ == '__main__':
    try:
        main()
    except HTTPError as error:
        print(json.dumps({'event': 'jira_mcp_probe', 'status': 'BLOCKED', 'http_status': error.code,
                          'reason': 'Atlassian MCP rejected headless API-token authentication'}))
        sys.exit(1)
    except (ValueError, KeyError, URLError, TimeoutError) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({'event': 'jira_mcp_probe', 'status': 'BLOCKED', 'reason': reason}))
        sys.exit(1)
