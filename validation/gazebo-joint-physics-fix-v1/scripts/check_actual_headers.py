from pathlib import Path
import subprocess,json,hashlib
p=Path(__file__).resolve().parents[1];build=p/'work/config-01/build/physics';text=subprocess.check_output(['/usr/bin/ninja','-C',str(build),'-t','deps'],text=True);(p/'logs/physics.actual_deps.txt').write_text(text)
records=[s for s in text.splitlines() if s and not s.startswith(' ')];headers={str((Path(s.strip()) if Path(s.strip()).is_absolute() else build/s.strip()).resolve()) for s in text.splitlines() if s.startswith('    ')}
assert not [s for s in headers if s.startswith('/usr/local/')]
config=p/'work/config-01/prefix/include/dart/config.hpp';expected=json.loads((p/'reports/dart_reuse.json').read_text())['generated_header'];assert str(config) in headers and hashlib.sha256(config.read_bytes()).hexdigest()==expected['sha256']
(p/'reports/actual_header_selection.json').write_text(json.dumps({'status':'PASS','object_records':len(records),'unique_headers':len(headers),'local_headers':[],'DART_config_path':str(config),'DART_config_sha256':expected['sha256'],'same_build_source':expected['source'],'metadata_sha256':hashlib.sha256(text.encode()).hexdigest()},indent=2)+'\n');print('PASS actual DART config/header selection',len(records),'objects',len(headers),'unique dependencies')
