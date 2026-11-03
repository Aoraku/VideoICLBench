#!/usr/bin/env python3
"""Run a Python script/module in this PID with an honest, auditable display name.

Does not allocate GPU, launch children, replace environments, or install signals.
The target retains the original interpreter, venv, arguments, cwd and environment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import re
import sys
import time
from urllib.parse import urlsplit,urlunsplit

DISPLAY_NAME='robodojo-embodiedevo'
CODEC_VERSION='1.3.6'  # setproctitle, not request-body compression
HERE=Path(__file__).resolve().parent


def start_ticks(pid):
    if sys.platform!='linux':return None
    text=Path(f'/proc/{pid}/stat').read_text()
    return int(text[text.rindex(')')+2:].split()[19])


def safe_argv(argv):
    secret_flags={'--api-key','--apikey','--api_key','--token','--access-token','--refresh-token','--secret','--password','--authorization','--auth-token','--bearer-token'}
    output=[];redact=False
    for raw in argv:
        value=str(raw)
        if redact:output.append('[REDACTED]');redact=False;continue
        flag=value.split('=',1)[0]
        if flag in secret_flags:
            output.append(flag+'=[REDACTED]' if '=' in value else flag);redact='=' not in value;continue
        if re.search(r'(?i)(?:bearer\s+|(?<![A-Za-z0-9])sk-[A-Za-z0-9]|(?:api[_-]?key|access[_-]?token|password|secret|authorization)=)',value):
            output.append('[REDACTED_SECRET_ARGUMENT]');continue
        # Remove credentials and ALL query/fragment content, including --proxy=URL.
        if '://' in value:
            prefix=''
            if value.startswith('--') and '=' in value:
                prefix,value=value.split('=',1);prefix+='='
            try:
                u=urlsplit(value)
                host=u.hostname or ''
                if ':' in host:host='['+host+']'
                if u.port:host+=':'+str(u.port)
                if u.username is not None:host='[REDACTED]@'+host
                value=prefix+urlunsplit((u.scheme,host,u.path,'',''))
            except ValueError:value='[REDACTED_INVALID_URL]'
        output.append(value)
    return output


def set_display_name():
    # No mutation of shared venvs: Linux deployment supplies this release-local wheel.
    vendor=HERE/'vendor'/f'{sys.platform}-cp{sys.version_info.major}{sys.version_info.minor}'
    inserted=vendor.is_dir()
    if inserted:sys.path.insert(0,str(vendor))
    prior_noenv=os.environ.get('SPT_NOENV')
    os.environ['SPT_NOENV']='1'
    try:
        import setproctitle
        if setproctitle.__version__!=CODEC_VERSION:
            raise RuntimeError('release requires setproctitle '+CODEC_VERSION)
        setproctitle.setproctitle(DISPLAY_NAME)
        if setproctitle.getproctitle()!=DISPLAY_NAME:raise RuntimeError('process title readback differs')
        return dict(module_path=setproctitle.__file__,version=setproctitle.__version__,title=setproctitle.getproctitle(),environment_buffer_preserved=True)
    finally:
        if inserted:sys.path.remove(str(vendor))
        if prior_noenv is None:os.environ.pop('SPT_NOENV',None)
        else:os.environ['SPT_NOENV']=prior_noenv


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if '--' not in args:raise ValueError('separate launcher arguments and target with --')
    split=args.index('--');own,target=args[:split],args[split+1:]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identity-dir',type=Path,required=True);p.add_argument('--role',required=True)
    options=p.parse_args(own)
    if not target or target[0]=='-m' and len(target)<2:raise ValueError('Python script or -m module required')
    if target[0].startswith('-') and target[0]!='-m':raise ValueError('Only Python script and -m module entrypoints supported')
    if not options.role or len(options.role)>160:raise ValueError('invalid role')
    pid=os.getpid();ticks=start_ticks(pid)
    original=dict(schema='robodojo-process-identity-v1',pid=pid,start_ticks=ticks,
        ppid=os.getppid(),role=options.role,display_name=DISPLAY_NAME,
        interpreter=sys.executable,base_executable=getattr(sys,'_base_executable',None),
        prefix=sys.prefix,base_prefix=sys.base_prefix,cwd=os.getcwd(),
        original_argv=safe_argv([sys.executable,*target]),
        argv_sha256=hashlib.sha256(json.dumps([sys.executable,*target],ensure_ascii=False).encode()).hexdigest(),
        environment_passthrough={k:os.environ.get(k) for k in ('DISPLAY','PYTHONPATH')},
        created_unix=time.time(),renaming_mechanism='setproctitle_after_python_initialization')
    options.identity_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    record=options.identity_dir/f'process-{pid}-{ticks if ticks is not None else time.time_ns()}.private.json'
    executable,prefix,base_prefix=sys.executable,sys.prefix,sys.base_prefix
    display=os.environ.get('DISPLAY');pythonpath=os.environ.get('PYTHONPATH')
    environment_before=dict(os.environ)
    original['title_readback']=set_display_name()
    if (sys.executable,sys.prefix,sys.base_prefix,os.environ.get('DISPLAY'),os.environ.get('PYTHONPATH'))!=(executable,prefix,base_prefix,display,pythonpath):
        raise RuntimeError('process title changed Python environment')
    if dict(os.environ)!=environment_before:raise RuntimeError('process title changed environment values')
    fd=os.open(record,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(original,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    # Restore exactly the path/argv convention of a direct Python entrypoint.
    sys.orig_argv=[sys.executable,*target]
    if target[0]=='-m':
        sys.argv=[target[1],*target[2:]]
        sys.path[0]=os.getcwd()
        runpy.run_module(target[1],run_name='__main__',alter_sys=True)
    else:
        script=target[0]
        sys.argv=list(target)
        sys.path[0]=str(Path(script).resolve().parent)
        runpy.run_path(script,run_name='__main__')


if __name__=='__main__':main()
