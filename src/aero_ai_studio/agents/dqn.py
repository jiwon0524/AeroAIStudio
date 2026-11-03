"""Optional CPU PyTorch DQN; imported lazily so GridWorld/Q-learning need no torch."""
from __future__ import annotations
from collections import deque
from pathlib import Path
import random
import os
from uuid import uuid4
import torch
from torch import nn
from aero_ai_studio.simulation.base import ACTIONS
from aero_ai_studio.simulation.action_mapping import grid_world_action_mapping
from aero_ai_studio.observation.encoder import observation_vector
from aero_ai_studio.observation.models import Observation
from aero_ai_studio.agents.base import Transition
from aero_ai_studio.training.temporal import NOMINAL_DISCOUNT_TIME_UNIT_SECONDS


def _double_dqn_targets(rewards: torch.Tensor, dones: torch.Tensor,
                        elapsed_discount_units: torch.Tensor, bootstrap: torch.Tensor,
                        gamma: float) -> tuple[torch.Tensor, torch.Tensor]:
    """Return per-item discounts and targets, requiring aligned 1-D batches."""
    shapes = {tuple(value.shape) for value in (rewards, dones, elapsed_discount_units, bootstrap)}
    if len(shapes) != 1 or rewards.ndim != 1:
        raise ValueError("DQN target inputs must have the same one-dimensional batch shape")
    discounts = torch.pow(torch.full_like(elapsed_discount_units, float(gamma)), elapsed_discount_units)
    targets = rewards + discounts * bootstrap * (1.0 - dones)
    return discounts, targets


class ReplayBuffer:
    def __init__(self, capacity: int):
        self.items = deque(maxlen=capacity)

    def append(self, transition: tuple) -> None:
        self.items.append(transition)

    def sample(self, count: int, rng: random.Random) -> list:
        return [self.normalize_transition(item) for item in rng.sample(list(self.items), count)]

    @staticmethod
    def normalize_transition(transition: tuple) -> tuple:
        """Migrate legacy five-field replay items to the nominal duration."""
        if len(transition) == 5:
            return (*transition, 1.0)
        if len(transition) == 6:
            return transition
        return transition

    def __len__(self) -> int:
        return len(self.items)


