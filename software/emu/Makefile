# software/emu - the host emulator every software bench runs on.
ROOT := ../..
include $(ROOT)/mk/common.mk
CFLAGS ?= -O2 -Wall
.PHONY: emu sdl check ps2 sdtest

emu: $(BUILD)/emu ## build the batch emulator -> build/emu
# ⭐ The CPU cores are hardware/cpu/sim's since 2026-09-24; this is the machine.
CPUSIM := $(HW)/cpu/sim
$(BUILD)/emu: machine.c $(CPUSIM)/cpu6809.c $(CPUSIM)/hd6309.c $(CPUSIM)/cpu6809.h $(CPUSIM)/hd6309.h $(CPUSIM)/hd6309ops.h ps2script.h $(HW)/audio/refplayer/card.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -I$(HW)/audio/refplayer -o $@ machine.c $(CPUSIM)/cpu6809.c $(CPUSIM)/hd6309.c $(HW)/audio/refplayer/card.c

SDL_CFLAGS := -I$(ROOT)/.tools/sdl2/usr/include/SDL2 -I$(ROOT)/.tools/sdl2/usr/include/x86_64-linux-gnu -I$(HW)/audio/refplayer -I$(CPUSIM)
SDL_LDFLAGS := -L$(ROOT)/.tools/sdl2/usr/lib/x86_64-linux-gnu -lSDL2 -lm

sdl: $(BUILD)/arm6309 ## build the interactive SDL2 emulator -> build/arm6309
$(BUILD)/arm6309: sdl_app.c machine.c $(CPUSIM)/cpu6809.c $(CPUSIM)/hd6309.c $(HW)/audio/refplayer/card.c $(HW)/audio/refplayer/render.c $(ROOT)/.tools/sdl2/usr/lib/x86_64-linux-gnu/libSDL2.so
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(SDL_CFLAGS) -o $@ sdl_app.c $(CPUSIM)/cpu6809.c $(CPUSIM)/hd6309.c $(HW)/audio/refplayer/card.c $(HW)/audio/refplayer/render.c $(SDL_LDFLAGS)

check: ## the CPU cores against their reference tables (hardware/cpu's sim), and the emulator's own tests
	$(MAKE) -C $(HW)/cpu sim
sdtest: ## the SD card model
	sh test/run-sdtest.sh
ps2: ## the PS/2 input script, driven through ps2tst on a booted NitrOS-9 (~2 min; needs ../nitros9)
	sh test/run-ps2script.sh
