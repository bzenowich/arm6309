# software/monster - Mayhem in Monsterland
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: sheet video gen bench

gen: ## write its data tables into the port's cmds/
	python3 bench/mkmonster.py $(CMDSDIR)
bench: ## the block-streamed world, and its mutations (~6 min); needs ../nitros9
	sh bench/run-v3mon.sh

sheet: ## record the demo run and make its contact sheet -> build/video/sheet.png - ALWAYS FIRST
	SHEET=1 sh video/run-video.sh
video: ## the video of the run the sheet was made from -> video/*.mp4 (FRESH=1 records again)
	sh video/run-video.sh
