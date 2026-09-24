# hardware/video3 - the machine's video card.
ROOT := ../..
include $(ROOT)/mk/common.mk
RUN   = cd $(HW) && $(BUN) run
.PHONY: check timing sim bench fit cupl

check: $(BUN) ## v3lane swept against CUPL's reference, and the register map
	$(RUN) video3/logic/v3lane.check.ts
	$(RUN) video3/logic/regmap.check.ts
timing: $(BUN) ## the cadence and budget arithmetic (was check:video3)
	$(RUN) video3/logic/timing.check.ts
sim: ## v3dot, v3card and v3machine under Verilator - ~4 min
	$(MAKE) -C $(HW) verilog
	cd $(HW) && TBS="v3dot v3card v3machine" sh tools/sim/run.sh
bench: ## the four exercisers on the host emulator, and SS.CopyN - ~2 min
	sh bench/run-v3.sh
	sh bench/run-v3copyn.sh
fit: ## fit the four CPLDs (needs the Wine prefix; one fit at a time - it takes a while)
	cd $(HW) && for p in v3dot v3scan v3ptr v3host; do sh tools/gal/prjbureau/fit1508.sh video3/logic/$$p.pld || exit 1; done
cupl: ## recompile v3lane's reference JEDEC with Atmel's CUPL
	cd $(HW) && sh tools/gal/prjbureau/cupl-reference.sh video3/logic/v3lane.pld
