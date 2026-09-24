# hardware/storage - the SD card interface.
ROOT := ../..
include $(ROOT)/mk/common.mk
RUN   = cd $(HW) && $(BUN) run
.PHONY: check sim cupl

check: $(BUN) ## both GALs against CUPL's references, and the census
	$(RUN) storage/logic/storage.check.ts
	$(RUN) storage/logic/census.ts
sim: ## storage_tb, with a behavioural SD card in the socket (~20 s)
	$(MAKE) -C $(HW) verilog
	cd $(HW) && TBS=storage sh tools/sim/run.sh
cupl: ## recompile both reference JEDECs with Atmel's CUPL
	cd $(HW) && for p in sdbus sdeng; do sh tools/gal/prjbureau/cupl-reference.sh storage/logic/$$p.pld || exit 1; done
