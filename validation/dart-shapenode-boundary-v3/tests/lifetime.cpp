// COMPILE ONLY. No main, no target execution, no instance creation.
#include <dart/dynamics/ShapeNode.hpp>
#include <dart/dynamics/ShapeFrame.hpp>
#include <dart/dynamics/Node.hpp>
#include <dart/collision/bullet/BulletCollisionDetector.hpp>
#include <dart/collision/bullet/BulletCollisionObject.hpp>
#include <type_traits>
static_assert(std::has_virtual_destructor_v<dart::dynamics::Node>);
static_assert(std::has_virtual_destructor_v<dart::dynamics::ShapeNode>);
static_assert(std::has_virtual_destructor_v<dart::collision::CollisionObject>);
extern "C" {
void compile_delete_node(dart::dynamics::Node* p) { delete p; }
void compile_delete_shape_frame(dart::dynamics::ShapeFrame* p) { delete p; }
void compile_delete_collision_object(dart::collision::CollisionObject* p) { delete p; }
void compile_delete_group(dart::collision::CollisionGroup* p) { delete p; }
void compile_delete_detector(dart::collision::CollisionDetector* p) { delete p; }
void* compile_complete_address(dart::dynamics::Node* p) { return dynamic_cast<void*>(p); }
dart::dynamics::ShapeFrame* compile_shape_frame(dart::dynamics::ShapeNode* p) { return p; }
extern const unsigned long lifetime_sizes[] = {sizeof(dart::dynamics::ShapeNode),alignof(dart::dynamics::ShapeNode),sizeof(dart::collision::BulletCollisionObject)};
}
