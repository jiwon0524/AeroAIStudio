// Diagnostic-only natural-state observer. No joint, pose, velocity or force setters.
#include "gazebo_paused_physical_checkpoint.hh"
#include <gz/plugin/Register.hh>
#include <gz/sim/components/JointPosition.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/sim/components/PoseCmd.hh>
#include <gz/sim/components/LinearVelocity.hh>
#include <gz/sim/components/AngularVelocity.hh>
#include <gz/msgs/int32.pb.h>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>
#include <fstream>
#include <mutex>
#include <cstring>

namespace aero_diagnostic {
class NaturalQPhaseObserver final : public gz::sim::System,
 public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
 public gz::sim::ISystemPostUpdate {
 gz::transport::Node node;
 gz::transport::Node::Publisher publisher;
 std::ofstream output;
 std::mutex mutex;
 int queued=-1, current=-1;
 uint64_t sequence=0, pendingId=0, currentId=0, callbacks=0, applyCallback=0;
 uint64_t advancingCallbacks=0, lastAdvIteration=0, poseObservations=0, prePoseActive=0;
 int64_t lastAdvNs=0;
 bool busy=false, armed=false, armAccepted=false;
 std::string error;
 const std::array<std::string,3> names{{"body","left_wheel","right_wheel"}};
 const std::array<std::string,3> collisions{{"body_collision","left_collision","right_collision"}};
 gz::sim::Entity Entity(const std::string &name,const gz::sim::EntityComponentManager &ecm) const {
   return checkpoint::One("simple_agent::"+name,ecm);
 }
 std::optional<double> Q(const char *name,const gz::sim::EntityComponentManager &ecm) const {
   auto joint=gz::sim::Joint(Entity(name,ecm));auto q=joint.Position(ecm);
   if(!q||q->size()!=1||!std::isfinite(q->front()))return std::nullopt;
   return q->front();
 }
 bool Request(const gz::msgs::Int32 &req,gz::msgs::Boolean &reply) {
   std::lock_guard<std::mutex> lock(mutex);
   const int code=req.data();
   bool ok=!busy && queued<0 && (code==0 || (code==1&&!armAccepted));
   if(ok){busy=true;queued=code;pendingId=++sequence;if(code==1)armAccepted=true;}
   reply.set_data(ok);return true;
 }
 void Resolve(gz::sim::EntityComponentManager &ecm) {
   for(const auto &s:{"left_joint","right_joint"}) {
     auto e=Entity(s,ecm);if(e)gz::sim::Joint(e).EnablePositionCheck(ecm);
   }
   for(size_t i=0;i<names.size();++i){
     auto e=Entity(names[i]+"::"+collisions[i],ecm);if(!e)continue;
     // Readback requests only; no Pose or WorldPose state is assigned here.
     if(!ecm.Component<gz::sim::components::WorldPose>(e))
       ecm.CreateComponent(e,gz::sim::components::WorldPose());
     if(!ecm.Component<gz::sim::components::WorldLinearVelocity>(e))
       ecm.CreateComponent(e,gz::sim::components::WorldLinearVelocity());
     if(!ecm.Component<gz::sim::components::WorldAngularVelocity>(e))
       ecm.CreateComponent(e,gz::sim::components::WorldAngularVelocity());
   }
 }
 uint64_t PoseCommands(const gz::sim::EntityComponentManager &ecm) const {
   uint64_t count=0;ecm.Each<gz::sim::components::WorldPoseCmd>(
    [&](const gz::sim::Entity &,const gz::sim::components::WorldPoseCmd *){++count;return true;});return count;
 }
 void MathVector(std::ostream &o,const gz::math::Vector3d &v) const {
   o<<'['<<v.X()<<','<<v.Y()<<','<<v.Z()<<']';
 }
 template<class C> void ComponentVector(std::ostream &o,gz::sim::Entity e,
 const gz::sim::EntityComponentManager &ecm) const {
   auto v=ecm.Component<C>(e);if(v)MathVector(o,v->Data());else o<<"null";
 }
 public: void Configure(const gz::sim::Entity &,
 const std::shared_ptr<const sdf::Element> &sdf,gz::sim::EntityComponentManager &ecm,
 gz::sim::EventManager &) override {
   output.open(sdf->Get<std::string>("output"),std::ios::app);
   if(!output)throw std::runtime_error("qualification raw output unavailable");
   publisher=node.Advertise<gz::msgs::StringMsg>(sdf->Get<std::string>("topic"));
   if(!node.Advertise(sdf->Get<std::string>("service"),&NaturalQPhaseObserver::Request,this))
     throw std::runtime_error("qualification service advertisement failed");
   Resolve(ecm);
 }
 public: void PreUpdate(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
   prePoseActive=PoseCommands(ecm);poseObservations+=prePoseActive;
   Resolve(ecm);
   {std::lock_guard<std::mutex> lock(mutex);
    if(queued<0)return;current=queued;currentId=pendingId;queued=-1;}
   error.clear();applyCallback=callbacks+1;
   if(!info.paused){error="observation request requires paused callback";return;}
   if(!Q("right_joint",ecm)||!Q("left_joint",ecm))error="generalized coordinate readback unavailable";
   if(current==1)armed=true;

 }
 public: void PostUpdate(const gz::sim::UpdateInfo &info,
 const gz::sim::EntityComponentManager &ecm) override {
   ++callbacks;
   const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count();
   if(!info.paused){++advancingCallbacks;lastAdvIteration=info.iterations;lastAdvNs=ns;}
   auto active=PoseCommands(ecm);poseObservations+=active;
   bool automatic=armed&&!info.paused;
   if(current<0&&!automatic)return;
   if(automatic){armed=false;current=2;currentId=0;applyCallback=callbacks;}

   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"schema_version\":1,\"request_id\":"<<currentId<<",\"operation_code\":"<<current
    <<",\"paused\":"<<(info.paused?"true":"false")<<",\"iteration\":"<<info.iterations
    <<",\"sim_time_ns\":"<<ns<<",\"postupdate_count\":"<<callbacks<<",\"apply_callback\":"<<applyCallback
    <<",\"advancing_callback_count\":"<<advancingCallbacks<<",\"last_advancing_iteration\":"<<lastAdvIteration
    <<",\"last_advancing_time_ns\":"<<lastAdvNs<<",\"WorldPoseCmd_active\":"<<active
    <<",\"WorldPoseCmd_active_PRE\":"<<prePoseActive<<",\"WorldPoseCmd_observations\":"<<poseObservations<<",\"error\":\""<<checkpoint::Escape(error)<<"\""
    <<",\"event\":\""<<(automatic?"advancing_observation":current==1?"armed_readback":"readback")<<"\",\"generalized_q\":{\"left\":";
   auto l=Q("left_joint",ecm),r=Q("right_joint",ecm);
   if(l)o<<*l;else o<<"null";o<<",\"right\":";if(r)o<<*r;else o<<"null";
   o<<"},\"links\":{";
   for(size_t i=0;i<names.size();++i){
     if(i)o<<',';auto link=Entity(names[i],ecm),collision=Entity(names[i]+"::"+collisions[i],ecm);
     o<<'"'<<names[i]<<"\":{\"link_entity\":"<<link<<",\"collision_entity\":"<<collision<<",\"ECM_pose\":";
     checkpoint::Pose(o,link,ecm);o<<",\"engine_derived_collision_pose\":";
     auto p=ecm.Component<gz::sim::components::WorldPose>(collision);
     if(p){o<<"{\"position_world_m\":";MathVector(o,p->Data().Pos());
       o<<",\"orientation_world_xyzw\":["<<p->Data().Rot().X()<<','<<p->Data().Rot().Y()<<','<<p->Data().Rot().Z()<<','<<p->Data().Rot().W()<<"]}";}
     else o<<"null";
     o<<",\"engine_derived_linear_velocity\":";ComponentVector<gz::sim::components::WorldLinearVelocity>(o,collision,ecm);
     o<<",\"engine_derived_angular_velocity\":";ComponentVector<gz::sim::components::WorldAngularVelocity>(o,collision,ecm);
     o<<",\"ECM_linear_velocity\":";ComponentVector<gz::sim::components::WorldLinearVelocity>(o,link,ecm);
     o<<",\"ECM_angular_velocity\":";ComponentVector<gz::sim::components::WorldAngularVelocity>(o,link,ecm);o<<'}';
   }
   o<<"},\"joint_wrench\":{\"left\":";checkpoint::Joint(o,"left_joint",ecm);
   o<<",\"right\":";checkpoint::Joint(o,"right_joint",ecm);o<<"},\"supports\":{";
   const std::array<std::pair<const char*,const char*>,4> support{{
    {"left_wheel","simple_agent::left_wheel::left_collision"},{"right_wheel","simple_agent::right_wheel::right_collision"},
    {"front_caster","simple_agent::front_caster::front_collision"},{"rear_caster","simple_agent::rear_caster::rear_collision"}}};
   bool first=true;for(const auto &s:support){if(!first)o<<',';first=false;o<<'"'<<s.first<<"\":";checkpoint::Support(o,s.second,ecm);}
   o<<"}}";output<<o.str()<<'\n';output.flush();{std::lock_guard<std::mutex> lock(mutex);if(!automatic)busy=false;}gz::msgs::StringMsg message;message.set_data(o.str());publisher.Publish(message);
   current=-1;
 }
};
}
GZ_ADD_PLUGIN(aero_diagnostic::NaturalQPhaseObserver,gz::sim::System,
 aero_diagnostic::NaturalQPhaseObserver::ISystemConfigure,
 aero_diagnostic::NaturalQPhaseObserver::ISystemPreUpdate,
 aero_diagnostic::NaturalQPhaseObserver::ISystemPostUpdate)
