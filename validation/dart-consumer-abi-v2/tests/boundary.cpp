// COMPILE ONLY: no main, no static object construction, no World or solver calls.
#include <dart/collision/CollisionObject.hpp>
#include <dart/collision/CollisionDetector.hpp>
#include <dart/collision/CollisionGroup.hpp>
#include <dart/collision/CollisionResult.hpp>
#include <dart/collision/Contact.hpp>
#include <dart/collision/bullet/BulletCollisionDetector.hpp>
#include <dart/collision/bullet/BulletCollisionObject.hpp>
#include <dart/dynamics/ShapeFrame.hpp>
#include <dart/dynamics/ShapeNode.hpp>
#include <type_traits>
#include <cstddef>
#include <memory>
using namespace dart::collision;
using dart::dynamics::ShapeFrame;
using dart::dynamics::ShapeNode;
static_assert(std::is_base_of_v<CollisionObject,BulletCollisionObject>);
static_assert(std::is_base_of_v<CollisionGroup,BulletCollisionGroup>);
static_assert(std::is_base_of_v<CollisionDetector,BulletCollisionDetector>);
static_assert(std::has_virtual_destructor_v<CollisionObject>);
static_assert(std::has_virtual_destructor_v<CollisionGroup>);
static_assert(std::has_virtual_destructor_v<CollisionDetector>);
#define SA(T) sizeof(T),alignof(T)
extern "C" {
extern const unsigned long boundary_sizes[] = {
 SA(CollisionObject),SA(CollisionGroup),SA(CollisionDetector),SA(CollisionResult),
 SA(Contact),SA(BulletCollisionObject),SA(BulletCollisionGroup),SA(BulletCollisionDetector),
 SA(ShapeFrame),SA(ShapeNode)};
extern const unsigned long compiler_values[] = {sizeof(btScalar), EIGEN_MAX_ALIGN_BYTES, EIGEN_MAX_STATIC_ALIGN_BYTES, sizeof(std::string), sizeof(std::shared_ptr<CollisionObject>), sizeof(std::unique_ptr<CollisionObject>), __GXX_ABI_VERSION};
extern const unsigned long contact_offsets[] = {
 offsetof(Contact,point),offsetof(Contact,normal),offsetof(Contact,force),
 offsetof(Contact,collisionObject1),offsetof(Contact,collisionObject2),
 offsetof(Contact,penetrationDepth),offsetof(Contact,triID1),offsetof(Contact,triID2),offsetof(Contact,userData)};
const ShapeFrame* boundary_shape_frame(const CollisionObject* p) { return p->getShapeFrame(); }
const char* boundary_virtual_type(const CollisionDetector* p) { return p->getType().c_str(); }
BulletCollisionObject* boundary_cast(CollisionObject* p) { return dynamic_cast<BulletCollisionObject*>(p); }
CollisionObject* boundary_upcast(BulletCollisionObject* p) { return p; }
CollisionGroup* boundary_group_upcast(BulletCollisionGroup* p) { return p; }
CollisionDetector* boundary_detector_upcast(BulletCollisionDetector* p) { return p; }
ShapeFrame* boundary_node_upcast(ShapeNode* p) { return p; }
double boundary_contact_depth(const Contact* p) { return p->penetrationDepth; }
void boundary_contact_depth_set(Contact* p,double v) { p->penetrationDepth=v; }
const Contact& boundary_vector(const std::vector<Contact>* p,std::size_t i) { return (*p)[i]; }
}
std::shared_ptr<CollisionDetector> boundary_shared(std::shared_ptr<BulletCollisionDetector> p) { return p; }
