// COMPILE ONLY: no main; functions containing delete are never executed.
#include <dart/dynamics/Node.hpp>
#include <dart/dynamics/ShapeNode.hpp>
#include <dart/collision/bullet/BulletCollisionObject.hpp>
#include <dart/collision/bullet/BulletCollisionGroup.hpp>
#include <type_traits>
static_assert(std::has_virtual_destructor_v<dart::dynamics::Node>);
static_assert(std::has_virtual_destructor_v<dart::collision::CollisionObject>);
extern "C" {
extern const unsigned long sizes[] = {sizeof(dart::dynamics::ShapeNode),alignof(dart::dynamics::ShapeNode),sizeof(dart::collision::BulletCollisionObject),sizeof(dart::collision::BulletCollisionGroup)};
void compile_delete_node(dart::dynamics::Node* p) { delete p; }
void compile_delete_collision(dart::collision::CollisionObject* p) { delete p; }
}
