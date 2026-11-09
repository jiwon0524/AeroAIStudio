#pragma once
#include <cstddef>
namespace aero_joint {
// One shared observer DSO is linked by all three source-built components.
void Engine(const void *typedThis, const void *anchor);
void Begin(const void *detector);
void Record(const char *entry, const void *typedThis,
            const void *baseThis, const void *anchor);
bool End();
bool WaitGo(int fd, int timeoutMs);
bool Allowed();
void Revoke();
void Freeze();
bool Frozen();
}
