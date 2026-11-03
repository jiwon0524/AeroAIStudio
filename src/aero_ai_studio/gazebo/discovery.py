from __future__ import annotations
import os
import re
import subprocess
import sys
import shutil


def parse_names(text: str) -> list[str]:
    return sorted(set(re.findall(r'(?m)^\s*(/[^\s]+)\s*$',text)))


def discover(executable: str,partition: str | None=None) -> dict:
    env=dict(os.environ)
    if partition:env['GZ_PARTITION']=partition
    result={}
    for kind in ('topic','service'):
        p=subprocess.run([executable,kind,'-l'],capture_output=True,text=True,timeout=5,env=env,
                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        if p.returncode:raise RuntimeError(f'Gazebo {kind} discovery failed: {p.stderr}')
        result[kind+'s']=parse_names(p.stdout)
    worlds=sorted(set(n.split('/')[2] for n in result['services'] if n.startswith('/world/') and n.endswith('/control')))
    result['worlds']=worlds
    return result


def launch_arguments(executable,world,gui=False,paused=True):
    p=subprocess.run([executable,'sim','--help'],capture_output=True,text=True,timeout=5,
                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    help_text=p.stdout+p.stderr
    if p.returncode:raise RuntimeError('Cannot inspect installed gz sim options')
    args=[executable,'sim']
    if not paused:
        if '--run' not in help_text:raise RuntimeError('Installed simulator does not advertise --run')
        args.append('--run')
    if not gui:
        if '--server-only' in help_text:args.append('--server-only')
        elif re.search(r'(^|[\s,])-s([\s,]|$)',help_text):args.append('-s')
        else:raise RuntimeError('No advertised server-only option')
        if '--headless-rendering' not in help_text:raise RuntimeError('No advertised headless renderer; use a GUI-capable runtime')
        args.append('--headless-rendering')
    return [*args,str(world.resolve())],help_text
