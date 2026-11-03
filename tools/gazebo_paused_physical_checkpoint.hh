#pragma once
// Observation-only serialization. Never creates or writes a physics component.
#include <array>
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <gz/sim/System.hh>
#include <cmath>
#include <sstream>
#include <gz/sim/Joint.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/sim/components/Model.hh>

namespace aero_diagnostic::checkpoint
{
inline std::string Escape(const std::string &s)
{ std::string r; for(char c:s) { if(c=='"'||c=='\\')r+='\\'; r+=c; } return r; }
inline void Number(std::ostream &o,double v) { if(std::isfinite(v))o<<v;else o<<"null"; }
template<class V> inline void Vector(std::ostream &o,const V &v)
{ o<<'[';Number(o,v.x());o<<',';Number(o,v.y());o<<',';Number(o,v.z());o<<']'; }
inline gz::sim::Entity One(const std::string &name,const gz::sim::EntityComponentManager &ecm)
{ const auto found=gz::sim::entitiesFromScopedName(name,ecm);return found.size()==1?*found.begin():gz::sim::kNullEntity; }
inline void Pose(std::ostream &o,gz::sim::Entity entity,const gz::sim::EntityComponentManager &ecm)
{
 if(entity==gz::sim::kNullEntity){o<<"null";return;}
 const auto p=gz::sim::worldPose(entity,ecm);
 o<<"{\"position_world_m\":["<<p.Pos().X()<<','<<p.Pos().Y()<<','<<p.Pos().Z()<<']';
 o<<",\"orientation_world_xyzw\":["<<p.Rot().X()<<','<<p.Rot().Y()<<','<<p.Rot().Z()<<','<<p.Rot().W()<<"]}";
}
inline void Joint(std::ostream &o,const char *name,const gz::sim::EntityComponentManager &ecm)
{
 const auto entity=One(std::string("simple_agent::")+name,ecm);
 gz::sim::Joint joint(entity);
 const auto force=entity==gz::sim::kNullEntity?std::nullopt:joint.TransmittedWrench(ecm);
 const auto velocity=entity==gz::sim::kNullEntity?std::nullopt:joint.Velocity(ecm);
 const bool valid=force && force->size()==1;
 o<<"{\"entity_id\":"<<entity<<",\"state\":\""<<(valid?"VALID_WRENCH":"UNAVAILABLE")
  <<"\",\"actual_velocity_available\":"<<((velocity&&velocity->size()==1)?"true":"false");
 if(velocity&&velocity->size()==1){o<<",\"actual_velocity_rad_s\":";Number(o,velocity->front());}
 if(valid){o<<",\"force_xyz_N\":";Vector(o,force->front().force());o<<",\"torque_xyz_N_m\":";Vector(o,force->front().torque());}
 o<<'}';
}
inline void Support(std::ostream &o,const char *scoped,const gz::sim::EntityComponentManager &ecm)
{
 const auto collision=One(scoped,ecm),ground=One("ground::body::collision",ecm);
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
   if(j)o<<',';o<<"{\"depth_m\":";if(j<c.depth_size())Number(o,c.depth(j));else o<<"null";
   o<<",\"normal_world\":";if(j<c.normal_size())Vector(o,c.normal(j));else o<<"null";
   o<<",\"position_world_m\":";if(j<c.position_size())Vector(o,c.position(j));else o<<"null";
   o<<",\"body_1_force_world_n\":";if(j<c.wrench_size())Vector(o,c.wrench(j).body_1_wrench().force());else o<<"null";
   o<<",\"body_2_force_world_n\":";if(j<c.wrench_size())Vector(o,c.wrench(j).body_2_wrench().force());else o<<"null";
   o<<'}';
  }
  o<<"]}";
 }
 o<<"]}";
}
inline std::string Serialize(const gz::sim::UpdateInfo &info,const gz::sim::EntityComponentManager &ecm,
 const std::string &native,uint64_t id,uint64_t phase,uint64_t world,uint64_t lastIteration,int64_t lastNs)
{
 if(!info.paused)throw std::invalid_argument("checkpoint serialization requires an actual paused PostUpdate");
 const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count();
 std::ostringstream o;o<<std::setprecision(17);
 o<<"{\"message_kind\":\"paused_physical_checkpoint\",\"schema_version\":1,\"checkpoint_id\":"<<id
  <<",\"world_entity_id\":"<<world<<",\"iteration\":"<<info.iterations<<",\"sim_time_ns\":"<<ns
  <<",\"paused\":true,\"update_phase\":\"PostUpdate/const_ECM/single_callback\",\"postupdate_count\":"<<phase
  <<",\"last_advancing_iteration\":"<<lastIteration<<",\"last_advancing_time_ns\":"<<lastNs
  <<",\"coherence_semantics\":\"atomic observation of current ECM components, not a new paused physics solve\""
  <<",\"field_sources\":{\"model_pose\":\"worldPose(model, const ECM)\",\"native\":\"Link worldPose and WorldLinear/AngularVelocity, same callback\","
    "\"wheels\":\"Joint.Velocity and body-relative native link orientation, same callback\","
    "\"support\":\"current ContactSensorData components, held engine/sensor results; producer stamp retained if present\","
    "\"wrench\":\"current Joint.TransmittedWrench components, held engine results in joint frame; producer timestamp unavailable\"}"
  <<",\"measurement_age_limitation\":\"Read phase is common; component production times are not asserted simultaneous. Paused contact/wrench are held values, never new physics samples.\""
  <<",\"model_entity_id\":"<<One("simple_agent",ecm)<<",\"model_name\":\"simple_agent\",\"model_pose\":";
 Pose(o,One("simple_agent",ecm),ecm);
 o<<",\"native\":"<<native;
 o<<",\"wrench\":{\"iteration\":"<<info.iterations<<",\"sim_time_ns\":"<<ns<<",\"paused\":true,"
   "\"read_phase_id\":"<<phase<<",\"force_frame\":\"joint\",\"torque_frame\":\"joint\",\"left\":";
 Joint(o,"left_joint",ecm);o<<",\"right\":";Joint(o,"right_joint",ecm);o<<'}';
 o<<",\"support\":{\"iteration\":"<<info.iterations<<",\"sim_time_ns\":"<<ns<<",\"paused\":true,\"read_phase_id\":"<<phase<<",\"supports\":{";
 const std::array<std::pair<const char *,const char *>,4> supports{{
  {"left_wheel","simple_agent::left_wheel::left_collision"},{"right_wheel","simple_agent::right_wheel::right_collision"},
  {"front_caster","simple_agent::front_caster::front_collision"},{"rear_caster","simple_agent::rear_caster::rear_collision"}}};
 bool first=true;for(const auto &s:supports){if(!first)o<<',';first=false;o<<'"'<<s.first<<"\":";Support(o,s.second,ecm);}
 o<<"}}}";return o.str();
}
}
