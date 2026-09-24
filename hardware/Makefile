# hardware/ - the machine's cards, and what they share.
#
# Each card has its own Makefile (make -C audio help); this one runs what spans
# them. `check` is the old `npm run check`: every GAL and CPLD design against its
# own model, the live ones against Atmel's CUPL, the slot, the $FF map, the
# decode, the placement, and the documents' own numbers - ~60 s.
# ⛔ Its exit code is the answer: bun colours FAIL lines, so grep '^FAIL' matches
# nothing (CLAUDE.md).
ROOT := ..
include $(ROOT)/mk/common.mk

CARDS := mainboard cpu video3 audio io storage net
RUN    = cd $(HW) && $(BUN) run
.PHONY: check pld verilog sim sim-hand machine boards netlist render all clean-all \
        docs reach pins fold jedec cupl decode census place

check: $(BUN) ## every static check (was npm run check) - ~60 s
	$(RUN) tools/lib/slot.check.ts
	$(RUN) tools/lib/cards.check.ts
	$(RUN) tools/lib/decode.check.ts
	$(MAKE) place
	$(MAKE) -C mainboard check
	$(MAKE) jedec cupl
	$(MAKE) -C video3 check
	$(MAKE) -C storage check
	$(MAKE) -C audio check
	$(MAKE) fold pins reach docs

jedec: $(BUN) ## the motherboard GALs assembled, and every .pld is 7-bit ASCII
	$(RUN) tools/gal/jedec.check.ts
cupl: $(BUN) ## every live GAL against Atmel CUPL's own fuse map
	$(RUN) tools/gal/jedec/cupl.check.ts
decode: $(BUN) ## each card's address decode against the $FF map
	$(RUN) tools/lib/decode.check.ts
fold: $(BUN) ## the CUPL constant fold, on its fixture
	$(RUN) tools/gal/fold.check.ts
pins: $(BUN) ## every programmable pin has the sense of what it is wired to
	$(RUN) tools/gal/pins.check.ts
reach: $(BUN) ## every signal produced is read by something
	$(RUN) tools/gal/reach.check.ts
place: $(BUN) ## each card's IC budget and length, against its drawing
	$(RUN) tools/place/place.check.ts
docs: $(BUN) ## every utilisation figure in the prose matches the fitter
	$(RUN) tools/lib/docs.check.ts

pld: $(BUN) ## write each CPLD's .pld from its term lists (was gen:pld)
	$(RUN) tools/gal/cpld.gen.ts
verilog: $(BUN) ## generate every part's Verilog into its card's sim/
	$(RUN) tools/sim/gen.ts

sim: verilog ## the card testbenches under Verilator (was check:video) - ~4 min
	cd $(HW) && sh tools/sim/run.sh
sim-hand: ## the motherboard's two hand-written models (was check:sim)
	$(MAKE) -C mainboard sim-hand
machine: verilog ## the whole machine off its boot ROM (was check:machine) - SCENARIOS=... - ~25 min
	cd $(HW) && sh tools/sim/run-machine.sh

# tsci writes dist/<path>/ mirroring the source; each board's output is moved
# into its own card's build/board/, and dist/ is not kept.
# ⚠ tsci prints "Build completed with errors" and exits 0 when it cannot reach the
# supplier API; connectivity is unaffected (CLAUDE.md).
BOARDS := $(wildcard */board/*.circuit.tsx archive/*/board/*.circuit.tsx)
boards: $(BUN) ## render every .circuit.tsx into its card's build/board/
	@set -e; cd $(HW); for f in $(BOARDS); do \
	  d=$${f%%/board/*}; n=$$(basename $$f .circuit.tsx); echo "-- $$f"; \
	  node_modules/.bin/tsci build "$$f"; \
	  mkdir -p $$d/build; rm -rf $$d/build/board; mv dist/$$d/board/$$n $$d/build/board; \
	done; rm -rf dist
netlist: $(BUN) ## the motherboard's and the archived video card's connectivity (needs `make boards`)
	$(RUN) tools/lib/netlist.check.ts mainboard/build/board/circuit.json
	$(RUN) tools/lib/netlist.check.ts archive/video/build/board/circuit.json
render: $(BUN) ## the placement study's drawings -> tools/build/boards.html
	$(RUN) tools/place/render.ts
census: $(BUN) ## the archived video card's macrocell census
	$(RUN) archive/video/logic/census.ts

all: ## everything, in order (was build:all) - over an hour
	$(MAKE) pld boards check netlist sim-hand sim machine
	$(MAKE) -C audio bench

clean-all: clean ## remove every card's build/ as well
	for c in $(CARDS) tools archive/video; do rm -rf $$c/build; done
	rm -rf dist
