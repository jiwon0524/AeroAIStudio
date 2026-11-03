from __future__ import annotations
import time
from aero_ai_studio.gazebo.transport import stamp


def world_reset_stats_contract(sample,sequence_before,sequence_after,*,time_tolerance=.002):
    """Check a new, paused initial-epoch WorldStatistics sample."""
    if not isinstance(sample,dict):
        sample={}
    sim_time=stamp(sample)
    sim_time_present=bool(sample.get('sim_time_raw_present','sim_time' in sample))
    iterations=(sample.get('iterations_normalized') if 'iterations_normalized' in sample
                else sample.get('iterations'))
    iterations_raw_present=sample.get('iterations_raw_present','iterations' in sample)
    iterations_defaulted=sample.get('iterations_defaulted_from_protobuf',False)
    sequence_new=(sequence_before is not None and sequence_after is not None and
                  int(sequence_after)>int(sequence_before))
    conditions={
        'stats_sequence_new':sequence_new,
        'sim_time_present':sim_time_present,
        'initial_sim_time':abs(sim_time)<=time_tolerance,
        'iterations_zero':iterations is not None and int(iterations)==0,
        'paused':sample.get('paused') is True,
    }
    failures=[name for name,passed in conditions.items() if not passed]
    return {
        'stats_sequence_before':sequence_before,
        'stats_sequence_after':sequence_after,
        'simulation_time':sim_time,
        'paused':sample.get('paused'),
        'iterations_raw_present':iterations_raw_present,
        'iterations_raw_value':sample.get('iterations_raw_value',sample.get('iterations')),
        'iterations_normalized':iterations,
        'iterations_defaulted_from_protobuf':iterations_defaulted,
        **conditions,
        'pass':not failures,
        'failure_reason':None if not failures else ','.join(failures),
    }


def model_only_reset_stats_contract(before,after,sequence_before,sequence_after,*,time_tolerance=.002):
    """Require MODEL_ONLY to preserve the simulation clock and iteration count."""
    before={} if not isinstance(before,dict) else before
    after={} if not isinstance(after,dict) else after
    before_time,after_time=stamp(before),stamp(after)
    before_iterations=before.get('iterations_normalized',before.get('iterations'))
    after_iterations=after.get('iterations_normalized',after.get('iterations'))
    sequence_new=(sequence_before is not None and sequence_after is not None and
                  int(sequence_after)>int(sequence_before))
    time_preserved=(before.get('sim_time_raw_present','sim_time' in before) and
                    after.get('sim_time_raw_present','sim_time' in after) and
                    abs(after_time-before_time)<=time_tolerance)
    iterations_preserved=(before_iterations is not None and after_iterations is not None and
                          int(before_iterations)==int(after_iterations))
    paused=after.get('paused') is True
    conditions={'stats_sequence_new':sequence_new,'simulation_time_preserved':bool(time_preserved),
                'iterations_preserved':iterations_preserved,'paused':paused}
    failures=[name for name,passed in conditions.items() if not passed]
    return {'mode':'model_only','clock_semantics':'preserve_simulation_time_and_iterations',
        'simulation_time_before':before_time,'simulation_time_after':after_time,
        'iterations_before':before_iterations,'iterations_after':after_iterations,
        'stats_sequence_before':sequence_before,'stats_sequence_after':sequence_after,
        **conditions,'pass':not failures,
        'failure_reason':None if not failures else ','.join(failures)}
