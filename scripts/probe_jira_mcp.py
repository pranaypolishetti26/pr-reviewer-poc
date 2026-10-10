"""Read-only, noninteractive community Jira MCP probe; never logs credentials."""

import asyncio
import json
import os
from pathlib import Path
import signal
import sys


def check(data, step):
    result = data.get('result', {})
    if data.get('error') or result.get('isError'):
        message = json.dumps(data).lower()
        reason = next((word for word in ('scope', '401', '403', '404', 'permission', 'unauthorized')
                       if word in message), 'mcp_error')
        raise ValueError(f'JIRA_MCP_BLOCKED: {step}: {reason}')
    return result


async def probe(server, issue):
    # Suppress server stderr: service errors can contain response bodies or credentials.
    # Isolate its environment from unrelated AWS/GitHub/Kiro secrets.
    env = {key: value for key, value in os.environ.items()
           if key in ('PATH', 'HOME', 'TMPDIR', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR',
                      'SSL_CERT_FILE', 'SSL_CERT_DIR', 'LANG')}
    env.update(server['env'])
    process = await asyncio.create_subprocess_exec(
        server['command'], *server.get('args', []), env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
        limit=2 * 1024 * 1024)
    request_id = 0

    async def rpc(method, params, notification=False):
        nonlocal request_id
        request_id += 1
        request = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            request['id'] = request_id
        process.stdin.write((json.dumps(request) + '\n').encode())
        await process.stdin.drain()
        if notification:
            return
        while True:
            line = await process.stdout.readline()
            if not line:
                raise ValueError('JIRA_MCP_BLOCKED: server exited before response')
            data = json.loads(line)
            if data.get('id') == request_id:
                return check(data, method)

    try:
        await rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                'clientInfo': {'name': 'codebuild-jira-probe', 'version': '2'}})
        await rpc('notifications/initialized', {}, notification=True)
        tools = await rpc('tools/list', {})
        names = {tool['name'] for tool in tools.get('tools', [])}
        if names != {'jira_get_issue'}:
            raise ValueError('JIRA_MCP_BLOCKED: expected only the read-only jira_get_issue tool')
        result = await rpc('tools/call', {'name': 'jira_get_issue', 'arguments': {
            'issue_key': issue, 'fields': 'summary,description,status',
            'comment_limit': 0, 'update_history': False}})
        payloads = [json.loads(item['text']) for item in result.get('content', [])
                    if item.get('type') == 'text']
        if not any(isinstance(item, dict) and item.get('key') == issue
                   and (item.get('description') or item.get('fields', {}).get('description'))
                   for item in payloads):
            raise ValueError('JIRA_MCP_BLOCKED: ticket description was not returned')
        print(json.dumps({'event': 'jira_mcp_probe', 'status': 'PASS', 'headless': True,
                          'server': 'mcp-atlassian', 'issue': issue}))
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()


async def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--config':
        raise ValueError('JIRA_MCP_BLOCKED: use --config with the prepared MCP configuration')
    servers = json.loads(Path(sys.argv[2]).read_text())['mcpServers']
    if 'mcp-atlassian' not in servers:
        print(json.dumps({'event': 'jira_mcp_probe', 'status': 'SKIPPED', 'reason': 'no Jira reference'}))
        return
    await asyncio.wait_for(probe(servers['mcp-atlassian'],
                                os.environ.get('JIRA_PROBE_ISSUE', 'SCRUM-5')), timeout=180)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (ValueError, KeyError, OSError, TimeoutError) as error:
        reason = str(error) if isinstance(error, ValueError) and str(error).startswith('JIRA_MCP_BLOCKED:') else type(error).__name__
        print(json.dumps({'event': 'jira_mcp_probe', 'status': 'BLOCKED', 'reason': reason}))
        sys.exit(1)
