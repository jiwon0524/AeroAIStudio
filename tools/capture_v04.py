"""Capture the existing application's panels using an explicit test workspace."""
import argparse
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from aero_ai_studio.ui.window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(args.workspace)
    errors = []
    window.report = errors.append
    window.resize(1600, 1040)
    window.show()
    for page, name in [(3, 'scenario'), (2, 'training'), (11, 'evaluation'), (5, 'replay'), (4, 'brain'), (12, 'comparison'), (8, 'models')]:
        window.nav.setCurrentRow(page)
        if page == 3:
            window.grid_size.setValue(20)
            window.difficulty.setCurrentText('hard')
            window.generate_random()
        if page == 5:
            window.failure_filter.setCurrentText('collision')
            window.episode_select.setCurrentIndex(window.episode_select.count() - 1)
            window.seek(min(2, window.replay.count - 1))
        if page == 12:
            for i in range(min(2, window.compare_list.count())):
                window.compare_list.item(i).setSelected(True)
            window.compare_selected()
        app.processEvents()
        window.grab().save(str(args.output / f'{name}.png'))
    window.close()
    if errors:
        raise RuntimeError(errors)
    print('7 existing UI panels captured')


if __name__ == '__main__':
    main()