class GazeboStepper:
    """Fixed-step control with reconciliation for lost service acknowledgements."""
    STEP_RETRIES=1
    RECONCILE_TIMEOUT=.75
    TIME_TOLERANCE=.002

    def __init__(self,transport,world: str,physics_dt=.001,dt=.1,timeout=5):
        if dt<=0 or physics_dt<=0 or abs(round(dt/physics_dt)*physics_dt-dt)>1e-8:
            raise ValueError('dt must be a positive integer multiple of physics_dt')
        self.transport,self.world=transport,world
        self.physics_dt,self.dt,self.timeout=physics_dt,dt,timeout
        self.time=0.
        self.last_verification={}
        self.topic=f'/world/{world}/stats'
        transport.subscribe(self.topic,'WorldStatistics')

    def control(self,data):return self.transport.request(f'/world/{self.world}/control','WorldControl','Boolean',data)
    def pause(self):self.control({'pause':True})
    def resume(self):self.control({'pause':False})

    def reset_world(self):
        """Reset Harmonic's physics/system state and reconcile its clock epoch.

        In gz-sim 8 ``reset: {all: true}`` resets systems and simulation time.
        The acknowledgement only means the request was accepted, so wait for a
        newer /stats sample at the initial epoch before changing local time.
        """
        before=self.transport.sample(self.topic,self.time-self.TIME_TOLERANCE,self.timeout)
        before_time=stamp(before)
        before_iterations=before.get('iterations_normalized',before.get('iterations'))
        before_snapshot=self._snapshot()
        sequence_before=before_snapshot.get('sequence')
        if sequence_before is None:
            raise RuntimeError('Cannot reset Gazebo world without a /stats receive sequence')
        evidence={'method':'world_control_reset_all','before_sim_time':before_time,
            'before_iterations':before_iterations,'stats_sequence_before':sequence_before,
            'service_response':None,'after_sim_time':None,'after_iterations':None,
            'paused_after':None,'stats_sequence_after':None,'valid':False}
        try:
            response=self.control({'pause':True,'reset':{'all':True}})
            evidence['service_response']=response
            if not response.get('data',False):
                raise RuntimeError('Gazebo rejected WorldControl reset all (Boolean false)')
            after,sequence=self.transport.sample_after_sequence(self.topic,sequence_before,
                min_time=-self.TIME_TOLERANCE,max_time=self.TIME_TOLERANCE,timeout=self.timeout)
            after_time=stamp(after)
            iterations=after.get('iterations_normalized',after.get('iterations'))
            paused=after.get('paused')
            contract=world_reset_stats_contract(after,sequence_before,sequence)
            evidence.update(after_sim_time=after_time,after_iterations=iterations,
                            paused_after=paused,stats_sequence_after=sequence,
                            iterations_raw_present=contract['iterations_raw_present'],
                            iterations_normalized=contract['iterations_normalized'],
                            iterations_defaulted_from_protobuf=contract['iterations_defaulted_from_protobuf'],
                            stats_reset_contract=contract)
            if not contract['pass']:
                raise RuntimeError('Gazebo reset all did not produce a paused initial-epoch /stats state: '
                                   +str(contract['failure_reason']))
            evidence['valid']=True
            self.time=after_time
            self.last_verification={'classification':'world_reset_all_acknowledged',**evidence}
            return evidence
        except Exception as error:
            evidence['failure']=str(error)
            self.last_verification={'classification':'world_reset_all_failed',**evidence}
            error.reset_evidence=evidence
            raise

    def reset_model_only(self):
        """Reset model state while preserving a verified paused simulation epoch."""
        before=self.transport.sample(self.topic,self.time-self.TIME_TOLERANCE,self.timeout)
        before_time=stamp(before)
        before_snapshot=self._snapshot()
        sequence_before=before_snapshot.get('sequence')
        if sequence_before is None:
            raise RuntimeError('Cannot reset Gazebo model without a /stats receive sequence')
        evidence={'method':'world_control_reset_model_only','before_sim_time':before_time,
            'before_iterations':before.get('iterations_normalized',before.get('iterations')),
            'stats_sequence_before':sequence_before,'service_response':None,
            'after_sim_time':None,'after_iterations':None,'paused_after':None,
            'stats_sequence_after':None,'valid':False}
        try:
            response=self.control({'pause':True,'reset':{'model_only':True}})
            evidence['service_response']=response
            if not response.get('data',False):
                raise RuntimeError('Gazebo rejected WorldControl reset model_only (Boolean false)')
            after,sequence=self.transport.sample_after_sequence(self.topic,sequence_before,
                min_time=before_time-self.TIME_TOLERANCE,
                max_time=before_time+self.TIME_TOLERANCE,timeout=self.timeout)
            contract=model_only_reset_stats_contract(before,after,sequence_before,sequence)
            evidence.update(after_sim_time=stamp(after),
                after_iterations=after.get('iterations_normalized',after.get('iterations')),
                paused_after=after.get('paused'),stats_sequence_after=sequence,
                stats_reset_contract=contract)
            if not contract['pass']:
                raise RuntimeError('Gazebo model_only reset violated preserved stats contract: '
                                   +str(contract['failure_reason']))
            evidence['valid']=True
            self.time=stamp(after)
            self.last_verification={'classification':'world_reset_model_only_acknowledged',**evidence}
            return evidence
        except Exception as error:
            evidence['failure']=str(error)
            self.last_verification={'classification':'world_reset_model_only_failed',**evidence}
            error.reset_evidence=evidence
            raise

    def _snapshot(self):
        if hasattr(self.transport,'snapshot'):
            return self.transport.snapshot(self.topic)
        data=self.transport.latest(self.topic) if hasattr(self.transport,'latest') else None
        return {'data':data,'sequence':self.transport.cursor(self.topic) if hasattr(self.transport,'cursor') else None,
                'received_at':None}

    def _wait_fresh_stats(self,after_sequence,timeout):
        deadline=time.monotonic()+timeout
        latest=None
        while time.monotonic()<deadline:
            latest=self._snapshot()
            sequence=latest.get('sequence')
            if latest.get('data') is not None and sequence is not None and sequence>after_sequence:
                return latest
            time.sleep(min(.01,max(0.,deadline-time.monotonic())))
        return latest

    def _iteration_delta(self,before,after):
        a,b=before.get('iterations'),after.get('iterations')
        return None if a is None or b is None else int(b)-int(a)

    def _verify_progress(self,sample,before_time,expected,iterations_before,*,require_iterations=False):
        actual=stamp(sample);delta=actual-before_time
        iteration_delta=self._iteration_delta(iterations_before,sample)
        expected_steps=round(expected/self.physics_dt)
        paused=sample.get('paused')
        time_ok=delta>0 and abs(delta-expected)<=self.TIME_TOLERANCE
        iterations_ok=(iteration_delta==expected_steps if iteration_delta is not None else not require_iterations)
        paused_ok=(paused is True if paused is not None else not require_iterations)
        return {'after_sim_time':actual,'observed_delta':delta,'iteration_delta':iteration_delta,
                'expected_iteration_delta':expected_steps,'time_ok':time_ok,
                'iterations_ok':iterations_ok,'paused_after':paused,'paused_ok':paused_ok,
                'valid':time_ok and iterations_ok and paused_ok}

    def _raise_recovery_failure(self,message,evidence):
        if evidence.get('classification') in (None,'pending','not_executed_retry_safe'):
            evidence['classification']='ambiguous_partial_progress'
        evidence['failure']=message
        self.last_verification=evidence
        error=RuntimeError(message)
        error.step_recovery=evidence
        raise error

    def step_simulation(self,n_steps=1):
        if type(n_steps) is not int or n_steps<1:raise ValueError('n_steps must be positive')
        expected_steps=round(self.dt/self.physics_dt)*n_steps
        expected=n_steps*self.dt
        before_sample=self.transport.sample(self.topic,self.time-self.TIME_TOLERANCE,self.timeout)
        before_time=stamp(before_sample)
        if self.time and abs(before_time-self.time)>self.TIME_TOLERANCE:
            raise RuntimeError('Gazebo simulation time changed outside the stepper before fixed stepping')
        before_snapshot=self._snapshot()
        # The sample is the time baseline; snapshot metadata establishes the cursor
        # from which a timeout-time stats update must arrive.
        sequence_before=before_snapshot.get('sequence')
        iterations_before=before_sample.get('iterations')
        paused_before=before_sample.get('paused')
        target=before_time+expected
        request={'pause':True,'multi_step':expected_steps}
        evidence={'before_sim_time':before_time,'expected_delta':expected,'expected_steps':expected_steps,
                  'iterations_before':iterations_before,'paused_before':paused_before,
                  'stats_sequence_before':sequence_before,
                  'sensor_sequence_before':self.transport.sequence_snapshot() if hasattr(self.transport,'sequence_snapshot') else None,
                  'service_timeout':False,'observed_after_timeout_sim_time':None,'observed_delta':None,
                  'iterations_after':None,'paused_after':None,'classification':'pending',
                  'retry_count':0,'duplicate_step_prevented':False,'attempts':[]}

        for attempt in range(self.STEP_RETRIES+1):
            # Before each retry, take a fresh stats snapshot and prove the prior
            # timed-out command did not advance the paused world.
            if attempt:
                snap=self._snapshot();data=snap.get('data')
                fresh=(data is not None and snap.get('received_at') is not None and
                       time.monotonic()-snap['received_at']<=self.RECONCILE_TIMEOUT)
                current=stamp(data) if data else None
                current_iterations=data.get('iterations') if data else None
                same=(fresh and current is not None and abs(current-before_time)<=self.TIME_TOLERANCE and
                      current_iterations==iterations_before and data.get('paused') is True)
                evidence['retry_preflight']={'fresh':fresh,'sim_time':current,'iterations':current_iterations,
                    'paused':None if data is None else data.get('paused'),'safe':same,
                    'stats_sequence':snap.get('sequence')}
                if not same:
                    self._raise_recovery_failure('Gazebo step retry refused: latest stats do not prove zero progress',evidence)
                evidence['retry_count']=attempt
                evidence['duplicate_step_prevented']=True

            acknowledged=False
            try:
                try:
                    result=self.control(request)
                except RuntimeError as error:
                    evidence.update(classification='service_rejected' if 'Boolean false' in str(error) else 'service_failed',
                                    service_timeout=False,failure=str(error),duplicate_step_prevented=True)
                    evidence['attempts'].append({'attempt':attempt+1,'error':str(error)})
                    self.last_verification=evidence
                    raise
                evidence['attempts'].append({'attempt':attempt+1,'response':result})
                # HarmonicTransport rejects Boolean false. Keep a defensive check
                # here for alternate transport implementations and fixtures.
                if not result.get('data',False):
                    evidence['classification']='service_rejected'
                    self.last_verification=evidence
                    raise RuntimeError('Gazebo rejected fixed-step WorldControl request (Boolean false)')
                acknowledged=True
                sample=self.transport.sample(self.topic,target-1e-6,self.timeout)
                progress=self._verify_progress(sample,before_time,expected,{'iterations':iterations_before})
                evidence.update(progress)
                evidence['iterations_after']=sample.get('iterations')
                evidence['classification']='acknowledged' if progress['valid'] else 'ambiguous_partial_progress'
                evidence['service_timeout']=False
                evidence['sensor_sequence_after']=self.transport.sequence_snapshot() if hasattr(self.transport,'sequence_snapshot') else None
                self.last_verification=evidence
                if not progress['valid']:
                    raise RuntimeError('Gazebo simulation-time / iteration / pause evidence does not match fixed-step request')
                self.time=progress['after_sim_time']
                return self.time
            except TimeoutError as error:
                if acknowledged:
                    observed=self._snapshot();data=observed.get('data')
                    evidence.update(service_timeout=False,classification='acknowledged_progress_unverified',
                        observed_after_timeout_sim_time=stamp(data) if data else None,
                        observed_delta=None if data is None else stamp(data)-before_time,
                        iterations_after=None if data is None else data.get('iterations'),
                        paused_after=None if data is None else data.get('paused'),
                        duplicate_step_prevented=True,failure=str(error))
                    self.last_verification=evidence
                    self._raise_recovery_failure('Gazebo acknowledged WorldControl but fixed-step progress could not be verified',evidence)
                evidence['service_timeout']=True
                evidence['attempts'].append({'attempt':attempt+1,'error':str(error)})
                # A timeout says nothing about whether the server executed the
                # request. Only a new stats message can resolve that ambiguity.
                observed=self._wait_fresh_stats(sequence_before,self.RECONCILE_TIMEOUT)
                data=None if observed is None else observed.get('data')
                if data is None or observed.get('sequence') is None or observed['sequence']<=sequence_before:
                    evidence.update(classification='ambiguous_stats_unavailable',
                                    duplicate_step_prevented=True)
                    self.last_verification=evidence
                    self._raise_recovery_failure('Gazebo WorldControl timed out and fresh /stats evidence is unavailable',evidence)
                observed_time=stamp(data);observed_delta=observed_time-before_time
                iteration_delta=self._iteration_delta({'iterations':iterations_before},data)
                evidence.update(observed_after_timeout_sim_time=observed_time,observed_delta=observed_delta,
                    iterations_after=data.get('iterations'),iteration_delta=iteration_delta,
                    paused_after=data.get('paused'),stats_sequence_after=observed.get('sequence'),
                    sensor_sequence_after=self.transport.sequence_snapshot() if hasattr(self.transport,'sequence_snapshot') else None)
                close=lambda value,expected_value:abs(value-expected_value)<=self.TIME_TOLERANCE
                exact_time=close(observed_delta,expected)
                exact_iterations=iteration_delta==expected_steps
                paused_ok=data.get('paused') is True
                if exact_time and exact_iterations and paused_ok:
                    evidence.update(classification='executed_response_lost',duplicate_step_prevented=True,
                                    after_sim_time=observed_time,actual_delta=observed_delta,
                                    expected_iteration_delta=expected_steps,time_ok=True,iterations_ok=True,paused_ok=True,
                                    valid=True)
                    self.last_verification=evidence;self.time=observed_time
                    return self.time
                no_progress=(close(observed_delta,0.) and iteration_delta==0 and paused_ok and
                             paused_before is True)
                if no_progress and attempt<self.STEP_RETRIES:
                    evidence['classification']='not_executed_retry_safe'
                    evidence['duplicate_step_prevented']=True
                    sequence_before=observed['sequence']
                    continue
                evidence['classification']='ambiguous_partial_progress'
                evidence['duplicate_step_prevented']=True
                self.last_verification=evidence
                self._raise_recovery_failure(
                    'Gazebo WorldControl timeout left partial, excessive, or unverified progress; refusing duplicate step',evidence)

        self._raise_recovery_failure('Gazebo WorldControl retry budget exhausted',evidence)

    def set_real_time_factor(self,value):
        if value<0:raise ValueError('Negative real-time factor')
        return self.transport.request(f'/world/{self.world}/set_physics','Physics','Boolean',{'real_time_factor':float(value),'max_step_size':self.physics_dt})
