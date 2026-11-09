#pragma once
static constexpr const char fixture_sdf[]=R"AERO(<?xml version="1.0"?>
<sdf version="1.10">
  <world name="aero_dart_minimal_v1">
    <gravity>0 0 -9.81</gravity>
    <physics name="fixed_1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>0</real_time_factor>
    </physics>
    <plugin filename="@SYSTEM@" name="gz::sim::systems::Physics"><engine><filename>@ENGINE@</filename></engine></plugin>
    <model name="falling_box">
      <pose>0 0 1 0 0 0</pose><static>false</static>
      <link name="body">
        <inertial><mass>1</mass><inertia><ixx>0.001666666666666667</ixx><iyy>0.001666666666666667</iyy><izz>0.001666666666666667</izz></inertia></inertial>
        <collision name="box"><geometry><box><size>0.1 0.1 0.1</size></box></geometry></collision>
      </link>
    </model>
  </world>
</sdf>
)AERO";
