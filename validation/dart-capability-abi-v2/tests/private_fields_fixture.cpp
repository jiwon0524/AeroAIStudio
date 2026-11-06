// DART object/constraint unit fixture. No collision detection, World, or step.
#include <dart/dynamics/Skeleton.hpp>
#include <dart/dynamics/BodyNode.hpp>
#include <dart/dynamics/FreeJoint.hpp>
#include <dart/dynamics/WeldJoint.hpp>
#include <dart/dynamics/RevoluteJoint.hpp>
#include <dart/dynamics/SphereShape.hpp>
#include <dart/dynamics/ShapeNode.hpp>
#include <dart/collision/CollisionObject.hpp>
#include <dart/collision/Contact.hpp>
#include <dart/collision/fcl/FCLCollisionDetector.hpp>
#include <dart/constraint/ContactConstraint.hpp>
#include <dart/constraint/ContactSurface.hpp>
#include <dart/constraint/JointConstraint.hpp>
#include "dart/external/odelcpsolver/internal_trace.h"
#include <iostream>
#include <algorithm>
using namespace dart;
class Object final:public collision::CollisionObject {public:Object(collision::CollisionDetector* d,const dynamics::ShapeFrame* f):CollisionObject(d,f){}void updateEngineData()override{}};
int main(int argc,char** argv){if(argc!=4)return 10;bool low=std::string(argv[1])=="caster",limit=std::string(argv[1])=="limit";
 auto sk=dynamics::Skeleton::create("synthetic_agent");auto root=sk->createJointAndBodyNodePair<dynamics::FreeJoint>();root.second->setName("fixture_body");
 auto wheel=sk->createJointAndBodyNodePair<dynamics::RevoluteJoint>(root.second);wheel.first->setName("fixture_joint");wheel.second->setName("fixture_wheel");
 auto ground=dynamics::Skeleton::create("synthetic_ground");auto gb=ground->createJointAndBodyNodePair<dynamics::WeldJoint>();gb.second->setName("ground_body");
 auto sa=root.second->createShapeNodeWith<dynamics::CollisionAspect,dynamics::DynamicsAspect>(std::make_shared<dynamics::SphereShape>(.1),"fixture_collision");auto sb=gb.second->createShapeNodeWith<dynamics::CollisionAspect,dynamics::DynamicsAspect>(std::make_shared<dynamics::SphereShape>(.1),"ground_collision");
 auto cd=collision::FCLCollisionDetector::create();Object oa(cd.get(),sa),ob(cd.get(),sb);
 collision::Contact contact;contact.collisionObject1=&oa;contact.collisionObject2=&ob;contact.point=Eigen::Vector3d(.16,.02,0);contact.normal=Eigen::Vector3d::UnitZ();contact.penetrationDepth=8e-9;
 constraint::ContactSurfaceParams params;params.mPrimaryFrictionCoeff=params.mSecondaryFrictionCoeff=low?.001:1.;constraint::ContactConstraint cc(contact,.001,params);
 namespace tr=external::ode::trace;tr::Config conf;conf.enabled=std::string(argv[2])=="on";conf.first=conf.last=1;conf.run="SYNTHETIC_PRIVATE_FIELDS";conf.world="fixture";if(!tr::Configure(conf))return 11;
 double x[6]{},lo[6]{},hi[6]{},b[6]{},w[6]{};int fi[6];std::fill(fi,fi+6,-1);constraint::ConstraintInfo info;info.x=x;info.lo=lo;info.hi=hi;info.b=b;info.w=w;info.findex=fi;info.invTimeStep=1000;
 {tr::StepScope scope((void*)1,"fixture",0,0,.001);
  tr::BeginAssembly(cc.getDimension(),"fixture_contact");tr::SetRow(0,0,int(cc.getDimension()));static_cast<constraint::ConstraintBase&>(cc).getInformation(&info);double lambda[]={.01,.002,.003};static_cast<constraint::ConstraintBase&>(cc).applyImpulse(lambda);tr::EndAssembly();
  wheel.first->setActuatorType(dynamics::Joint::SERVO);wheel.first->setCommand(0,5.);wheel.first->setForceLowerLimit(0,-10);wheel.first->setForceUpperLimit(0,10);
  if(limit){wheel.first->setLimitEnforcement(true);wheel.first->setPositionLowerLimit(0,.1);}
  constraint::JointConstraint jc(wheel.first);static_cast<constraint::ConstraintBase&>(jc).update();std::fill(w,w+6,0);std::fill(fi,fi+6,-1);
  tr::BeginAssembly(jc.getDimension(),"fixture_joint");tr::SetRow(0,0,int(jc.getDimension()));static_cast<constraint::ConstraintBase&>(jc).getInformation(&info);tr::EndAssembly();
  std::cout<<cc.getDimension()<<' '<<contact.force.z()<<' '<<jc.getDimension()<<' '<<b[0]<<' '<<lo[0]<<' '<<hi[0]<<'\n';
 }
 if(conf.enabled&&!tr::FlushExclusive(argv[3]))return 12;
}
