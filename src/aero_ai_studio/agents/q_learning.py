from __future__ import annotations

import random
import json
from pathlib import Path
from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.simulation.base import ACTIONS, Position
from aero_ai_studio.observation.encoder import BasicStateEncoder, CompactStateEncoder,CanonicalStateEncoder
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.agents.base import Transition


class QLearningAgent:
    artifact_name = 'q_table.json'
    supports_training = True
    supports_continuous_actions = False
    supports_images = False
    supports_sensors = True
    def __init__(self, learning_rate: float = 0.1, gamma: float = 0.95, seed: int = 42, encoder: str = 'basic', observation_mode: str = 'basic', local_radius: int = 2):
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.table: dict[str, dict[str, float]] = {}
        self.rng = random.Random(seed)
        encoders={'basic':BasicStateEncoder,'compact':CompactStateEncoder,'canonical':CanonicalStateEncoder}
        if encoder not in encoders:raise ValueError('Unknown Q encoder')
        self.encoder = encoders[encoder]()
        self.observation_mode, self.local_radius = observation_mode, local_radius
        self.decision: dict = {}

    def reset(self) -> None:
        self.decision = {}

    def select_action(self, observation: Observation, epsilon: float = 0) -> str:
        state = self.encoder.encode(observation)
        values = dict(self.scores(state))
        action, exploring = self.choose(state, epsilon)
        self.decision = {'q_values': values, 'exploring': exploring, 'algorithm': 'Q-Learning',
                         'encoded_state': list(state), 'score_source': 'Q-table'}
        return action

    def learn(self, transition: Transition) -> None:
        self.update(self.encoder.encode(transition.observation), transition.action, transition.reward,
                    self.encoder.encode(transition.next_observation), transition.done)

    def get_decision_info(self) -> dict:
        return self.decision

    def get_metadata(self) -> dict:
        return {'algorithm': 'q_learning', 'observation_mode': self.observation_mode,
                'encoder': self.encoder.name, 'local_radius': self.local_radius}

    def scores(self, state: Position) -> dict[str, float]:
        key = f"{state[0]},{state[1]}" if len(state) == 2 and all(type(x) is int for x in state) else json.dumps(state, separators=(',', ':'))
        return self.table.setdefault(key, dict.fromkeys(ACTIONS, 0.0))

    def choose(self, state: Position, epsilon: float) -> tuple[str, bool]:
        values = self.scores(state)
        exploring = self.rng.random() < epsilon
        candidates = list(ACTIONS) if exploring else [a for a in ACTIONS if values[a] == max(values.values())]
        return self.rng.choice(candidates), exploring

    def update(self, state: Position, action: str, reward: float, next_state: Position, done: bool) -> None:
        values = self.scores(state)
        target = reward if done else reward + self.gamma * max(self.scores(next_state).values())
        values[action] += self.learning_rate * (target - values[action])

    def save(self, path: Path) -> None:
        write_json(path, {"schema_version": 1, "algorithm": "q_learning", "actions": list(ACTIONS),
                          "learning_rate": self.learning_rate, "gamma": self.gamma, "table": self.table,
                          'agent_metadata': self.get_metadata()})

    @classmethod
    def load(cls, path: Path) -> QLearningAgent:
        data = read_json(path)
        meta = data.get('agent_metadata', {})
        agent = cls(data["learning_rate"], data["gamma"], encoder=meta.get('encoder', 'basic'),
                    observation_mode=meta.get('observation_mode', 'basic'), local_radius=meta.get('local_radius', 2))
        agent.table = data["table"]
        return agent
