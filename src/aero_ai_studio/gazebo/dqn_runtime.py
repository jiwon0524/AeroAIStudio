"""Checkpoint and inference contracts for actual Gazebo PHYSICS DQN runs."""
from __future__ import annotations
import json
from pathlib import Path

from aero_ai_studio.simulation.action_mapping import gazebo_physics_action_mapping


class DQNCheckpointError(ValueError):
    pass


def checkpoint_contract(path: Path) -> dict:
    """Inspect saved model and training metadata; never infer training semantics."""
    path=Path(path).expanduser().resolve()
    if path.is_dir():
        artifact=path/'model.pt'
        metadata_candidates=(path/'metadata.json',path/'checkpoint.json')
    else:
        artifact=path
        metadata_candidates=(path.parent/'metadata.json',path.parent/'checkpoint.json')
    if not artifact.is_file():
        raise DQNCheckpointError(f'No DQN model.pt artifact at {artifact}')
    metadata_path=next((candidate for candidate in metadata_candidates if candidate.is_file()),None)
    if metadata_path is None:
        raise DQNCheckpointError('Checkpoint is missing metadata.json/checkpoint.json training provenance')
    try:
        container=json.loads(metadata_path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError) as error:
        raise DQNCheckpointError(f'Cannot read checkpoint metadata: {error}') from error
    is_checkpoint=metadata_path.name=='checkpoint.json'
    config=container.get('config') if is_checkpoint else container.get('training_config')
    scenario=container.get('scenario')
    agent_meta=container.get('agent_metadata',{})
    if not isinstance(config,dict) or not isinstance(scenario,dict):
        raise DQNCheckpointError('Checkpoint lacks training_config/config or training scenario')
    if config.get('algorithm')!='dqn' or container.get('algorithm','dqn')!='dqn':
        raise DQNCheckpointError('Checkpoint training provenance is not DQN')
    required={
        'simulator':'gazebo',
        'gazebo_control_mode':'PHYSICS',
        'observation_mode':'sensor',
    }
    mismatches={key:{'expected':expected,'actual':config.get(key)}
                for key,expected in required.items() if config.get(key)!=expected}
    if mismatches:
        raise DQNCheckpointError(f'Incompatible DQN training environment: {mismatches}')
    if agent_meta.get('algorithm') not in (None,'dqn'):
        raise DQNCheckpointError('Agent metadata algorithm is not DQN')
    if agent_meta.get('observation_mode')!='sensor':
        raise DQNCheckpointError('DQN checkpoint observation mode is not SENSOR')
    if (agent_meta.get('input_size')!=22 or agent_meta.get('encoder')!='sensor_vector_v1' or
        agent_meta.get('architecture')!='mlp_22_128_128_4'):
        raise DQNCheckpointError('DQN checkpoint observation encoder/dimension is incompatible')
    expected_mapping=gazebo_physics_action_mapping()
    if agent_meta.get('action_mapping')!=expected_mapping:
        raise DQNCheckpointError(f'DQN checkpoint action mapping must be {expected_mapping}')
    if config.get('training_kind')!='full':
        raise DQNCheckpointError('Only a full Gazebo PHYSICS training artifact can be used for actual validation; smoke models are excluded')
    return {'artifact':artifact,'metadata_path':metadata_path,'metadata':container,'config':config,
            'scenario':scenario,'agent_metadata':agent_meta,'action_mapping':expected_mapping,
            'observation_mode':'sensor','observation_dimension':22}


def load_compatible_dqn(path: Path):
    """Validate provenance before deserializing weights, then freeze for inference."""
    contract=checkpoint_contract(path)
    import torch
    from aero_ai_studio.agents.dqn import DQNAgent
    try:
        artifact=torch.load(contract['artifact'],map_location='cpu',weights_only=True)
    except Exception as error:
        raise DQNCheckpointError(f'Cannot safely load DQN weights: {error}') from error
    model_meta=artifact.get('metadata',{}) if isinstance(artifact,dict) else {}
    for key in ('algorithm','architecture','observation_mode','encoder','input_size','action_mapping'):
        expected=contract['agent_metadata'].get(key)
        if model_meta.get(key)!=expected:
            raise DQNCheckpointError(f'Model artifact metadata mismatch for {key}: {model_meta.get(key)!r} != {expected!r}')
    try:
        agent=DQNAgent.load(contract['artifact'])
    except Exception as error:
        raise DQNCheckpointError(f'DQN architecture/state dict is incompatible: {error}') from error
    agent.network.eval();agent.target.eval()
    for parameter in (*agent.network.parameters(),*agent.target.parameters()):
        parameter.requires_grad_(False)
    contract['agent']=agent
    return contract
