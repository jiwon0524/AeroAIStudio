// Constructor/configuration unit only: deliberately never calls World::step.
#include <dart/simulation/World.hpp>
#include "dart/external/odelcpsolver/internal_trace.h"
#include <iostream>
int main(){dart::simulation::World world("env_fixture");auto s=dart::external::ode::trace::GetStatus();std::cout<<s.enabled<<' '<<s.faults<<' '<<s.records<<' '<<world.getSimFrames()<<' '<<world.getTime()<<'\n';}
