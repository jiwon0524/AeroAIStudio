import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog
from aero_ai_studio.ui.window import MainWindow
from aero_ai_studio.core.storage import read_json
from test_ui_v04 import wait_worker


def test_dqn_ui_observation_sync_and_diagnostics(tmp_path,monkeypatch):
    pytest.importorskip('torch')
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path)
    errors=[]
    w.report=errors.append
    w.show()
    w.project_name.setText('V05 integration')
    w.create_project()
    w.grid_size.setValue(4)
    w.object_text.clear()
    w.save_scenario()
    w.algorithm.setCurrentText('DQN')
    assert w.train_observation.currentText()=='sensor'
    w.episodes.setValue(8)
    w.max_steps.setValue(20)
    w.batch_size.setValue(2)
    w.buffer_size.setValue(50)
    w.start_training()
    wait_worker(app,w.worker)
    assert (w.run_paths[0]/'model.pt').exists()
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('DQN UI',True))
    w.save_model()
    assert read_json(w.model_paths[0]/'metadata.json')['algorithm']=='dqn'
    w.nav.setCurrentRow(5)
    w.seek(min(1,w.replay.count-1))
    step=w.replay.seek(w.replay.index)
    assert json.loads(w.observation_text.toPlainText().split('\n\n',1)[1])==step['observation']
    assert w.observation_grid.snapshot['agent']==step['state']
    assert w.replay_observation.toPlainText()==w.observation_text.toPlainText()
    w.timeline.setCurrentRow(0)
    assert w.replay.index==0 and w.brain_map.step['algorithm']=='DQN'
    w.nav.setCurrentRow(14)
    assert 'WHAT AI SAW' in w.observation_text.toPlainText()
    w.eval_episodes.setValue(2)
    w.eval_max_steps.setValue(20)
    w.start_evaluation()
    wait_worker(app,w.eval_worker)
    assert w.eval_history.count()==1
    world=w.export_gazebo()
    assert world.exists()
    monkeypatch.setattr('aero_ai_studio.ui.v05_panels.gazebo_status',lambda:{'available':False,'status':'Unavailable','detail':'Gazebo not detected'})
    assert w.launch_gazebo()['status']=='Unavailable'
    assert not errors
    w.close()
