# The Paula-class PCM card: host-side reference model.
#
# audio/docs/modplayer.md §8 build step 0. Host-only by construction -- it
# models the sound card and runs the replayer that will be transliterated
# into 6309 assembly, so that the 6309 port has something to be diffed
# against. There is no firmware here and there never will be: the card is
# discrete logic.
#
# The A/B harness that validates this model against libopenmpt lives in
# audio/tools/modcompare/ and is deliberately outside the build -- it is a
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
# hardware/gal/verilog/modplay_tb.sv plays a module on audio_card.v and records
# what the four AD7528 pairs are given; this renders that through the analogue
# chain. ⛔ IT LINKS render.c AND NOT card.c, and the difference is the whole
# point: the digital card is the RTL's job in that simulation, and a tool that
# could reach card.c would let the model under test answer its own question.
add_executable(dacwav tools/dacwav/dacwav.c refplayer/render.c)
target_include_directories(dacwav PRIVATE refplayer)
target_compile_options(dacwav PRIVATE ${ARM6309_WARNINGS})
target_link_libraries(dacwav PRIVATE m)
