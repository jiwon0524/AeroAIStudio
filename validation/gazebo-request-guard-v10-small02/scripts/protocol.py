"""Reuse exact existing harmless GO/100-sample/EXIT_ACK classes by source AST.
Imports only class definitions, not historical launcher/stage entrypoints.
"""
from common import *
import ast
OLD=R.parent/'gazebo-joint-execution-contract-v1'
def definitions(path,names):
    tree=ast.parse(path.read_text());nodes=[x for x in tree.body if isinstance(x,ast.ClassDef) and x.name in names]
    need({x.name for x in nodes}==set(names),'missing reused protocol definitions')
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),globals())
definitions(R.parent/'gazebo-joint-isolation-v1/scripts/protocol.py',{'Lines'})
definitions(OLD/'scripts/protocol.py',{'AckWindow','HarmlessSession'})
BaseSession=HarmlessSession
class Session(BaseSession):
    def __init__(self,window,initial):
        super().__init__(window,initial);self.child=self.cleanup=False;self.can_go=lambda:True
    def packet(self,row):
        if row.get('kind')=='fixture_child':
            need(self.window.go and not self.window.waiting and not self.child and row=={'kind':'fixture_child','status':0},'child completion protocol')
            self.child=True
        elif row.get('kind')=='fixture_cleanup':
            need(self.window.ack and not self.cleanup and row=={'kind':'fixture_cleanup','joined':True},'late callback protocol')
            self.cleanup=True
        else:super().packet(row)
    def stderr(self,line):
        need(not line,'unexpected probe diagnostic')
    def finalize(self,*args):
        need(self.child and self.cleanup,'child/callback completion missing')
        result=super().finalize(*args)
        return dict(result,status='PASS_SMALL_HARMLESS_PATH_ONLY',large_objects_prepared=False,maximum_memory_proven=False)
