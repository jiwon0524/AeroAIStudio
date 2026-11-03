from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from aero_ai_studio.scenario.generator import generate_scenario

STAGES=(('easy',0,.05),('normal',0,.10),('normal',1,.10),('normal',3,.10),('hard',3,.18))


@dataclass
class CurriculumSchedule:
    stage: int=0
    threshold: float=.8
    minimum_episodes: tuple=()
    minimum_evaluations: int=1
    episodes_in_stage: int=0
    evaluations_in_stage: int=0
    stage_best_success: float=0.

    def record_episode(self):self.episodes_in_stage+=1

    def state_dict(self,events):
        return {'stage':self.stage,'events':events,'current_stage':self.stage,'episodes_in_stage':self.episodes_in_stage,
                'evaluations_in_stage':self.evaluations_in_stage,'stage_best_success':self.stage_best_success,
                'promotion_history':[e for e in events if e['promoted']],'evaluation_history':events}

    def restore(self,data,total_completed=0):
        self.stage=data.get('current_stage',data['stage'])
        events=data.get('evaluation_history',data.get('events',[]))
        last=max((e['episode'] for e in events if e['promoted']),default=0)
        self.episodes_in_stage=data.get('episodes_in_stage',total_completed-last)
        self.evaluations_in_stage=data.get('evaluations_in_stage',sum(e['stage']==self.stage for e in events))
        self.stage_best_success=data.get('stage_best_success',max((e['evaluation_success'] for e in events if e['stage']==self.stage),default=0.))
        return events

    def scenario(self,size: int,seed: int):
        difficulty,moving,density=STAGES[self.stage]
        return generate_scenario(size,seed,difficulty,density=density,moving_count=moving,danger_count=0)

    def update(self,success_rate: float,remaining_budget: int | None=None) -> bool:
        self.evaluations_in_stage+=1
        self.stage_best_success=max(self.stage_best_success,success_rate)
        minimum=self.minimum_episodes[self.stage] if self.minimum_episodes else 0
        reserve=sum(self.minimum_episodes[self.stage+1:]) if self.minimum_episodes else 0
        if (success_rate>=self.threshold and self.stage<len(STAGES)-1 and self.episodes_in_stage>=minimum
            and self.evaluations_in_stage>=self.minimum_evaluations and (remaining_budget is None or remaining_budget>=reserve)):
            self.stage+=1
            self.episodes_in_stage=0
            self.evaluations_in_stage=0
            self.stage_best_success=0.
            return True
        return False

    def complete(self):
        return self.stage==len(STAGES)-1 and (not self.minimum_episodes or self.episodes_in_stage>=self.minimum_episodes[-1])

    def evaluate(self,agent,spec,factory,max_steps,seed,episodes=10,env=None) -> float:
        from aero_ai_studio.agents.factory import policy_observation
        policy=deepcopy(agent)
        if hasattr(policy,'network'):
            policy.network.eval();policy.target.eval()
        owns_env=env is None
        env=env or factory(spec,max_steps)
        success=0;outcomes=[]
        try:
            for i in range(episodes):
                policy.rng.seed(seed+i)
                env.reset(seed+i)
                policy.reset()
                for _ in range(max_steps):
                    result=env.step(policy.select_action(policy_observation(env,policy),0.))
                    if result.terminated or result.truncated:break
                success+=result.reason=='goal'
                outcomes.append({'reason':result.reason,'success':result.reason=='goal',
                                 'reward':float(result.reward),'steps':_+1})
        finally:
            if owns_env:env.close()
        self.last_evaluation={'episodes':outcomes,'success_rate':success/episodes if episodes else 0}
        return self.last_evaluation['success_rate']
