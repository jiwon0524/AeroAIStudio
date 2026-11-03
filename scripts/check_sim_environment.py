from aero_ai_studio.gazebo.diagnostics import diagnose
import importlib.util
import json
import platform

result=diagnose(full=True)
try:bindings=importlib.util.find_spec('gz.transport13') is not None
except ModuleNotFoundError:bindings=False
result['Harmonic Python bindings']={'available':bindings,'target':'gz.transport13 + gz.msgs10'}
result['Ubuntu release']=platform.freedesktop_os_release() if hasattr(platform,'freedesktop_os_release') and platform.system()=='Linux' else 'NOT VERIFIED (not Linux)'
print(json.dumps(result,ensure_ascii=False,indent=2))
