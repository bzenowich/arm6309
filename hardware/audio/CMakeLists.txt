cmake_minimum_required(VERSION 3.20)
project(arm6309_audio C)

# A project of its own since 2026-09-23 - `make` in this directory builds it into
# build/host (and, for the firmware, build/arm). There is no top-level CMake
# project any more; the root Makefile is what visits every component.
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(ARM6309_WARNINGS -Wall -Wextra -Wshadow -Wundef -Wconversion)
if(NOT CMAKE_CROSSCOMPILING)
    enable_testing()
endif()

# The Paula-class PCM card: host-side reference model.
#
# hardware/audio/docs/modplayer.md §8 build step 0. Host-only by construction -- it
# models the sound card and runs the replayer that will be transliterated
# into 6309 assembly, so that the 6309 port has something to be diffed
# against. There is no firmware here and there never will be: the card is
# discrete logic.
#
# The A/B harness that validates this model against libopenmpt lives in
# hardware/audio/tools/modcompare/ and is deliberately outside the build -- it is a
# bench instrument, and it is Python.

set(REFPLAYER_SOURCES
    refplayer/card.c
    refplayer/mod_load.c
    refplayer/mod_replay.c
    refplayer/period_table.c
    refplayer/render.c)

add_executable(refplayer ${REFPLAYER_SOURCES} refplayer/main.c)
target_include_directories(refplayer PRIVATE refplayer)
target_compile_options(refplayer PRIVATE ${ARM6309_WARNINGS})
target_link_libraries(refplayer PRIVATE m)

add_executable(test_refplayer test/test_refplayer.c ${REFPLAYER_SOURCES})
target_include_directories(test_refplayer PRIVATE refplayer)
target_compile_options(test_refplayer PRIVATE ${ARM6309_WARNINGS})
target_link_libraries(test_refplayer PRIVATE m)
add_test(NAME refplayer COMMAND test_refplayer)

# ⭐ dacwav -- the RTL card's converter log to a WAV. NEW 2026-09-10.
#
# hardware/audio/sim/modplay_tb.sv plays a module on audio_card.v and records
# what the four AD7528 pairs are given; this renders that through the analogue
# chain. ⛔ IT LINKS render.c AND NOT card.c, and the difference is the whole
# point: the digital card is the RTL's job in that simulation, and a tool that
# could reach card.c would let the model under test answer its own question.
add_executable(dacwav tools/dacwav/dacwav.c refplayer/render.c)
target_include_directories(dacwav PRIVATE refplayer)
target_compile_options(dacwav PRIVATE ${ARM6309_WARNINGS})
target_link_libraries(dacwav PRIVATE m)
