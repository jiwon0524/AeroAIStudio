#!/bin/sh
# Compile/link only. Never run the generated executable or use ldd.
set -eu
cd /tmp/AeroAIStudio-dart-internal-trace
out=validation/dart-skeleton-lifetime-v1/work/skeleton_fixture
if test -e "$out"; then echo 'Refusing to overwrite pinned executable' >&2; exit 1; fi
/usr/bin/g++ -std=c++17 -O2 -Wall -Wextra -Werror -fstack-protector-strong \
 -Ivalidation/dart-capability-abi-v2/work/dependencies/usr/include \
 -Ivalidation/dart-capability-abi-v2/work/baseline-source -I/usr/include/eigen3 \
 validation/dart-skeleton-lifetime-v1/fixtures/skeleton.cpp \
 /usr/lib/x86_64-linux-gnu/libdart.so.6.13.2 -Wl,-z,relro,-z,now -o "$out"
