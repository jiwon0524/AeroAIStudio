from __future__ import annotations
from pathlib import Path
import json
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QPlainTextEdit, QLabel, QHBoxLayout, QComboBox, QCheckBox, QGroupBox, QVBoxLayout, QWidget
from aero_ai_studio.ui.widgets import GridView
from aero_ai_studio.gazebo.diagnostics import diagnose, gazebo_status as _gazebo_status
from aero_ai_studio.gazebo.environment import GazeboEnvironment
from aero_ai_studio.gazebo.world_generator import GazeboWorldGenerator
from aero_ai_studio.ui.v06_panels import V06Panels

def gazebo_status():return _gazebo_status(probe=False)


class DiagnosticsWorker(QThread):
    result = Signal(dict)
    def run(self):
        self.result.emit(diagnose(full=True))


class V05Panels(V06Panels):
    def add_agent_controls(self, form):
        from aero_ai_studio.ui.window import combo, integer, decimal
        self.algorithm = combo(['Q-Learning','DQN'])
        import importlib.util
        if importlib.util.find_spec('torch') is None:
            self.algorithm.model().item(1).setEnabled(False)
            self.algorithm.setToolTip('DQN is optional. Install with Setup.ps1 -IncludeDqn or pip install -e ".[dqn]"')
        self.train_observation = combo(['basic','local','sensor'])
        self.local_window = combo(['3x3','5x5','7x7'])
        self.local_window.setCurrentIndex(1)
        self.simulator = combo(['GridWorld','Gazebo'])
        if not gazebo_status()['available']:
            self.simulator.model().item(1).setEnabled(False)
        form.addRow('Simulator',self.simulator)
        form.addRow('Algorithm',self.algorithm)
        form.addRow('AI Observation',self.train_observation)
        form.addRow('Local window',self.local_window)
        self.algorithm.currentTextChanged.connect(self.algorithm_changed)
        self.batch_size=integer(64,1,4096)
        self.buffer_size=integer(10000,1,1000000)
        self.target_interval=integer(500,1,1000000)
        self.epsilon_end=decimal(0)
        group=QGroupBox('DQN / advanced settings')
        group.setCheckable(True)
        inner=QWidget()
        from PySide6.QtWidgets import QFormLayout
        advanced=QFormLayout(inner)
        for title,widget in [('Batch size',self.batch_size),('Replay buffer size',self.buffer_size),
                             ('Target update steps',self.target_interval),('Epsilon end',self.epsilon_end)]:
            advanced.addRow(title,widget)
        layout=QVBoxLayout(group)
        layout.addWidget(inner)
        group.toggled.connect(inner.setVisible)
        group.setChecked(False)
        form.addRow(group)
        self.add_v06_controls(form)

    def algorithm_changed(self, name):
        if name=='DQN':
            self.train_observation.setCurrentText('sensor')
            self.lr.setValue(.001)
            self.epsilon_end.setValue(.05)
        else:
            self.lr.setValue(.1)
            self.epsilon_end.setValue(0)

    def build_observation_debug(self):
        layout=self.page('Observation Debug','Privileged environment on the left · recorded policy input on the right · shared Replay step')
        from aero_ai_studio.ui.window import button
        layout.addWidget(button('Select episode in Replay',lambda:self.nav.setCurrentRow(5)))
        row=QHBoxLayout()
        self.observation_grid=GridView()
        self.observation_text=QPlainTextEdit()
        self.observation_text.setReadOnly(True)
        self.observation_text.setStyleSheet('font-family: Consolas;')
        row.addWidget(self.observation_grid,1)
        row.addWidget(self.observation_text,1)
        layout.addLayout(row,1)

    def set_observation_step(self, step):
        if not step:
            text='No recorded policy observation. Legacy replay does not reconstruct policy inputs.'
            self.observation_grid.set_state({})
            if hasattr(self,'trajectory_view'):self.trajectory_view.set_episode({})
            self.brain_v4.setText('No selected step')
        else:
            obs=step.get('observation')
            text=(f"WHAT AI SAW · Episode {step.get('episode','legacy')} · Step {step['time']+1}\n"
                  f"Algorithm: {step.get('algorithm','Q-Learning')}\n"
                  f"Encoded policy input: {step.get('agent_decision',{}).get('encoded_state',step.get('agent_decision',{}).get('input_vector','not recorded'))}\n\n"+
                  json.dumps(obs,ensure_ascii=False,indent=2)) if obs else 'Observation not recorded (legacy). Full environment is DEBUG data.'
            snapshot={**step,'agent':step['state']}
            actual=step.get('telemetry',{}).get('actual_world',{})
            if actual.get('agent_pose'):
                snapshot['agent']=[actual['agent_pose']['x']-.5,actual['agent_pose']['y']-.5]
                if actual.get('goal_pose'):
                    snapshot['goal']=[float(actual['goal_pose'].get('x',0))-.5,float(actual['goal_pose'].get('y',0))-.5]
                snapshot['obstacles']=[[float(p.get('x',0))-.5,float(p.get('y',0))-.5] for p in actual.get('obstacles',{}).values()]
            self.observation_grid.set_state(snapshot)
        self.observation_text.setPlainText(text)
        self.replay_observation.setPlainText(text)

    def build_diagnostics(self):
        from aero_ai_studio.ui.window import button
        layout=self.page('Environment Diagnostics','Gazebo: Ubuntu 24.04 / Harmonic target · ROS2 Jazzy optional · GridWorld works without Gazebo')
        self.diagnostics_text=QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setPlainText(json.dumps(diagnose(),ensure_ascii=False,indent=2))
        layout.addWidget(self.diagnostics_text)
        row=QHBoxLayout()
        self.diagnostics_button=button('Refresh diagnostics',self.refresh_diagnostics)
        row.addWidget(self.diagnostics_button)
        row.addWidget(button('Export scenario to Gazebo',self.export_gazebo))
        row.addWidget(button('Launch Gazebo',self.launch_gazebo))
        row.addWidget(button('Stop Gazebo',self.stop_gazebo))
        row.addWidget(button('Run 3D Closed Loop',self.run_closed_loop))
        row.addWidget(button('Reset Simulation',lambda:self.recover_gazebo(False)))
        row.addWidget(button('Restart World',lambda:self.recover_gazebo(True)))
        layout.addLayout(row)
        self.gazebo_label=QLabel(gazebo_status()['detail'])
        self.gazebo_label.setWordWrap(True)
        layout.addWidget(self.gazebo_label)
        self.diagnostics_worker=None
        self.gazebo_environment=None
        self.sim_worker=None
        self.sim_cancel=None
        self.gazebo_timer=QTimer(self)
        self.gazebo_timer.setInterval(1000)
        self.gazebo_timer.timeout.connect(self.poll_gazebo)

    def refresh_diagnostics(self):
        if self.diagnostics_worker and self.diagnostics_worker.isRunning():return
        self.diagnostics_button.setEnabled(False)
        self.diagnostics_worker=DiagnosticsWorker()
        self.diagnostics_worker.result.connect(lambda value:self.diagnostics_text.setPlainText(json.dumps(value,ensure_ascii=False,indent=2)))
        self.diagnostics_worker.finished.connect(lambda:self.diagnostics_button.setEnabled(True))
        self.diagnostics_worker.start()

    def export_gazebo(self):
        try:
            root=self.require_project()
            scenario=self.scenario_from_fields()
            path=GazeboWorldGenerator().generate(scenario,root/'generated_worlds',closed_loop=True,control_mode=self.gazebo_control_mode.currentText())
            self.statusBar().showMessage(f'Generated SDF: {path}',12000)
            self.gazebo_label.setText(f'SDF generated: {path}\nFour-ray GPU LiDAR and kinematic entity control. Actual Gazebo execution must be verified on Ubuntu.')
            return path
        except Exception as error:
            self.report(error)

    def launch_gazebo(self):
        status=gazebo_status()
        if not status['available']:
            self.gazebo_label.setText(status['detail'])
            self.statusBar().showMessage('Gazebo unavailable. GridWorld remains available.',8000)
            return status
        try:
            root=self.require_project()
            if self.gazebo_environment and self.gazebo_environment.process and self.gazebo_environment.process.poll() is None:
                self.gazebo_label.setText('Gazebo already running; stop it first')
                return
            self.gazebo_environment=GazeboEnvironment(self.scenario_from_fields(),root=root/'generated_worlds',control_mode=self.gazebo_control_mode.currentText())
            gui=self.gazebo_mode.currentText()=='GUI'
            self.async_sim(lambda:self.gazebo_environment.launch(gui=gui),self.launch_complete)
        except Exception as error:
            self.report(error)

    def stop_gazebo(self):
        self.gazebo_timer.stop()
        if self.sim_cancel:self.sim_cancel.set()
        if self.gazebo_environment:
            if self.sim_worker and self.sim_worker.isRunning():
                self.gazebo_label.setText('Stop requested; waiting for bounded operation/episode to finish')
                environment=self.gazebo_environment
                self.sim_worker.finished.connect(lambda:self.async_sim(environment.close,lambda *_:self.gazebo_label.setText('Gazebo stopped')))
            else:self.async_sim(self.gazebo_environment.close,lambda *_:self.gazebo_label.setText('Gazebo stopped'))

    def launch_complete(self,status):
        self.gazebo_label.setText(json.dumps(status,indent=2)+'\nProcess status is not proof of a rendered frame.')
        self.gazebo_timer.start()

    def recover_gazebo(self,restart=False):
        if not self.gazebo_environment:
            self.gazebo_label.setText('No active world; launch first')
            return
        operation=self.gazebo_environment.restart if restart else self.gazebo_environment.reset
        self.async_sim(operation,lambda result:self.gazebo_label.setText('Recovery returned actual observation: '+str(result)))

    def poll_gazebo(self):
        if self.gazebo_environment:
            # Polling process metadata only; never sensor/service work in the Qt thread.
            state={**self.gazebo_environment.manager.status(),'simulation_state':self.gazebo_environment.lifecycle,
                   'error':self.gazebo_environment.last_error}
            self.gazebo_label.setText(json.dumps(state,indent=2)+'\nProcess status is not proof of a rendered frame.')
            if state['status']!='Running':self.gazebo_timer.stop()
