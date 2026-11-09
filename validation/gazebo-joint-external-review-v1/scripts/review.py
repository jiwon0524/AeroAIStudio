"""Read-only source/ELF review. Never import or execute native target code."""
from pathlib import Path
import hashlib, json, subprocess, sys

R = Path(__file__).resolve().parents[1]
B = R.parents[1]
OLD = B / 'validation/gazebo-joint-execution-contract-v1'
sys.path.insert(0, str(OLD / 'scripts'))
import contract

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def site(path, *terms):
    p = B / path
    lines = p.read_text().splitlines()
    found = {t: [i for i, line in enumerate(lines, 1) if t in line] for t in terms}
    assert all(found.values()), (p, found)
    return dict(path=str(p.relative_to(B)), sha256=sha(p), lines=found)

def main():
    m = contract.read()
    contract.validate(m)
    prior = json.loads((OLD / 'reports/source_paths.json').read_text())
    # Verify every old source/object binding, not just similar upstream source.
    for row in prior['built_sources']:
        assert sha(Path(row['path'])) == row['source_sha256']
        assert sha(Path(row['object'])) == row['object_sha256']
    for row in prior['paths']:
        for e in row['evidence']:
            assert sha(Path(e['path'])) == e['sha256']
    rows = []
    def add(name, phase, classification, reachability, evidence, gap):
        rows.append(dict(name=name, phase=phase, classification=classification,
                         reachability=reachability, evidence=evidence, remaining=gap))
    sim = 'validation/gazebo-joint-execution-contract-v1/work/src/sim/src/'
    dart = 'validation/gazebo-joint-header-fix-v1/work/config-01/src/dart/dart/'
    native = 'validation/gazebo-joint-native-resource-v1/inputs/'
    add('ODE init/collision/exit', 'init/100 steps/exit', '미확인',
        'Nominal ODE constructor is selected. Collision callback invocation depends on broadphase pairs; mapping alone proves neither callback execution nor resource access.',
        [site(dart+'collision/ode/OdeCollisionDetector.cpp', 'dInitODE2(0)', 'dWorldCreate()', 'dSpaceCollide(', 'dCollide(', 'dWorldDestroy(mWorldId)', 'dCloseODE();'),
         site(dart+'collision/ode/OdeCollisionGroup.cpp', 'dSpaceDestroy(mSpaceId)')],
        'Exact libode internal implementation/TLS/callback closure missing. No installed pre-access guard. Also review libccd and allocator/error callbacks; no-open imports are insufficient.')
    add('default FCL constructor', 'init/exit', '미확인',
        'DART FCL wrapper constructor is reached before ODE replacement. Its reviewed body creates a DART collision-object manager; that does NOT prove external fcl geometry/collision constructors execute.',
        [site(dart+'constraint/ConstraintSolver.cpp', 'mCollisionDetector(collision::FCLCollisionDetector::create())'),
         site(dart+'collision/fcl/FCLCollisionDetector.cpp', 'FCLCollisionDetector::FCLCollisionDetector()', 'new ManagerForSharableCollisionObjects(this)', 'new fcl::CollisionObject')],
        'Global ELF constructors/destructors, allocator and shared dependencies remain unclosed. External FCL collision calls are conditional, not established merely by default wrapper creation.')
    add('crypto digest/provider/config', 'init/provider checks/exit', '미확인',
        'VerifyAnchor explicitly invokes EVP digest; native hashing invokes SHA256. Provider/config/dynamic-module access inside libcrypto is possible but not observed or source-bound here.',
        [site('validation/gazebo-joint-header-fix-v1/inputs/verify_anchor.cc', 'EVP_DigestInit_ex', 'EVP_sha256()', 'EVP_MD_CTX_free'),
         site(native+'native_resource.cc', 'SHA256((const unsigned char*)')],
        'Matching libcrypto initialization/provider/configuration/cleanup closure or exact pre-access guard needed. Clearing env or omitting openssl.cnf mounts does not detect silent fallback.')
    add('transport support', 'init/concurrent/100 steps/exit', '미확인',
        'Valid fixed world creates ParametersRegistry and transport Node, Advertise services and clock/stats publishers. No peer is needed to enter these APIs; socket/config behavior inside transport/ZeroMQ remains unknown.',
        [site(sim+'SimulationRunner.cc', 'ParametersRegistry>', 'std::make_unique<transport::Node>(opts)', 'this->clockPub =', 'this->statsPub ='),
         site(sim+'ServerPrivate.cc', 'this->node.Advertise(worldsService')],
        'Before-access socket/connect/bind/discovery/config/thread shutdown interception absent. Network namespace limits reach, not attempted access or verdict latching.')
    add('record/playback logging plugin', 'init', '도달 불가',
        'For fixed harness only: default ServerConfig has record=false and playback empty; harness changes neither. LoadLoggingPlugins builds empty list.',
        [site(sim+'ServerConfig.cc', 'useLogRecord{false}', 'logPlaybackPath = ""'),
         site(sim+'SimulationRunner.cc', 'if (!_config.LogPlaybackPath().empty())', 'else if (_config.UseLogRecord())'),
         site('validation/gazebo-joint-execution-contract-v1/inputs/harness_native.cc', 'gz::sim::ServerConfig config;')],
        'Bounded exclusion only. gz-common console/log streams and transport support remain separate unresolved paths; logging plugin disabled does not disable all logging.')
    add('console/support logging', 'init/concurrent/exit', '미확인',
        'Diagnostic stream operations exist; ServerControl stop-thread message is conditional on request, not established as called.',
        [site(sim+'ServerPrivate.cc', 'gzlog << "Stopping Gazebo"', 'if (_req.stop())')],
        'Exact gz-common console stream initialization/file sink and destructor behavior unavailable in bound build sources. Fixed stdout/stderr alone is not a whole logging proof.')
    add('sealed Sim plugin request', 'before ready/after GO/exit if called', '접근 전에 차단',
        'Reviewed Sim entrypoints call CheckLoadRequest before lookup/open/LoadLib. Failure latch and fatal packet remain active after seal; this does not guard foreign DSO direct calls.',
        [site(sim+'SystemLoader.cc', 'aero_resource::CheckLoadRequest();', 'FindSharedLibrary(filename)', 'aero_resource::BeforeLoad'),
         site(native+'native_resource.cc', 'if(failed||sealed) Fail', 'failed=true;', 'sealed=true;')],
        'Only reviewed Sim entrypoints. Exceptions across destructors/DSOs remain runtime and risk questions; external uninstrumented attempts emit no guaranteed packet.')
    add('required schema/config/plugin reads', 'init', '고정된 입력·출력만 허용',
        'Native required identity/hash/parse outcomes and sealed read list are reused; missing input/fallback causes failure before complete/ready/GO.',
        [site(native+'native_resource.cc', 'O_RDONLY|O_CLOEXEC|O_NOFOLLOW', 'required FD bytes mismatch', 'unapproved schema/conversion name', 'missing native pre-GO outcome')],
        'Actual fd/mount/provider behavior remains runtime-only. This allowlist does not mediate all external file opens.')
    add('teardown after EXIT_ACK', 'exit', '미확인',
        'Harness exit barrier precedes local Server destruction and later DSO/global destruction. ACK is not evidence that teardown is complete.',
        [site('validation/gazebo-joint-execution-contract-v1/inputs/harness_native.cc', 'gz::sim::Server server(config);', 'if(!aero_exit_barrier()) return 70;'),
         site(dart+'collision/ode/OdeCollisionDetector.cpp', 'dCloseODE();')],
        'ODE/FCL/crypto/transport/plugin destructor resource attempts need pre-access coverage until process exit, all threads included. EOF/exit/cleanup success cannot forgive a latched violation.')
    providers = []
    for source in sorted({v['source'] for k,v in m['mounts'].items() if any(t in k for t in ('libode.so','libfcl.so','libcrypto.so','libgz-transport13.so','libgz-common5.so','libzmq.so'))}):
        p = Path(source)
        symbols = subprocess.check_output(['/usr/bin/nm', '-D', '--undefined-only', str(p)], text=True)
        selected = [line.strip() for line in symbols.splitlines() if any(t in line.lower() for t in ('open','socket','connect','bind','dlopen','getenv','config','fwrite','syscall'))]
        providers.append(dict(source=source, sha256=sha(p), mount_aliases=[k for k,v in m['mounts'].items() if v['source']==source],
                              candidate_imports=selected, interpretation='Import candidates only; not called-path evidence, not exhaustive syscall coverage.'))
    candidate = json.loads((R/'reports/build_receipt.json').read_text()) if (R/'reports/build_receipt.json').exists() else None
    report = dict(status='BLOCKED_EXTERNAL_RESOURCE_CLOSURE', rows=rows, providers=providers,
        reused_bounded_paths=[r for r in prior['paths'] if r['path'] in ('fixed_world_assets','ikfast_shared_library','local_resource_retriever','dantzig_ode_lcp','engine_load')],
        prior_manifest_sha256=sha(OLD/'reports/manifest.json'), verified_built_bindings=len(prior['built_sources']),
        unchanged_elf_receipt=dict(changed_components=[], changed_elfs=[], contract_resealed=False,
             reason='Original sealed deployment remains unchanged and refused. Separate ODE init-return candidate does not close internal resource access.'),
        separate_candidate=candidate,
        stage_b='BLOCKED', risk_acceptance='UNDECIDED', runtime='UNVERIFIED', subject_execution=False)
    (R/'reports/review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Reviewed',len(rows),'paths;',len(providers),'ELF providers; external closure BLOCKED')

if __name__ == '__main__':
    main()
