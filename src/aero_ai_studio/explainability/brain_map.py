from dataclasses import dataclass
from aero_ai_studio.simulation.base import StepResult


def record_step(episode: int, index: int, state: tuple, scores: dict, action: str,
                exploring: bool, epsilon: float, before: dict, after: dict, result: StepResult) -> dict:
    return {"episode": episode, "time": index, "state": list(state), "goal": before["goal"],
            "obstacles": before["obstacles"], "width": before["width"], "height": before["height"],
            "q_values": scores, "selected_action": action, "exploring": exploring, "epsilon": epsilon,
            "decision_type": "Exploration" if exploring else "Exploitation",
            "reward": result.reward, "new_state": list(result.observation), "reason": result.reason,
            "terminated": result.terminated, "truncated": result.truncated,
            "dynamic_objects": before.get("dynamic_objects", []),
            "next_dynamic_objects": after.get("dynamic_objects", []),
            "danger_zones": before.get("danger_zones", []), "slow_zones": before.get("slow_zones", []),
            "mission": before.get("mission", "unknown"), "action_evidence": before.get("action_evidence", {})}


@dataclass(frozen=True)
class BrainEvent:
    """Observed decision evidence, never a claim about hidden thoughts."""
    step: dict

    def text(self) -> str:
        s = self.step
        best = max(s["q_values"].values())
        candidates = [a.upper() for a, v in s["q_values"].items() if v == best]
        evidence = s.get("action_evidence", {})
        values = "\n".join(f"  {a.upper():6} {v: .4f}  " +
                           (f"{'Valid' if evidence[a]['valid'] else 'Invalid'} · Risk {evidence[a]['collision_risk']} · Danger {evidence[a]['danger_zone']}" if a in evidence else "risk not recorded (legacy)")
                           for a, v in s["q_values"].items())
        policy = "epsilon exploration (random action)" if s["exploring"] else "greedy (ties selected randomly)"
        nearby = [p for p in s['obstacles'] + [d['position'] for d in s.get('dynamic_objects', [])]
                  if abs(p[0] - s['state'][0]) + abs(p[1] - s['state'][1]) <= 3]
        obs = s.get('observation')
        observed = ('WHAT AI SAW\n' + __import__('json').dumps(obs, ensure_ascii=False, indent=2) + '\n') if obs else 'Observation not recorded (legacy)\n'
        extra=('\nBRAIN MAP V4\nProposed: '+str(s.get('proposed_action',s['selected_action']))+
               '\nSafety: '+str(s.get('safety','not recorded'))+'\nFinal: '+str(s.get('final_action',s['selected_action']))+
               '\nReward Breakdown: '+str(s.get('reward_components','not recorded'))+
               '\nPrediction: '+str((obs or {}).get('sensor_state',{}).get('prediction','not recorded'))+
               '\nPose / timestamp: '+str(s.get('pose'))+' / '+str(s.get('timestamp'))+'\n'
               +'\nActual telemetry: '+str(s.get('telemetry','not recorded'))+'\n'
               +'Safety audit (heuristic): '+str(s.get('safety_metrics','not recorded'))+'\n')
        return (f"Episode {s.get('episode', 'legacy')} · Step {s['time'] + 1}\n"
                f"Algorithm: {s.get('algorithm', 'Q-Learning')} · Score source: {s.get('agent_decision', {}).get('score_source', 'Q-table')}\n"
                f"CURRENT STATE  {s['state']}\nGoal  {s['goal']}\nObstacles  {len(s['obstacles'])}\n"
                f"Nearby objects (≤3 cells): {nearby}\nMission: {s.get('mission', 'not recorded')}\n"
                f"\nACTION SCORES (before update)\n{values}\n\nHighest: {', '.join(candidates)}\n"
                f"SELECTED  {s['selected_action'].upper()}\nDecision Type: {'Exploration' if s['exploring'] else 'Exploitation'}\n"
                f"Reason: {'Exploration' if s['exploring'] else 'Highest Q-value (random ties)'}\nPolicy  {policy}\nEpsilon  {s['epsilon']:.5f}\n"
                f"\nRESULT\nReward  {s['reward']:+.1f}\nNew state  {s['new_state']}\n{s['reason'].upper()}\n\n"
                "Q-values are learned action estimates, not probabilities.\n"
                "Collision risk is a local geometry heuristic, not a learned probability.\n"
                "Geometry risk / nearby objects above are DEBUG data, not necessarily policy inputs.\n"
                "This map shows recorded evidence, not hidden internal reasoning.\n\n" + extra+observed)
