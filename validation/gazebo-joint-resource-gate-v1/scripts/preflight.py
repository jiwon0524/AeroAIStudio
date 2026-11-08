"""Read-only refusal CLI. Deliberately has no service/marker/GO code path."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]


def inspect():
    # Even fabricated successful resource packets cannot override these missing
    # native instrumentation boundaries. No execution switch is implemented.
    return {
        'status': 'BLOCKED',
        'exit_code': 78,
        'blockers': [
            'NATIVE_SCHEMA_CLOSURE_RESULT_ABSENT: Root cache init and recursive '
            'initXml include results are not propagated/attested',
            'NATIVE_CONFIG_RESULT_ABSENT: empty valid config is indistinguishable '
            'from failed LoadFile/parse at the existing public plugin-list API',
            'NATIVE_SELECTION_BINDING_ABSENT: actual parsed world bytes and '
            'SystemLoader final choice must be bound to the RO manifest',
            'POST_GO_LOAD_PATH_UNSEALED: Step calls ProcessPendingEntitySystems; '
            'reject late requests before SystemManager::LoadPlugin, not after loading',
        ],
        'manager_queried': False,
        'service_started': False,
        'marker_created': False,
        'go_sent': False,
        'stage_b': 'BLOCKED',
        'risk_acceptance': 'UNDECIDED',
        'actual_runtime': 'UNVERIFIED',
    }


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
    sys.exit(78)
