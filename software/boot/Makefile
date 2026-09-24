# software/boot - the boot ROM: the machine's first instructions.
#
# boot.bin is a tracked design output (the machine executes it, and the NitrOS-9
# recipe takes it as ROM page 0); its .hex and .lst are build output.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check rom v3rom bootsheet sheet video

rom: ## assemble boot.asm with A09 -> boot.bin, build/boot.{hex,lst}, and check its vectors
	sh $(ROOT)/software/tools/mkrom.sh
v3rom: ## v3machine_tb's fixture ROM -> build/v3boot.{bin,hex,lst}
	sh v3boot/mkv3rom.sh
check: rom v3rom ## both ROMs assemble, 8 KB each, vectors where their labels are
bootsheet: ## bench/run-bootsheet.sh: the same session's sheet, with the RTL machine's dialog screenshots
	sh bench/run-bootsheet.sh

sheet: ## record the demo run and make its contact sheet -> build/video/sheet.png - ALWAYS FIRST
	SHEET=1 sh video/run-video.sh
video: ## the video of the run the sheet was made from -> video/*.mp4 (FRESH=1 records again)
	sh video/run-video.sh
