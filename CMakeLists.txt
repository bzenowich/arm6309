cmake_minimum_required(VERSION 3.20)
project(arm6309 C ASM)

# The machine, not just the CPU. Each subsystem owns its own CMakeLists:
#
#   cpu/    the HD6309E module -- STM32G431 firmware, plus its host checks
#   audio/  the Paula-class PCM card -- host reference model only
#   video/  spec only, nothing to build yet
#   io/     spec only, nothing to build yet
#
# Two configurations, and they build disjoint sets of targets:
#
#   cmake -B build-host -G Ninja
#   cmake -B build-arm  -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Subsystems live in subdirectories; their artefacts do not. Keeping every
# binary at the top of the build tree is what lets the documented commands
# stay `build-host/refplayer` and `build-arm/spike.elf`.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

set(ARM6309_WARNINGS -Wall -Wextra -Wshadow -Wundef -Wconversion)

if(CMAKE_CROSSCOMPILING)
    message(STATUS "Firmware build: cpu/ only.")
else()
    message(STATUS "Host build: syntax checks, logic tests and host tools.")
    message(STATUS "For firmware: cmake -B build-arm "
                   "-DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake")
    enable_testing()
endif()

add_subdirectory(cpu)

if(NOT CMAKE_CROSSCOMPILING)
    # Host-only by construction -- see audio/CMakeLists.txt.
    add_subdirectory(audio)
endif()
