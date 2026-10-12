#!/usr/bin/env python
"""Execute a reviewed project task DAG with content-based resume and real gates.

Usage: python run_pipeline.py --project PATH --plan pipeline.json [--step ID]
Each step has id, command (argv array), inputs, outputs, and optional needs,
checks (argv arrays), env, parameters and timeout_seconds. Commands are run
without an implicit shell. Tokens: {python}, {project}, {skill}.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid

import project_io
from project_io import append_event, artifact, atomic_json, canonical_hash, now, project_lock, project_path

SKILL = Path(__file__).resolve().parents[1]


def overlap(left, right):
    return left == right or left in right.parents or right in left.parents


def load_plan(path, root):
    plan = json.loads(Path(path).read_text())
    if plan.get('version') != 1 or not isinstance(plan.get('steps'), list) or not plan['steps']:
        raise ValueError('Expected version=1 and a nonempty steps list')
    steps, owners = {}, []
    for step in plan['steps']:
        name = step.get('id', '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', name) or name in steps:
            raise ValueError('Step IDs must be unique ASCII identifiers')
        for command in [step.get('command')] + step.get('checks', []):
            if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
                raise ValueError(name + ': commands/checks must be nonempty argv arrays')
        for field in ['inputs','outputs','needs']:
            if not isinstance(step.get(field, []), list) or not all(isinstance(s,str) for s in step.get(field, [])):
                raise ValueError(name + ': ' + field + ' must be a list of paths/IDs')
        if not step.get('outputs'):
            raise ValueError(name + ': declare outputs; process exit alone is not success')
        if not isinstance(step.get('env', {}), dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in step.get('env', {}).items()):
            raise ValueError(name + ': env must contain string keys and values')
        timeout = step.get('timeout_seconds', 3600)
        if not isinstance(timeout, (float,int)) or timeout <= 0:
            raise ValueError(name + ': timeout_seconds must be positive')
        inputs = []
        for value in step.get('inputs', []):
            inputs.append(Path(value).resolve() if Path(value).is_absolute() else project_path(root, value))
        for value in step['outputs']:
            target = project_path(root, value)
            if target.relative_to(root).parts[0] in {'raw','.pipeline','.d2a','.git'}:
                raise ValueError(name + ': outputs cannot replace raw inputs, state or environments')
            if any(overlap(target, p) for p in inputs):
                raise ValueError(name + ': an output overlaps an input; write a new artifact')
            if any(overlap(target, p) for _,p in owners):
                raise ValueError(name + ': output ownership overlaps another declared output')
            owners.append((name,target))
        steps[name] = step
    ordered, visiting = [], set()
    def visit(name):
        if name not in steps:
            raise ValueError('Unknown dependency: ' + name)
        if name in visiting:
            raise ValueError('Cyclic dependency: ' + name)
        if name in ordered:
            return
        visiting.add(name)
        for parent in steps[name].get('needs', []):
            visit(parent)
        visiting.remove(name)
        ordered.append(name)
    for name in steps:
        visit(name)
    return steps, ordered


def expand(argv, root):
    tokens = {'{python}':sys.executable, '{project}':str(root), '{skill}':str(SKILL)}
    result = []
    for value in argv:
        for token, replacement in tokens.items():
            value = value.replace(token, replacement)
        result.append(value)
    return result


def input_records(step, root):
    declared = list(step.get('inputs', []))
    outputs = [project_path(root, value) for value in step['outputs']]
    # Also capture project-local command/check scripts even if accidentally omitted.
    for command in [step['command']] + step.get('checks', []):
        for value in expand(command, root):
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = root / candidate
            try:
                if candidate.is_file() and candidate.resolve().is_relative_to(root) and not any(overlap(candidate.resolve(), p) for p in outputs):
                    rel = str(candidate.resolve().relative_to(root))
                    if rel not in declared:
                        declared.append(rel)
            except OSError:
                continue
    return {name:artifact(Path(name) if Path(name).is_absolute() else project_path(root,name)) for name in declared}


def output_records(step, root):
    return {name:artifact(project_path(root, name)) for name in step['outputs']}


def remove_owned(path):
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def run_command(argv, root, env, timeout, log, receipt, state_path):
    command = expand(argv, root)
    with log.open('ab') as output:
        output.write(('\nARGV ' + json.dumps(command) + '\n').encode())
        output.flush()
        process = subprocess.Popen(command, cwd=root, env={**os.environ, **env}, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        receipt.update({'pid':process.pid,'current_command':command})
        atomic_json(state_path, receipt)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            # Only the process group created by this invocation is affected.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise
    if code != 0:
        raise RuntimeError(f'Command exited {code}; see {log.relative_to(root)}')


def execute_step(root, step, dependencies, runtime, force=False):
    name = step['id']
    state_path = project_path(root, f'.pipeline/tasks/{name}.json')
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    inputs = input_records(step, root)
    definition = {'step':step,'inputs':inputs,'dependencies':dependencies,'runtime':{'python':runtime['python']}}
    fingerprint = canonical_hash(definition)
    if not force and previous.get('status') == 'succeeded' and previous.get('fingerprint') == fingerprint:
        try:
            intact = output_records(step, root) == previous['outputs']
        except (FileNotFoundError, ValueError):
            intact = False
        if intact:
            append_event(project_path(root, '.pipeline/events.jsonl'), {'step':name,'status':'reused','at':now(),'fingerprint':fingerprint})
            return {**previous,'reused':True}
    # project_lock already excludes a second runner; this only catches an orphaned child
    # of a killed runner. PID reuse makes it a heuristic, so --force bypasses it.
    if not force and previous.get('status') == 'running' and previous.get('pid'):
        try:
            os.kill(previous['pid'], 0)
        except (ProcessLookupError, PermissionError):
            pass
        else:
            raise RuntimeError(name + f": previous process {previous['pid']} may still be running; inspect it, then rerun with --force")
    attempt = uuid.uuid4().hex
    backup_dir = project_path(root, f'.pipeline/attempts/{name}/{attempt}')
    backup_dir.mkdir(parents=True)
    log = backup_dir / 'run.log'
    receipt = {'step':name,'attempt':attempt,'status':'running','started_at':now(),'fingerprint':fingerprint,
               'definition':definition,'packages':runtime['packages'],'log':str(log.relative_to(root))}
    atomic_json(state_path, receipt)
    append_event(project_path(root, '.pipeline/events.jsonl'), receipt)
    backups, managed = [], []
    started = time.monotonic()
    try:
        # Isolate previous outputs so an exit-0 no-op cannot pass on stale files.
        for index,value in enumerate(step['outputs']):
            dest = project_path(root,value)
            if dest.exists():
                backup = backup_dir / ('previous-' + str(index))
                dest.rename(backup)
                backups.append((dest,backup))
            managed.append(dest)
            dest.parent.mkdir(parents=True,exist_ok=True)
        deadline = started + step.get('timeout_seconds',3600)
        env = step.get('env',{})
        for command in [step['command']] + step.get('checks',[]):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(expand(command,root), step.get('timeout_seconds',3600))
            run_command(command,root,env,remaining,log,receipt,state_path)
        outputs = output_records(step,root)
        if input_records(step,root) != inputs:
            raise ValueError('An input changed during execution; results are not reusable')
        receipt.update({'status':'succeeded','outputs':outputs,'checks_passed':len(step.get('checks',[]))})
    except BaseException as error:
        for dest in managed:
            remove_owned(dest)
        for dest,backup in backups:
            dest.parent.mkdir(parents=True,exist_ok=True)
            backup.rename(dest)
        receipt.update({'status':'failed','error':str(error) or type(error).__name__})
        raise
    finally:
        receipt.pop('pid',None)
        receipt.update({'finished_at':now(),'duration_seconds':round(time.monotonic()-started,3)})
        atomic_json(state_path,receipt)
        append_event(project_path(root,'.pipeline/events.jsonl'),receipt)
    # Previous generated outputs remain in the attempt directory for explicit
    # cleanup after validation; never delete a prior scientific release silently.
    return {**receipt,'reused':False}


def run(root, plan_path, selected=None, force=False, dry_run=False):
    root = Path(root).resolve()
    steps, order = load_plan(plan_path,root)
    if selected:
        keep = set()
        def add(name):
            if name not in steps:
                raise ValueError('Unknown step: '+name)
            if name not in keep:
                keep.add(name)
                for parent in steps[name].get('needs',[]): add(parent)
        for name in selected: add(name)
        order = [n for n in order if n in keep]
    if dry_run:
        return {'ok':True,'dry_run':True,'steps':[{'id':n,'command':expand(steps[n]['command'],root)} for n in order]}
    runtime = {'python':sys.version,'packages':sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions() if d.metadata['Name'])}
    completed, results = {}, []
    with project_lock(root,'pipeline'):
        project_io.load_hash_cache(root)
        try:
            for name in order:
                deps = {n:{'fingerprint':completed[n]['fingerprint'],'outputs':completed[n]['outputs']} for n in steps[name].get('needs',[])}
                receipt = execute_step(root,steps[name],deps,runtime,force)
                completed[name] = receipt
                result = {'id':name,'status':'reused' if receipt['reused'] else 'succeeded','fingerprint':receipt['fingerprint']}
                results.append(result)
                print(json.dumps(result),flush=True)
            report = {'ok':True,'steps':results,'finished_at':now()}
        except BaseException as error:
            report = {'ok':False,'steps':results,'failed_step':name,'error':str(error) or type(error).__name__,'finished_at':now()}
            atomic_json(project_path(root,'reports/pipeline.json'),report)
            raise
        atomic_json(project_path(root,'reports/pipeline.json'),report)
        project_io.save_hash_cache(root)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',type=Path,required=True)
    ap.add_argument('--plan',type=Path,default=Path('pipeline.json'))
    ap.add_argument('--step',action='append')
    ap.add_argument('--force',action='store_true')
    ap.add_argument('--dry-run',action='store_true')
    args = ap.parse_args()
    plan = args.plan if args.plan.is_absolute() else args.project/args.plan
    try:
        report = run(args.project,plan,args.step,args.force,args.dry_run)
    except Exception as error:
        report = {'ok':False,'error':str(error)}
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
