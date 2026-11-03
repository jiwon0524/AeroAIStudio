from __future__ import annotations
from functools import partial
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QCheckBox,QComboBox,QHBoxLayout,QLabel
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.diagnostics import gazebo_status
from aero_ai_studio.evaluation.evaluator import Evaluator,EvaluationConfig
from aero_ai_studio.ui.widgets import TrajectoryView


class SimulationWorker(QThread):
    result=Signal(object)
    error=Signal(str)
    def __init__(self,operation):
        super().__init__()
        self.operation=operation
    def run(self):
        try:self.result.emit(self.operation())
        except Exception as error:self.error.emit(str(error))


class V06Panels:
    def add_v06_controls(self,form):
        from aero_ai_studio.ui.window import integer,decimal,combo
        self.safety_enabled=QCheckBox('Enable Safety Layer (audited overrides)')
        self.safety_threshold=decimal(1.05,0,10)
        self.reward_version=combo(['legacy','v2'])
        self.double_dqn=QCheckBox('Double DQN')
        self.warmup_steps=integer(0,0,1000000)
        self.curriculum_enabled=QCheckBox('Curriculum Training')
        self.curriculum_threshold=decimal(.8,0,1)
        self.gazebo_mode=combo(['Headless','GUI'])
        self.train_encoder=combo(['auto','basic','compact','canonical'])
        self.gazebo_control_mode=combo(['KINEMATIC','PHYSICS'])
        self.curriculum_stage_min=integer(100,1,100000)
        self.curriculum_hard_min=integer(400,1,100000)
        self.curriculum_eval_min=integer(2,1,100)
        for title,widget in [('Gazebo mode',self.gazebo_mode),('Safety',self.safety_enabled),('Critical clearance (m)',self.safety_threshold),
                             ('Reward',self.reward_version),('DQN V2',self.double_dqn),('Replay warm-up',self.warmup_steps),
                             ('Curriculum',self.curriculum_enabled),('Promotion threshold',self.curriculum_threshold),('Q encoder',self.train_encoder),
                             ('Gazebo control',self.gazebo_control_mode),('Stage 0–3 minimum each',self.curriculum_stage_min),
                             ('Hard stage minimum',self.curriculum_hard_min),('Evaluations before promotion',self.curriculum_eval_min)]:form.addRow(title,widget)
        self.curriculum_enabled.toggled.connect(lambda on:self.episodes.setValue(max(self.episodes.value(),self.curriculum_stage_min.value()*4+self.curriculum_hard_min.value())) if on else None)

    def backend_factory(self,root,simulator=None):
        from aero_ai_studio.simulation.grid_world import GridWorld
        name=simulator or self.simulator.currentText()
        factories={'GridWorld':GridWorld,'Gazebo':partial(GazeboEnvironment,root=root/'generated_worlds',gui=self.gazebo_mode.currentText()=='GUI',
                                                        control_mode=self.gazebo_control_mode.currentText())}
        return factories[name]

    def add_trajectory(self):
        self.trajectory_view=TrajectoryView()
        layout=self.page('Trajectory','Top-down recorded path · GridWorld / Gazebo projection · red = collision endpoint')
        layout.addWidget(self.trajectory_view)

    def async_sim(self,operation,callback):
        if self.sim_worker and self.sim_worker.isRunning():
            self.statusBar().showMessage('Simulation operation is still running',5000)
            return
        self.sim_worker=SimulationWorker(operation)
        self.sim_worker.result.connect(callback)
        self.sim_worker.error.connect(self.report)
        self.sim_worker.start()

    def run_closed_loop(self):
        if not gazebo_status(probe=False)['available']:
            self.gazebo_label.setText('Gazebo unavailable — actual closed loop NOT VERIFIED')
            return
        try:
            from pathlib import Path
            root=self.require_project()
            model=self.eval_model.currentData()
            if not model:raise ValueError('Save/select a BASIC or SENSOR model for the closed loop')
            spec=self.scenario_from_fields()
            cfg=EvaluationConfig(1,100,10042,safety_enabled=self.safety_enabled.isChecked(),reward_version=self.reward_version.currentText(),suite='gazebo_static')
            evaluator=Evaluator(spec,cfg,self.backend_factory(root,'Gazebo'))
            self.sim_cancel=__import__('threading').Event()
            self.async_sim(lambda:evaluator.run(Path(model),root/'evaluations',cancel=self.sim_cancel),self.closed_loop_complete)
        except Exception as error:self.report(error)

    def closed_loop_complete(self,result):
        path,summary=result
        self.gazebo_label.setText(f"Gazebo loop: {summary['status']} / {summary['success_rate']:.1%} / {path}")
        self.refresh_assets()
