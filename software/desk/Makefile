# software/desk - the desktop shell, its file manager and the window move.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: bench shell files move video sheet

shell: ## the shell, clicked at with a PS2_SCRIPT (~3 min)
	sh bench/run-v3desk.sh
files: ## the file manager, its listing read off the pixels (~11 min)
	sh bench/run-v3files.sh
move: ## the window dragged, and every pixel outside it put back (~15 min)
	sh bench/run-v3move.sh
bench: shell files move ## all three (needs ../nitros9)
video: ## the video of the run the sheet was made from, if there is one (FRESH=1 records again) -> video/desk-demo.mp4
	if [ -z "$$FRESH" ] && [ -f build/video/frames.bin ] && ls build/video/sheet-*.png >/dev/null 2>&1; then \
	  echo "      encoding the run the sheets were made from (FRESH=1 records again)"; NORUN=1 sh video/run-desk.sh; \
	else sh video/run-desk.sh; fi
sheet: ## the same session as contact sheets -> build/video/sheet-*.png, in seconds - ALWAYS FIRST
	SHEET=1 sh video/run-desk.sh
