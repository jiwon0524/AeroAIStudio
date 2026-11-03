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
class EcmHierarchyFreshnessObserver final : public gz::sim::System,
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
 std::map<std::string,std::string> lastObservedValues;

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

 std::string PoseJSON(const gz::math::Pose3d &p) const {
   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"position_m\":";MathVector(o,p.Pos());
   o<<",\"orientation_xyzw\":["<<p.Rot().X()<<','<<p.Rot().Y()<<','<<p.Rot().Z()<<','<<p.Rot().W()<<"]}";
   return o.str();
 }
 void ComponentJSON(std::ostream &o,const std::string &key,gz::sim::Entity e,
   gz::sim::ComponentTypeId type,const std::string &value,bool present,
   const gz::sim::EntityComponentManager &ecm) {
   const auto change=present?static_cast<int>(ecm.ComponentState(e,type)):-1;
   auto old=lastObservedValues.find(key);
   o<<"{\"present\":"<<(present?"true":"false")<<",\"value\":"<<value
    <<",\"component_change_state\":"<<change<<",\"component_change_label\":\""
    <<(change==0?"NoChange":change==1?"PeriodicChange":change==2?"OneTimeChange":"UNAVAILABLE")
    <<"\",\"changed_since_previous_observation\":";
   if(old==lastObservedValues.end())o<<"null";else o<<(old->second==value?"false":"true");
   o<<",\"coordinate_frame\":\""<<(key.find(".WorldPose")!=std::string::npos?"WORLD":key.find(".ParentEntity")!=std::string::npos?"ENTITY_ID":"PARENT_ENTITY_FRAME")<<"\",\"producer_timestamp_ns\":null,\"freshness\":\"ECM_VALUE_AT_CALLBACK; change flag is not a producer timestamp\"}";
   lastObservedValues[key]=value;
 }
 void Trace(const char *stage,const gz::sim::UpdateInfo &info,const gz::sim::EntityComponentManager &ecm) {
   std::ostringstream o;o<<std::setprecision(17);
   o<<"{\"stage\":\""<<stage<<"\",\"callback_sequence\":"<<++observationSequence
    <<",\"iteration\":"<<info.iterations<<",\"sim_time_ns\":"
    <<std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count()
    <<",\"paused\":"<<(info.paused?"true":"false")
    <<",\"clock_semantics\":\"UpdateInfo end-of-step clock; PreUpdate values precede this step Physics Update\""
    <<",\"actual_generalized_q\":{\"left\":";
   auto l=Q("left_joint",ecm),r=Q("right_joint",ecm);
   if(l)o<<*l;else o<<"null";o<<",\"right\":";if(r)o<<*r;else o<<"null";
   o<<"},\"hierarchy\":{";
   const std::array<std::pair<const char*,const char*>,12> entities{{
     {"world",nullptr},{"model",""},{"body","body"},{"left_wheel","left_wheel"},{"right_wheel","right_wheel"},
     {"front_caster","front_caster"},{"rear_caster","rear_caster"},
     {"body_collision","body::body_collision"},{"left_collision","left_wheel::left_collision"},
     {"right_collision","right_wheel::right_collision"},{"front_collision","front_caster::front_collision"},
     {"rear_collision","rear_caster::rear_collision"}}};
   bool first=true;
   for(const auto &item:entities){
     if(!first)o<<',';first=false;
     auto e=item.second==nullptr?worldEntity:std::string(item.second).empty()?checkpoint::One("simple_agent",ecm):Entity(item.second,ecm);
     auto p=ecm.Component<gz::sim::components::Pose>(e);
     auto w=ecm.Component<gz::sim::components::WorldPose>(e);
     auto parent=ecm.Component<gz::sim::components::ParentEntity>(e);
     o<<'"'<<item.first<<"\":{\"entity_id\":"<<e<<",\"resolved\":"<<(e?"true":"false")
      <<",\"graph_parent_entity\":"<<(e?ecm.ParentEntity(e):0)<<",\"Pose\":";
     ComponentJSON(o,std::to_string(e)+".Pose",e,gz::sim::components::Pose::typeId,p?PoseJSON(p->Data()):"null",p!=nullptr,ecm);
     o<<",\"WorldPose\":";
     ComponentJSON(o,std::to_string(e)+".WorldPose",e,gz::sim::components::WorldPose::typeId,w?PoseJSON(w->Data()):"null",w!=nullptr,ecm);
     o<<",\"ParentEntity\":";
     ComponentJSON(o,std::to_string(e)+".ParentEntity",e,gz::sim::components::ParentEntity::typeId,parent?std::to_string(parent->Data()):"null",parent!=nullptr,ecm);
     o<<",\"reconstructed_world_pose\":";if(e)checkpoint::Pose(o,e,ecm);else o<<"null";
     o<<",\"reconstruction_provenance\":\"gz::sim::worldPose(entity,const ECM); may combine held components\"}";
   }
   o<<"},\"engine_reference\":{";
   for(size_t i=0;i<names.size();++i){
     if(i)o<<',';auto e=Entity(names[i]+"::"+collisions[i],ecm);
     auto p=ecm.Component<gz::sim::components::WorldPose>(e);
     o<<'"'<<names[i]<<"\":{\"collision_entity_id\":"<<e<<",\"pose\":"<<(p?PoseJSON(p->Data()):"null")
      <<",\"provenance\":\"ENGINE_DERIVED_COLLISION_WorldPose_VIA_ECM; identity offset checked; producer timestamp unavailable\"}";
   }
   o<<"}}";traces.push_back(o.str());
 }
 public: void Configure(const gz::sim::Entity &world,
 const std::shared_ptr<const sdf::Element> &sdf,gz::sim::EntityComponentManager &ecm,
 gz::sim::EventManager &) override {
   worldEntity=world;
   output.open(sdf->Get<std::string>("output"),std::ios::app);
   if(!output)throw std::runtime_error("qualification raw output unavailable");
   publisher=node.Advertise<gz::msgs::StringMsg>(sdf->Get<std::string>("topic"));
   if(!node.Advertise(sdf->Get<std::string>("service"),&EcmHierarchyFreshnessObserver::Request,this))
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
   if(traceActive)Trace("Update/observer_after_Physics_Update",info,ecm);
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
   o<<"},\"callback_trace\":[";for(size_t i=0;i<traces.size();++i){if(i)o<<',';o<<traces[i];}o<<"]}";output<<o.str()<<'\n';output.flush();{std::lock_guard<std::mutex> lock(mutex);if(!automatic)busy=false;}gz::msgs::StringMsg message;message.set_data(o.str());publisher.Publish(message);
   current=-1;traceActive=false;
 }
};
}
GZ_ADD_PLUGIN(aero_diagnostic::EcmHierarchyFreshnessObserver,gz::sim::System,
 aero_diagnostic::EcmHierarchyFreshnessObserver::ISystemConfigure,
 aero_diagnostic::EcmHierarchyFreshnessObserver::ISystemPreUpdate,
 aero_diagnostic::EcmHierarchyFreshnessObserver::ISystemPostUpdate,
 aero_diagnostic::EcmHierarchyFreshnessObserver::ISystemUpdate)
