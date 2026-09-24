# software/emu - the host emulator every software bench runs on.
ROOT := ../..
include $(ROOT)/mk/common.mk
CFLAGS ?= -O2 -Wall
.PHONY: emu check ps2 sdtest

emu: $(BUILD)/emu ## build the emulator -> build/emu
$(BUILD)/emu: machine.c cpu6809.c hd6309.c cpu6809.h hd6309.h hd6309ops.h ps2script.h $(HW)/audio/refplayer/card.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) -I$(HW)/audio/refplayer -o $@ machine.c cpu6809.c hd6309.c $(HW)/audio/refplayer/card.c
check: ## the CPU cores against their reference tables, and the emulator's own tests
	$(MAKE) -C $(HW)/audio host   # its replay leg is diffed against the audio card's reference player
	sh test/run.sh
sdtest: ## the SD card model
	sh test/run-sdtest.sh
ps2: ## the PS/2 input script, driven through ps2tst on a booted NitrOS-9 (~2 min; needs ../nitros9)
	sh test/run-ps2script.sh
