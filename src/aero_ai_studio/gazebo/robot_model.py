"""Simple differential-drive validation robot. No UAV or external assets."""
import xml.etree.ElementTree as ET


def add_ground_robot(world,scenario,world_name):
    old=world.find("model[@name='agent_marker']")
    if old is not None:world.remove(old)
    model=ET.SubElement(world,'model',name='simple_agent')
    ET.SubElement(model,'pose').text=f'{scenario.start[0]+.5} {scenario.start[1]+.5} 0.16 0 0 0'
    ET.SubElement(model,'static').text='false'
    def inertia(link,mass,ix,iy,iz):
        inert=ET.SubElement(link,'inertial')
        ET.SubElement(inert,'mass').text=str(mass)
        tensor=ET.SubElement(inert,'inertia')
        for key,val in [('ixx',ix),('iyy',iy),('izz',iz),('ixy',0),('ixz',0),('iyz',0)]:ET.SubElement(tensor,key).text=str(val)
    body=ET.SubElement(model,'link',name='body')
    inertia(body,2,.017,.033,.043)
    for tag in ('collision','visual'):
        part=ET.SubElement(body,tag,name='body_collision' if tag=='collision' else 'body_visual')
        ET.SubElement(ET.SubElement(ET.SubElement(part,'geometry'),'box'),'size').text='.45 .32 .16'
    for label,y in [('left',.21),('right',-.21)]:
        wheel=ET.SubElement(model,'link',name=label+'_wheel')
        ET.SubElement(wheel,'pose').text=f'0 {y} -.06 1.5707963267948966 0 0'
        inertia(wheel,.2,.00056,.00056,.001)
        for tag in ('collision','visual'):
            part=ET.SubElement(wheel,tag,name=label+'_'+tag)
            cylinder=ET.SubElement(ET.SubElement(part,'geometry'),'cylinder')
            ET.SubElement(cylinder,'radius').text='.1';ET.SubElement(cylinder,'length').text='.05'
            if tag=='collision':
                ode=ET.SubElement(ET.SubElement(ET.SubElement(part,'surface'),'friction'),'ode')
                ET.SubElement(ode,'mu').text='1';ET.SubElement(ode,'mu2').text='1'
        joint=ET.SubElement(model,'joint',name=label+'_joint',type='revolute')
        ET.SubElement(joint,'parent').text='body';ET.SubElement(joint,'child').text=label+'_wheel'
        axis=ET.SubElement(joint,'axis')
        # The wheel link is rolled +90 deg: its local +Z is model -Y.
        # DiffDrive needs both positive wheel rates about model +Y so that
        # positive linear.x rolls along body +X and positive angular.z turns CCW.
        ET.SubElement(axis,'xyz',expressed_in='__model__').text='0 1 0'
        limit=ET.SubElement(axis,'limit');ET.SubElement(limit,'lower').text='-1e16';ET.SubElement(limit,'upper').text='1e16'
    for label,x in [('front',.16),('rear',-.16)]:
        caster=ET.SubElement(model,'link',name=label+'_caster')
        ET.SubElement(caster,'pose').text=f'{x} 0 -.12 0 0 0'
        inertia(caster,.05,.00001,.00001,.00001)
        for tag in ('collision','visual'):
            part=ET.SubElement(caster,tag,name=label+'_'+tag)
            ET.SubElement(ET.SubElement(ET.SubElement(part,'geometry'),'sphere'),'radius').text='.04'
            if tag=='collision':
                ode=ET.SubElement(ET.SubElement(ET.SubElement(part,'surface'),'friction'),'ode')
                ET.SubElement(ode,'mu').text='.001';ET.SubElement(ode,'mu2').text='.001'
        joint=ET.SubElement(model,'joint',name=label+'_fixed',type='fixed')
        ET.SubElement(joint,'parent').text='body';ET.SubElement(joint,'child').text=label+'_caster'
    diff=ET.SubElement(model,'plugin',filename='gz-sim-diff-drive-system',name='gz::sim::systems::DiffDrive')
    for key,value in [('left_joint','left_joint'),('right_joint','right_joint'),('wheel_separation','.42'),('wheel_radius','.1'),
                      ('topic',f'/aero/{world_name}/cmd_vel'),('odom_publish_frequency','100')]:ET.SubElement(diff,key).text=value
    contact=ET.SubElement(body,'sensor',name='body_contacts',type='contact')
    ET.SubElement(contact,'always_on').text='true';ET.SubElement(contact,'update_rate').text='1000'
    settings=ET.SubElement(contact,'contact')
    ET.SubElement(settings,'collision').text='body_collision'
    # Sim 8 Contact reads contact/topic, not the generic sensor/topic.
    ET.SubElement(settings,'topic').text=f'/aero/{world_name}/contacts'
    return body
