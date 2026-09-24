# software/stardew - the farm
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: gen bench sheet video

gen: ## write its data tables into the port's cmds/
	python3 bench/mkstardew.py $(CMDSDIR)
bench: ## the farm, and the day in the palette (~25 min); needs ../nitros9
	sh bench/run-v3star.sh

sheet: ## record the demo run and make its contact sheet -> build/video/sheet.png - ALWAYS FIRST
	SHEET=1 sh video/run-video.sh
video: ## the video of the run the sheet was made from -> video/*.mp4 (FRESH=1 records again)
	sh video/run-video.sh
