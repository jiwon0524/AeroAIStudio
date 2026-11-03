import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import threading
from PySide6.QtWidgets import QApplication,QInputDialog
from aero_ai_studio.ui.window import MainWindow
from aero_ai_studio.core.storage import read_json
from test_ui_v04 import wait_worker


def test_v06_safety_brain_trajectory_async_ui(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path)
    errors=[]
    w.report=errors.append
    w.show()
    w.project_name.setText('V06 integration')
    w.create_project()
    w.grid_size.setValue(4)
    w.object_text.clear()
    w.save_scenario()
    w.train_observation.setCurrentText('sensor')
    w.safety_enabled.setChecked(True)
    w.reward_version.setCurrentText('v2')
    w.episodes.setValue(12)
    w.max_steps.setValue(20)
    w.start_training()
    wait_worker(app,w.worker)
    meta=read_json(w.run_paths[0]/'run.json')
    assert meta['config']['safety_enabled'] and meta['config']['reward_version']=='v2'
    w.nav.setCurrentRow(5)
    assert 'Proposed:' in w.brain_text.toPlainText() and 'Reward Breakdown' in w.brain_text.toPlainText()
    assert w.trajectory_view.path
    w.nav.setCurrentRow(15)
    app.processEvents()
    monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('V06 model',True))
    w.save_model()
    w.eval_episodes.setValue(2)
    w.eval_max_steps.setValue(20)
    w.eval_safety.setChecked(True)
    w.eval_suite.setCurrentText('dynamic_easy')
    w.start_evaluation()
    wait_worker(app,w.eval_worker)
    assert w.eval_history.count()==1
    identifiers=[]
    w.async_sim(lambda:threading.get_ident(),identifiers.append)
    wait_worker(app,w.sim_worker)
    assert identifiers[0]!=threading.get_ident()
    assert not errors
    w.close()
