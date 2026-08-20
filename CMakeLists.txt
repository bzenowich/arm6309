cmake_minimum_required(VERSION 3.20)
project(arm6309 C ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(ARM6309_SOURCES
    src/startup.c
    src/clock.c
    src/gpio.c
    src/stub_core.c
    src/spike_poll.c
    src/main.c)

set(ARM6309_WARNINGS -Wall -Wextra -Wshadow -Wundef -Wconversion)

if(CMAKE_CROSSCOMPILING)
    # ---------------------------------------------------------- firmware --
    add_executable(spike ${ARM6309_SOURCES})
    target_include_directories(spike PRIVATE include)

    target_compile_options(spike PRIVATE
        -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
        # -O2, not -Os: the bus loop is the product. Revisit only with a
        # measurement in hand -- see docs/plan.md §5.
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
        -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/spike.map)

    set_target_properties(spike PROPERTIES SUFFIX ".elf")

    add_custom_command(TARGET spike POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:spike> spike.bin
        COMMAND ${CMAKE_OBJCOPY} -O ihex   $<TARGET_FILE:spike> spike.hex
        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:spike>
        COMMENT "Generating spike.bin / spike.hex")
else()
    # ------------------------------------------------------- host checks --
    # No cross toolchain needed. Catches syntax and type errors in the target
    # sources and unit-tests the parts that are pure logic.
    message(STATUS "Host build: syntax checks and logic tests only.")
    message(STATUS "For firmware: cmake -B build-arm "
                   "-DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake")

    enable_testing()

    add_executable(test_stub_core test/test_stub_core.c src/stub_core.c)
    target_include_directories(test_stub_core PRIVATE include)
    target_compile_options(test_stub_core PRIVATE ${ARM6309_WARNINGS})
    add_test(NAME stub_core COMMAND test_stub_core)

    # Syntax-check every target source with the host compiler. clock.c, gpio.c
    # and spike_poll.c cannot RUN here (they dereference absolute peripheral
    # addresses) but they must still compile cleanly.
    set(SYNTAX_STAMPS "")
    foreach(src ${ARM6309_SOURCES})
        string(REPLACE "/" "_" stamp "${src}.stamp")
        add_custom_command(
            OUTPUT ${stamp}
            COMMAND ${CMAKE_C_COMPILER} -fsyntax-only -std=c11
                    ${ARM6309_WARNINGS}
                    -I${CMAKE_CURRENT_SOURCE_DIR}/include
                    ${CMAKE_CURRENT_SOURCE_DIR}/${src}
            COMMAND ${CMAKE_COMMAND} -E touch ${stamp}
            DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/${src}
            COMMENT "Syntax-checking ${src}")
        list(APPEND SYNTAX_STAMPS ${stamp})
    endforeach()
    add_custom_target(syntax ALL DEPENDS ${SYNTAX_STAMPS})
endif()
