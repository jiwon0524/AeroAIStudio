from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import Event
import logging

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QStackedWidget, QLabel, QPushButton, QFormLayout, QLineEdit, QPlainTextEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QInputDialog, QSlider, QSplitter, QScrollArea)

from aero_ai_studio.core.storage import read_json, write_json
from aero_ai_studio.projects.repository import Project, ProjectRepository
from aero_ai_studio.scenario.models import (ScenarioSpec, SceneObject, ENVIRONMENTS, MISSIONS,
    WEATHERS, OBJECTS, RANDOMIZATIONS)
from aero_ai_studio.scenario.repository import ScenarioRepository
from aero_ai_studio.simulation.grid_world import GridWorld
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.agents.q_learning import QLearningAgent
from aero_ai_studio.agents.factory import load_agent
from aero_ai_studio.explainability.brain_map import BrainEvent
from aero_ai_studio.replay.replay_engine import ReplayEngine
from aero_ai_studio.models.registry import ModelRegistry
from aero_ai_studio.deploy.export import export_local, TARGETS
from aero_ai_studio.paper.models import PAPER_MODES, PaperDocument
from aero_ai_studio.video.models import VideoAnalysis
from aero_ai_studio.ui.widgets import GridView, RewardChart, BrainMapView
from aero_ai_studio.ui.fonts import ensure_fonts
from aero_ai_studio.ui.research_panels import ResearchPanels
from aero_ai_studio.core.logging import configure_logging
from aero_ai_studio.scenario.models import DynamicObject, ObservationSpec

PAGES = ("Dashboard", "Projects", "AI Training", "Scenario Lab", "AI Brain Map", "Replay",
         "Paper Lab", "Video Lab", "Models", "Deploy", "Settings", "Evaluation", "Training Comparison", 'Diagnostics', 'Observation Debug','Trajectory')


def combo(items: tuple | list) -> QComboBox:
    widget = QComboBox()
    widget.addItems(items)
    return widget


def integer(value: int, minimum: int, maximum: int) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    return widget


def decimal(value: float, minimum: float = 0, maximum: float = 1) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(4)
    widget.setRange(minimum, maximum)
    widget.setSingleStep(0.01)
    widget.setValue(value)
    return widget


def button(label: str, slot) -> QPushButton:
    widget = QPushButton(label)
    widget.clicked.connect(slot)
    return widget


