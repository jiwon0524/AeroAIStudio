"""Pure readback classification, NOT permission to start/stop/attach/resume.
A missing live identity always authorizes zero actions, even during teardown.
classify makes no manager call; inspect_bound reads once and never mutates units.
"""
def classify(row,name,description,receipt=None):
    if row.get('LoadState')=='not-found':
        return 'ABSENT_AFTER_RECEIPT' if receipt else 'ABSENT'
    if row.get('Id')!=name or row.get('Description')!=description:
        return 'FOREIGN_OR_UNBOUND'
    invocation=row.get('InvocationID','')
    group=row.get('ControlGroup','')
    if receipt and invocation and invocation!=receipt['InvocationID']:
        return 'INVOCATION_CHANGED'
    if not invocation or not group.startswith('/') or group=='/':
        return 'INCOMPLETE_AFTER_RECEIPT' if receipt else 'INCOMPLETE_BEFORE_RECEIPT'
    if receipt and group!=receipt['ControlGroup']:
        return 'CGROUP_CHANGED'
    if row.get('MemoryMax')!='5368709120':
        return 'WRONG_CAP'
    return 'OWNED_SNAPSHOT'

def inspect_bound(manager,name,description,persist,receipt=None):
    """Prepare a single-read observer for a future reviewed driver.
    The exact row logged is the row validated. No retries, teardown exceptions,
    or start/stop actions; a future action still needs its own fresh binding.
    """
    row=dict(manager.inspect(name))
    classification=classify(row,name,description,receipt)
    if persist(dict(stage='owner-inspect',state=dict(row),classification=classification)) is not True:
        raise ValueError('ownership snapshot persistence failed')
    if classification!='OWNED_SNAPSHOT':
        raise ValueError('unit ownership not proven: '+classification)
    return row

class Failures:
    """First observed failure per source, not a fictitious global time order."""
    def __init__(self):
        self.first={};self.secondary=[];self.cleanup=[]
    def record(self,source,stage,reason,cleanup=False):
        event=dict(source=source,stage=stage,reason=reason)
        if cleanup:self.cleanup.append(event)
        elif source not in self.first:self.first[source]=event
        else:self.secondary.append(event)
    def snapshot(self):
        return dict(first={k:dict(v) for k,v in self.first.items()},
                    secondary=[dict(x) for x in self.secondary],
                    cleanup=[dict(x) for x in self.cleanup])
