#!/bin/sh
# Compile/link only. Never execute the ELF or use ldd.
set -eu
cd /tmp/AeroAIStudio-dart-internal-trace
out=validation/dart-body-shape-lifetime-v1/work/body_shape_fixture
if test -e "$out" || test -L "$out"; then echo 'Refusing to overwrite executable' >&2; exit 1; fi
/usr/bin/g++ -std=c++17 -O2 -Wall -Wextra -Werror -fstack-protector-strong \
 -isystem validation/dart-capability-abi-v2/work/dependencies/usr/include \
 -isystem validation/dart-capability-abi-v2/work/baseline-source -isystem /usr/include/eigen3 \
 validation/dart-body-shape-lifetime-v1/fixtures/body_shape.cpp \
 /usr/lib/x86_64-linux-gnu/libdart.so.6.13.2 -Wl,-z,relro,-z,now -o "$out"
