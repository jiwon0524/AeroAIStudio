from pathlib import Path
from aero_ai_studio.agents.q_learning import QLearningAgent


def create_agent(config):
    if config.algorithm == 'q_learning':
        return QLearningAgent(config.learning_rate, config.gamma, config.seed, config.state_encoder,
                              config.observation_mode, config.local_radius)
    if config.algorithm == 'dqn':
        from aero_ai_studio.agents.dqn import DQNAgent
        from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping,grid_world_action_mapping
        mapping=(gazebo_physics_action_mapping() if config.simulator=='gazebo' else grid_world_action_mapping())
        return DQNAgent(config.learning_rate, config.gamma, config.seed, config.batch_size,
                        config.buffer_size, config.target_interval, config.observation_mode, config.local_radius,
                        config.double_dqn,config.warmup_steps,config.reward_clip,mapping)
    raise ValueError('Unsupported algorithm')


def load_agent(directory: Path):
    if (directory / 'model.pt').exists():
        from aero_ai_studio.agents.dqn import DQNAgent
        return DQNAgent.load(directory / 'model.pt')
    return QLearningAgent.load(directory / 'q_table.json')


def policy_observation(env, agent):
    return env.get_agent_observation(agent.observation_mode, agent.local_radius)