class TrainingWorker(QThread):
    progress = Signal(dict)
    completed = Signal(object)
    failed = Signal(str)
    visual = Signal(dict)

    def __init__(self, trainer: Trainer, runs: Path, resume: Path | None = None, visual_mode: bool = False):
        super().__init__()
        self.trainer = trainer
        self.runs = runs
        self.cancel = Event()
        self.checkpoint_request = Event()
        self.resume = resume
        self.visual_mode = visual_mode

    def run(self) -> None:
        try:
            self.completed.emit(self.trainer.run(self.runs, self.progress.emit, self.cancel,
                                self.resume, self.checkpoint_request, self.visual.emit if self.visual_mode else None))
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(ResearchPanels, QMainWindow):
    def __init__(self, workspace: Path):
        super().__init__()
        ensure_fonts()
        self.setWindowTitle("Aero AI Studio · V0.7 · Actual Gazebo Validation Pending")
        self.resize(1420, 920)
        self.workspace = workspace.resolve()
        configure_logging(self.workspace)
        self.repo = ProjectRepository(self.workspace)
        self.project: Project | None = None
        self.scenario: ScenarioSpec | None = None
        self.worker: TrainingWorker | None = None
        self.eval_worker = None
        self.editor_start, self.editor_goal = (0, 0), (19, 19)
        self.editor_dynamic: list[DynamicObject] = []
        self.editor_observation = ObservationSpec()
        self.replay = ReplayEngine()
        self.run_paths: list[Path] = []
        self.model_paths: list[Path] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self._closing = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        self.nav = QListWidget()
        self.nav.addItems(PAGES)
        self.nav.setFixedWidth(180)
        self.stack = QStackedWidget()
        layout.addWidget(self.nav)
        content = QWidget()
        body = QVBoxLayout(content)
        self.context_label = QLabel('Project: — | Scenario: — | Run: — | Model: —')
        self.context_label.setWordWrap(True)
        body.addWidget(self.context_label)
        body.addWidget(self.stack, 1)
        layout.addWidget(content, 1)
        self.nav.currentRowChanged.connect(self.navigate)
        self.build_dashboard()
        self.build_projects()
        self.build_training()
        self.build_scenario()
        self.build_brain()
        self.build_replay()
        self.build_labs()
        self.build_models()
        self.build_deploy()
        self.build_settings()
        self.build_evaluation()
        self.build_comparison()
        self.build_diagnostics()
        self.build_observation_debug()
        self.add_trajectory()
        self.eval_model.currentIndexChanged.connect(lambda *_: self.update_context())
        self.setStyleSheet('''
            QWidget { background: #131e2a; color: #dce7f3; font-family: 'Segoe UI'; font-size: 13px; }
            QListWidget { background: #0e1721; border: 0; }
            QListWidget::item { padding: 14px 8px; }
            QListWidget::item:selected { background: #234b70; color: #ffffff; }
            QPushButton { background: #244e73; border: 1px solid #35688e; border-radius: 4px; padding: 9px 14px; }
            QPushButton:hover { background: #30638d; }
            QPushButton:disabled { color: #6c7c8e; background: #1c2a38; }
            QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget { background: #0f1924; border: 1px solid #304153; padding: 5px; }
            QGroupBox { border: 1px solid #304153; margin-top: 16px; padding: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; }
            QHeaderView::section { background: #223548; padding: 6px; }
        ''')
        self.refresh_projects()
        self.nav.setCurrentRow(0)

    def page(self, title: str, subtitle: str) -> QVBoxLayout:
        page = QWidget()
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setMaximumHeight(50)
        heading.setStyleSheet("font-size: 25px; font-weight: 600; padding: 8px 0;")
        layout.addWidget(heading)
        description = QLabel(subtitle)
        description.setWordWrap(True)
        description.setMaximumHeight(48)
        layout.addWidget(description)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return layout

    def report(self, error: Exception | str) -> None:
        logging.getLogger(__name__).error('%s', error)
        QMessageBox.warning(self, "Aero AI Studio", str(error))

    def navigate(self, index: int) -> None:
        self.timer.stop()
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.refresh_dashboard()
        if index in (4, 5, 8, 9, 11, 12):
            self.refresh_assets()

    def build_dashboard(self) -> None:
        layout = self.page("Research overview", "PC-only simulation · Q-Learning · recorded decision evidence")
        cards = QHBoxLayout()
        self.cards: dict[str, QLabel] = {}
        for title in ("Projects", "Training Runs", "Models", "Average Success Rate"):
            group = QGroupBox(title)
            inner = QVBoxLayout(group)
            value = QLabel("—")
            value.setStyleSheet("font-size: 30px; color: #70bdff;")
            inner.addWidget(value)
            cards.addWidget(group)
            self.cards[title] = value
        layout.addLayout(cards)
        self.dashboard_text = QPlainTextEdit()
        self.dashboard_text.setReadOnly(True)
        layout.addWidget(self.dashboard_text)
        layout.addWidget(button("New Project", lambda: self.nav.setCurrentRow(1)))

    def refresh_dashboard(self) -> None:
        try:
            projects = self.repo.list()
            runs = [read_json(p) for p in self.repo.root.glob("*/runs/*/run.json")]
            models = list(self.repo.root.glob("*/models/*/metadata.json"))
            finished = [r for r in runs if r.get("episodes_completed", 0)]
            values = [str(len(projects)), str(len(runs)), str(len(models)),
                      f"{sum(r['success_rate'] for r in finished) / len(finished):.1%}" if finished else "—"]
            for label, value in zip(self.cards.values(), values):
                label.setText(value)
            latest = max(runs, key=lambda r: r["created_date"], default=None)
            failures = []
            metric_files = sorted(self.repo.root.glob("*/runs/*/metrics.json"),
                                  key=lambda p: read_json(p.parent / "run.json")["created_date"])
            for p in metric_files:
                failures.extend((p.parent.name, r) for r in read_json(p) if not r["success"])
            current = self.project.name if self.project else "None"
            self.dashboard_text.setPlainText(
                f"ACTIVE PROJECT  {current}\nWorkspace  {self.workspace}\n\n"
                f"LATEST SIMULATION\n{latest['id'] + ' · ' + latest['status'] if latest else 'No simulations yet'}\n\n"
                f"LATEST FAILURE\n{failures[-1][0] + ' · Episode ' + str(failures[-1][1]['episode']) + ' · ' + failures[-1][1]['reason'] if failures else 'No failures recorded'}\n\n"
                "Average success rate is the mean of recorded run training success rates, including exploration.\n\n"
                "WORKFLOW\nNew Project → Scenario Lab → AI Training → Replay + AI Brain Map → Models → Deploy")
        except Exception as error:
            self.report(error)

    def build_projects(self) -> None:
        layout = self.page("Projects", "Local workspaces. Opening a project restores its scenario, runs and models.")
        form = QFormLayout()
        self.project_name = QLineEdit()
        self.project_description = QLineEdit()
        self.project_type = combo(["Q-Learning", "Drone AI (planned)", "Robot AI (planned)", "Game AI (planned)"])
        self.objective = QLineEdit("Obstacle Avoidance")
        for title, widget in (("Project name", self.project_name), ("Description", self.project_description),
                              ("AI type", self.project_type), ("Objective", self.objective)):
            form.addRow(title, widget)
        layout.addLayout(form)
        self.create_button = button("New Project", self.create_project)
        layout.addWidget(self.create_button)
        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(lambda _: self.open_project())
        layout.addWidget(self.project_list)
        self.open_button = button("Open selected project", self.open_project)
        layout.addWidget(self.open_button)
        self.project_info = QLabel("No active project")
        self.project_info.setWordWrap(True)
        layout.addWidget(self.project_info)

    def refresh_projects(self) -> None:
        self.projects = self.repo.list()
        self.project_list.clear()
        for p in self.projects:
            self.project_list.addItem(f"{p.name}  ·  {p.ai_type}  ·  {p.created_date[:10]}  ·  {len(p.training_runs)} runs")
        if self.projects and self.project is None:
            self.project_list.setCurrentRow(0)
            self.open_project()

    def create_project(self) -> None:
        try:
            p = Project(self.project_name.text().strip(), self.project_description.text(),
                        self.project_type.currentText(), self.objective.text())
            self.repo.save(p)
            self.project = p
            self.scenario = None
            self.refresh_projects()
            self.set_project()
            logging.getLogger(__name__).info('project open %s', self.project.id)
            self.statusBar().showMessage(f"Created {p.name}", 5000)
            self.nav.setCurrentRow(3)
        except Exception as error:
            self.report(error)

    def open_project(self) -> None:
        index = self.project_list.currentRow()
        if index < 0:
            return
        try:
            self.project = self.projects[index]
            path = self.repo.path(self.project) / "scenarios" / "scenario.json"
            self.scenario = ScenarioRepository.load(path) if path.exists() else None
            self.set_project()
            logging.getLogger(__name__).info('project open %s scenario load %s', self.project.id, path if self.scenario else 'none')
        except Exception as error:
            self.report(error)

    def set_project(self) -> None:
        p = self.project
        if not p:
            return
        self.timer.stop()
        self.replay = ReplayEngine()
        self.replay_grid.set_state({})
        self.replay_brain.clear()
        self.brain_text.clear()
        self.brain_map.set_step({})
        self.set_observation_step({})
        self.timeline.clear()
        self.failure_text.clear()
        self.project_info.setText(f"Active: {p.name}\n{p.description}\nObjective: {p.objective}\n{self.repo.path(p)}")
        self.train_project.setText(f"Project: {p.name} · Scenario: {self.scenario.name if self.scenario else 'save a scenario first'}")
        if self.scenario:
            self.load_scenario_fields(self.scenario)
        else:
            self.load_scenario_fields(ScenarioSpec(objects=[SceneObject("wall", (8, y)) for y in range(4, 16)]))
        self.refresh_assets()

    def require_project(self) -> Path:
        if self.project is None:
            raise ValueError("Create or open a project first")
        return self.repo.path(self.project)

    def build_scenario(self) -> None:
        layout = self.page("Scenario Lab", "Synthetic World executes in 2D. Other worlds, sensors and physical conditions are configuration metadata only.")
        split = QSplitter()
        panel = QWidget()
        form = QFormLayout(panel)
        self.scene_name = QLineEdit("warehouse_test_01")
        self.world = combo(["synthetic", "korea_real", "hybrid"])
        self.environment = combo(list(ENVIRONMENTS))
        self.mission = combo(list(MISSIONS))
        self.weather = combo(list(WEATHERS))
        self.grid_size = integer(20, 4, 100)
        self.grid_preset = combo(['20x20', '10x10', '30x30', 'Custom'])
        self.grid_preset.currentTextChanged.connect(lambda value: self.grid_size.setValue(int(value.split('x')[0])) if value != 'Custom' else None)
        self.scene_seed = integer(42, 0, 2147483647)
        for title, widget in (("Name", self.scene_name), ("World mode", self.world), ("Environment", self.environment),
                              ("Mission", self.mission), ("Weather", self.weather), ("Square grid size", self.grid_size),
                              ("Random seed", self.scene_seed)):
            form.addRow(title, widget)
        form.addRow('Grid preset', self.grid_preset)
        self.map_tool = combo(['wall', 'static_obstacle', 'goal', 'agent', 'moving_obstacle', 'danger_zone', 'slow_zone', 'erase'])
        self.movement = combo(['horizontal', 'vertical', 'random'])
        form.addRow('Click map tool', self.map_tool)
        form.addRow('Moving obstacle pattern', self.movement)
        self.difficulty = combo(['easy', 'normal', 'hard', 'extreme'])
        self.difficulty.setCurrentText('normal')
        self.density = decimal(0.10, 0, 0.6)
        self.moving_count, self.danger_count = integer(2, 0, 500), integer(3, 0, 1000)
        for label, widget in [('Difficulty', self.difficulty), ('Obstacle density', self.density),
                              ('Moving count', self.moving_count), ('Danger count', self.danger_count)]:
            form.addRow(label, widget)
        self.difficulty.currentTextChanged.connect(self.apply_difficulty)
        form.addRow(button('Generate Random Scenario', self.generate_random))
        self.observation_mode = combo(['basic', 'local', 'sensor', 'full_debug', 'extended'])
        form.addRow('Scenario observation (FULL_DEBUG is not policy input)', self.observation_mode)
        self.sensor_checks = {s: QCheckBox(s) for s in ("camera", "lidar", "gps")}
        for check in self.sensor_checks.values():
            check.setChecked(True)
            form.addRow(check)
        self.random_checks = {s: QCheckBox(s + (" (metadata only)" if s not in ("obstacle_position", "obstacle_count",'goal_position','moving_speed') else "")) for s in RANDOMIZATIONS}
        for check in self.random_checks.values():
            form.addRow(check)
        form.addRow(QLabel("Objects: type,x,y. Danger terminates; Slow adds reward cost. Click map to edit."))
        self.object_text = QPlainTextEdit("\n".join(f"wall,8,{y}" for y in range(4, 16)))
        self.object_text.setMaximumHeight(150)
        form.addRow(self.object_text)
        self.object_type = combo(list(OBJECTS))
        self.object_x, self.object_y = integer(5, 0, 99), integer(5, 0, 99)
        row = QHBoxLayout()
        for widget in (self.object_type, self.object_x, self.object_y, button("Add", self.add_object)):
            row.addWidget(widget)
        form.addRow(row)
        row = QHBoxLayout()
        self.save_scenario_button = button("Save scenario + preview", self.save_scenario)
        self.load_scenario_button = button("Load JSON", self.import_scenario)
        row.addWidget(self.save_scenario_button)
        row.addWidget(self.load_scenario_button)
        layout.addLayout(row)
        gazebo_row=QHBoxLayout()
        gazebo_row.addWidget(button('Export to Gazebo',self.export_gazebo))
        gazebo_row.addWidget(button('Launch Gazebo',self.launch_gazebo))
        layout.addLayout(gazebo_row)
        self.scene_grid = GridView()
        self.scene_grid.editable = True
        self.scene_grid.cell_clicked.connect(self.edit_cell)
        self.grid_size.valueChanged.connect(self.resize_editor)
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setMinimumWidth(410)
        panel_scroll.setWidget(panel)
        split.addWidget(panel_scroll)
        split.addWidget(self.scene_grid)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        legend = QLabel('Click map: tool applies to draft. Gray=wall · orange=moving · red=danger · ochre=slow. Save to apply.')
        legend.setMaximumHeight(35)
        layout.addWidget(legend)
        layout.addWidget(split, 1)

    def add_object(self) -> None:
        self.object_text.appendPlainText(f"{self.object_type.currentText()},{self.object_x.value()},{self.object_y.value()}")

    def scenario_from_fields(self) -> ScenarioSpec:
        objects = []
        for line in self.object_text.toPlainText().splitlines():
            if line.strip():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 3:
                    raise ValueError("Each obstacle line must be type,x,y")
                objects.append(SceneObject(parts[0], (int(parts[1]), int(parts[2]))))
        size = self.grid_size.value()
        spec = ScenarioSpec(name=self.scene_name.text(), world_mode=self.world.currentText(),
                            environment=self.environment.currentText(), mission=self.mission.currentText(),
                            weather=self.weather.currentText(), width=size, height=size, start=self.editor_start, goal=self.editor_goal,
                            objects=objects, sensors=[s for s, c in self.sensor_checks.items() if c.isChecked()],
                            randomization={s: c.isChecked() for s, c in self.random_checks.items()}, seed=self.scene_seed.value(),
                            dynamic_objects=list(self.editor_dynamic), difficulty=self.difficulty.currentText(),
                            observation=ObservationSpec(**{**asdict(self.editor_observation), 'mode': self.observation_mode.currentText()}))
        spec.validate()
        return spec

    def load_scenario_fields(self, s: ScenarioSpec) -> None:
        self.scene_name.setText(s.name)
        for widget, value in ((self.world, s.world_mode), (self.environment, s.environment),
                              (self.mission, s.mission), (self.weather, s.weather)):
            widget.setCurrentText(value)
        self.grid_size.blockSignals(True)
        self.grid_size.setValue(s.width)
        self.grid_size.blockSignals(False)
        self.editor_start, self.editor_goal = s.start, s.goal
        self.editor_dynamic = list(s.dynamic_objects)
        self.editor_observation = s.observation
        self.observation_mode.setCurrentText(s.observation.mode)
        self.train_observation.setCurrentText('sensor' if s.observation.mode in ('extended','full_debug') else s.observation.mode)
        self.difficulty.setCurrentText(s.difficulty)
        self.scene_seed.setValue(s.seed)
        self.object_text.setPlainText("\n".join(f"{o.type},{o.position[0]},{o.position[1]}" for o in s.objects))
        for name, check in self.sensor_checks.items():
            check.setChecked(name in s.sensors)
        for name, check in self.random_checks.items():
            check.setChecked(s.randomization.get(name, False))
        self.preview_editor(s)

    def save_scenario(self) -> None:
        try:
            root = self.require_project()
            spec = self.scenario_from_fields()
            if spec.world_mode == "synthetic" and spec.mission in ("obstacle_avoidance", "navigation"):
                GridWorld(spec)
            ScenarioRepository.save(root / "scenarios" / "scenario.json", spec)
            self.scenario = spec
            self.project.scenario = "scenarios/scenario.json"
            self.repo.save(self.project)
            self.load_scenario_fields(spec)
            self.train_project.setText(f"Project: {self.project.name} · Scenario: {spec.name}")
            self.statusBar().showMessage("Scenario saved", 5000)
            self.update_context()
            logging.getLogger(__name__).info('scenario save/load %s', spec.name)
        except Exception as error:
            self.report(error)

    def import_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load scenario", str(self.workspace), "JSON (*.json)")
        if path:
            try:
                s = ScenarioRepository.load(Path(path))
                if s.width != s.height:
                    raise ValueError('UI editor supports square grids; Core supports rectangular grids')
                self.load_scenario_fields(s)
                self.statusBar().showMessage("Loaded into editor; Save scenario to apply", 7000)
            except Exception as error:
                self.report(error)

    def build_training(self) -> None:
        page_layout = self.page("AI Training / Train", "Q-Learning / DQN · background worker · recorded policy observations and decisions")
        split = QSplitter()
        controls = QWidget()
        layout = QVBoxLayout(controls)
        controls_scroll=QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(440)
        controls_scroll.setWidget(controls)
        split.addWidget(controls_scroll)
        page_layout.addWidget(split, 2)
        self.train_project = QLabel("Create a project and save a scenario first")
        layout.addWidget(self.train_project)
        form = QFormLayout()
        self.episodes = integer(1000, 1, 100000)
        self.lr, self.gamma = decimal(0.1, 0.0001), decimal(0.95)
        self.epsilon, self.decay = decimal(1.0), decimal(0.995, 0.0001)
        self.max_steps = integer(200, 1, 10000)
        self.train_seed = integer(42, 0, 2147483647)
        self.checkpoint_interval = integer(100, 1, 100000)
        self.training_mode = combo(['Fast Training', 'Visual Training'])
        self.render_interval = combo(['Every Episode', 'Every 10 Episodes', 'Every 100 Episodes'])
        self.render_interval.setCurrentIndex(1)
        for title, widget in (("Episodes", self.episodes), ("Learning rate", self.lr), ("Gamma", self.gamma),
                              ("Epsilon", self.epsilon), ("Epsilon decay", self.decay), ("Max steps", self.max_steps),
                              ("Seed", self.train_seed)):
            form.addRow(title, widget)
        form.addRow('Checkpoint interval', self.checkpoint_interval)
        form.addRow('Mode', self.training_mode)
        form.addRow('Render frequency', self.render_interval)
        self.add_agent_controls(form)
        layout.addLayout(form)
        self.start_button = button("Start Training", self.start_training)
        self.cancel_button = button("Stop after current episode", self.stop_training)
        self.cancel_button.setEnabled(False)
        action_row=QHBoxLayout()
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.cancel_button)
        row = QHBoxLayout()
        self.checkpoint_button = button('Save Checkpoint', self.request_checkpoint)
        self.checkpoint_button.setEnabled(False)
        self.resume_button = button('Resume Training', self.resume_training)
        row.addWidget(self.checkpoint_button)
        row.addWidget(self.resume_button)
        row.addWidget(button('Go to Evaluation', lambda: self.nav.setCurrentRow(11)))
        action_row.addLayout(row)
        page_layout.insertLayout(2,action_row)
        self.training_status = QLabel("Ready")
        self.training_status.setWordWrap(True)
        page_layout.insertWidget(3,self.training_status)
        self.chart = RewardChart()
        page_layout.addWidget(self.chart, 1)
        self.live_status = QLabel('Fast Training minimizes grid rendering. Visual Training samples selected episodes.')
        self.live_grid = GridView()
        self.live_grid.setMinimumHeight(260)
        self.live_status.setWordWrap(True)
        visual_panel = QWidget()
        visual_layout = QVBoxLayout(visual_panel)
        visual_layout.addWidget(self.live_status)
        visual_layout.addWidget(self.live_grid, 1)
        self.live_observation=QPlainTextEdit()
        self.live_observation.setReadOnly(True)
        self.live_observation.setMaximumHeight(150)
        visual_layout.addWidget(self.live_observation)
        split.addWidget(visual_panel)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)

    def start_training(self) -> None:
        try:
            root = self.require_project()
            if self.scenario is None:
                raise ValueError("Save a scenario first")
            if self.worker and self.worker.isRunning():
                return
            cfg = TrainingConfig(self.episodes.value(), self.lr.value(), self.gamma.value(), self.epsilon.value(),
                                 self.decay.value(), self.max_steps.value(), self.train_seed.value(),
                                 checkpoint_interval=self.checkpoint_interval.value(),
                                 visual_interval=(1, 10, 100)[self.render_interval.currentIndex()],
                                 visual_delay=0.02 if self.training_mode.currentIndex() else 0,
                                 algorithm='dqn' if self.algorithm.currentText()=='DQN' else 'q_learning',
                                 observation_mode=self.train_observation.currentText(),
                                 state_encoder=('basic' if self.train_observation.currentText()=='basic' else 'compact') if self.train_encoder.currentText()=='auto' else self.train_encoder.currentText(),
                                 local_radius=self.local_window.currentIndex()+1,batch_size=self.batch_size.value(),
                                 buffer_size=self.buffer_size.value(),target_interval=self.target_interval.value(),epsilon_end=self.epsilon_end.value(),
                                 safety_enabled=self.safety_enabled.isChecked(),safety_threshold=self.safety_threshold.value(),
                                 reward_version=self.reward_version.currentText(),double_dqn=self.double_dqn.isChecked(),
                                 warmup_steps=self.warmup_steps.value(),curriculum_enabled=self.curriculum_enabled.isChecked(),curriculum_threshold=self.curriculum_threshold.value(),
                                 simulator='gazebo' if self.simulator.currentText()=='Gazebo' else 'grid',
                                 gazebo_control_mode=self.gazebo_control_mode.currentText(),
                                 curriculum_minimum_episodes=(self.curriculum_stage_min.value(),)*4+(self.curriculum_hard_min.value(),) if self.curriculum_enabled.isChecked() else (),
                                 curriculum_minimum_evaluations=self.curriculum_eval_min.value())
            trainer = Trainer(ScenarioSpec.from_dict(self.scenario.to_dict()), cfg,self.backend_factory(root))
            self.launch_training(trainer, root / 'runs')
        except Exception as error:
            self.report(error)

    def launch_training(self, trainer: Trainer, runs: Path, resume: Path | None = None) -> None:
        if (self.worker and self.worker.isRunning()) or (self.eval_worker and self.eval_worker.isRunning()):
            raise ValueError('Wait for the current worker to finish')
        from aero_ai_studio.training.checkpoint import CheckpointStore
        self.chart.rows = list(CheckpointStore.load(resume)['metrics']) if resume else []
        self.chart.update()
        self.worker = TrainingWorker(trainer, runs, resume, self.training_mode.currentIndex() == 1)
        self.worker.progress.connect(self.training_progress)
        self.worker.visual.connect(self.training_visual)
        self.worker.completed.connect(self.training_complete)
        self.worker.failed.connect(self.training_failed)
        self.worker.finished.connect(self.worker_finished)
        self.set_busy(True)
        self.training_status.setText('Training started…')
        self.worker.start()

    def set_busy(self, busy: bool) -> None:
        for widget in (self.start_button, self.create_button, self.open_button,
                       self.project_list, self.save_scenario_button, self.load_scenario_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        for widget in (self.resume_button, self.evaluate_button, self.model_table):
            widget.setEnabled(not busy)
        self.checkpoint_button.setEnabled(busy)
        self.scene_grid.editable = not busy

    def stop_training(self) -> None:
        if self.worker:
            self.worker.cancel.set()

    def training_progress(self, row: dict) -> None:
        self.chart.rows.append(row)
        if row["episode"] % 10 == 0 or row["episode"] == 1:
            self.chart.update()
        self.training_status.setText(f"Episode {row['episode']}  |  Reward {row['reward']:+.1f}  |  Steps {row['steps']}  |  "
                                     f"Success {row['success_rate']:.1%}  |  Collisions {row['collision_count']}  |  Epsilon {row['epsilon']:.4f}")

    def training_complete(self, result: tuple) -> None:
        root, _, meta = result
        if root.name not in self.project.training_runs:
            self.project.training_runs.append(root.name)
        self.repo.save(self.project)
        self.training_status.setText(f"{meta['status'].upper()} · {meta['episodes_completed']} episodes · "
                                     f"Success {meta['success_rate']:.1%} · Average reward {meta['average_reward']:.2f}\nSaved: {root}")
        self.chart.update()
        self.refresh_assets()

    def training_failed(self, message: str) -> None:
        self.training_status.setText(f"FAILED · {message}")
        self.report(message)

    def worker_finished(self) -> None:
        self.set_busy(False)
        if self._closing:
            self.close()

    def build_brain(self) -> None:
        layout = self.page("AI Brain Map", "Shared Replay selection · actual pre-update Q-values, exploration policy and observed result")
        layout.addWidget(button("Select run / episode in Replay", lambda: self.nav.setCurrentRow(5)))
        self.brain_map = BrainMapView()
        layout.addWidget(self.brain_map)
        self.brain_v4=QLabel('Select a step to inspect proposal, Safety and reward components')
        self.brain_v4.setWordWrap(True)
        self.brain_v4.setMaximumHeight(120)
        layout.addWidget(self.brain_v4)
        self.brain_text = QPlainTextEdit()
        self.brain_text.setReadOnly(True)
        self.brain_text.setStyleSheet("font-family: Consolas; font-size: 15px;")
        layout.addWidget(self.brain_text)
        self.timeline = QListWidget()
        self.timeline.setMaximumHeight(150)
        self.timeline.currentRowChanged.connect(lambda row: self.seek(row) if row >= 0 else None)
        layout.addWidget(QLabel('Decision Timeline · click any step to synchronize Grid and Brain Map'))
        layout.addWidget(self.timeline)

    def build_replay(self) -> None:
        layout = self.page("Replay / Evaluation", "Blue A = pre-action state · yellow outline = result state · green G = goal · blocks = obstacles")
        form = QFormLayout()
        self.run_select = QComboBox()
        self.run_select.currentIndexChanged.connect(self.refresh_episodes)
        self.failure_filter = combo(["all", "success", "failed", "collision", "timeout", "moving_obstacle_collision", "danger_zone"])
        self.failure_filter.currentIndexChanged.connect(self.refresh_episodes)
        self.episode_select = QComboBox()
        self.episode_select.currentIndexChanged.connect(self.load_episode)
        form.addRow("Training run", self.run_select)
        form.addRow("Failure filter (failed = failed to reach target)", self.failure_filter)
        form.addRow("Episode", self.episode_select)
        layout.addLayout(form)
        row = QHBoxLayout()
        for label, criterion in [('Best Episode', 'best'), ('Shortest Episode', 'shortest'), ('Highest Reward', 'highest_reward')]:
            row.addWidget(button(label, lambda checked=False, c=criterion: self.select_replay_best(c)))
        row.addWidget(button('Brain Map / Timeline', lambda: self.nav.setCurrentRow(4)))
        row.addWidget(button('Observation Debug',lambda:self.nav.setCurrentRow(14)))
        row.addWidget(button('Trajectory',lambda:self.nav.setCurrentRow(15)))
        layout.addLayout(row)
        controls = QHBoxLayout()
        self.speed = combo(["1x", "2x", "4x"])
        self.speed.currentIndexChanged.connect(self.update_speed)
        for widget in (button("Play", self.play), button("Pause", self.timer.stop),
                       button("Previous Step", lambda: self.seek(self.replay.index - 1)),
                       button("Next Step", self.advance), self.speed):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.step_slider = QSlider(Qt.Orientation.Horizontal)
        self.step_slider.valueChanged.connect(self.seek)
        layout.addWidget(self.step_slider)
        self.replay_status = QLabel("Select a recorded run")
        layout.addWidget(self.replay_status)
        split = QSplitter()
        self.replay_grid = GridView()
        self.replay_brain = QPlainTextEdit()
        self.replay_brain.setReadOnly(True)
        self.replay_brain.setStyleSheet("font-family: Consolas;")
        from PySide6.QtWidgets import QTabWidget
        replay_tabs=QTabWidget()
        self.replay_observation=QPlainTextEdit()
        self.replay_observation.setReadOnly(True)
        replay_tabs.addTab(self.replay_brain,'Decision evidence')
        replay_tabs.addTab(self.replay_observation,'What AI Saw')
        split.addWidget(self.replay_grid)
        split.addWidget(replay_tabs)
        layout.addWidget(split, 1)
        self.failure_text = QPlainTextEdit()
        self.failure_text.setReadOnly(True)
        self.failure_text.setMaximumHeight(190)
        layout.addWidget(QLabel('Rule-based Failure Analysis · observations and possible causes'))
        layout.addWidget(self.failure_text)

    def refresh_assets(self) -> None:
        if not self.project:
            return
        root = self.repo.path(self.project)
        self.run_paths = sorted((root / "runs").glob("*/metrics.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        self.run_paths = [p.parent for p in self.run_paths]
        old = self.run_select.currentData()
        self.run_select.blockSignals(True)
        self.run_select.clear()
        for path in self.run_paths:
            meta = read_json(path / "run.json")
            self.run_select.addItem(f"{path.name} · {meta['status']}", str(path))
        for p in sorted((root / 'evaluations').glob('*/metrics.json')):
            self.run_select.addItem(f'EVALUATION · {p.parent.name}', str(p.parent))
        if old:
            index = self.run_select.findData(old)
            if index >= 0:
                self.run_select.setCurrentIndex(index)
        self.run_select.blockSignals(False)
        # Preserve the selected replay step when merely navigating between pages.
        if old != self.run_select.currentData() or not self.replay.episode:
            self.refresh_episodes()
        models = ModelRegistry.list(root / "models")
        self.model_paths = [path for path, _ in models]
        self.model_table.setRowCount(len(models))
        self.export_model.clear()
        for row, (path, meta) in enumerate(models):
            values = [meta["name"], meta["version"], meta["algorithm"], meta["training_run"],
                      meta["scenario"]["name"], f"{meta['success_rate']:.1%}", f"{meta['average_reward']:.2f}", meta["created_date"]]
            for column, value in enumerate(values):
                self.model_table.setItem(row, column, QTableWidgetItem(str(value)))
            self.export_model.addItem(f"{meta['name']} v{meta['version']}", str(path))
        self.refresh_research()

    def refresh_episodes(self, *_args) -> None:
        self.timer.stop()
        self.episode_select.blockSignals(True)
        self.episode_select.clear()
        path = self.run_select.currentData()
        if path:
            try:
                for row in ReplayEngine.episodes(Path(path), self.failure_filter.currentText()):
                    self.episode_select.addItem(f"#{row['episode']} · {'SUCCESS' if row['success'] else 'FAILED'} · "
                                                f"{row['reason']} · Reward {row['reward']:+.1f} · {row['steps']} steps", row["episode"])
            except Exception as error:
                self.report(error)
        self.episode_select.blockSignals(False)
        self.load_episode()

    def load_episode(self, *_args) -> None:
        self.timer.stop()
        number = self.episode_select.currentData()
        path = self.run_select.currentData()
        if number is None or not path:
            self.replay = ReplayEngine()
            self.replay_grid.set_state({})
            self.replay_brain.clear()
            self.brain_text.clear()
            self.brain_map.set_step({})
            self.set_observation_step({})
            self.timeline.clear()
            self.failure_text.clear()
            self.replay_status.setText("No episodes matching this filter")
            self.step_slider.setRange(0, 0)
            return
        try:
            self.replay.load(Path(path), number)
            self.update_analysis()
            self.trajectory_view.set_episode(self.replay.episode)
            self.step_slider.setRange(0, max(0, self.replay.count - 1))
            self.seek(0)
        except Exception as error:
            self.report(error)

    def seek(self, index: int) -> None:
        step = self.replay.seek(index)
        if step is None:
            return
        self.step_slider.blockSignals(True)
        self.step_slider.setValue(self.replay.index)
        self.step_slider.blockSignals(False)
        self.replay_grid.set_state({**step, "agent": step["state"]})
        evidence = BrainEvent(step).text()
        self.brain_map.set_step(step)
        shield=step.get('safety',{})
        components=step.get('reward_components',{})
        sensors=(step.get('observation') or {}).get('sensor_state',{})
        self.brain_v4.setText(f"Proposed: {step.get('proposed_action',step['selected_action'])}  |  Safety: "
            f"{'OVERRIDE' if shield.get('override') else 'allowed / disabled'}  |  Final: {step.get('final_action',step['selected_action'])}\n"
            f"Reason: {shield.get('reason','legacy')}  |  Motion: {sensors.get('moving_object_relative_motion','not recorded')}  |  TTC: {sensors.get('time_to_collision')}\n"
            f"Reward: "+'  '.join(f'{k} {v:+.2f}' for k,v in components.items() if v)+f"  |  Total {step['reward']:+.2f}")
        telemetry=step.get('telemetry',{})
        if telemetry:
            self.brain_v4.setText(self.brain_v4.text()+f"\nSim time: {telemetry.get('simulation_time')} | Sensor age(ms): {telemetry.get('sensor_age_ms')} | Collision: {telemetry.get('collision_source')}")
        self.set_observation_step(step)
        self.trajectory_view.cursor=self.replay.index
        self.trajectory_view.update()
        self.timeline.blockSignals(True)
        self.timeline.setCurrentRow(self.replay.index)
        self.timeline.blockSignals(False)
        self.update_context()
        self.replay_brain.setPlainText(evidence)
        self.brain_text.setPlainText(f"Episode #{self.replay.episode['episode']} · Step {self.replay.index + 1}/{self.replay.count}\n\n{evidence}")
        self.replay_status.setText(f"Episode #{self.replay.episode['episode']} · Step {self.replay.index + 1}/{self.replay.count} · "
                                   f"Action {step['selected_action']} · Reward {step['reward']:+.1f} · {step['reason']}")

    def play(self) -> None:
        if self.replay.count:
            if self.replay.index == self.replay.count - 1:
                self.seek(0)
            self.update_speed()
            self.timer.start()

    def update_speed(self, *_args) -> None:
        self.timer.setInterval(500 // (1, 2, 4)[self.speed.currentIndex()])

    def advance(self) -> None:
        if self.replay.index + 1 >= self.replay.count:
            self.timer.stop()
            return
        self.seek(self.replay.index + 1)

    def build_labs(self) -> None:
        paper = self.page("Paper Lab", "Architecture preview · PDF → Parser → AI Analyzer → Experiment Specification → Simulation Scenario")
        self.paper_title = QLineEdit()
        self.paper_source = QLineEdit()
        self.paper_mode = combo(list(PAPER_MODES))
        form = QFormLayout()
        form.addRow("Title", self.paper_title)
        form.addRow("PDF path / reference", self.paper_source)
        form.addRow("Explanation mode", self.paper_mode)
        paper.addLayout(form)
        paper.addWidget(button("Save paper reference", self.save_paper))
        paper.addWidget(QLabel("Planned: parsing, AI analysis and generated experiments. No LLM/API is connected."))
        paper.addStretch()
        video = self.page("Video Lab", "Architecture preview · Detection → Tracking → Motion → Behavior → Timeline → Simulation Replay")
        self.video_source = QLineEdit()
        form = QFormLayout()
        form.addRow("Video path / reference", self.video_source)
        video.addLayout(form)
        video.addWidget(button("Save video reference", self.save_video))
        video.addWidget(QLabel("No detector is connected. Timeline events will come from a future VideoAnalysisAdapter."))
        video.addStretch()

    def save_paper(self) -> None:
        try:
            root = self.require_project()
            doc = PaperDocument(self.paper_title.text(), self.paper_source.text(), self.paper_mode.currentText())
            if not doc.title.strip() or not doc.source.strip():
                raise ValueError("Title and source are required")
            write_json(root / "paper_reference.json", asdict(doc))
            self.statusBar().showMessage("Paper reference saved", 5000)
        except Exception as error:
            self.report(error)

    def save_video(self) -> None:
        try:
            root = self.require_project()
            if not self.video_source.text().strip():
                raise ValueError("Video source is required")
            write_json(root / "video_reference.json", asdict(VideoAnalysis(self.video_source.text())))
            self.statusBar().showMessage("Video reference saved", 5000)
        except Exception as error:
            self.report(error)

    def build_models(self) -> None:
        layout = self.page("Model Registry", "Q-table snapshots with source scenario and training metrics. Success rates include exploration.")
        layout.addWidget(button("Save selected Replay run as Model", self.save_model))
        self.model_table = QTableWidget(0, 8)
        self.model_table.setHorizontalHeaderLabels(["Name", "Version", "Algorithm", "Training run", "Scenario", "Success", "Avg reward", "Created UTC"])
        self.model_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.model_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.model_table)
        self.model_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        row = QHBoxLayout()
        row.addWidget(button('Evaluate selected model', self.evaluate_registry_model))
        for label, operation in [('Duplicate Model', 'duplicate'), ('Rename', 'rename'), ('Notes', 'notes'), ('Delete', 'delete')]:
            row.addWidget(button(label, lambda checked=False, op=operation: self.manage_model(op)))
        layout.addLayout(row)
        self.model_details = QPlainTextEdit()
        self.model_details.setReadOnly(True)
        self.model_details.setMaximumHeight(180)
        self.model_table.currentCellChanged.connect(self.show_model_details)
        layout.addWidget(self.model_details)

    def save_model(self) -> None:
        try:
            root = self.require_project()
            path = self.run_select.currentData()
            if not path:
                raise ValueError("Select a training run in Replay first")
            run = read_json(Path(path) / "run.json")
            if not run.get("episodes_completed"):
                raise ValueError("Run has no completed episodes")
            name, ok = QInputDialog.getText(self, "Save model", "Model name", text="obstacle_agent_v1")
            if not ok:
                return
            model = ModelRegistry.save(root / "models", name, load_agent(Path(path)), run)
            self.project.model = str(model.relative_to(root)).replace("\\", "/")
            self.repo.save(self.project)
            self.refresh_assets()
            self.statusBar().showMessage(f"Model saved: {name}", 5000)
        except Exception as error:
            self.report(error)

    def build_deploy(self) -> None:
        layout = self.page("Deploy", "Local Python exports portable inference and Q-table. Other targets are planned adapters.")
        self.export_model = QComboBox()
        self.export_target = combo(list(TARGETS))
        form = QFormLayout()
        form.addRow("Model", self.export_model)
        form.addRow("Export target", self.export_target)
        layout.addLayout(form)
        layout.addWidget(button("Export model", self.export_model_clicked))
        layout.addWidget(QLabel("Local inference uses (x,y) only and is specific to the saved scenario. It has no physical control interface."))
        layout.addStretch()

    def export_model_clicked(self) -> None:
        try:
            if self.export_target.currentText() != "Local Python":
                raise ValueError("This export adapter is not implemented in V0.4")
            model = self.export_model.currentData()
            if not model:
                raise ValueError("Save a model first")
            root = self.require_project()
            destination = root / "exports" / Path(model).name
            export_local(Path(model), destination)
            self.statusBar().showMessage(f"Exported: {destination}", 12000)
            QMessageBox.information(self, "Export complete", str(destination))
        except Exception as error:
            self.report(error)

    def build_settings(self) -> None:
        layout = self.page("Settings", "Workspace is selected at startup with --workspace. All persisted data stays local.")
        label = QLabel(f"Workspace\n{self.workspace}\n\nSimulation: GridWorld / optional Gazebo Harmonic\nAlgorithms: Q-Learning / optional DQN\n"
                       "UI: PySide6\n\nGazebo runtime requires Ubuntu validation. No real drone/PX4/offboard or map service is connected.")
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()

    def closeEvent(self, event) -> None:
        if self.sim_worker and self.sim_worker.isRunning():
            if self.sim_cancel:self.sim_cancel.set()
            self.sim_worker.finished.connect(self.close)
            event.ignore()
            return
        if self.diagnostics_worker and self.diagnostics_worker.isRunning():
            self._closing=True
            self.diagnostics_worker.finished.connect(self.close)
            event.ignore()
            return
        if self.gazebo_environment and not self.gazebo_environment.closed:
            self.async_sim(self.gazebo_environment.close,lambda *_:self.close())
            self.sim_worker.finished.connect(self.close)
            event.ignore()
            return
        if self.eval_worker and self.eval_worker.isRunning():
            self._closing = True
            self.eval_worker.cancel.set()
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self._closing = True
            self.worker.cancel.set()
            self.statusBar().showMessage("Saving partial run before closing…")
            event.ignore()
            return
        self.timer.stop()
        event.accept()
