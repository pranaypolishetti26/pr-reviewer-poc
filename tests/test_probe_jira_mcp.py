import asyncio
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import probe_jira_mcp as probe


class ProbeTests(unittest.TestCase):
    def run_server(self, names, result):
        # A real stdio process checks framing and shutdown without network or credentials.
        source = '''import json,sys,os
assert 'GITHUB_PERSONAL_ACCESS_TOKEN' not in os.environ
for line in sys.stdin:
 request=json.loads(line)
 if 'id' not in request: continue
 method=request['method']
 if method=='initialize': result={'protocolVersion':'2025-03-26'}
 elif method=='tools/list': result={'tools':[{'name':n} for n in NAMES]}
 else:
  assert request['params']['arguments']['issue_key']=='SCRUM-5'
  result=RESULT
 print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)
'''.replace('NAMES', repr(names)).replace('RESULT', repr(result))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'server.py'
            path.write_text(source)
            server = {'command': sys.executable, 'args': [str(path)], 'env': {}}
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                asyncio.run(asyncio.wait_for(probe.probe(server, 'SCRUM-5'), 5))
            return json.loads(output.getvalue())

    def test_actual_ticket_description_is_required(self):
        ticket = {'key': 'SCRUM-5', 'description': 'Acceptance criteria'}
        result = {'content': [{'type': 'text', 'text': json.dumps(ticket)}]}
        self.assertEqual(self.run_server(['jira_get_issue'], result)['status'], 'PASS')
        result['content'][0]['text'] = json.dumps({'key': 'SCRUM-5', 'error': 'missing'})
        with self.assertRaisesRegex(ValueError, 'description was not returned'):
            self.run_server(['jira_get_issue'], result)

    def test_write_tools_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'expected only'):
            self.run_server(['jira_get_issue', 'jira_create_issue'], {})

    def test_tool_errors_are_not_ticket_evidence(self):
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.run_server(['jira_get_issue'], {'isError': True, 'content': [
                {'type': 'text', 'text': '401 Unauthorized: scope does not match for SCRUM-5'}]})
