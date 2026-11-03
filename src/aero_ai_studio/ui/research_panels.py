"""V0.4 panels extend the existing window; core engines remain Qt-independent."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from threading import Event
import json

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QLabel, QFormLayout, QComboBox, QHBoxLayout, QPlainTextEdit,
    QListWidget, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QInputDialog,
    QAbstractItemView, QLineEdit)

from aero_ai_studio.core.storage import read_json
from aero_ai_studio.evaluation.evaluator import Evaluator, EvaluationConfig
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.scenario.models import ScenarioSpec, SceneObject, DynamicObject
from aero_ai_studio.scenario.generator import generate_scenario, PRESETS
from aero_ai_studio.explainability.failure_analyzer import analyze_failure
from aero_ai_studio.training.comparison import compare_runs
from aero_ai_studio.training.checkpoint import CheckpointStore
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.ui.widgets import GridView, ComparisonChart
from aero_ai_studio.ui.v05_panels import V05Panels
from aero_ai_studio.evaluation.generalization import GeneralizationEvaluator, GeneralizationConfig


class EvaluationWorker(QThread):
    progress = Signal(dict)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, evaluator: Evaluator, model: Path, root: Path):
        super().__init__()
        self.evaluator, self.model, self.root = evaluator, model, root
        self.cancel = Event()

    def run(self) -> None:
        try:
            self.completed.emit(self.evaluator.run(self.model, self.root, self.progress.emit, self.cancel))
        except Exception as error:
            self.failed.emit(str(error))


class ResearchPanels(V05Panels):
    def build_evaluation(self) -> None:
        from aero_ai_studio.ui.window import button, integer
        layout = self.page('Evaluation', 'Greedy only · epsilon=0 · no weight updates · independent evaluation artifacts')
        form = QFormLayout()
        self.eval_model = QComboBox()
        self.eval_scenario = QComboBox()
        self.eval_scenario.addItems(['Model scenario snapshot', 'Current saved project scenario'])
        self.eval_mode=QComboBox()
        self.eval_mode.addItems(['Evaluation','Generalization Test'])
        self.eval_suite=QComboBox()
        self.eval_suite.addItems(['custom','static_known','static_unseen','dynamic_easy','dynamic_normal','dynamic_hard','gazebo_static'])
        from PySide6.QtWidgets import QCheckBox
        self.eval_safety=QCheckBox('Evaluation Safety Layer')
        self.general_random,self.general_moving,self.general_difficulty=QCheckBox('Random Obstacles'),QCheckBox('Moving Obstacles'),QCheckBox('Different Difficulty (hard)')
        self.general_random.setChecked(True)
        self.eval_episodes, self.eval_max_steps, self.eval_seed = integer(100, 1, 100000), integer(200, 1, 10000), integer(10042, 0, 2147483647)
        for title, widget in [('Model', self.eval_model), ('Scenario', self.eval_scenario), ('Episodes', self.eval_episodes),
                              ('Max steps', self.eval_max_steps), ('Random seed', self.eval_seed)]:
            form.addRow(title, widget)
        layout.addLayout(form)
        form.addRow('Mode (all evaluation seeds must be new)',self.eval_mode)
        form.addRow('Evaluation suite',self.eval_suite)
        form.addRow(self.eval_safety)
        for option in (self.general_random,self.general_moving,self.general_difficulty):form.addRow(option)
        self.evaluate_button = button('Evaluate selected model', self.start_evaluation)
        self.stop_eval_button = button('Stop Evaluation', self.stop_evaluation)
        self.stop_eval_button.setEnabled(False)
        layout.addWidget(self.evaluate_button)
        layout.addWidget(self.stop_eval_button)
        self.eval_status = QLabel('Ready. Evaluation results are separate from Training success rates.')
        self.eval_status.setWordWrap(True)
        layout.addWidget(self.eval_status)
        self.eval_history = QComboBox()
        self.eval_history.currentIndexChanged.connect(self.show_evaluation)
        layout.addWidget(self.eval_history)
        self.eval_results = QPlainTextEdit()
        self.eval_results.setReadOnly(True)
        layout.addWidget(self.eval_results)
        layout.addWidget(button('Replay selected evaluation', self.replay_evaluation))

    def build_comparison(self) -> None:
        from aero_ai_studio.ui.window import button
        layout = self.page('Training Comparison', 'Select up to five runs · graphs show training metrics, including exploration')
        self.compare_list = QListWidget()
        self.compare_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.compare_list.setMaximumHeight(130)
        layout.addWidget(self.compare_list)
        layout.addWidget(button('Compare selected runs', self.compare_selected))
        self.compare_table = QTableWidget(0, 16)
        self.compare_table.setHorizontalHeaderLabels(['Run / color', 'Episodes', 'Train success', 'Avg reward', 'Avg steps', 'LR', 'Gamma', 'Final ε', 'Models',
                                                    'Algorithm','Observation','Eval success','Collision rate','Timeout rate','Time(s)','Model(bytes)'])
        self.compare_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.compare_table.setMaximumHeight(210)
        layout.addWidget(self.compare_table)
        self.compare_chart = ComparisonChart()
        layout.addWidget(self.compare_chart)

    def refresh_research(self) -> None:
        if not self.project:
            return
        root = self.repo.path(self.project)
        old = self.eval_model.currentData()
        self.eval_model.clear()
        self.compare_list.clear()
        for path in self.run_paths:
            self.compare_list.addItem(path.name)
        for path, meta in ModelRegistry.list(root / 'models'):
            self.eval_model.addItem(f"{meta['name']} v{meta['version']}", str(path))
        index = self.eval_model.findData(old)
        if index >= 0:
            self.eval_model.setCurrentIndex(index)
        old_eval = self.eval_history.currentData()
        self.eval_history.blockSignals(True)
        self.eval_history.clear()
        for p in sorted((root / 'evaluations').glob('*/evaluation.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            info = read_json(p)
            self.eval_history.addItem(f"{info['id']} · {info['status']} · {info.get('success_rate', 0):.1%}", str(p.parent))
        found = self.eval_history.findData(old_eval)
        if found >= 0:
            self.eval_history.setCurrentIndex(found)
        self.eval_history.blockSignals(False)
        self.show_evaluation()
        self.update_context()

    def update_context(self) -> None:
        project = self.project.name if self.project else '—'
        scenario = self.scenario.name if self.scenario else '—'
        run = self.run_select.currentText() if hasattr(self, 'run_select') else '—'
        model = self.eval_model.currentText() if hasattr(self, 'eval_model') else '—'
        self.context_label.setText(f'Project: {project}   |   Scenario: {scenario}\nRun: {run or "—"}   |   Model: {model or "—"}')

    def start_evaluation(self) -> None:
        try:
            root = self.require_project()
            if self.eval_suite.currentText()=='gazebo_static':
                from aero_ai_studio.gazebo.diagnostics import gazebo_status
                if not gazebo_status(probe=False)['available']:
                    self.eval_status.setText('Gazebo unavailable — actual closed loop NOT VERIFIED')
                    return
            if (self.worker and self.worker.isRunning()) or (self.eval_worker and self.eval_worker.isRunning()):
                raise ValueError('Wait for the current worker to finish')
            selected = self.eval_model.currentData()
            if not selected:
                raise ValueError('Select or save a model first')
            model = Path(selected)
            spec = ScenarioSpec.from_dict(read_json(model / 'metadata.json')['scenario'])
            if self.eval_scenario.currentIndex() == 1:
                if self.scenario is None:
                    raise ValueError('Save a project scenario first')
                spec = ScenarioSpec.from_dict(self.scenario.to_dict())
            from aero_ai_studio.evaluation.suites import evaluation_scenario
            spec=evaluation_scenario(spec,self.eval_suite.currentText(),self.eval_seed.value())
            cfg = EvaluationConfig(self.eval_episodes.value(), self.eval_max_steps.value(), self.eval_seed.value(),
                                   safety_enabled=self.eval_safety.isChecked(),safety_threshold=self.safety_threshold.value(),
                                   reward_version=self.reward_version.currentText(),suite=self.eval_suite.currentText())
            evaluator=Evaluator(spec,cfg,self.backend_factory(root,'Gazebo' if cfg.suite=='gazebo_static' else 'GridWorld'))
            if self.eval_mode.currentText()=='Generalization Test':
                evaluator=GeneralizationEvaluator(spec,cfg,GeneralizationConfig(random_obstacles=self.general_random.isChecked(),
                        moving_obstacles=self.general_moving.isChecked(),different_difficulty=self.general_difficulty.isChecked()))
            self.eval_worker = EvaluationWorker(evaluator, model, root / 'evaluations')
            self.eval_worker.progress.connect(lambda row: self.eval_status.setText(f"Evaluating episode {row['episode']} · {row['reason']}"))
            self.eval_worker.completed.connect(self.evaluation_complete)
            self.eval_worker.failed.connect(self.report)
            self.eval_worker.finished.connect(self.evaluation_finished)
            self.set_busy(True)
            self.evaluate_button.setEnabled(False)
            self.stop_eval_button.setEnabled(True)
            self.eval_worker.start()
        except Exception as error:
            self.report(error)

    def evaluation_complete(self, result: tuple) -> None:
        path, summary = result
        if summary['status'] == 'completed':
            ModelRegistry.attach_evaluation(self.eval_worker.model, path, summary)
        self.eval_status.setText(f"{summary['status'].upper()} · Success {summary['success_rate']:.1%} · "
                                 f"Reward {summary['average_reward']:.2f} · Steps {summary['average_steps']:.2f}")
        self.refresh_assets()
        self.eval_history.setCurrentIndex(self.eval_history.findData(str(path)))

    def evaluation_finished(self) -> None:
        self.set_busy(False)
        self.stop_eval_button.setEnabled(False)
        if self._closing:
            self.close()

    def stop_evaluation(self) -> None:
        if self.eval_worker:
            self.eval_worker.cancel.set()

    def show_evaluation(self, *_args) -> None:
        path = self.eval_history.currentData()
        if path:
            data = read_json(Path(path) / 'evaluation.json')
            def metric(key: str, percent: bool = False) -> str:
                value = data.get(key)
                return 'N/A (no successful episodes)' if value is None else f'{value:.1%}' if percent else f'{value:.3f}'
            self.eval_results.setPlainText(
                f"EVALUATION · {data['status'].upper()} · epsilon = 0\n\n"
                f"Success Rate       {metric('success_rate', True)}\nFailure Rate       {metric('failure_rate', True)}\n"
                f"Average Reward     {metric('average_reward')}\nAverage Steps      {metric('average_steps')}\n"
                f"Collision Count    {data.get('collision_count', 0)}\nTimeout Count      {data.get('timeout_count', 0)}\n"
                f"Shortest Path Ratio  {metric('shortest_path_ratio')}\nPath Efficiency      {metric('path_efficiency')}\n\n"
                f"Episodes completed {data.get('episodes_completed', 0)}\nScenario {data['scenario']['name']}\n"
                f"Seed {data['config']['seed']} · Max Steps {data['config']['max_steps']}\n\n"
                "Shortest Path Ratio = optimal static distance / successful travelled distance (higher is better).\n"
                "Path Efficiency = successful travelled distance / optimal static distance (lower is better).\n"
                "Both are averaged over successful episodes only; dynamic timing and Slow Zone costs are excluded.\n\n"
                f"Result ID  {data['id']}\nModel ID   {Path(data['model']).name}\n"
                "This evaluation did not update model weights. Greedy ties are seeded random choices.")
            self.eval_results.appendPlainText(f"\nSafety overrides: {data.get('safety_override_count','legacy')}\nAverage minimum clearance: {data.get('average_minimum_clearance','legacy')}")
            if data.get('mode')=='generalization':
                self.eval_results.appendPlainText(f"\nGENERALIZATION\nTraining scenario (fresh seeds): {data['training_scenario_success']:.1%}\n"
                    f"Unseen scenario: {data['unseen_scenario_success']:.1%}\nGap: {data['generalization_gap']:.1%}")
        else:
            self.eval_results.clear()

    def replay_evaluation(self) -> None:
        path = self.eval_history.currentData()
        if path:
            self.nav.setCurrentRow(5)
            index = self.run_select.findData(path)
            if index >= 0:
                self.run_select.setCurrentIndex(index)

    def evaluate_registry_model(self) -> None:
        row = self.model_table.currentRow()
        if row < 0:
            self.report('Select a model row first')
            return
        path = str(self.model_paths[row])
        self.nav.setCurrentRow(11)
        self.eval_model.setCurrentIndex(self.eval_model.findData(path))

    def compare_selected(self) -> None:
        selected = [self.run_paths[self.compare_list.row(item)] for item in self.compare_list.selectedItems()]
        if not selected or len(selected) > 5:
            self.report('Select between one and five training runs')
            return
        data = compare_runs(selected, self.require_project() / 'models')
        colors = ['blue', 'green', 'yellow', 'pink', 'purple']
        self.compare_table.setRowCount(len(data))
        for row, entry in enumerate(data):
            values = [entry['run'] + ' · ' + colors[row], entry['episodes'], f"{entry['final_success_rate']:.1%}",
                      f"{entry['average_reward']:.2f}", f"{entry['average_steps']:.2f}", entry['learning_rate'],
                      entry['gamma'], f"{entry['final_epsilon']:.5f}", ', '.join(entry['models']),
                      entry['algorithm'],entry['observation'],f"{entry['evaluation_success']:.1%}" if entry['evaluation_success'] is not None else 'N/A',
                      f"{entry['collision_rate']:.1%}",f"{entry['timeout_rate']:.1%}",
                      f"{entry['training_seconds']:.2f}" if entry['training_seconds'] is not None else 'N/A',entry['model_size_bytes']]
            for col, value in enumerate(values):
                self.compare_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.compare_chart.runs = data
        self.compare_chart.update()

    def request_checkpoint(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.checkpoint_request.set()
            self.statusBar().showMessage('Checkpoint requested at end of current episode', 5000)
        else:
            self.report('A final checkpoint is saved automatically when training ends. Resume selects a saved checkpoint.')

    def resume_training(self) -> None:
        try:
            root = self.require_project()
            paths = sorted((root / 'runs').glob('*/checkpoints/episode_*/checkpoint.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            if not paths:
                raise ValueError('No committed checkpoints in this project')
            labels = [f"{p.parents[2].name} / {p.parent.name}" for p in paths]
            label, ok = QInputDialog.getItem(self, 'Resume Training', 'Checkpoint', labels, 0, False)
            if not ok:
                return
            checkpoint = paths[labels.index(label)].parent
            saved = CheckpointStore.load(checkpoint)
            total, ok = QInputDialog.getInt(self, 'Resume Training', 'Total episode target (including completed episodes)',
                                          max(saved['config']['episodes'], saved['episode'] + 100), saved['episode'] + 1, 100000)
            if not ok:
                return
            cfg = TrainingConfig(**saved['config'])
            cfg.episodes = total
            self.gazebo_control_mode.setCurrentText(cfg.gazebo_control_mode)
            cfg.visual_interval = (1, 10, 100)[self.render_interval.currentIndex()]
            cfg.visual_delay = 0.02 if self.training_mode.currentIndex() else 0
            self.launch_training(Trainer(ScenarioSpec.from_dict(saved['scenario']), cfg,self.backend_factory(root,'Gazebo' if cfg.simulator=='gazebo' else 'GridWorld')), root / 'runs', checkpoint)
        except Exception as error:
            self.report(error)

    def training_visual(self, step: dict) -> None:
        self.live_observation.setPlainText('PRE-ACTION POLICY OBSERVATION (Grid shows resulting state)\n'+json.dumps(step.get('observation'),ensure_ascii=False,indent=2))
        self.live_grid.set_state({**step, 'agent': step['new_state'], 'dynamic_objects': step.get('next_dynamic_objects', [])})
        self.live_status.setText(f"Episode {step['episode']} · Step {step['time'] + 1} · Action {step['selected_action']} · "
                                 f"Reward {step['reward']:+.1f} · Epsilon {step['epsilon']:.4f}")

    def edit_cell(self, x: int, y: int) -> None:
        try:
            s = self.scenario_from_fields()
            tool = self.map_tool.currentText()
            pos = (x, y)
            if tool == 'goal':
                if pos == s.start:
                    raise ValueError('Goal must differ from agent')
                s.goal = pos
            elif tool == 'agent':
                if pos == s.goal:
                    raise ValueError('Agent must differ from goal')
                s.start = pos
            elif pos in (s.start, s.goal):
                raise ValueError('Move the start/goal before editing this cell')
            s.objects = [o for o in s.objects if o.position != pos]
            s.dynamic_objects = [o for o in s.dynamic_objects if o.position != pos]
            if tool == 'moving_obstacle':
                s.dynamic_objects.append(DynamicObject(position=pos, movement=self.movement.currentText()))
            elif tool not in ('erase', 'goal', 'agent'):
                s.objects.append(SceneObject(tool, pos))
            self.load_scenario_fields(s)
        except Exception as error:
            self.report(error)

    def generate_random(self) -> None:
        try:
            s = generate_scenario(self.grid_size.value(), self.scene_seed.value(), self.difficulty.currentText(),
                                  self.density.value(), self.moving_count.value(), self.danger_count.value())
            self.load_scenario_fields(s)
            self.statusBar().showMessage('Generated into editor; Save scenario to apply', 5000)
        except Exception as error:
            self.report(error)

    def apply_difficulty(self, name: str) -> None:
        density, moving, danger = PRESETS[name]
        self.density.setValue(density)
        self.moving_count.setValue(moving)
        self.danger_count.setValue(danger)

    def resize_editor(self, size: int) -> None:
        self.editor_start, self.editor_goal = (0, 0), (size - 1, size - 1)
        lines = []
        for line in self.object_text.toPlainText().splitlines():
            parts = line.split(',')
            if len(parts) == 3:
                try:
                    if 0 <= int(parts[1]) < size and 0 <= int(parts[2]) < size and (int(parts[1]), int(parts[2])) not in (self.editor_start, self.editor_goal):
                        lines.append(line)
                except ValueError:
                    pass
        self.object_text.setPlainText('\n'.join(lines))
        self.editor_dynamic = [o for o in self.editor_dynamic if 0 <= o.position[0] < size and 0 <= o.position[1] < size and o.position not in (self.editor_start, self.editor_goal)]
        try:
            self.preview_editor(self.scenario_from_fields())
        except Exception as error:
            self.statusBar().showMessage(str(error), 4000)

    def preview_editor(self, s: ScenarioSpec) -> None:
        self.scene_grid.set_state({'width': s.width, 'height': s.height, 'agent': s.start, 'goal': s.goal,
                                  'obstacles': [o.position for o in s.objects if o.type not in ('danger_zone', 'slow_zone')],
                                  'danger_zones': [o.position for o in s.objects if o.type == 'danger_zone'],
                                  'slow_zones': [o.position for o in s.objects if o.type == 'slow_zone'],
                                  'dynamic_objects': [asdict(o) for o in s.dynamic_objects]})

    def select_replay_best(self, criterion: str) -> None:
        from aero_ai_studio.replay.replay_engine import ReplayEngine
        path = self.run_select.currentData()
        if not path:
            return
        episode = ReplayEngine.best_episode(Path(path), criterion)
        if episode is None:
            self.report('No successful episodes in this run')
            return
        self.failure_filter.setCurrentText('all')
        self.episode_select.setCurrentIndex(self.episode_select.findData(episode))

    def update_analysis(self) -> None:
        data = analyze_failure(self.replay.episode)
        causes = '\n'.join('• ' + item for item in data['possible_causes']) or 'No failure causes: successful or empty episode.'
        scores = '  '.join(f'{a.upper()}={v:.3f}' for a, v in data['relevant_q_values'].items())
        self.failure_text.setPlainText(f"Failure Type: {data['failure_type']} · Failure Step: {data['failure_step']}\n"
                                       f"Possible Causes:\n{causes}\nRelevant Q-values: {scores}\n"
                                       f"Previous Actions: {', '.join(data['previous_actions'])}\n{data['method']}")
        self.timeline.blockSignals(True)
        self.timeline.clear()
        for i, step in enumerate(self.replay.episode.get('steps', [])):
            self.timeline.addItem(f"Step {i + 1:03d}  {step['selected_action'].upper():5}  {step['reward']:+.1f}  {step['reason']}")
        self.timeline.blockSignals(False)

    def manage_model(self, operation: str) -> None:
        try:
            if (self.worker and self.worker.isRunning()) or (self.eval_worker and self.eval_worker.isRunning()):
                raise ValueError('Wait for the worker to finish before changing models')
            row = self.model_table.currentRow()
            if row < 0:
                raise ValueError('Select a model row first')
            model = self.model_paths[row]
            if operation == 'duplicate':
                ModelRegistry.duplicate(model)
            elif operation == 'rename':
                name, ok = QInputDialog.getText(self, 'Rename model', 'Name', text=read_json(model / 'metadata.json')['name'])
                if ok:
                    ModelRegistry.rename(model, name)
            elif operation == 'delete':
                if QMessageBox.question(self, 'Delete model', f'Delete {model.name}? Evaluation logs will remain.',
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
                ModelRegistry.delete(self.require_project() / 'models', model)
                if self.project.model and Path(self.project.model).name == model.name:
                    self.project.model = None
                    self.repo.save(self.project)
            elif operation == 'notes':
                meta = read_json(model / 'metadata.json')
                notes, ok = QInputDialog.getMultiLineText(self, 'Model notes', 'Notes', meta.get('notes', ''))
                if ok:
                    from aero_ai_studio.core.storage import write_json
                    meta['notes'] = notes
                    write_json(model / 'metadata.json', meta)
            self.refresh_assets()
        except Exception as error:
            self.report(error)

    def show_model_details(self, row: int, *_args) -> None:
        if 0 <= row < len(self.model_paths):
            self.model_details.setPlainText(json.dumps(read_json(self.model_paths[row] / 'metadata.json'), ensure_ascii=False, indent=2))
        else:
            self.model_details.clear()
