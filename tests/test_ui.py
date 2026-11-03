"""Offscreen Qt integration: project → scenario → worker → failed replay → model → export."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import time
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from aero_ai_studio.ui.window import MainWindow


def test_desktop_workflow(tmp_path: Path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    errors = []
    window.report = errors.append
    window.show()
    window.project_name.setText("UI workflow")
    window.create_project()
    assert window.project is not None
    window.save_scenario()
    assert window.scenario is not None
    window.episodes.setValue(1000)
    window.start_training()
    deadline = time.monotonic() + 120
    while window.worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    window.worker.wait(5000)
    app.processEvents()
    assert not errors
    assert len(window.project.training_runs) == 1
    assert len(window.chart.rows) == 1000
    window.nav.setCurrentRow(5)
    window.failure_filter.setCurrentText("collision")
    assert window.episode_select.count() > 0
    assert window.replay.count > 0
    window.seek(min(1, window.replay.count - 1))
    selected = window.replay.index
    evidence = window.brain_text.toPlainText()
    assert "Q-values" in evidence
    window.nav.setCurrentRow(4)
    assert window.replay.index == selected
    assert window.brain_text.toPlainText() == evidence
    window.play()
    assert window.timer.isActive()
    window.timer.stop()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("UI model", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window.save_model()
    assert len(window.model_paths) == 1
    window.export_model_clicked()
    root = window.repo.path(window.project)
    assert list((root / "exports").glob("*/policy.py"))
    assert not errors
    window.close()
    reopened = MainWindow(tmp_path)
    assert reopened.project.name == "UI workflow"
    assert reopened.scenario is not None
    assert len(reopened.run_paths) == len(reopened.model_paths) == 1
    reopened.close()
