import argparse
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import time
from PySide6.QtWidgets import QApplication
from aero_ai_studio.ui.window import MainWindow


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    w=MainWindow(args.workspace)
    w.resize(1600,1040)
    errors=[]
    w.report=errors.append
    w.show()
    w.nav.setCurrentRow(5)
    w.seek(min(1,w.replay.count-1))
    for index,name in [(5,'replay'),(4,'brain'),(14,'observation'),(13,'diagnostics'),(2,'training'),(11,'evaluation')]:
        w.nav.setCurrentRow(index)
        if index==13:
            w.refresh_diagnostics()
            end=time.monotonic()+20
            while w.diagnostics_worker.isRunning() and time.monotonic()<end:
                app.processEvents()
                time.sleep(.01)
            w.diagnostics_worker.wait(5000)
        if index==2:
            w.algorithm.setCurrentText('DQN')
        app.processEvents()
        w.grab().save(str(args.output/(name+'.png')))
    w.close()
    assert not errors,errors
    print('6 V0.5 panels captured')


if __name__=='__main__':main()
