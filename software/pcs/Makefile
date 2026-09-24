# software/pcs - Bill Budge's Pinball Construction Set, ported from the 6502.
#
# ⛔ Run `check` before `bench`: the model carries its own self-tests, and a
# broken transliteration is not worth six minutes on a 6809. The model is never
# corrected to agree with the 6809; when they differ the 6502 decides.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check gen bench tables sheet video

check: ## the Python transliteration's own self-tests
	python3 bench/pcsobj.py
gen: ## write pcsdat.asm and the shipped tables (bench/pcstbl/, if the disk images are in reference/)
	python3 bench/mkpcs.py $(CMDSDIR)
bench: check ## the scan converter, 600 frames of the simulator, and three mutations (~8 min; needs ../nitros9)
	sh bench/run-pcs.sh
tables: ## every shipped table on one contact sheet, against the model (~15 min)
	sh bench/run-pcssheet.sh

sheet: ## record the demo run and make its contact sheet -> build/video/sheet.png - ALWAYS FIRST
	SHEET=1 sh video/run-video.sh
video: ## the video of the run the sheet was made from -> video/*.mp4 (FRESH=1 records again)
	sh video/run-video.sh
