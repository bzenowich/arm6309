# software/tilescroll - Explore: a world of any size, streamed through the ring
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: sheet video gen bench

gen: ## write its data tables into the port's cmds/
	python3 bench/mktilescroll.py $(CMDSDIR)
bench: ## the ring checked byte for byte, and two mutations (~12 min); needs ../nitros9
	sh bench/run-tilescroll.sh

sheet: ## record the demo run and make its contact sheet -> build/video/sheet.png - ALWAYS FIRST
	SHEET=1 sh video/run-video.sh
video: ## the video of the run the sheet was made from -> video/*.mp4 (FRESH=1 records again)
	sh video/run-video.sh
