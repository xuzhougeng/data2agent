#!/usr/bin/env python
"""Prepare isolated skill-forward fixtures; this does not run or grade an Agent.

Run with a verified project Python. Give each fresh evaluator only its request,
the copied skill, project path and env.json, plus side-effect limits. Do not pass
parent conversation history or anticipated findings.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--skill',type=Path,default=REPO/'skills/data2agent')
    args = ap.parse_args()
    workspace = Path(tempfile.mkdtemp(prefix='data2agent-forward-'))
    skill = workspace/'skill'
    shutil.copytree(args.skill,skill,ignore=shutil.ignore_patterns('__pycache__','vendor'))
    scenarios=json.loads((HERE/'requests.json').read_text())
    for name,scenario in scenarios.items():
        project=workspace/name
        shutil.copytree(HERE/'fixtures'/name,project)
        (project/'.d2a').mkdir()
        report=subprocess.run([sys.executable,str(skill/'scripts/check_env.py'),'--profile','project'],capture_output=True,text=True,check=True)
        (project/'.d2a/check_env.json').write_text(report.stdout)
        env={'PY':sys.executable,'PORTAL':None,'portal_available':False,'profile':'project',
             'SKILL_ROOT':str(skill),'PROJECT_ROOT':str(project)}
        (project/'.d2a/env.json').write_text(json.dumps(env,indent=2)+'\n')
        scenario.update({'project':str(project),'skill':str(skill/'SKILL.md'),
                          'limits':'Write only within this project. Use existing verified packages; no network installs or external publication. Use the assigned localhost port and do not affect unrelated services. Preserve fixture inputs. Record verification limitations.'})
    (workspace/'evaluation-requests.json').write_text(json.dumps(scenarios,indent=2)+'\n')
    print(json.dumps({'workspace':str(workspace),'requests':scenarios},indent=2))


if __name__=='__main__':
    main()
