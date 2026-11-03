from __future__ import annotations
import importlib.metadata
import platform
import shutil
import subprocess
import sys
import os


def command(args: list[str], timeout: float = 3) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        return result.returncode == 0, (result.stdout + result.stderr).strip()[:2000]
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)


def gazebo_status(probe: bool=True) -> dict:
    executable = shutil.which('gz')
    if not executable:
        return {'status': 'Unavailable', 'available': False, 'executable': None,
                'detail': 'Gazebo not detected. Target: Ubuntu 24.04 + Gazebo Harmonic. GridWorld remains available.'}
    if not probe:return {'status':'Available','available':True,'executable':executable,'detail':'gz executable detected; runtime/bindings pending verification'}
    ok, version = command([executable, 'sim', '--versions'])
    return {'status': 'Available' if ok else 'Unavailable', 'available': ok, 'executable': executable,
            'detail': version, 'target': 'Harmonic / gz-sim 8; Ionic 9 and Jetty 10 need runtime validation'}


def diagnose(full: bool = False) -> dict:
    def package(name: str) -> dict:
        try:
            return {'status': 'Available', 'version': importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:
            return {'status': 'Optional', 'version': None}
    ros = shutil.which('ros2')
    bridge_ok, bridge_text = command([ros, 'pkg', 'prefix', 'ros_gz_bridge']) if ros and full else (False, 'Not probed' if ros else 'ROS2 not detected')
    result = {'OS': platform.platform(), 'Python': sys.version.split()[0], 'PyTorch': package('torch'),
              'Gazebo': gazebo_status(probe=full), 'ROS2': {'status': 'Available' if ros else 'Optional', 'executable': ros},
              'ros_gz_bridge': {'status': 'Available' if bridge_ok else 'Optional', 'detail': bridge_text},
              'CUDA': {'status': 'Optional', 'detail': 'Not probed (use Refresh diagnostics)'},
              'GPU': {'status': 'Optional', 'detail': 'Not probed'}}
    if full:
        if result['PyTorch']['version']:
            try:
                import torch
                available = torch.cuda.is_available()
                result['CUDA'] = {'status': 'Available' if available else 'Optional', 'runtime': torch.version.cuda}
                result['GPU'] = {'status': 'Available' if available else 'Optional',
                                 'detail': torch.cuda.get_device_name(0) if available else 'CPU PyTorch; CUDA is optional'}
            except (ImportError, OSError) as error:
                result['PyTorch'] = {'status': 'Unavailable', 'detail': str(error)}
        nvidia = shutil.which('nvidia-smi')
        if nvidia:
            ok, text = command([nvidia, '--query-gpu=name', '--format=csv,noheader'])
            if ok:
                result['GPU'] = {'status': 'Available', 'detail': text}
            ok,driver=command([nvidia,'--query-gpu=driver_version','--format=csv,noheader'])
            result['NVIDIA Driver']={'status':'Available' if ok else 'Optional','detail':driver}
        if ros:
            result['ROS2'].update(distribution=os.environ.get('ROS_DISTRO'),help=command([ros,'--help'])[0],
                                 packages=command([ros,'pkg','list'])[1])
    result.update(CPU=platform.processor() or platform.machine(),venv={'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix},
                  DISPLAY=os.environ.get('DISPLAY'),WAYLAND_DISPLAY=os.environ.get('WAYLAND_DISPLAY'),
                  session_type=os.environ.get('XDG_SESSION_TYPE'),
                  gpu_rendering_vs_training='Gazebo Ogre2/EGL capability is independent of PyTorch CUDA availability')
    return result
