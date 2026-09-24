# software/ - what runs on the machine, and the host tools that build and check it.
#
# `check` is fast and needs nothing but a C compiler, Python and A09; `bench`
# runs every program's bench and needs ../nitros9 on its arm6309 branch - it is
# hours, so run the one your change can reach (make -C desk bench, ...).
ROOT := ..
include $(ROOT)/mk/common.mk
PROGRAMS := boot nitros9 toolbox desk pcs stardew monster mvania tilescroll paint
.PHONY: check bench sheet video clean-all

check: ## the boot ROMs assemble, the emulator's CPU cores, PCS's model (~1 min)
	$(MAKE) -C boot check
	$(MAKE) -C emu check
	$(MAKE) -C pcs check
bench: ## every program's bench, one after another - hours
	$(MAKE) -C nitros9 check
	for p in nitros9 toolbox desk pcs tilescroll stardew monster mvania; do $(MAKE) -C $$p bench || exit 1; done
	$(MAKE) -C emu ps2
clean-all: clean ## remove every program's build/
	for p in $(PROGRAMS) emu tools; do rm -rf $$p/build; done
DEMOS := boot tilescroll stardew pcs monster mvania paint desk
sheet: ## every program's demo run and contact sheet - review them before `make video`
	for p in $(DEMOS); do $(MAKE) -C $$p sheet || exit 1; done
video: ## every program's video, each of the run its sheet was made from
	for p in $(DEMOS); do $(MAKE) -C $$p video || exit 1; done
