from __future__ import annotations
from collections import Counter


def detect_loop(steps: list[dict], repetitions: int = 3) -> dict | None:
    states = [tuple(s['state']) for s in steps]
    for end in range(len(states), repetitions - 1, -1):
        for period in range(1, min(8, end // repetitions) + 1):
            block = states[end - period:end]
            if all(states[end - period * (i + 1):end - period * i] == block for i in range(repetitions)):
                return {'start_step': end - period * repetitions + 1, 'end_step': end,
                        'period': period, 'repetitions': repetitions}
    return None


def analyze_failure(episode: dict) -> dict:
    steps = episode.get('steps', [])
    reason = episode.get('reason', 'unknown')
    result = {'failure_type': 'Success' if episode.get('success') else reason.replace('_', ' ').title(),
              'failure_step': len(steps), 'possible_causes': [], 'relevant_q_values': {},
              'previous_actions': [s['selected_action'] for s in steps[-8:]],
              'loop': detect_loop(steps), 'method': 'Recorded log rules; observations, not proof of causation'}
    if not steps:
        return result
    last = steps[-1]
    result['relevant_q_values'] = last.get('q_values', {})
    visits = Counter(tuple(s['state']) for s in steps)
    result['max_state_visits'] = max(visits.values())
    causes = result['possible_causes']
    if not episode.get('success'):
        if 'collision' in reason:
            action = last['selected_action']
            obs=last.get('observation',{})
            if obs.get('mode')=='basic':
                causes.append('Recorded BASIC policy input has no obstacle measurements; debug geometry was not a policy sensor.')
            sensors=obs.get('sensor_state',{})
            ray={'up':'front_distance','down':'back_distance','left':'left_distance','right':'right_distance'}.get(action,'stop')
            if sensors and sensors.get(ray,99)<=1:
                causes.append(f'The selected direction was already blocked in the recorded range sensor input ({ray}={sensors[ray]}).')
            scores = last.get('q_values', {})
            same = [s for s in steps if s['state'] == last['state'] and s['selected_action'] == action]
            causes.append(f"Selected {action.upper()} at state {last['state']}; recorded {len(same)} times in this episode.")
            if last.get('exploring'):
                causes.append('Terminal action came from epsilon exploration.')
            elif action in scores and scores[action] == max(scores.values()):
                causes.append('Terminal action had a maximal recorded Q-value despite the observed collision.')
            if reason == 'moving_obstacle_collision':
                if sensors:
                    causes.append('Dynamic obstacle conflict; recorded relative motion was '+str(sensors.get('moving_obstacle_relative_motion','UNKNOWN'))+'. This is a measurement, not a collision prediction.')
                else:
                    causes.append('Dynamic obstacle conflict; Basic (x,y) observation does not encode object motion.')
        if reason == 'danger_zone':
            causes.append('Agent entered a terminal Danger Zone (reward -50).')
        if result['loop']:
            loop = result['loop']
            causes.append(f"Repeated state sequence: period {loop['period']}, steps {loop['start_step']}–{loop['end_step']}.")
        best_distance = float('inf')
        stagnant = longest = 0
        for s in steps:
            d = abs(s['new_state'][0] - s['goal'][0]) + abs(s['new_state'][1] - s['goal'][1])
            if d < best_distance:
                best_distance, stagnant = d, 0
            else:
                stagnant += 1
            longest = max(longest, stagnant)
        result['longest_no_new_distance_best'] = longest
        if reason == 'timeout':
            causes.append(f"Step limit reached; longest interval without a new best Manhattan distance: {longest} steps.")
        if result['max_state_visits'] > 2:
            causes.append(f"Most visited state occurred {result['max_state_visits']} times.")
    return result
