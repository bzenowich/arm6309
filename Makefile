# arm6309 - a 6309 machine: hardware/ is the cards, software/ what runs on them.
#
# Every component has a Makefile with the same targets - `make -C hardware/audio
# help`, `make -C software/pcs help` - and writes only to its own build/.
# ⚠ The applications' 6809 source is in ../nitros9 on its arm6309 branch
# (README.md, Layout).
ROOT := .
include $(ROOT)/mk/common.mk
.PHONY: check sim machine bench sheet video all clean-all

check: ## hardware's static checks, and software's fast ones (~2 min)
	$(MAKE) -C hardware check
	$(MAKE) -C software check
sim: ## the card testbenches under Verilator (~4 min)
	$(MAKE) -C hardware sim
machine: ## the whole machine off its boot ROM (~25 min)
	$(MAKE) -C hardware machine
sheet: ## every program's demo run, as contact sheets - review them before `make video`
	$(MAKE) -C software sheet
video: ## every program's demo video, each of the run its sheet was made from
	$(MAKE) -C software video
bench: ## every software bench - hours
	$(MAKE) -C software bench
all: ## hardware's everything (over an hour), then every software bench
	$(MAKE) -C hardware all
	$(MAKE) -C software bench
clean-all: ## every build/ in the tree
	$(MAKE) -C hardware clean-all
	$(MAKE) -C software clean-all
