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
#include <map>
#include <gz/sim/components/ParentEntity.hh>

namespace aero_diagnostic {
class PhysicalMicrostateObserver;
static std::map<gz::sim::Entity, PhysicalMicrostateObserver *> observers;
class PhysicalMicrostateObserver final : public gz::sim::System,
 public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
 public gz::sim::ISystemPostUpdate, public gz::sim::ISystemUpdate {
 gz::transport::Node node;
 gz::transport::Node::Publisher publisher;
 std::ofstream output;
 std::mutex mutex;
 int queued=-1, current=-1;
 uint64_t sequence=0, pendingId=0, currentId=0, callbacks=0, applyCallback=0;
 uint64_t advancingCallbacks=0, lastAdvIteration=0, poseObservations=0, prePoseActive=0;
 int64_t lastAdvNs=0;
 bool busy=false, armed=false, armAccepted=false, traceActive=false;
 gz::sim::Entity worldEntity=gz::sim::kNullEntity;
 uint64_t observationSequence=0;
 std::vector<std::string> traces;

 std::string error;
 const std::array<std::string,5> names{{"body","left_wheel","right_wheel","front_caster","rear_caster"}};
 const std::array<std::string,5> collisions{{"body_collision","left_collision","right_collision","front_collision","rear_collision"}};
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

 void MicroSupport(std::ostream &o,const char *scoped,const gz::sim::EntityComponentManager &ecm) const
{
 const auto collision=checkpoint::One(scoped,ecm),ground=checkpoint::One("ground::body::collision",ecm);
 const auto *data=collision==gz::sim::kNullEntity?nullptr:ecm.Component<gz::sim::components::ContactSensorData>(collision);
 const int count=data?data->Data().contact_size():0;
 o<<"{\"collision_entity_id\":"<<collision<<",\"component_available\":"<<(data?"true":"false")
  <<",\"state\":\""<<(!data?"UNAVAILABLE":count?"VALID_CONTACTS":"VALID_EMPTY_CONTACT_SET")
  <<"\",\"component_producer_stamp_ns\":";
 if(data&&data->Data().has_header()&&data->Data().header().has_stamp())
 {const auto &stamp=data->Data().header().stamp();o<<(static_cast<int64_t>(stamp.sec())*1000000000LL+stamp.nsec());}
 else o<<"null";
 o<<",\"contacts\":[";
 if(data)for(int i=0;i<count;++i)
 {
  if(i)o<<',';const auto &c=data->Data().contact(i);
  const bool isGround=ground!=gz::sim::kNullEntity&&(c.collision1().id()==ground||c.collision2().id()==ground);
  o<<"{\"pair_classification\":\""<<(isGround?"SUPPORT_GROUND":"OTHER")<<"\",\"points\":[";
  const int n=std::max({c.normal_size(),c.depth_size(),c.wrench_size(),c.position_size()});
  for(int j=0;j<n;++j)
  {
   if(j)o<<',';o<<"{\"depth_m\":";if(j<c.depth_size())checkpoint::Number(o,c.depth(j));else o<<"null";
   o<<",\"normal_world\":";if(j<c.normal_size())checkpoint::Vector(o,c.normal(j));else o<<"null";
   o<<",\"position_world_m\":";if(j<c.position_size())checkpoint::Vector(o,c.position(j));else o<<"null";
   o<<",\"body_1_force_world_n\":";if(j<c.wrench_size() && c.wrench(j).has_body_1_wrench() && c.wrench(j).body_1_wrench().has_force())checkpoint::Vector(o,c.wrench(j).body_1_wrench().force());else o<<"null";
   o<<",\"body_2_force_world_n\":";if(j<c.wrench_size() && c.wrench(j).has_body_2_wrench() && c.wrench(j).body_2_wrench().has_force())checkpoint::Vector(o,c.wrench(j).body_2_wrench().force());else o<<"null";
   o<<",\"body_1_torque_reported_N_m\":";
   if(j<c.wrench_size() && c.wrench(j).has_body_1_wrench() && c.wrench(j).body_1_wrench().has_torque())checkpoint::Vector(o,c.wrench(j).body_1_wrench().torque());else o<<"null";
   o<<",\"body_2_torque_reported_N_m\":";
   if(j<c.wrench_size() && c.wrench(j).has_body_2_wrench() && c.wrench(j).body_2_wrench().has_torque())checkpoint::Vector(o,c.wrench(j).body_2_wrench().torque());else o<<"null";
   o<<'}';
  }
  o<<"]}";
 }
 o<<"]}";
}

 std::string Snapshot(const gz::sim::EntityComponentManager &ecm) const {
   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"generalized_q\":{\"left\":";
   auto l=Q("left_joint",ecm),r=Q("right_joint",ecm);
   if(l)o<<*l;else o<<"null";o<<",\"right\":";if(r)o<<*r;else o<<"null";
   o<<"},\"geometry\":{";
   for(size_t i=0;i<names.size();++i){
     if(i)o<<',';auto link=Entity(names[i],ecm),collision=Entity(names[i]+"::"+collisions[i],ecm);
     auto p=ecm.Component<gz::sim::components::WorldPose>(collision);
     o<<'"'<<names[i]<<"\":{\"collision_pose\":";
     if(p){o<<"{\"position_world_m\":";MathVector(o,p->Data().Pos());
       o<<",\"orientation_world_xyzw\":["<<p->Data().Rot().X()<<','<<p->Data().Rot().Y()<<','<<p->Data().Rot().Z()<<','<<p->Data().Rot().W()<<"]}";}
     else o<<"null";
     o<<",\"ECM_link_pose\":";checkpoint::Pose(o,link,ecm);
     o<<",\"linear_velocity_world_m_s\":";ComponentVector<gz::sim::components::WorldLinearVelocity>(o,collision,ecm);
     o<<",\"angular_velocity_world_rad_s\":";ComponentVector<gz::sim::components::WorldAngularVelocity>(o,collision,ecm);
     o<<",\"ECM_link_linear_velocity\":";ComponentVector<gz::sim::components::WorldLinearVelocity>(o,link,ecm);
     o<<",\"ECM_link_angular_velocity\":";ComponentVector<gz::sim::components::WorldAngularVelocity>(o,link,ecm);
     o<<",\"provenance\":\"Physics-populated collision WorldPose/WorldVelocity via ECM; identity collision offset verified in SDF; center equals collision frame; producer timestamp unavailable\"}";
   }
   o<<"},\"joint_wrench\":{\"left\":";checkpoint::Joint(o,"left_joint",ecm);
   o<<",\"right\":";checkpoint::Joint(o,"right_joint",ecm);o<<"},\"supports\":{";
   for(size_t i=1;i<names.size();++i){
     if(i>1)o<<',';o<<'"'<<names[i]<<"\":";
     auto scoped="simple_agent::"+names[i]+"::"+collisions[i];MicroSupport(o,scoped.c_str(),ecm);
   }
   o<<"},\"solver_internal_state\":null,\"provenance\":{"
    "\"geometry\":\"ENGINE_DERIVED_COMPONENT_READBACK; callback observes publication, not internal solve time\","
    "\"contacts\":\"ContactSensorData; held/filtered possible; contact torque retains reported frame; producer stamp retained when present\","
    "\"wrench\":\"Joint.TransmittedWrench in joint frame; producer timestamp unavailable\","
    "\"q\":\"Joint.Position readback; guard only\","
    "\"normal_relative_velocity\":\"UNAVAILABLE: no direct public contact-relative readback on this observer path\","
    "\"tangential_relative_velocity\":\"UNAVAILABLE: no direct public contact-relative readback on this observer path\","
    "\"solver\":\"SOLVER_INTERNAL_STATE_NOT_PUBLICLY_OBSERVABLE through installed Sim system interface\"}}";
   return o.str();
 }
 public: void Trace(const char *stage,const gz::sim::UpdateInfo &info,const gz::sim::EntityComponentManager &ecm) {
   if(!traceActive)return;
   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"stage\":\""<<stage<<"\",\"callback_sequence\":"<<++observationSequence
    <<",\"iteration\":"<<info.iterations<<",\"sim_time_ns\":"
    <<std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count()
    <<",\"paused\":"<<(info.paused?"true":"false")
    <<",\"clock_semantics\":\"end-of-step labels; no substep timestamps or within-stage ordering\",\"microstate\":"<<Snapshot(ecm)<<'}';
   traces.push_back(o.str());
 }
 public: ~PhysicalMicrostateObserver() override {observers.erase(worldEntity);}
 public: void Configure(const gz::sim::Entity &world,
 const std::shared_ptr<const sdf::Element> &sdf,gz::sim::EntityComponentManager &ecm,
 gz::sim::EventManager &) override {
   worldEntity=world;
   if(observers.count(world))throw std::runtime_error("duplicate microstate observer");
   observers[world]=this;
   output.open(sdf->Get<std::string>("output"),std::ios::app);
   if(!output)throw std::runtime_error("qualification raw output unavailable");
   publisher=node.Advertise<gz::msgs::StringMsg>(sdf->Get<std::string>("topic"));
   if(!node.Advertise(sdf->Get<std::string>("service"),&PhysicalMicrostateObserver::Request,this))
     throw std::runtime_error("qualification service advertisement failed");
   Resolve(ecm);
 }
 public: void PreUpdate(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
   prePoseActive=PoseCommands(ecm);poseObservations+=prePoseActive;
   Resolve(ecm);
   {std::lock_guard<std::mutex> lock(mutex);
    if(queued>=0){current=queued;currentId=pendingId;queued=-1;}}
   traceActive=current>=0 || (armed&&!info.paused);
   if(!traceActive)return;
   traces.clear();error.clear();applyCallback=callbacks+1;
   Trace("PreUpdate",info,ecm);
   if(current>=0){
     if(!info.paused){error="observation request requires paused callback";return;}
     if(!Q("right_joint",ecm)||!Q("left_joint",ecm))error="generalized coordinate readback unavailable";
     if(current==1)armed=true;
   }
 }
 public: void Update(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
   // Read-only. Default priority and SDF order place this after the Physics Update.
   if(traceActive)Trace("Update/after_Physics_Update",info,ecm);
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

   Trace("PostUpdate/const_ECM",info,ecm);
   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"schema_version\":1,\"request_id\":"<<currentId<<",\"operation_code\":"<<current
    <<",\"paused\":"<<(info.paused?"true":"false")<<",\"iteration\":"<<info.iterations
    <<",\"sim_time_ns\":"<<ns<<",\"postupdate_count\":"<<callbacks<<",\"apply_callback\":"<<applyCallback
    <<",\"advancing_callback_count\":"<<advancingCallbacks<<",\"last_advancing_iteration\":"<<lastAdvIteration
    <<",\"last_advancing_time_ns\":"<<lastAdvNs<<",\"WorldPoseCmd_active\":"<<active
    <<",\"WorldPoseCmd_active_PRE\":"<<prePoseActive<<",\"WorldPoseCmd_observations\":"<<poseObservations<<",\"error\":\""<<checkpoint::Escape(error)<<"\""
    <<",\"event\":\""<<(automatic?"advancing_observation":current==1?"armed_readback":"readback")<<"\",\"microstate\":"<<Snapshot(ecm);
   o<<",\"callback_trace\":[";for(size_t i=0;i<traces.size();++i){if(i)o<<',';o<<traces[i];}o<<"]}";
   output<<o.str()<<'\n';output.flush();
   {std::lock_guard<std::mutex> lock(mutex);if(!automatic)busy=false;}
   gz::msgs::StringMsg message;message.set_data(o.str());publisher.Publish(message);
   current=-1;traceActive=false;
 }
};
// Separate read-only Update tap loaded immediately before Physics. All PreUpdates
// finish before this Update; the primary observer has armed the common trace.
class MicrostateBeforePhysics final : public gz::sim::System,
 public gz::sim::ISystemConfigure, public gz::sim::ISystemUpdate {
 gz::sim::Entity worldEntity=gz::sim::kNullEntity;
 public: void Configure(const gz::sim::Entity &world,
 const std::shared_ptr<const sdf::Element> &,gz::sim::EntityComponentManager &,
 gz::sim::EventManager &) override {worldEntity=world;}
 public: void Update(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
   auto found=observers.find(worldEntity);
   if(found==observers.end())throw std::runtime_error("primary microstate observer unavailable");
   found->second->Trace("Update/before_Physics_Update",info,ecm);
 }
};

}
GZ_ADD_PLUGIN(aero_diagnostic::PhysicalMicrostateObserver,gz::sim::System,
 aero_diagnostic::PhysicalMicrostateObserver::ISystemConfigure,
 aero_diagnostic::PhysicalMicrostateObserver::ISystemPreUpdate,
 aero_diagnostic::PhysicalMicrostateObserver::ISystemPostUpdate,
 aero_diagnostic::PhysicalMicrostateObserver::ISystemUpdate)

GZ_ADD_PLUGIN(aero_diagnostic::MicrostateBeforePhysics,gz::sim::System,
 aero_diagnostic::MicrostateBeforePhysics::ISystemConfigure,
 aero_diagnostic::MicrostateBeforePhysics::ISystemUpdate)
