import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox
from aero_ai_studio.ui.window import MainWindow
from aero_ai_studio.training.trainer import Trainer, TrainingConfig
from aero_ai_studio.core.storage import read_json


def wait_worker(app, worker):
    limit = time.monotonic() + 120
    while worker.isRunning() and time.monotonic() < limit:
        app.processEvents()
        time.sleep(0.002)
    assert worker.wait(5000)
    app.processEvents()


def test_v04_desktop_evaluation_resume_editor_timeline(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    w = MainWindow(tmp_path)
    errors = []
    w.report = errors.append
    w.show()
    w.project_name.setText('V0.4 UI integration')
    w.create_project()
    w.grid_size.setValue(10)
    w.object_text.clear()
    w.load_scenario_fields(w.scenario_from_fields())
    w.map_tool.setCurrentText('danger_zone')
    # Exercise native Qt mouse-to-cell mapping, not only the edit handler.
    app.processEvents()
    grid = w.scene_grid
    size = min((grid.width() - 30) / 10, (grid.height() - 30) / 10)
    ox, oy = (grid.width() - size * 10) / 2, (grid.height() - size * 10) / 2
    QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=QPoint(int(ox + 2.5 * size), int(oy + 3.5 * size)))
    assert any(o.type == 'danger_zone' and o.position == (2, 3) for o in w.scenario_from_fields().objects)
    w.map_tool.setCurrentText('moving_obstacle')
    w.edit_cell(4, 4)
    assert len(w.scenario_from_fields().dynamic_objects) == 1
    w.map_tool.setCurrentText('erase')
    w.edit_cell(4, 4)
    assert not w.scenario_from_fields().dynamic_objects
    w.map_tool.setCurrentText('goal')
    w.edit_cell(8, 8)
    assert w.scenario_from_fields().goal == (8, 8)
    w.generate_random()
    assert w.scenario_from_fields().dynamic_objects
    # Small fixed scene for the end-to-end training/evaluation portion.
    w.grid_size.setValue(4)
    w.object_text.clear()
    w.editor_dynamic = []
    w.save_scenario()
    w.training_mode.setCurrentText('Visual Training')
    trainer = Trainer(w.scenario, TrainingConfig(episodes=100, max_steps=30, visual_interval=10, checkpoint_interval=20))
    w.launch_training(trainer, w.require_project() / 'runs')
    w.request_checkpoint()
    wait_worker(app, w.worker)
    assert w.live_grid.snapshot and 'Episode' in w.live_status.text()
    first = w.run_paths[0]
    assert list((first / 'checkpoints').glob('episode_*/checkpoint.json'))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **k: ('Agent', True))
    w.save_model()
    w.model_table.selectRow(0)
    w.evaluate_registry_model()
    assert w.nav.currentRow() == 11
    w.eval_episodes.setValue(10)
    w.eval_max_steps.setValue(30)
    w.start_evaluation()
    wait_worker(app, w.eval_worker)
    result = read_json(Path(w.eval_history.currentData()) / 'evaluation.json')
    assert result['episodes_completed'] == 10 and result['epsilon'] == 0
    assert read_json(w.model_paths[0] / 'metadata.json')['evaluation']
    w.replay_evaluation()
    assert 'EVALUATION' in w.run_select.currentText()
    assert w.timeline.count() == w.replay.count
    w.timeline.setCurrentRow(min(2, w.replay.count - 1))
    assert w.replay.index == w.timeline.currentRow()
    assert w.brain_map.step['epsilon'] == 0
    w.select_replay_best('highest_reward')
    w.select_replay_best('shortest')
    # Restart UI and resume from the most recent committed checkpoint.
    w.close()
    w = MainWindow(tmp_path)
    w.report = errors.append
    w.show()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *a, **k: (a[3][0], True))
    monkeypatch.setattr(QInputDialog, 'getInt', lambda *a, **k: (120, True))
    w.resume_training()
    wait_worker(app, w.worker)
    resumed = read_json(w.run_paths[0] / 'run.json')
    assert resumed['resume_episode'] == 101 and resumed['episodes_completed'] == 120
    w.nav.setCurrentRow(12)
    w.compare_list.item(0).setSelected(True)
    w.compare_list.item(1).setSelected(True)
    w.compare_selected()
    assert w.compare_table.rowCount() == 2 and len(w.compare_chart.runs) == 2
    w.nav.setCurrentRow(8)
    w.model_table.selectRow(0)
    w.manage_model('duplicate')
    assert len(w.model_paths) == 2
    w.model_table.selectRow(0)
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **k: QMessageBox.StandardButton.No)
    w.manage_model('delete')
    assert len(w.model_paths) == 2
    assert not errors
    assert (tmp_path / 'logs' / 'app.log').exists()
    w.close()
