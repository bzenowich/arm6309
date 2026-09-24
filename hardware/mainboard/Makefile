# hardware/mainboard - the motherboard: MMU, SIMMs, boot ROM, clock, backplane.
ROOT := ../..
include $(ROOT)/mk/common.mk
RUN   = cd $(HW) && $(BUN) run
V     = verilator --binary --timing -Wall -Wno-DECLFILENAME
.PHONY: check sim sim-hand bench cupl

check: $(BUN) ## U3 (mmu) against its model, over the whole address space
	$(RUN) mainboard/logic/mmu.check.ts
sim: ## mainboard_tb - U3, U6, U9, U10, the map SRAMs, flash and SIMMs
	$(MAKE) -C $(HW) verilog
	cd $(HW) && TBS=mainboard sh tools/sim/run.sh
sim-hand: ## the hand-written mmu.v and clkdec.v with their own testbenches
	mkdir -p $(BUILD)
	cd sim && $(V) --Mdir $(BUILD)/obj_mmu --top-module mmu_tb mmu.v mmu_tb.sv -o mmu_tb && $(BUILD)/obj_mmu/mmu_tb
	cd sim && $(V) --Mdir $(BUILD)/obj_clkdec --top-module clkdec_tb clkdec.v clkdec_tb.sv -o clkdec_tb && $(BUILD)/obj_clkdec/clkdec_tb
bench: sim sim-hand ## both simulations
cupl: ## recompile the four GALs' reference JEDECs with Atmel's CUPL (needs the Wine prefix)
	cd $(HW) && for p in mmu clkdec u9 u10; do sh tools/gal/prjbureau/cupl-reference.sh mainboard/logic/$$p.pld || exit 1; done
