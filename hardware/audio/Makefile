# hardware/audio - the Paula-class PCM card, and its host reference model.
#
# ⛔ `bench` is what to run before committing a change to this card: audio_tb
# alone passed through two audible regressions that `modplay` caught.
ROOT := ../..
include $(ROOT)/mk/common.mk
RUN   = cd $(HW) && $(BUN) run
.PHONY: check census sim oracle modplay bench fit host test

check: $(BUN) ## the superseded GALs' models, and the control store (arom)
	$(RUN) audio/logic/audio.check.ts
	$(RUN) audio/logic/arom.check.ts
census: $(BUN) ## the card's macrocell census
	$(RUN) audio/logic/audio.census.ts
sim: ## audio_tb - both CPLDs, the state file, the sample RAM, the converters (~25 s)
	$(MAKE) -C $(HW) verilog
	cd $(HW) && TBS=audio sh tools/sim/run.sh
oracle: ## this card against an independent Paula (was check:oracle)
	$(MAKE) -C $(HW) verilog
	sh sim/oracle/run-oracle.sh
modplay: host ## a module plays, A/B'd against libopenmpt (needs libopenmpt and numpy)
	$(MAKE) -C $(HW) verilog
	cd $(HW) && sh audio/sim/run-modplay.sh "$$(sh audio/sim/probes.sh)/14_fourchan.mod" 2
bench: sim oracle modplay ## all three (was check:audio:all) - ~5 min
fit: ## regenerate both .pld files and fit them (needs the Wine prefix; one fit at a time)
	$(MAKE) -C $(HW) pld
	cd $(HW) && sh tools/gal/prjbureau/fit1508.sh audio/logic/audio.pld && sh tools/gal/prjbureau/fit1508.sh audio/logic/aseq.pld
host: ## the reference player, its test and dacwav -> build/host/
	cmake -S . -B $(BUILD)/host -G Ninja >/dev/null && cmake --build $(BUILD)/host
test: host ## the reference model's tests
	ctest --test-dir $(BUILD)/host --output-on-failure
