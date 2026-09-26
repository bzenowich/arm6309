# software/tracker - ProTracker 3.62 recreation with a Haiku-like interface
#
# ⛔ Run `check` before `bench`: the model carries its own self-tests.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check gen bench video

check: ## run the Python tracker/player reference self-tests
	python3 bench/checkmod.py

gen: ## generate modtab.inc tables into CMDSDIR
	python3 bench/mkmod.py $(CMDSDIR)

bench: check ## run automated playback and UI verification benches
	sh bench/run-tracker.sh

