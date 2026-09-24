# software/paint - Paint, the BBS and the ANSI-art viewer.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: gen sheet video

gen: ## the recorded CoArm streams -> build/
	mkdir -p $(BUILD)
	python3 tools/v3show.py $(BUILD)

VIEWERS := $(or $(WHICH),v3bbs v3art v3paint)
sheet: ## record each viewer's run and make its contact sheet -> build/video/<which>/sheet.png - ALWAYS FIRST (WHICH=v3bbs|v3art|v3paint for one)
	for w in $(VIEWERS); do SHEET=1 WHICH=$$w sh video/run-video.sh || exit 1; done
video: ## the videos of the runs the sheets were made from -> video/<which>.mp4 (FRESH=1 records again)
	for w in $(VIEWERS); do WHICH=$$w sh video/run-video.sh || exit 1; done
