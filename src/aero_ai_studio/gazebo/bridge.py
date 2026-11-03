import shutil
import subprocess
import sys
from aero_ai_studio.gazebo.diagnostics import command


class RosGazeboBridgeManager:
    def __init__(self):
        self.process = None

    def start_bridge(self, mappings: list[str]) -> dict:
        ros = shutil.which('ros2')
        if not ros or not command([ros,'pkg','prefix','ros_gz_bridge'])[0]:
            return {'status': 'Unavailable', 'detail': 'ros_gz_bridge not detected; optional for world launch'}
        if not mappings or any(m.startswith('-') for m in mappings):
            raise ValueError('Explicit topic@ROS_type@Gazebo_type mappings are required')
        if self.process and self.process.poll() is None:
            return self.get_status()
        self.process = subprocess.Popen([ros,'run','ros_gz_bridge','parameter_bridge',*mappings],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        return self.get_status()

    def stop_bridge(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def get_status(self) -> dict:
        return {'status': 'Running' if self.process and self.process.poll() is None else 'Stopped'}

    def list_topics(self) -> list[str]:
        ros = shutil.which('ros2')
        ok, text = command([ros, 'topic', 'list']) if ros else (False, '')
        return text.splitlines() if ok else []
