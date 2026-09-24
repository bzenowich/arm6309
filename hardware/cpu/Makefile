# hardware/cpu - the HD6309E on an STM32G431: firmware and its host checks.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check host firmware

host: ## syntax-check the firmware and build the host tests -> build/host/
	cmake -S . -B $(BUILD)/host -G Ninja >/dev/null && cmake --build $(BUILD)/host
check: host ## the host tests
	ctest --test-dir $(BUILD)/host --output-on-failure
firmware: ## the timing spike for the target (needs arm-none-eabi-gcc) -> build/arm/spike.{elf,bin,hex}
	cmake -S . -B $(BUILD)/arm -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake -G Ninja >/dev/null
	cmake --build $(BUILD)/arm
