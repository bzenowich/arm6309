# software/toolbox - the ROM toolbox's drawing routines, and their ROM pages.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: pages bench

pages: ## the toolbox's ROM pages - fonts, icons, the document -> build/tbox.bin
	mkdir -p $(BUILD)
	python3 tools/mktbox.py $(BUILD)/tbox.bin
bench: ## what a text call costs, and the glyph strike pixel for pixel (~11 min; needs ../nitros9)
	sh bench/run-v3text.sh
