from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import shutil
from aero_ai_studio.evaluation.evaluator import EvaluationConfig, Evaluator
from aero_ai_studio.scenario.models import ScenarioSpec, DynamicObject
from aero_ai_studio.scenario.generator import generate_scenario
from aero_ai_studio.core.storage import read_json, write_json, identifier


@dataclass
class GeneralizationConfig:
    new_seeds: bool = True
    random_obstacles: bool = True
    moving_obstacles: bool = False
    different_difficulty: bool = False
    difficulty: str = 'hard'


class GeneralizationEvaluator:
    def __init__(self, scenario: ScenarioSpec, config: EvaluationConfig, options: GeneralizationConfig):
        if not options.new_seeds:
            raise ValueError('Generalization evaluation always requires disjoint new seeds')
        self.scenario, self.config, self.options = scenario, config, options

    def run(self, model: Path, evaluations: Path, progress=None, cancel=None) -> tuple[Path, dict]:
        root = evaluations / identifier('eval_generalization')
        baseline, seen = Evaluator(self.scenario, self.config).run(model, root / 'reference', progress, cancel)
        unseen = ScenarioSpec.from_dict(self.scenario.to_dict())
        options = self.options
        if options.different_difficulty:
            unseen = generate_scenario(self.scenario.width, self.config.seed + 100000, options.difficulty,
                                       moving_count=3 if options.moving_obstacles else 0)
        if options.random_obstacles:
            unseen.randomization['obstacle_position'] = True
        if options.moving_obstacles and not unseen.dynamic_objects:
            free = [(x,y) for x in range(unseen.width) for y in range(unseen.height)
                    if (x,y) not in {o.position for o in unseen.objects} | {unseen.start, unseen.goal}]
            unseen.dynamic_objects = [DynamicObject(position=p, movement='random') for p in free[:3]]
        target, result = Evaluator(unseen, replace(self.config, seed=self.config.seed + 200000)).run(model, root / 'unseen', progress, cancel)
        shutil.copytree(target / 'episodes', root / 'episodes')
        shutil.copy2(target / 'metrics.json', root / 'metrics.json')
        result.update(id=root.name, mode='generalization', training_scenario_success=seen['success_rate'],
                      unseen_scenario_success=result['success_rate'],
                      generalization_gap=seen['success_rate']-result['success_rate'],
                      reference_evaluation=str(baseline), unseen_evaluation=str(target),
                      note='Reference uses the training scenario with fresh seeds; no training reset seed is reused')
        write_json(root / 'evaluation.json', result)
        return root, result
