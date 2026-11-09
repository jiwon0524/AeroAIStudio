"""Fresh-source reproduction entrypoint; refuses to overwrite any source copy.

Requires work/sdformat-sdformat14_14.9.0 extracted from the archive pinned in
source_receipt.json, and the preserved predecessor Sim source at its old path.
Run only in a fresh phase directory. Apply the reviewed final native.patch.
"""
from pathlib import Path
import hashlib,json,shutil,subprocess
R=Path(__file__).resolve().parents[1];B=R.parents[1]
receipt=json.loads((R/'reports/source_receipt.json').read_text())
assert hashlib.sha256((R/'work/sdformat.tar.gz').read_bytes()).hexdigest()==receipt['archive']['sha256']
assert hashlib.sha256((R/'inputs/native.patch').read_bytes()).hexdigest()==receipt['patch_sha256']
src=R/'work/src';assert not src.exists(),'preserve existing source copies'
shutil.copytree(B/'validation/gazebo-joint-codegen-fix-v1/inputs/pinned-include',R/'inputs/pinned-include',symlinks=True,dirs_exist_ok=True)
shutil.copytree(B/'validation/gazebo-joint-codegen-fix-v1/work/config-01/src/sim',src/'sim',symlinks=True)
shutil.copytree(R/'work/sdformat-sdformat14_14.9.0',src/'sdformat',symlinks=True)
for row in receipt['files']:assert hashlib.sha256((src/row['path']).read_bytes()).hexdigest()==row['before']
subprocess.run(['/usr/bin/patch','--batch','-p0','-d',str(src),'-i',str(R/'inputs/native.patch')],check=True)
for row in receipt['files']:assert hashlib.sha256((src/row['path']).read_bytes()).hexdigest()==row['after']
print('PASS isolated patched source copies; no subject executed')
