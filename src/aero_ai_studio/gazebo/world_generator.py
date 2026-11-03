from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
import hashlib
import json
import os
from aero_ai_studio.scenario.models import ScenarioSpec
from aero_ai_studio.core.storage import write_json


class GazeboWorldGenerator:
    def generate(self, scenario: ScenarioSpec, root: Path, closed_loop: bool=False,control_mode: str='KINEMATIC') -> Path:
        if control_mode not in ('KINEMATIC','PHYSICS'):raise ValueError('Unknown control mode')
        scenario.validate()
        if scenario.world_mode != 'synthetic':
            raise ValueError('V0.5 SDF export supports Synthetic World only')
        digest = hashlib.sha256((json.dumps(scenario.to_dict(), sort_keys=True)+('PHYSICS' if control_mode=='PHYSICS' else '')).encode()).hexdigest()[:12]
        name = 'aero_' + digest
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        sdf = ET.Element('sdf', version='1.9')
        world = ET.SubElement(sdf, 'world', name=name)
        ET.SubElement(world, 'gravity').text = '0 0 -9.8'
        physics = ET.SubElement(world, 'physics', name='fixed_step', type='ignored')
        ET.SubElement(physics, 'max_step_size').text = '0.001'
        ET.SubElement(physics, 'real_time_factor').text = '1'
        for filename, plugin in [('physics','Physics'), ('user-commands','UserCommands'), ('scene-broadcaster','SceneBroadcaster')]:
            ET.SubElement(world, 'plugin', filename=f'gz-sim-{filename}-system', name=f'gz::sim::systems::{plugin}')
        if closed_loop:
            sensors=ET.SubElement(world,'plugin',filename='gz-sim-sensors-system',name='gz::sim::systems::Sensors')
            ET.SubElement(sensors,'render_engine').text='ogre2'
            if control_mode=='PHYSICS':ET.SubElement(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
        light = ET.SubElement(world, 'light', name='sun', type='directional')
        ET.SubElement(light, 'pose').text = '0 0 10 0 0 0'
        ET.SubElement(light, 'diffuse').text = '0.9 0.9 0.9 1'
        ET.SubElement(light, 'direction').text = '-0.5 0.1 -0.9'
        def box(label: str, x: float, y: float, z: float, sx: float, sy: float, sz: float, rgba: str, collision: bool = True):
            model = ET.SubElement(world, 'model', name=label)
            ET.SubElement(model, 'static').text = 'true'
            ET.SubElement(model, 'pose').text = f'{x} {y} {z} 0 0 0'
            link = ET.SubElement(model, 'link', name='body')
            for tag in (('collision', 'visual') if collision else ('visual',)):
                element = ET.SubElement(link, tag, name=tag)
                geometry = ET.SubElement(element, 'geometry')
                ET.SubElement(ET.SubElement(geometry, 'box'), 'size').text = f'{sx} {sy} {sz}'
                if tag == 'visual':
                    material = ET.SubElement(element, 'material')
                    ET.SubElement(material, 'ambient').text = rgba
                    ET.SubElement(material, 'diffuse').text = rgba
        w, h = scenario.width, scenario.height
        box('ground', w/2, h/2, -0.05, w, h, 0.1, '0.35 0.4 0.45 1')
        for geometry in world.find("model[@name='ground']").findall('link/*/geometry'):
            geometry.remove(geometry.find('box'))
            plane=ET.SubElement(geometry,'plane')
            ET.SubElement(plane,'normal').text='0 0 1'
            ET.SubElement(plane,'size').text=f'{w} {h}'
        for index, (x,y,sx,sy) in enumerate([(w/2,0,w,.15),(w/2,h,w,.15),(0,h/2,.15,h),(w,h/2,.15,h)]):
            box(f'boundary_{index}', x,y,1,sx,sy,2,'0.5 0.55 0.6 1')
        for index, obj in enumerate(scenario.objects):
            zone = obj.type in ('danger_zone','slow_zone')
            color = '0.8 0.15 0.25 1' if obj.type == 'danger_zone' else '0.7 0.6 0.15 1' if zone else '0.4 0.5 0.6 1'
            box(f'{obj.type}_{index}',obj.position[0]+.5,obj.position[1]+.5,.025 if zone else .75,
                .9,.9,.05 if zone else 1.5,color,not zone)
        for index, obj in enumerate(scenario.dynamic_objects):
            box(f'moving_proxy_{index}',obj.position[0]+.5,obj.position[1]+.5,.5,.6,.6,1,'0.95 0.5 0.1 1')
        box('goal_marker',scenario.goal[0]+.5,scenario.goal[1]+.5,.05,.8,.8,.1,'0.1 0.9 0.4 1',False)
        box('agent_marker',scenario.start[0]+.5,scenario.start[1]+.5,.25,.4,.4,.5,'0.2 0.6 1 1',False)
        if closed_loop:
            if control_mode=='PHYSICS':
                from aero_ai_studio.gazebo.robot_model import add_ground_robot
                link=add_ground_robot(world,scenario,name)
            else:link=world.find("model[@name='agent_marker']/link")
            sensor=ET.SubElement(link,'sensor',name='aero_range',type='gpu_lidar')
            ET.SubElement(sensor,'pose').text='0 0 0.45 0 0 0'
            ET.SubElement(sensor,'topic').text=f'/aero/{name}/scan'
            ET.SubElement(sensor,'update_rate').text='1000'
            ET.SubElement(sensor,'always_on').text='true'
            lidar=ET.SubElement(sensor,'lidar')
            horizontal=ET.SubElement(ET.SubElement(lidar,'scan'),'horizontal')
            for key,value in [('samples','4'),('resolution','1'),('min_angle','0'),('max_angle','4.71238898038469')]:
                ET.SubElement(horizontal,key).text=value
            rayrange=ET.SubElement(lidar,'range')
            for key,value in [('min','.01'),('max','100'),('resolution','.001')]:ET.SubElement(rayrange,key).text=value
        path = directory / 'world.sdf'
        temporary = directory / 'world.sdf.tmp'
        ET.indent(sdf)
        ET.ElementTree(sdf).write(temporary, encoding='utf-8', xml_declaration=True)
        ET.parse(temporary)
        os.replace(temporary, path)
        write_json(directory / 'metadata.json', {'world_name': name, 'scenario': scenario.to_dict(),
                    'target': 'Gazebo Harmonic / Ubuntu 24.04', 'cell_size_m': 1,
                    'coordinate_mapping': 'grid(x,y) -> world(x+0.5,y+0.5), +y follows grid rows',
                    'dynamic_semantics': 'Kinematic set_pose movement by V0.6 Environment' if closed_loop else 'Static proxies in launch-only world',
                    'training_available': closed_loop,'range_backend':'gpu_lidar' if closed_loop else None,
                    'control_mode':control_mode,'agent_entity':'simple_agent' if control_mode=='PHYSICS' else 'agent_marker',
                    'goal_entity':'goal_marker','obstacle_entities':[f'{o.type}_{i}' for i,o in enumerate(scenario.objects)],
                    'sensor_topic':f'/aero/{name}/scan','contact_topic':f'/aero/{name}/contacts' if control_mode=='PHYSICS' else None,
                    'command_topic':f'/aero/{name}/cmd_vel'})
        return path
