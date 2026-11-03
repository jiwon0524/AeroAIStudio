"""Static-only Gazebo curriculum; promotion logic/state reuse V0.6 CurriculumSchedule."""
from aero_ai_studio.training.curriculum import CurriculumSchedule
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.scenario.models import ScenarioSpec


class GazeboPhysicsCurriculum(CurriculumSchedule):
    DENSITIES=(0.,.05,.10,.15,.18)

    def __init__(self,*args,target_scenario:ScenarioSpec,**kwargs):
        super().__init__(*args,**kwargs)
        self.target_scenario=ScenarioSpec.from_dict(target_scenario.to_dict())

    def scenario(self,size:int,seed:int):
        if self.stage==4:
            return ScenarioSpec.from_dict(self.target_scenario.to_dict())
        difficulty='easy' if self.stage<2 else 'normal'
        # PHYSICS Gazebo currently validates static contacts only; curriculum
        # density increases without introducing GridWorld-only moving entities.
        return generate_scenario(size,seed,difficulty,density=self.DENSITIES[self.stage],
                                 moving_count=0,danger_count=0)