class DQNAgent:
    artifact_name = 'model.pt'
    supports_training = True
    supports_continuous_actions = False
    supports_images = False
    supports_sensors = True

    def __init__(self, learning_rate: float = 0.001, gamma: float = 0.95, seed: int = 42,
                 batch_size: int = 64, buffer_size: int = 10000, target_interval: int = 500,
                 observation_mode: str = 'sensor', local_radius: int = 2,
                 double_dqn: bool=False, warmup_steps: int=0, reward_clip: float=0.,
                 action_mapping: list[dict] | None=None):
        torch.set_num_threads(1)
        self.learning_rate, self.gamma = learning_rate, gamma
        self.batch_size, self.buffer_size, self.target_interval = batch_size, buffer_size, target_interval
        self.observation_mode, self.local_radius = observation_mode, local_radius
        self.double_dqn,self.warmup_steps,self.reward_clip=double_dqn,warmup_steps,reward_clip
        self.action_mapping=action_mapping if action_mapping is not None else grid_world_action_mapping()
        self.rng = random.Random(seed)
        # Network initialization is seeded without changing other agents' global RNG.
        with torch.random.fork_rng():
            torch.manual_seed(seed)
            self.network = nn.Sequential(nn.Linear(22,128), nn.ReLU(), nn.Linear(128,128), nn.ReLU(), nn.Linear(128,4))
        self.target = nn.Sequential(nn.Linear(22,128), nn.ReLU(), nn.Linear(128,128), nn.ReLU(), nn.Linear(128,4))
        self.target.load_state_dict(self.network.state_dict())
        self.target.eval()
        self.optimizer = torch.optim.Adam(self.network.parameters(), lr=learning_rate)
        self.buffer = ReplayBuffer(buffer_size)
        self.learn_steps = 0
        self.global_step = 0
        self.target_updates = 0
        self.optimizer_updates = 0
        self.last_loss: float | None = None
        self.decision: dict = {}

    def reset(self) -> None:
        self.decision = {}

    def select_action(self, observation: Observation, epsilon: float = 0) -> str:
        vector = observation_vector(observation)
        with torch.no_grad():
            values = self.network(torch.tensor(vector, dtype=torch.float32)).tolist()
        exploring = self.rng.random() < epsilon
        options = list(range(4)) if exploring else [i for i,v in enumerate(values) if v == max(values)]
        index = self.rng.choice(options)
        self.decision = {'q_values': dict(zip(ACTIONS, values)), 'exploring': exploring,
                         'algorithm': 'DQN', 'score_source': 'Network output Q-values', 'input_vector': vector}
        return ACTIONS[index]

    def get_decision_info(self) -> dict:
        return self.decision

    def get_metadata(self) -> dict:
        return {'algorithm': 'dqn', 'architecture':'mlp_22_128_128_4',
                'observation_mode': self.observation_mode, 'encoder': 'sensor_vector_v1',
                'local_radius': self.local_radius, 'input_size': 22,
                'action_mapping':self.action_mapping,
                'batch_size': self.batch_size,
                'buffer_size': self.buffer_size, 'target_interval': self.target_interval,
                'learning_rate': self.learning_rate, 'gamma': self.gamma,
                'double_dqn':self.double_dqn,'warmup_steps':self.warmup_steps,'reward_clip':self.reward_clip,
                'discount_time_unit_seconds': NOMINAL_DISCOUNT_TIME_UNIT_SECONDS}

    def learn(self, t: Transition) -> None:
        self.global_step+=1
        self.learn_steps+=1
        reward=max(-self.reward_clip,min(self.reward_clip,t.reward)) if self.reward_clip else t.reward
        self.buffer.append((observation_vector(t.observation), ACTIONS.index(t.action), float(reward),
                            observation_vector(t.next_observation), bool(t.done),
                            float(t.elapsed_discount_units)))
        if len(self.buffer) >= max(self.batch_size,self.warmup_steps) and self.learn_steps % 4 == 0:
            batch = self.buffer.sample(self.batch_size, self.rng)
            states, actions, rewards, next_states, dones, elapsed_units = zip(*batch)
            q = self.network(torch.tensor(states, dtype=torch.float32)).gather(1, torch.tensor(actions).unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                ns=torch.tensor(next_states,dtype=torch.float32)
                bootstrap=self.target(ns).gather(1,self.network(ns).argmax(1,keepdim=True)).squeeze(1) if self.double_dqn else self.target(ns).max(1).values
                _, expected = _double_dqn_targets(
                    torch.tensor(rewards, dtype=torch.float32),
                    torch.tensor(dones, dtype=torch.float32),
                    torch.tensor(elapsed_units, dtype=torch.float32),
                    bootstrap,
                    self.gamma,
                )
            loss = nn.functional.smooth_l1_loss(q, expected)
            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.network.parameters(), 10)
            self.optimizer.step()
            self.optimizer_updates+=1
            self.last_loss = float(loss.detach())
        if self.learn_steps % self.target_interval == 0:
            self.target.load_state_dict(self.network.state_dict())
            self.target_updates+=1

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        data = {'schema_version': '0.6', 'metadata': self.get_metadata(), 'network': self.network.state_dict(),
                'target': self.target.state_dict(), 'optimizer': self.optimizer.state_dict(),
                'buffer': list(self.buffer.items), 'rng': self.rng.getstate(), 'learn_steps': self.learn_steps,
                'global_step':self.global_step,'target_updates':self.target_updates,
                'optimizer_updates':self.optimizer_updates,'last_loss': self.last_loss}
        try:
            with tmp.open('wb') as stream:
                torch.save(data, stream)
                stream.flush()
                os.fsync(stream.fileno())
            # weights_only avoids arbitrary pickle objects in the supported payload.
            torch.load(tmp, map_location='cpu', weights_only=True)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: Path) -> DQNAgent:
        data = torch.load(path, map_location='cpu', weights_only=True)
        if data.get('schema_version') not in ('0.5', '0.6'):
            raise ValueError(f"Unsupported DQN checkpoint schema: {data.get('schema_version')}")
        m = data['metadata']
        agent = cls(m['learning_rate'], m['gamma'], batch_size=m['batch_size'], buffer_size=m['buffer_size'],
                    target_interval=m['target_interval'], observation_mode=m['observation_mode'], local_radius=m['local_radius'],
                    double_dqn=m.get('double_dqn',False),warmup_steps=m.get('warmup_steps',0),reward_clip=m.get('reward_clip',0.))
        if 'action_mapping' in m:
            agent.action_mapping=m['action_mapping']
        agent.network.load_state_dict(data['network'])
        agent.target.load_state_dict(data['target'])
        agent.optimizer.load_state_dict(data['optimizer'])
        agent.buffer.items.extend(ReplayBuffer.normalize_transition(item) for item in data['buffer'])
        agent.rng.setstate(data['rng'])
        agent.learn_steps, agent.last_loss = data['learn_steps'], data['last_loss']
        agent.global_step=data.get('global_step',agent.learn_steps)
        agent.target_updates=data.get('target_updates',0)
        agent.optimizer_updates=data.get('optimizer_updates',0)
        return agent
