// AN-T diagnostic composition: accepted AN-R outer observer is unchanged.
#include "gazebo_physical_microstate_observer.cc"
#include <gz/sim/physics/Events.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/EventManager.hh>

namespace aero_diagnostic {
using ContactEvent=gz::sim::events::CollectContactSurfaceProperties;
using SurfaceParams=gz::physics::SetContactPropertiesCallbackFeature::ContactSurfaceParams<gz::sim::events::Policy>;

static std::string SurfaceJSON(const SurfaceParams &p) {
 std::ostringstream o;o<<std::setprecision(17);o<<'{';bool first=true;
 auto scalar=[&](const char *name,const auto &v){if(!first)o<<',';first=false;o<<'"'<<name<<"\":";if(v)checkpoint::Number(o,*v);else o<<"null";};
 scalar("frictionCoeff",p.frictionCoeff);scalar("secondaryFrictionCoeff",p.secondaryFrictionCoeff);
 scalar("rollingFrictionCoeff",p.rollingFrictionCoeff);scalar("secondaryRollingFrictionCoeff",p.secondaryRollingFrictionCoeff);
 scalar("torsionalFrictionCoeff",p.torsionalFrictionCoeff);scalar("slipCompliance",p.slipCompliance);
 scalar("secondarySlipCompliance",p.secondarySlipCompliance);scalar("restitutionCoeff",p.restitutionCoeff);
 scalar("errorReductionParameter",p.errorReductionParameter);scalar("maxErrorReductionVelocity",p.maxErrorReductionVelocity);
 scalar("maxErrorAllowance",p.maxErrorAllowance);scalar("constraintForceMixing",p.constraintForceMixing);
 auto vector=[&](const char *name,const auto &v){o<<",\""<<name<<"\":";if(v)checkpoint::Vector(o,*v);else o<<"null";};
 vector("firstFrictionalDirection",p.firstFrictionalDirection);vector("contactSurfaceMotionVelocity",p.contactSurfaceMotionVelocity);
 o<<'}';return o.str();
}
static void MathJSONVector(std::ostream &o,const gz::math::Vector3d &v){o<<'[';checkpoint::Number(o,v.X());o<<',';checkpoint::Number(o,v.Y());o<<',';checkpoint::Number(o,v.Z());o<<']';}
class ContactSurfaceEventObserver;
static std::map<gz::sim::Entity,ContactSurfaceEventObserver *> contactObservers;
class ContactSurfaceEventObserver final : public gz::sim::System,
 public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
 public gz::sim::ISystemUpdate, public gz::sim::ISystemPostUpdate {
 std::ofstream output;gz::common::ConnectionPtr connection;gz::sim::EventManager *manager=nullptr;
 const gz::sim::EntityComponentManager *view=nullptr;gz::sim::Entity world=0;
 bool enabled=false,window=false,paused=true,ioFailed=false;
 uint64_t sequence=0,eventSequence=0,iteration=0,mutations=0,outsideWindow=0,cycle=0,activationIteration=0,optInsCreated=0,optInsPresent=0,creationSuccesses=0,firstActivation=0;
 bool activationSeen=false;unsigned beforeMask=0,attemptMask=0,returnedMask=0,afterMask=0;
 std::map<std::string,gz::sim::Entity> supportEntities;
 int64_t ns=0;unsigned priorListeners=0;std::map<gz::sim::Entity,std::string> identities;
 std::string Header(const char *kind,const char *stage){std::ostringstream o;o<<"{\"kind\":\""<<kind<<"\",\"stage\":\""<<stage<<"\",\"callback_sequence\":"<<++sequence<<",\"iteration\":"<<iteration<<",\"sim_time_ns\":"<<ns<<",\"cycle\":"<<cycle<<",\"paused\":"<<(paused?"true":"false")<<",\"listener_enabled\":"<<(enabled?"true":"false")<<",\"listener_count\":"<<(manager?manager->ConnectionCount<ContactEvent>():0);return o.str();}
 void Write(const std::string &s){output<<s<<'\n';output.flush();if(!output)ioFailed=true;}
 void Resolve(gz::sim::EntityComponentManager &ecm){
  optInsPresent=0;beforeMask=attemptMask=returnedMask=afterMask=0;unsigned index=0;
  const std::array<std::pair<const char*,const char*>,4> names{{{"left_wheel","left_collision"},{"right_wheel","right_collision"},{"front_caster","front_collision"},{"rear_caster","rear_collision"}}};
  for(const auto &v:names){const unsigned bit=1u<<index++;auto e=checkpoint::One(std::string("simple_agent::")+v.first+"::"+v.second,ecm);if(!e)continue;identities[e]=v.first;supportEntities[v.first]=e;auto before=ecm.Component<gz::sim::components::EnableContactSurfaceCustomization>(e);if(before)beforeMask|=bit;
   // Public observation opt-in before treatment; its neutrality is NOT assumed.
   if(enabled&&!before){attemptMask|=bit;++optInsCreated;auto created=ecm.CreateComponent(e,gz::sim::components::EnableContactSurfaceCustomization(true));if(created&&created->Data()){returnedMask|=bit;++creationSuccesses;}activationIteration=iteration;}
   auto requested=ecm.Component<gz::sim::components::EnableContactSurfaceCustomization>(e);if(requested&&requested->Data()){++optInsPresent;afterMask|=bit;}
  }
  if(enabled&&optInsPresent==4&&!activationSeen){firstActivation=iteration;activationSeen=true;}
  auto ground=checkpoint::One("ground::body::collision",ecm);if(ground)identities[ground]="ground";
 }
 // Masks are observations, not inferred allocation or removal counters.
 std::string LifecycleJSON() const {
  std::ostringstream o;o<<",\"opt_in_lifecycle_schema\":2,\"identities_resolved\":"<<identities.size()
   <<",\"opt_in_creation_attempt_count\":"<<optInsCreated<<",\"opt_in_creation_returned_true_count\":"<<creationSuccesses
   <<",\"opt_in_present_after_resolve\":"<<optInsPresent<<",\"opt_in_before_mask\":"<<beforeMask
   <<",\"opt_in_attempt_mask\":"<<attemptMask<<",\"opt_in_returned_true_mask\":"<<returnedMask<<",\"opt_in_after_mask\":"<<afterMask
   <<",\"opt_in_latest_attempt_iteration\":"<<activationIteration<<",\"opt_in_first_activation_iteration\":";
  if(activationSeen)o<<firstActivation;else o<<"null";
  o<<",\"opt_in_entities\":{";bool first=true;for(const auto &v:supportEntities){if(!first)o<<',';first=false;o<<'"'<<v.first<<"\":"<<v.second;}o<<'}';return o.str();
 }
 unsigned PresenceMask(const gz::sim::EntityComponentManager &ecm) const {
  const std::array<const char*,4> names{{"left_wheel","right_wheel","front_caster","rear_caster"}};unsigned mask=0;
  for(unsigned i=0;i<names.size();++i){auto e=supportEntities.find(names[i]);if(e==supportEntities.end())continue;auto c=ecm.Component<gz::sim::components::EnableContactSurfaceCustomization>(e->second);if(c)mask|=1u<<i;}return mask;
 }
 std::string Identity(gz::sim::Entity e) const {auto i=identities.find(e);return i==identities.end()?"UNRESOLVED":i->second;}
 std::string Readback() const {
  std::ostringstream o;o<<std::setprecision(17);o<<"{\"engine_collision_pose\":{";
  const std::array<std::pair<const char*,const char*>,5> names{{{"body","body_collision"},{"left_wheel","left_collision"},{"right_wheel","right_collision"},{"front_caster","front_collision"},{"rear_caster","rear_collision"}}};
  bool first=true;for(const auto &v:names){if(!first)o<<',';first=false;o<<'"'<<v.first<<"\":";auto e=checkpoint::One(std::string("simple_agent::")+v.first+"::"+v.second,*view);auto p=view->Component<gz::sim::components::WorldPose>(e);
   if(!p)o<<"null";else {const auto &q=p->Data();o<<"{\"position_world_m\":["<<q.Pos().X()<<','<<q.Pos().Y()<<','<<q.Pos().Z()<<"],\"orientation_world_xyzw\":["<<q.Rot().X()<<','<<q.Rot().Y()<<','<<q.Rot().Z()<<','<<q.Rot().W()<<"]}";}}
  o<<"},\"supports\":{";first=true;for(size_t i=1;i<names.size();++i){if(!first)o<<',';first=false;o<<'"'<<names[i].first<<"\":";auto name=std::string("simple_agent::")+names[i].first+"::"+names[i].second;checkpoint::Support(o,name.c_str(),*view);}
  o<<"},\"joint_wrench\":{\"left\":";checkpoint::Joint(o,"left_joint",*view);o<<",\"right\":";checkpoint::Joint(o,"right_joint",*view);
  o<<"},\"provenance\":\"Public AN-R component paths; identity collision offsets; contact/wrench may be held; no producer timestamps\"}";return o.str();
 }
 void Observe(const gz::sim::Entity &c1,const gz::sim::Entity &c2,const gz::math::Vector3d &point,
 const std::optional<gz::math::Vector3d> force,const std::optional<gz::math::Vector3d> normal,
 const std::optional<double> depth,const size_t count,const SurfaceParams &params) {
  ++eventSequence;if(!window||paused)++outsideWindow;
  std::ostringstream o;o<<std::setprecision(17);o<<Header("contact_event","CollectContactSurfaceProperties")<<",\"event_sequence\":"<<eventSequence
   <<",\"inside_physics_window\":"<<(window?"true":"false")<<",\"collision1\":"<<c1<<",\"collision2\":"<<c2
   <<",\"collision1_identity\":\""<<Identity(c1)<<"\",\"collision2_identity\":\""<<Identity(c2)<<"\",\"point_world_m\":";MathJSONVector(o,point);
  o<<",\"normal_world\":";if(normal)MathJSONVector(o,*normal);else o<<"null";
  o<<",\"depth_argument_m\":";if(depth)checkpoint::Number(o,*depth);else o<<"null";
  o<<",\"force_argument\":";if(force)MathJSONVector(o,*force);else o<<"null";
  o<<",\"force_semantics\":\"PRE_SOLVE_NONPHYSICAL_FORCE_ARGUMENT\",\"num_contacts_on_collision\":"<<count<<",\"surface_properties\":"<<SurfaceJSON(params)
   <<",\"readback\":"<<(view?Readback():"null")<<",\"producer_timestamp_ns\":null,\"clock_semantics\":\"UpdateInfo end-of-step label, not substep time\"}";Write(o.str());
 }
 public: ~ContactSurfaceEventObserver() override {connection.reset();manager=nullptr;Write(Header("health","shutdown")+",\"event_count\":"+std::to_string(eventSequence)+",\"surface_mutation_count\":"+std::to_string(mutations)+",\"outside_window_count\":"+std::to_string(outsideWindow)+",\"io_failed\":"+(ioFailed?"true":"false")+"}");contactObservers.erase(world);}
 public: void Configure(const gz::sim::Entity &entity,const std::shared_ptr<const sdf::Element> &sdf,
 gz::sim::EntityComponentManager &ecm,gz::sim::EventManager &events) override {
  world=entity;manager=&events;enabled=sdf->Get<bool>("enabled");output.open(sdf->Get<std::string>("output"),std::ios::app);
  if(!output||contactObservers.count(world))throw std::runtime_error("contact observer output or singleton unavailable");
  contactObservers[world]=this;priorListeners=events.ConnectionCount<ContactEvent>();Resolve(ecm);
  if(enabled)connection=events.Connect<ContactEvent>([this](const gz::sim::Entity &a,const gz::sim::Entity &b,const gz::math::Vector3d &p,
    const std::optional<gz::math::Vector3d> f,const std::optional<gz::math::Vector3d> n,const std::optional<double> d,const size_t count,const SurfaceParams &params){
    const auto before=SurfaceJSON(params);Observe(a,b,p,f,n,d,count,params);
    if(before!=SurfaceJSON(params))++mutations;
  });
  Write(Header("health","configure")+",\"prior_listener_count\":"+std::to_string(priorListeners)+LifecycleJSON()+"}");
 }
 public: void PreUpdate(const gz::sim::UpdateInfo &info,gz::sim::EntityComponentManager &ecm) override {
  ++cycle;view=&ecm;iteration=info.iterations;ns=std::chrono::duration_cast<std::chrono::nanoseconds>(info.simTime).count();paused=info.paused;window=false;Resolve(ecm);
  Write(Header("stage","PreUpdate")+LifecycleJSON()+"}");
 }
 public: void BeforePhysics(){window=true;Write(Header("stage","Update/before_Physics_Update")+"}");}
 public: void Update(const gz::sim::UpdateInfo &,gz::sim::EntityComponentManager &ecm) override {window=false;Write(Header("stage","Update/after_Physics_Update")+",\"opt_in_present_after_physics_mask\":"+std::to_string(PresenceMask(ecm))+"}");}
 public: void PostUpdate(const gz::sim::UpdateInfo &,const gz::sim::EntityComponentManager &) override {Write(Header("stage","PostUpdate/const_ECM")+"}");}
};
class ContactEventBeforePhysics final : public gz::sim::System,public gz::sim::ISystemConfigure,public gz::sim::ISystemUpdate {
 gz::sim::Entity world=0;
 public: void Configure(const gz::sim::Entity &entity,const std::shared_ptr<const sdf::Element> &,gz::sim::EntityComponentManager &,gz::sim::EventManager &) override {world=entity;}
 public: void Update(const gz::sim::UpdateInfo &,gz::sim::EntityComponentManager &) override {auto i=contactObservers.find(world);if(i==contactObservers.end())throw std::runtime_error("contact event observer unavailable");i->second->BeforePhysics();}
};
}
GZ_ADD_PLUGIN(aero_diagnostic::ContactSurfaceEventObserver,gz::sim::System,
 aero_diagnostic::ContactSurfaceEventObserver::ISystemConfigure,aero_diagnostic::ContactSurfaceEventObserver::ISystemPreUpdate,
 aero_diagnostic::ContactSurfaceEventObserver::ISystemUpdate,aero_diagnostic::ContactSurfaceEventObserver::ISystemPostUpdate)
GZ_ADD_PLUGIN(aero_diagnostic::ContactEventBeforePhysics,gz::sim::System,
 aero_diagnostic::ContactEventBeforePhysics::ISystemConfigure,aero_diagnostic::ContactEventBeforePhysics::ISystemUpdate)
