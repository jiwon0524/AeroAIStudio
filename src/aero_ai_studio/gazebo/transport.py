"""Lazy Harmonic native transport. No Linux dependency is imported at app startup."""
from __future__ import annotations
import importlib
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from typing import Protocol


def stamp(data: dict) -> float:
    value=data.get('sim_time')
    if value is None:
        value=data.get('header',{}).get('stamp',{})
    seconds=float(value.get('sec',0));nanoseconds=float(value.get('nsec',0))
    # Pose_V from SceneBroadcaster may leave its top-level header empty and put
    # the simulation stamp in each contained Pose header.
    if seconds==0 and nanoseconds==0:
        poses=data.get('pose',())
        if poses:
            nested=poses[0].get('header',{}).get('stamp',{})
            seconds=float(nested.get('sec',0));nanoseconds=float(nested.get('nsec',0))
    return seconds+nanoseconds*1e-9


def normalize_topic_message(message_type: str, data: dict) -> dict:
    """Normalize only protobuf defaults whose schema semantics are known."""
    if message_type != 'WorldStatistics':
        return data
    if not isinstance(data, dict):
        raise TypeError('WorldStatistics callback must provide a parsed message dictionary')
    result=dict(data)
    raw_present='iterations' in data
    raw_value=data.get('iterations')
    if raw_present:
        if isinstance(raw_value,bool):
            raise ValueError('WorldStatistics.iterations must be an integer scalar')
        normalized=int(raw_value)
    else:
        # In gz.msgs.WorldStatistics, iterations is a non-presence int64.
        # A parsed message with the field omitted therefore has protobuf value 0.
        normalized=0
    result.update(iterations=normalized,
        iterations_raw_present=raw_present,
        iterations_raw_value=raw_value,
        iterations_normalized=normalized,
        iterations_defaulted_from_protobuf=not raw_present,
        sim_time_raw_present='sim_time' in data)
    return result


class GazeboTransport(Protocol):
    def request(self,service: str,request_type: str,response_type: str,payload: dict) -> dict: ...
    def subscribe(self,topic: str,message_type: str) -> None: ...
    def sample(self,topic: str,min_time: float=-1,timeout: float=5) -> dict: ...
    def close(self) -> None: ...


