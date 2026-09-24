# software/nitros9 - NitrOS-9 Level 2 on this machine.
#
# The port itself is in ../nitros9 on its arm6309 branch; everything here needs
# it (NITROS9DIR=... to point elsewhere), and LWTOOLS/ToolShed in .tools/
# (make -C ../tools lwtools).
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check rom sdboot sdbench bench

rom: ## the 1 MB ROM and the bootable system card -> build/rom/{arm6309_rom.bin,system.img}
	sh mkrom.sh $(BUILD)/rom
check: ## boot to a shell on the host emulator, dir and mfree (~30 s)
	sh run-emu.sh
sdboot: ## the OS boots off the card and only off the card: three card states (~4 min)
	sh run-sdboot.sh
sdbench: ## the desktop, Paint and a demo run off the SD card (~3 min)
	sh bench/run-v3sd.sh
bench: sdboot sdbench ## both
