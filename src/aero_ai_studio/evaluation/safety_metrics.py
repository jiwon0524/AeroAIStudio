from aero_ai_studio.observation.canonical import CanonicalSensorObservation


def safety_step_metrics(observation,safety,critical_threshold=.5):
    c=CanonicalSensorObservation.from_observation(observation)
    clearance=min(c.front_clearance,c.back_clearance,c.left_clearance,c.right_clearance)
    return {'near_collision':clearance<critical_threshold,'critical_clearance_threshold':critical_threshold,
            'observed_minimum_clearance':clearance,
            'useful_override_heuristic':safety.useful_override_heuristic,
            'harmful_override_heuristic':safety.harmful_override_heuristic,
            'interpretation':'Sensor/rule heuristic only; no counterfactual causal proof'}
