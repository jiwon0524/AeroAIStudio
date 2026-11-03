from pathlib import Path
from aero_ai_studio.core.storage import read_json, write_json

TARGETS = ("Local Python", "REST API", "ONNX", "ROS2", "PX4", "Game Adapter")


def export_local(model: Path, destination: Path) -> Path:
    if (model / 'model.pt').exists():
        import shutil
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model / 'model.pt', destination / 'model.pt')
        shutil.copy2(model / 'metadata.json', destination / 'metadata.json')
        (destination / 'policy.py').write_text('''"""Requires aero-ai-studio[dqn]; accepts an explicit SENSOR/LOCAL Observation."""
from pathlib import Path
from aero_ai_studio.agents.dqn import DQNAgent
AGENT = DQNAgent.load(Path(__file__).with_name('model.pt'))
def act(observation):
    return AGENT.select_action(observation, 0)
''', encoding='utf-8')
        return destination
    data = read_json(model / "q_table.json")
    if data.get('agent_metadata', {}).get('encoder', 'basic') != 'basic':
        import shutil
        destination.mkdir(parents=True, exist_ok=True)
        for filename in ('q_table.json','metadata.json'):
            shutil.copy2(model / filename, destination / filename)
        (destination / 'policy.py').write_text('''"""Compact Q inference requires aero-ai-studio and matching Observation schema."""
from pathlib import Path
from aero_ai_studio.agents.q_learning import QLearningAgent
AGENT = QLearningAgent.load(Path(__file__).with_name('q_table.json'))
def act(observation):
    return AGENT.select_action(observation, 0)
''', encoding='utf-8')
        return destination
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "q_table.json", data)
    write_json(destination / "metadata.json", read_json(model / "metadata.json"))
    script = '''"""Pure Python inference for this scenario's fixed 2D occupancy grid."""
import json
from pathlib import Path
TABLE = json.loads(Path(__file__).with_name("q_table.json").read_text(encoding="utf-8"))["table"]
def act(x: int, y: int) -> str:
    key = f"{x},{y}"
    if key not in TABLE:
        raise ValueError("Unseen state; no validated action available")
    return max(TABLE[key], key=TABLE[key].get)
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    a = p.parse_args()
    print(act(a.x, a.y))
'''
    (destination / "policy.py").write_text(script, encoding="utf-8")
    return destination
