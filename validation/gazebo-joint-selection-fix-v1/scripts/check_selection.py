from pathlib import Path
import runpy,sys
here=Path(__file__).resolve().parent
runpy.run_path(str(here/('check_selected_dart.py' if sys.argv[1]=='dart' else 'check_selection_broad.py')),run_name='__main__')
