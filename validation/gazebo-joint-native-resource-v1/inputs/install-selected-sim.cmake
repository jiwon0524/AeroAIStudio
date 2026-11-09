# Included after all targets exist. Future component installs avoid the original
# Unspecified/all-target install, which can require unbuilt GUI/system binaries.
if(AERO_JOINT_STAGE STREQUAL "dart")
  set(_joint_libs dart dart-external-odelcpsolver dart-collision-ode dart-collision-bullet dart-utils dart-utils-urdf)
  set(_joint_components dart external-odelcpsolver collision-ode collision-bullet utils utils-urdf)
  foreach(_t IN LISTS _joint_libs)
    if(NOT TARGET ${_t})
      message(FATAL_ERROR "Required joint target absent: ${_t}")
    endif()
    install(TARGETS ${_t} LIBRARY DESTINATION lib COMPONENT aero-joint-libraries)
  endforeach()
  foreach(_c IN LISTS _joint_components)
    # Components.cmake owns the single export-file registration.
    install(FILES "${PROJECT_BINARY_DIR}/share/dart/cmake/dart_${_c}Component.cmake"
      DESTINATION share/dart/cmake COMPONENT aero-joint-cmake)
  endforeach()
  install(FILES "${PROJECT_BINARY_DIR}/cmake/dart.pc" DESTINATION lib/pkgconfig COMPONENT aero-joint-cmake)
  install(FILES "${PROJECT_BINARY_DIR}/DARTConfig.cmake"
    "${PROJECT_BINARY_DIR}/cmake/DARTConfigVersion.cmake"
    DESTINATION share/dart/cmake COMPONENT aero-joint-cmake)
  install(DIRECTORY "${PROJECT_SOURCE_DIR}/cmake/" DESTINATION share/dart/cmake
    COMPONENT aero-joint-cmake FILES_MATCHING PATTERN "Find*.cmake" PATTERN "DARTFind*.cmake")
elseif(AERO_JOINT_STAGE STREQUAL "physics" OR AERO_JOINT_STAGE STREQUAL "sim")
  if(AERO_JOINT_STAGE STREQUAL "physics")
    set(_joint_core gz-physics7)
    set(_joint_libs gz-physics7 gz-physics7-dartsim-plugin)
    set(_joint_exports gz-physics7 gz-physics7-sdf gz-physics7-mesh gz-physics7-heightmap gz-physics7-dartsim gz-physics7-dartsim-plugin)
  else()
    set(_joint_core gz-sim8)
    set(_joint_libs gz-sim8 gz-sim8-physics-system)
    set(_joint_exports gz-sim8 gz-sim8-physics-system)
  endif()
  foreach(_t IN LISTS _joint_libs)
    if(NOT TARGET ${_t})
      message(FATAL_ERROR "Required joint target absent: ${_t}")
    endif()
    install(TARGETS ${_t} LIBRARY DESTINATION lib COMPONENT aero-joint-libraries)
  endforeach()
  foreach(_t IN LISTS _joint_exports)
    install(FILES "${PROJECT_BINARY_DIR}/cmake/pkgconfig/${_t}.pc" DESTINATION lib/pkgconfig COMPONENT aero-joint-cmake)
    # Sole export registration is owned by isolated GzPackaging-sim.cmake.
    install(FILES "${PROJECT_BINARY_DIR}/cmake/${_t}-config.cmake"
      "${PROJECT_BINARY_DIR}/cmake/${_t}-config-version.cmake"
      DESTINATION lib/cmake/${_t} COMPONENT aero-joint-cmake)
  endforeach()
  if(AERO_JOINT_STAGE STREQUAL "physics")
    install(TARGETS gz-physics7-dartsim-plugin LIBRARY DESTINATION lib/gz-physics-7/engine-plugins COMPONENT aero-joint-libraries)
  else()
    install(TARGETS gz-sim8-physics-system LIBRARY DESTINATION lib/gz-sim-8/plugins COMPONENT aero-joint-libraries)
  endif()
else()
  message(FATAL_ERROR "AERO_JOINT_STAGE must be dart/physics/sim")
endif()

include("${AERO_JOINT_INPUTS}/export-targets.cmake")
