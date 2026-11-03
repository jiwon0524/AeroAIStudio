from aero_ai_studio.gazebo.sensor_provider import RangeSensorProvider


class EpochTransport:
    def __init__(self):
        self.sequence=8
        self.scan={'header':{'stamp':{'sec':0,'nsec':100_000_000}},
                   'ranges':[2.,3.,4.,5.],'range_max':30.}

    def subscribe(self,*_):pass
    def cursor(self,_topic):return self.sequence

    def sample_after_sequence(self,topic,after_sequence,*,min_time,max_time,timeout):
        assert after_sequence==8
        assert min_time<=.1<=max_time
        self.sequence+=1
        return self.scan,self.sequence

    def sample(self,*_args,**_kwargs):
        raise AssertionError('must reject previous-clock-epoch cached sample')


def test_sensor_provider_restarts_timestamp_epoch_and_requires_new_receive_sequence():
    transport=EpochTransport()
    provider=RangeSensorProvider(transport,'world',(5.5,2.5),physics=True)
    provider.previous_timestamp=12.4
    provider.sequence=31
    provider.frame=object()
    provider.reset_epoch()
    assert provider.previous_timestamp is None
    assert provider.frame is None
    assert provider.latest is None
    assert provider.epoch_receive_sequence==8
    observation=provider.get_range_observation(
        {'x':1.5,'y':1.5,'yaw':0.},min_time=.098,simulation_time=.1)
    assert observation.sensor_state['sensor_timestamp']==.1
    assert observation.sensor_state['sequence']==32
    assert provider.epoch_receive_sequence is None