class HarmonicTransport:
    TYPES={'Empty':'empty','Boolean':'boolean','Scene':'scene','Pose':'pose','WorldControl':'world_control',
           'WorldStatistics':'world_stats','LaserScan':'laserscan','Physics':'physics','EntityFactory':'entity_factory',
           'Twist':'twist','Contacts':'contacts','Pose_V':'pose_v','Odometry':'odometry'}

    def __init__(self,partition: str | None=None,timeout: float=5):
        try:
            native=importlib.import_module('gz.transport13')
            self.json=importlib.import_module('google.protobuf.json_format')
        except ImportError as error:
            raise RuntimeError('Harmonic Python bindings required: python3-gz-transport13 / python3-gz-msgs10. Use Ubuntu system-site-packages venv.') from error
        self.timeout=timeout
        self.executable=shutil.which('gz')
        if not self.executable:raise RuntimeError('gz service executable required for isolated service RPC')
        self.request_history=[]
        old=os.environ.get('GZ_PARTITION')
        if partition:os.environ['GZ_PARTITION']=partition
        try:self.node=native.Node()
        finally:
            if partition:
                if old is None:os.environ.pop('GZ_PARTITION',None)
                else:os.environ['GZ_PARTITION']=old
        self.partition=self.node.options.partition
        self.text=importlib.import_module('google.protobuf.text_format')
        self.condition=threading.Condition()
        self.samples={}
        self.received_at={}
        self.topics=set()
        self.closed=False
        self.callbacks=[]
        self.publishers={}
        self.history={}
        self.sequences={}
        self.sequenced_history={}

    def message(self,name):
        return getattr(importlib.import_module('gz.msgs10.'+self.TYPES[name]+'_pb2'),name)

    def wait_for_service(self,service,request_type,response_type,timeout=None):
        req=self.message(request_type).DESCRIPTOR.full_name
        rep=self.message(response_type).DESCRIPTOR.full_name
        deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
        delay=.05
        while True:
            providers=self.node.service_info(service)
            if providers:
                schemas={(p.req_type_name,p.rep_type_name) for p in providers}
                if (req,rep) not in schemas:
                    raise RuntimeError(f'Gazebo service schema mismatch: {service}; expected {req} -> {rep}; advertised {sorted(schemas)}')
                return {'service':service,'request_type':req,'response_type':rep}
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Gazebo service not advertised/ready: '+service)
            time.sleep(min(delay,remaining));delay=min(delay*2,.2)

    def request(self,service,request_type,response_type,payload,*,max_attempts=None):
        req,rep=self.message(request_type),self.message(response_type)
        message=self.json.ParseDict(payload,req())
        deadline=time.monotonic()+self.timeout
        evidence={'service':service,'request_type':req.DESCRIPTOR.full_name,'response_type':rep.DESCRIPTOR.full_name,
                  'payload':payload,'backend':'gz-service-subprocess','attempts':[]}
        self.request_history.append(evidence)
        self.wait_for_service(service,request_type,response_type,max(0,deadline-time.monotonic()))
        # Transport 13's synchronous Python RPC holds the GIL while topic
        # callbacks need it. Keep RPC outside the subscriber process. A Python
        # thread or a second Node in this process would not isolate that GIL.
        env=dict(os.environ,GZ_PARTITION=self.partition)
        retry_pose=service.endswith('/set_pose') and request_type=='Pose' and response_type=='Boolean'
        attempts=3 if retry_pose else 1
        if max_attempts is not None:
            if type(max_attempts) is not int or not 1<=max_attempts<=attempts:
                raise ValueError('Invalid service attempt limit')
            attempts=max_attempts
        for attempt in range(attempts):
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            budget=min(2.,remaining) if retry_pose else remaining
            timeout_ms=max(1,int(budget*1000))
            command=[self.executable,'service','-s',service,'--reqtype',req.DESCRIPTOR.full_name,
                     '--reptype',rep.DESCRIPTOR.full_name,'--timeout',str(timeout_ms),
                     '--req',self.text.MessageToString(message)]
            record={'timeout_ms':timeout_ms};evidence['attempts'].append(record)
            try:
                completed=subprocess.run(command,capture_output=True,text=True,env=env,timeout=remaining)
                record.update(returncode=completed.returncode,stdout=completed.stdout,stderr=completed.stderr)
                output=completed.stdout.strip()
                if 'timed out' in (output+' '+completed.stderr).lower():
                    raise TimeoutError('Service response timed out')
                if 'service call failed' in (output+' '+completed.stderr).lower():
                    raise RuntimeError('Gazebo service call failed: '+service+'; '+completed.stderr+output)
                if completed.returncode:
                    raise RuntimeError(f'gz service exited {completed.returncode}: {completed.stderr or output}')
                response=self.text.Parse(output,rep())
                result=self.json.MessageToDict(response,preserving_proto_field_name=True)
                if response_type=='Boolean' and not result.get('data',False):
                    raise RuntimeError('Gazebo rejected request (Boolean false): '+service)
                record['response']=result
                return result
            except (subprocess.TimeoutExpired,TimeoutError) as error:
                record['error']=str(error)
                if not retry_pose or attempt==attempts-1:break
                remaining=deadline-time.monotonic()
                if remaining<=0:break
                time.sleep(min(.1*2**attempt,remaining))
        raise TimeoutError(f'Gazebo service failed/timed out: {service}; {req.DESCRIPTOR.full_name} -> {rep.DESCRIPTOR.full_name}; attempts={len(evidence["attempts"])}')

    def subscribe(self,topic,message_type):
        if topic in self.topics:return
        def callback(message):
            data=self.json.MessageToDict(message,preserving_proto_field_name=True)
            data=normalize_topic_message(message_type,data)
            with self.condition:
                if not hasattr(self,'received_at'):self.received_at={}
                self.samples[topic]=data
                self.received_at[topic]=time.monotonic()
                self.history.setdefault(topic,deque(maxlen=2000)).append(data)
                sequence=self.sequences.get(topic,0)+1
                self.sequences[topic]=sequence
                self.sequenced_history.setdefault(topic,deque(maxlen=2000)).append((sequence,data))
                self.condition.notify_all()
        self.callbacks.append(callback)
        if not self.node.subscribe(self.message(message_type),topic,callback):raise RuntimeError('Gazebo subscription failed: '+topic)
        self.topics.add(topic)

    def wait_for_topic(self,topic,message_type,timeout=None):
        expected=self.message(message_type).DESCRIPTOR.full_name
        deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
        while True:
            publishers,_=self.node.topic_info(topic)
            if publishers:
                advertised={p.msg_type_name for p in publishers}
                if advertised!={expected}:raise RuntimeError(f'Gazebo topic schema mismatch: {topic}: {advertised}')
                return {'topic':topic,'message_type':expected}
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Gazebo topic publisher not ready: '+topic)
            time.sleep(min(.05,remaining))

    def cursor(self,topic):
        with self.condition:return self.sequences.get(topic,0)

    def snapshot(self,topic):
        """Return the latest received message with transport-side freshness evidence."""
        with self.condition:
            return {'data':self.samples.get(topic),'sequence':self.sequences.get(topic,0),
                    'received_at':self.received_at.get(topic)}

    def sequence_snapshot(self):
        with self.condition:return dict(self.sequences)

    def messages_after(self,topic,sequence,timeout=0):
        """Receive sequence, independent of simulation stamps; detect lost history."""
        deadline=time.monotonic()+timeout
        with self.condition:
            while not self.closed:
                history=self.sequenced_history.get(topic,())
                if history and history[0][0]>sequence+1:
                    raise RuntimeError('Gazebo receive history overflow: '+topic)
                messages=[(seq,data) for seq,data in history if seq>sequence]
                if messages:return messages
                remaining=deadline-time.monotonic()
                if remaining<=0:return []
                self.condition.wait(min(.01,remaining))
        raise RuntimeError('Gazebo transport closed')

    def sample(self,topic,min_time=-1,timeout=5):
        deadline=time.monotonic()+timeout
        with self.condition:
            while not self.closed:
                data=self.samples.get(topic)
                if data is not None and stamp(data)>=min_time:return data
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError(f'No fresh Gazebo sample: {topic}, expected sim time >= {min_time}')
                self.condition.wait(min(.2,remaining))
        raise RuntimeError('Gazebo transport closed')

    def sample_after_sequence(self,topic,after_sequence,*,min_time=-1,max_time=None,timeout=5):
        """Wait for a post-epoch message, using receive sequence and sim time.

        Simulation resets rewind timestamps, so ``sample`` alone can mistake a
        buffered message from the previous epoch for current telemetry.
        """
        deadline=time.monotonic()+timeout
        cursor=int(after_sequence)
        while not self.closed:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise TimeoutError(f'No post-epoch Gazebo sample: {topic}, after sequence {after_sequence}')
            messages=self.messages_after(topic,cursor,timeout=remaining)
            for sequence,data in messages:
                cursor=sequence
                timestamp=stamp(data)
                if timestamp < min_time:
                    continue
                if max_time is not None and timestamp > max_time:
                    continue
                return data,sequence
        raise RuntimeError('Gazebo transport closed')

    def latest(self,topic):
        with self.condition:return self.samples.get(topic)

    def since(self,topic,timestamp):
        with self.condition:return [m for m in self.history.get(topic,()) if stamp(m)>timestamp]

    def publish(self,topic,message_type,payload):
        cls=self.message(message_type)
        if topic not in self.publishers:self.publishers[topic]=self.node.advertise(topic,cls)
        publisher=self.publishers[topic]
        deadline=time.monotonic()+self.timeout
        while not publisher.has_connections():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Gazebo command subscriber not ready: '+topic)
            time.sleep(min(.01,remaining))
        if not publisher.publish(self.json.ParseDict(payload,cls())):
            raise RuntimeError('Gazebo publish failed: '+topic)

    def close(self):
        with self.condition:
            self.closed=True
            self.condition.notify_all()
        for topic in self.topics:self.node.unsubscribe(topic)
        self.topics.clear()
