"""Parse bounded proposed mixed diagnostics; never authorizes any runtime action.
V10DIAG retains the old summary. V10IO records exact operation returns and
immediate errno before the emitter/close can change it. Input is supplied bytes.
"""
import re
CAP=16384
def parse(data):
    if not isinstance(data,bytes) or len(data)>CAP or (data and not data.endswith(b'\n')):
        raise ValueError('diagnostic size/type/incomplete frame')
    rows=[];sequence={}
    for line in data.splitlines():
        if len(line)>=192:raise ValueError('diagnostic frame cap')
        diag=re.fullmatch(rb'V10DIAG (\d+) (\d+) ([a-z-]+) (-?\d+) (\d+)',line)
        io=re.fullmatch(rb'V10IO (\d+) (\d+) ((?:uid-map|setgroups|gid-map)-(?:open|write|close)) (-?\d+) (\d+) (\d+)',line)
        if not diag and not io:raise ValueError('diagnostic framing')
        match=io or diag;pid,n,stage,result=match.groups()[:4]
        pid,n,result=int(pid),int(n),int(result)
        if not 0<n<=32 or pid<=0 or n!=sequence.get(pid,n-1)+1:
            raise ValueError('diagnostic PID/sequence/cap')
        sequence[pid]=n
        row=dict(pid=pid,seq=n,stage=stage.decode(),result=result,
                 errno=int(match.groups()[-1]),kind='IO' if io else 'SUMMARY')
        if io:row['requested']=int(io.groups()[-2])
        rows.append(row)
    return rows
