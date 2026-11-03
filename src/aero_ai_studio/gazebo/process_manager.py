from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from aero_ai_studio.gazebo.diagnostics import gazebo_status


class GazeboProcessManager:
    def __init__(self):
        self.process=None
        self.log_stream=None
        self.partition='aero_'+uuid4().hex
        self.availability={'available':False}

    def launch(self,world: Path,gui=False,paused=True):
        status=gazebo_status()
        self.availability=status
        if not status['available']:return status
        from aero_ai_studio.gazebo.discovery import launch_arguments
        args,help_text=launch_arguments(status['executable'],world,gui,paused)
        self.runtime_help=help_text
        env=dict(os.environ,GZ_PARTITION=self.partition)
        self.log_stream=world.with_name('gazebo.log').open('ab')
        try:
            self.process=subprocess.Popen(args,env=env,stdout=self.log_stream,stderr=subprocess.STDOUT,
                            start_new_session=sys.platform!='win32',creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        except OSError:
            self.close()
            raise
        return self.status()

    def status(self):
        return {'status':'Running' if self.process and self.process.poll() is None else 'Stopped',
                'available':self.availability['available'],'pid':self.process.pid if self.process else None,
                'exit_code':self.process.poll() if self.process else None,'partition':self.partition}

    def close(self):
        if self.process and self.process.poll() is None:
            if sys.platform!='win32':
                import signal
                try:os.killpg(self.process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            else:self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if sys.platform!='win32':
                    import signal
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                else:self.process.kill()
                self.process.wait(timeout=5)
        if self.log_stream:self.log_stream.close();self.log_stream=None
