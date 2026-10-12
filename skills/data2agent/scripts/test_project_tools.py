#!/usr/bin/env python
"""Behavioral checks for acquisition integrity, resume, invalidation and failure gates."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys
import time
import os
import subprocess
import shlex
from unittest.mock import patch

import fetch_sources
import run_pipeline
from project_io import project_lock
from verify_mcp_server import Stdio


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='d2a-project-tools-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content if isinstance(content,str) else json.dumps(content))
        return path

    def acquire(self, rows, **kwargs):
        plan = self.write('source-plan.json', rows)
        with contextlib.redirect_stdout(io.StringIO()):
            return fetch_sources.run(self.root,plan,workers=1,**kwargs)

    def pipeline(self, steps, **kwargs):
        plan = self.write('pipeline.json',{'version':1,'steps':steps})
        with contextlib.redirect_stdout(io.StringIO()):
            return run_pipeline.run(self.root,plan,**kwargs)


class Sources(Workspace):
    def test_namespaced_files_are_pinned_and_reused(self):
        self.write('inputs/a/counts.txt','1\n2\n')
        self.write('inputs/b/counts.txt','3\n4\n')
        rows=[{'id':n,'local_path':f'inputs/{n}/counts.txt','path':f'raw/{n}/counts.txt'} for n in ['a','b']]
        self.assertTrue(self.acquire(rows)['ok'])
        receipt=json.loads((self.root/'work/sources.json').read_text())
        self.assertNotEqual(receipt[0]['sha256'],receipt[1]['sha256'])
        self.write('inputs/a/counts.txt','changed upstream')
        self.assertTrue(self.acquire(rows)['ok'])
        self.assertEqual((self.root/'raw/a/counts.txt').read_text(),'1\n2\n')
        self.assertEqual(receipt,json.loads((self.root/'work/sources.json').read_text()))
        self.assertIn('"operation": "reused"',(self.root/'.pipeline/sources.jsonl').read_text())

    def test_modified_input_is_refused(self):
        self.write('inputs/data','author values')
        rows=[{'id':'a','local_path':'inputs/data','path':'raw/data'}]
        self.acquire(rows)
        self.write('raw/data','edited values')
        report=self.acquire(rows)
        self.assertFalse(report['ok'])
        self.assertIn('modified',report['failures'][0]['error'])

    def test_refresh_preserves_previous_bytes_and_checks_new_pin(self):
        self.write('inputs/data','v1')
        rows=[{'id':'a','local_path':'inputs/data','path':'raw/data'}]
        self.acquire(rows)
        self.write('inputs/data','v2')
        rows[0]['sha256']=hashlib.sha256(b'wrong').hexdigest()
        self.assertFalse(self.acquire(rows,refresh=True)['ok'])
        self.assertEqual((self.root/'raw/data').read_text(),'v1')
        rows[0]['sha256']=hashlib.sha256(b'v2').hexdigest()
        self.assertTrue(self.acquire(rows,refresh=True)['ok'])
        self.assertEqual((self.root/'raw/data').read_text(),'v2')
        self.assertEqual(next((self.root/'raw/.history').rglob('data')).read_text(),'v1')

    def test_refresh_repairs_a_modified_recorded_input(self):
        self.write('inputs/data','author values')
        rows=[{'id':'a','local_path':'inputs/data','path':'raw/data'}]
        self.acquire(rows)
        self.write('raw/data','truncated')
        self.assertTrue(self.acquire(rows,refresh=True)['ok'])
        self.assertEqual((self.root/'raw/data').read_text(),'author values')
        self.assertEqual(next((self.root/'raw/.history').rglob('data')).read_text(),'truncated')

    def test_coexists_with_fetch_geo_receipts(self):
        import fetch_geo
        self.write('raw/GSE1_family.soft.gz','x')
        self.write('work/sources.json',[
            {'name':'GSE1_family.soft.gz','url':'https://geo/x','path':'raw/GSE1_family.soft.gz','bytes':1,'sha256':hashlib.sha256(b'x').hexdigest(),'downloaded':True,'note':'series matrix'},
            {'name':'big.tar','url':'https://geo/big.tar','path':None,'bytes':None,'sha256':None,'downloaded':False,'note':'listed only'}])
        self.write('inputs/labels.tsv','a\tb\n')
        self.assertTrue(self.acquire([{'id':'labels','local_path':'inputs/labels.tsv','path':'raw/labels.tsv'}])['ok'])
        items=fetch_geo.load_sources(self.root/'work/sources.json')
        self.assertEqual({i['name'] for i in items},{'GSE1_family.soft.gz','big.tar','labels'})
        self.assertEqual([i['downloaded'] for i in items],[True,False,True])

    def test_client_errors_are_not_retried(self):
        import urllib.error
        calls=[]
        def fail(request,timeout):
            calls.append(1); raise urllib.error.HTTPError(request.full_url,404,'Not Found',{},None)
        with patch.object(fetch_sources.urllib.request,'urlopen',side_effect=fail),patch.object(fetch_sources.time,'sleep'):
            report=self.acquire([{'id':'a','url':'https://example.org/a','path':'raw/a'}])
        self.assertEqual(len(calls),1)
        self.assertIn('404',report['failures'][0]['error'])

    def test_existing_unrecorded_destination_is_not_attributed_to_url(self):
        self.write('raw/data','unrelated')
        with patch.object(fetch_sources.urllib.request,'urlopen',side_effect=AssertionError('must not download')):
            report=self.acquire([{'id':'a','url':'https://example.org/data','path':'raw/data'}])
        self.assertFalse(report['ok'])
        self.assertFalse((self.root/'work/sources.json').exists())

    def test_bounds_collisions_and_bad_pins(self):
        for rows in [
            [{'id':'a','local_path':'input','path':'raw/../outside'}],
            [{'id':'a','local_path':'input','path':'raw'}],
            [{'id':'a','local_path':'input','path':'raw/a','sha256':'bad'}],
            [{'id':'a','local_path':'input','path':'raw/a'},{'id':'b','local_path':'input','path':'raw/a'}],
        ]:
            with self.assertRaises(ValueError):self.acquire(rows)

    def test_transfer_length_and_byte_limit(self):
        class Response(io.BytesIO):
            headers={'Content-Length':'20'}
        with patch.object(fetch_sources.urllib.request,'urlopen',side_effect=lambda request,timeout:Response(b'123')),patch.object(fetch_sources.time,'sleep'):
            report=self.acquire([{'id':'a','url':'https://example.org/a','path':'raw/a'}])
        self.assertFalse(report['ok'])
        self.assertFalse((self.root/'raw/a').exists())
        self.write('inputs/data','1234567890')
        self.assertFalse(self.acquire([{'id':'b','local_path':'inputs/data','path':'raw/b'}],max_bytes=5)['ok'])


class Pipeline(Workspace):
    def setUp(self):
        super().setUp()
        self.write('raw/numbers','2\n3\n')
        self.write('raw/other','7\n')
        self.write('requirements.lock','example-environment-v1\n')
        self.write('pipeline/sum.py',"from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_text(str(sum(int(v) for v in Path(sys.argv[1]).read_text().split())))\n")
        self.write('pipeline/double.py',"from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_text(str(int(Path(sys.argv[1]).read_text())*2))\n")
        self.write('pipeline/check.py',"from pathlib import Path\nimport sys\nassert int(Path(sys.argv[1]).read_text())>=0\n")
        self.steps=[
            {'id':'sum','command':['{python}','pipeline/sum.py','raw/numbers','work/sum'],'inputs':['raw/numbers','requirements.lock'],'outputs':['work/sum'],'checks':[['{python}','pipeline/check.py','work/sum']]},
            {'id':'double','needs':['sum'],'command':['{python}','pipeline/double.py','work/sum','pkg/double'],'inputs':['work/sum'],'outputs':['pkg/double']},
            {'id':'other','command':['{python}','pipeline/sum.py','raw/other','pkg/other'],'inputs':['raw/other'],'outputs':['pkg/other']}
        ]

    def test_reuse_and_dependency_invalidation(self):
        self.assertTrue(self.pipeline(self.steps)['ok'])
        self.assertEqual((self.root/'pkg/double').read_text(),'10')
        second=self.pipeline(self.steps)
        self.assertEqual([s['status'] for s in second['steps']],['reused']*3)
        self.write('raw/numbers','4\n5\n')
        third=self.pipeline(self.steps)
        self.assertEqual([s['status'] for s in third['steps']],['succeeded','succeeded','reused'])
        self.assertEqual((self.root/'pkg/double').read_text(),'18')

    def test_corruption_and_code_changes_invalidate(self):
        self.pipeline(self.steps)
        self.write('pkg/double','bad output')
        result=self.pipeline(self.steps)
        self.assertEqual([s['status'] for s in result['steps']],['reused','succeeded','reused'])
        self.write('pipeline/double.py',"from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_text(str(int(Path(sys.argv[1]).read_text())*3))\n")
        self.pipeline(self.steps)
        self.assertEqual((self.root/'pkg/double').read_text(),'15')

    def test_checks_fail_and_restore_previous_output(self):
        self.pipeline(self.steps)
        self.write('raw/numbers','-5\n')
        with self.assertRaises(RuntimeError):self.pipeline(self.steps)
        self.assertEqual((self.root/'work/sum').read_text(),'5')
        self.assertEqual(json.loads((self.root/'.pipeline/tasks/sum.json').read_text())['status'],'failed')
        self.assertEqual((self.root/'pkg/double').read_text(),'10')

    def test_exit_zero_without_output_cannot_reuse_stale_file(self):
        self.pipeline(self.steps)
        self.steps[0]['command']=['{python}','-c','pass']
        self.steps[0]['checks']=[]
        with self.assertRaises(FileNotFoundError):self.pipeline(self.steps)
        self.assertEqual((self.root/'work/sum').read_text(),'5')

    def test_timeout_is_failed_not_complete(self):
        step={'id':'wait','command':['{python}','-c','import time; time.sleep(10)'], 'inputs':[], 'outputs':['work/wait'], 'timeout_seconds':0.1}
        with self.assertRaises(Exception):self.pipeline([step])
        self.assertEqual(json.loads((self.root/'.pipeline/tasks/wait.json').read_text())['status'],'failed')

    def test_timeout_bounds_the_whole_step_and_hash_cache_is_persisted(self):
        step={'id':'wait','command':['{python}','-c','pass'],'inputs':[],'outputs':['work/wait'],'timeout_seconds':0.5,
              'checks':[['{python}','-c','import time; time.sleep(10)']]*3}
        start=time.monotonic()
        with self.assertRaises(Exception):self.pipeline([step])
        self.assertLess(time.monotonic()-start,5)
        self.assertTrue(self.pipeline(self.steps)['ok'])
        self.assertTrue((self.root/'.pipeline/hash-cache.json').exists())

    def test_stale_running_receipt_needs_force(self):
        self.write('.pipeline/tasks/sum.json',{'step':'sum','status':'running','pid':os.getpid()})
        with self.assertRaises(RuntimeError):self.pipeline(self.steps,selected=['sum'])
        self.assertTrue(self.pipeline(self.steps,selected=['sum'],force=True)['ok'])

    def test_invalid_graph_and_output_ownership(self):
        cases=[]
        cyc=json.loads(json.dumps(self.steps));cyc[0]['needs']=['double'];cases.append(cyc)
        unknown=json.loads(json.dumps(self.steps));unknown[0]['needs']=['missing'];cases.append(unknown)
        raw=json.loads(json.dumps(self.steps));raw[0]['outputs']=['raw/numbers'];cases.append(raw)
        overlapping=json.loads(json.dumps(self.steps));overlapping[1]['outputs']=['work/sum/child'];cases.append(overlapping)
        for steps in cases:
            with self.assertRaises(ValueError):self.pipeline(steps)
        self.assertEqual((self.root/'raw/numbers').read_text(),'2\n3\n')

    def test_selected_steps_include_only_their_dependencies(self):
        report=self.pipeline(self.steps,selected=['double'])
        self.assertEqual([s['id'] for s in report['steps']],['sum','double'])
        self.assertFalse((self.root/'pkg/other').exists())

    def test_dry_run_has_no_task_state_and_lock_prevents_duplicate_execution(self):
        self.pipeline(self.steps,dry_run=True)
        self.assertFalse((self.root/'.pipeline').exists())
        with project_lock(self.root,'pipeline'):
            with self.assertRaises(RuntimeError):self.pipeline(self.steps)


class MCPTransport(Workspace):
    def test_request_timeout_bounds_a_silent_server(self):
        server=Stdio([sys.executable,'-c','import time; time.sleep(30)'],timeout=0.1)
        try:
            start=time.monotonic()
            with self.assertRaises(TimeoutError):server.request('initialize')
            self.assertLess(time.monotonic()-start,2)
        finally:server.close()


def host_python_satisfies_core_profile():
    skill=Path(__file__).resolve().parents[1]
    return subprocess.run([sys.executable,str(skill/'scripts/check_env.py'),'--profile','project'],capture_output=True).returncode==0


class Bootstrap(Workspace):
    @unittest.skipUnless(host_python_satisfies_core_profile(),'host Python lacks the core profile; run with a verified project Python')
    def test_project_profile_uses_core_and_produces_json_without_warning_noise(self):
        project=self.root/'project with spaces'
        (project/'.d2a').mkdir(parents=True)
        (project/'.d2a/venv').symlink_to(Path(sys.prefix),target_is_directory=True)
        log=self.root/'uv-calls.txt'
        stub=self.write('bin/uv','#!/bin/sh\nprintf "%s\\n" "$*" >> '+shlex.quote(str(log))+'\n')
        stub.chmod(0o755)
        skill=Path(__file__).resolve().parents[1]
        r=subprocess.run(['sh',str(skill/'scripts/bootstrap.sh'),str(project),'--profile','project'],
                         env={**os.environ,'PATH':str(stub.parent)+os.pathsep+os.environ['PATH']},
                         capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        env=json.loads((project/'.d2a/env.json').read_text())
        check=json.loads((project/'.d2a/check_env.json').read_text())
        self.assertEqual(env['profile'],'project')
        self.assertTrue(check['ok'])
        self.assertIn('requirements-core.txt',log.read_text())
        self.assertNotIn('requirements.txt',log.read_text())

    def test_working_directory_and_large_stderr_do_not_deadlock(self):
        self.write('server.py',"import json,sys,os\nfor line in sys.stdin:\n m=json.loads(line)\n sys.stderr.write('log'*40000);sys.stderr.flush()\n print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':{'cwd':os.getcwd()}}),flush=True)\n")
        server=Stdio([sys.executable,'server.py'],cwd=self.root,timeout=2)
        try:self.assertEqual(server.request('test')['cwd'],str(self.root))
        finally:server.close()


if __name__=='__main__':
    unittest.main()
