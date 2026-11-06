#include <dart/simulation/World.hpp>
#include <dart/constraint/BoxedLcpConstraintSolver.hpp>
#include <dart/constraint/ContactConstraint.hpp>
#include <dart/constraint/JointConstraint.hpp>
#include <dart/dynamics/Skeleton.hpp>
#include <dart/dynamics/BodyNode.hpp>
#include <dart/optimizer/ipopt/IpoptSolver.hpp>
#include <dart/optimizer/nlopt/NloptSolver.hpp>
#include <dart/collision/ode/OdeCollisionDetector.hpp>
#include <iostream>
#define OUT(T) std::cout << #T << " " << sizeof(T) << " " << alignof(T) << "\n"
int main(){OUT(dart::simulation::World);OUT(dart::constraint::BoxedLcpConstraintSolver);OUT(dart::constraint::ContactConstraint);OUT(dart::constraint::JointConstraint);OUT(dart::dynamics::Skeleton);OUT(dart::dynamics::BodyNode);OUT(dart::optimizer::IpoptSolver);OUT(dart::optimizer::NloptSolver);OUT(dart::collision::OdeCollisionDetector);}
