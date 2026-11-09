#pragma once
#include <string>
#include <cstddef>
#include <cstdint>
namespace aero_resource {
// All failures latch independently of sdformat's bool/Errors propagation.
void Fail(const char *reason);
std::string Schema(const std::string &name);
std::string Conversion(const std::string &name);
void Outcome(const char *role, bool ok, std::size_t errors);
std::string Config();
void World(const std::string &bytes);
void Expect(const char *role, const char *path, uint64_t dev, uint64_t ino,
            const char *sha);
void BeforeLoad(const char *role, const std::string &requested,
                const std::string &selected, const std::string &klass);
void Provider(const char *role, const void *vtable);
void Loaded(const char *role, bool ok);
void CheckLoadRequest();
void NoMoreLoads();
void Ready();
}
