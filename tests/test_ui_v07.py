import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from aero_ai_studio.ui.window import MainWindow
from aero_ai_studio.core.storage import read_json
from test_ui_v04 import wait_worker


def test_v07_curriculum_quota_and_physics_export_ui(tmp_path):
    app=QApplication.instance() or QApplication([])
    w=MainWindow(tmp_path);errors=[];w.report=errors.append;w.show()
    w.project_name.setText('V07 existing workflow');w.create_project()
    w.grid_size.setValue(4);w.object_text.clear();w.save_scenario()
    w.curriculum_stage_min.setValue(1);w.curriculum_hard_min.setValue(2);w.curriculum_eval_min.setValue(1)
    w.curriculum_enabled.setChecked(True);w.curriculum_threshold.setValue(0)
    w.episodes.setValue(12);w.max_steps.setValue(4);w.start_training()
    wait_worker(app,w.worker)
    meta=read_json(w.run_paths[0]/'run.json')
    assert meta['config']['curriculum_minimum_episodes']==[1,1,1,1,2]
    assert meta['curriculum_complete'] is False and meta['hard_training_episodes']==0
    w.gazebo_control_mode.setCurrentText('PHYSICS')
    world=w.export_gazebo()
    assert read_json(world.with_name('metadata.json'))['agent_entity']=='simple_agent'
    assert 'Validation Pending' in w.windowTitle()
    assert not errors
    w.close()
