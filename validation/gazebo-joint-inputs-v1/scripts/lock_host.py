from pathlib import Path
import hashlib,json,subprocess
r=Path(__file__).resolve().parents[1]
roots=['/usr/libexec/gcc/x86_64-linux-gnu/13','/usr/include','/usr/lib/python3.12','/usr/lib/gcc/x86_64-linux-gnu/13','/usr/include/c++/13','/usr/include/x86_64-linux-gnu/c++/13','/usr/include/x86_64-linux-gnu','/usr/share/cmake-3.28/Modules','/usr/share/cmake/gz-cmake3']
paths=set()
for root in roots:
 p=Path(root)
 if p.exists():paths.update(q for q in p.rglob('*') if q.is_file())
for name in ['/usr/lib/x86_64-linux-gnu/libc.so','/usr/lib/x86_64-linux-gnu/libc_nonshared.a','/usr/lib/x86_64-linux-gnu/libm.so','/usr/lib/x86_64-linux-gnu/libpthread.a','/usr/lib/x86_64-linux-gnu/libdl.a','/usr/lib/x86_64-linux-gnu/librt.a','/usr/bin/protoc','/usr/bin/python3','/usr/bin/gcc-13','/usr/bin/g++-13','/usr/bin/ld.bfd','/usr/bin/as','/usr/bin/cmake','/usr/bin/ninja','/usr/bin/pkg-config','/usr/lib/x86_64-linux-gnu/libstdc++.so.6','/usr/lib/x86_64-linux-gnu/libgcc_s.so.1','/usr/lib/x86_64-linux-gnu/libc.so.6','/lib64/ld-linux-x86-64.so.2','/usr/lib/x86_64-linux-gnu/crt1.o','/usr/lib/x86_64-linux-gnu/crti.o','/usr/lib/x86_64-linux-gnu/crtn.o','/usr/lib/x86_64-linux-gnu/libcrypto.so.3']:
 paths.add(Path(name))
rows=[]
for p in sorted(paths):
 rows.append({'path':str(p),'realpath':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
data=json.dumps(rows,sort_keys=True,indent=2)+'\n'; (r/'reports/toolchain_files.json').write_text(data)
installed=subprocess.check_output(['dpkg-query','-W','-f=${Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n'],text=True)
(r/'work/installed_packages.tsv').write_text(installed)
seeds=['gcc-13','g++-13','gcc-13-x86-64-linux-gnu','g++-13-x86-64-linux-gnu','cpp-13-x86-64-linux-gnu','binutils','binutils-x86-64-linux-gnu','cmake','cmake-data','ninja-build','pkgconf','libc6','libc6-dev','libstdc++6','libstdc++-13-dev','libgcc-13-dev','linux-libc-dev','libssl-dev']
versions=[line for line in installed.splitlines() if line.split('\t')[0] in seeds]
summary={'files':len(rows),'manifest_sha256':hashlib.sha256(data.encode()).hexdigest(),'versions':versions,'coverage':roots,'limitation':'header/tool inventory; include tracing not performed; tool ELF closure is in tool_elf_closure.json; project dependency closure not certified'}
(r/'reports/toolchain_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(summary)
