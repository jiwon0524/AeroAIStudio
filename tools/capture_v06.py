import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from aero_ai_studio.ui.window import MainWindow


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    w=MainWindow(a.workspace)
    if not w.project:raise ValueError('Choose an existing populated test workspace')
    w.resize(1600,1040)
    w.show()
    w.nav.setCurrentRow(5)
    w.seek(min(2,w.replay.count-1))
    for index,name in [(5,'replay'),(4,'brain'),(15,'trajectory'),(14,'observation'),(2,'training'),(11,'evaluation'),(13,'diagnostics')]:
        w.nav.setCurrentRow(index)
        app.processEvents()
        w.grab().save(str(a.output/(name+'.png')))
    w.close()
    print('7 V0.6 panels captured')


if __name__=='__main__':main()
