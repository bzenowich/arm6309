# The HD6309E module: STM32G431CBT6 firmware.
#
# Cross-compiled, it builds the Phase 1 timing spike. On the host it cannot
# run -- the sources dereference absolute peripheral addresses -- so the host
# configuration syntax-checks them instead and unit-tests the parts that are
# pure logic.

set(CPU_SOURCES
    src/startup.c
    src/clock.c
    src/gpio.c
    src/stub_core.c
    src/spike_poll.c
    src/spike_dma.c
    src/main.c)

if(CMAKE_CROSSCOMPILING)
    # ---------------------------------------------------------- firmware --
    # The assembly variant is target-only; the host build syntax-checks the C
    # sources and cannot assemble Thumb-2.
    add_executable(spike ${CPU_SOURCES} src/spike_poll_asm.S)
    target_include_directories(spike PRIVATE include)

    target_compile_options(spike PRIVATE
        -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
        # -O2, not -Os: the bus loop is the product. Revisit only with a
        # measurement in hand -- see cpu/docs/plan.md §5.
        -O2
        -ffreestanding -fno-common
        -ffunction-sections -fdata-sections
        -g3
        ${ARM6309_WARNINGS})

    target_link_options(spike PRIVATE
        -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
        -T${CMAKE_CURRENT_SOURCE_DIR}/linker/stm32g431cb.ld
        -nostartfiles
        --specs=nosys.specs
        -Wl,--gc-sections
        -Wl,--print-memory-usage
        -Wl,-Map=${CMAKE_BINARY_DIR}/spike.map)

    set_target_properties(spike PROPERTIES SUFFIX ".elf")

    add_custom_command(TARGET spike POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:spike>
                ${CMAKE_BINARY_DIR}/spike.bin
        COMMAND ${CMAKE_OBJCOPY} -O ihex   $<TARGET_FILE:spike>
                ${CMAKE_BINARY_DIR}/spike.hex
        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:spike>
        COMMENT "Generating spike.bin / spike.hex")
else()
    # ------------------------------------------------------- host checks --
    add_executable(test_stub_core test/test_stub_core.c src/stub_core.c)
    target_include_directories(test_stub_core PRIVATE include)
    target_compile_options(test_stub_core PRIVATE ${ARM6309_WARNINGS})
    add_test(NAME stub_core COMMAND test_stub_core)

    # Syntax-check every firmware source with the host compiler. clock.c,
    # gpio.c and spike_poll.c cannot RUN here but must still compile cleanly.
    set(SYNTAX_STAMPS "")
    foreach(src ${CPU_SOURCES})
        string(REPLACE "/" "_" stamp "cpu_${src}.stamp")
        add_custom_command(
            OUTPUT ${stamp}
            COMMAND ${CMAKE_C_COMPILER} -fsyntax-only -std=c11
                    ${ARM6309_WARNINGS}
                    -I${CMAKE_CURRENT_SOURCE_DIR}/include
                    ${CMAKE_CURRENT_SOURCE_DIR}/${src}
            COMMAND ${CMAKE_COMMAND} -E touch ${stamp}
            DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/${src}
            COMMENT "Syntax-checking cpu/${src}")
        list(APPEND SYNTAX_STAMPS ${stamp})
    endforeach()
    add_custom_target(cpu_syntax ALL DEPENDS ${SYNTAX_STAMPS})
endif()
