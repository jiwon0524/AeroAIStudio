"""Harmonic's event-only contact channel; silence is not a stream heartbeat."""
from __future__ import annotations
import math
from aero_ai_studio.gazebo.contracts import parse_contacts
from aero_ai_studio.gazebo.transport import stamp


class ContactProvider:
    def __init__(self,transport,topic,agent,timeout=5):
        self.transport,self.topic,self.agent=transport,topic,agent
        self.schema=transport.wait_for_topic(topic,'Contacts',timeout)
        transport.subscribe(topic,'Contacts')
        self.epoch=0
        self.reset(0.)

    def reset(self,simulation_time):
        # Transport remains connected across episode resets. Sequence alone
        # cannot reject old packets which arrive after reset; also check time.
        self.epoch+=1
        self.floor=simulation_time
        self.sequence=self.transport.cursor(self.topic)
        self.evidence=[]
        self.state={'topic':self.topic,'semantics':'event_only','epoch':self.epoch,
                    'after_simulation_time':self.floor,'receive_sequence':self.sequence,'assessment':'reset'}

    def poll(self,simulation_time,timeout=.05):
        if simulation_time<self.floor:raise RuntimeError('Contact simulation time rewound; reset contact epoch')
        self.transport.wait_for_topic(self.topic,'Contacts',0)
        frames=self.transport.messages_after(self.topic,self.sequence,timeout)
        events=[];ignored=0
        for sequence,message in frames:
            self.sequence=sequence
            if 'stamp' not in message.get('header',{}):raise ValueError('Contacts header timestamp required')
            timestamp=stamp(message)
            if not math.isfinite(timestamp):raise ValueError('Non-finite Contacts timestamp')
            if timestamp<=self.floor+1e-9:
                ignored+=1;continue
            if timestamp>simulation_time+.002:raise RuntimeError('Contact timestamp ahead of simulation')
            for event in parse_contacts(message,self.agent):
                if event.timestamp<=self.floor+1e-9:
                    ignored+=1;continue
                if event.timestamp>simulation_time+.002:raise RuntimeError('Contact event timestamp ahead of simulation')
                events.append(event.to_dict())
                self.evidence.append({'receive_sequence':sequence,'epoch':self.epoch,
                                      'delivery_lag_sim_seconds':simulation_time-event.timestamp,
                                      'event':event.to_dict(),'message':message})
        self.state={'topic':self.topic,'schema':self.schema,'semantics':'event_only',
                    'epoch':self.epoch,'after_simulation_time':self.floor,'receive_sequence':self.sequence,
                    'ignored_pre_reset':ignored,'received_frames':len(frames),'events':len(events),
                    'assessment':'contact' if events else 'no_new_contact_event',
                    'silence_is_health_proof':False,'delivery_wait_seconds':timeout}
        # Include late events from earlier steps in this episode. Never discard
        # them just because they miss the latest step's freshness window.
        return events
