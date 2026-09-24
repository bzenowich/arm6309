# hardware/archive/video - the machine's video card until 2026-09-20. FROZEN.
#
# Nothing in `make -C hardware check` runs this card any more (archive/README.md).
# Its per-part model checks still run, one at a time, if you ask.
ROOT := ../../..
include $(ROOT)/mk/common.mk
RUN   = cd $(HW) && $(BUN) run
PARTS := sync scan access regfile seqph seqctl tile cadence vlen pxsel
.PHONY: check $(PARTS)

check: $(PARTS) ## every per-part model check the card had
$(PARTS): $(BUN)
	$(RUN) archive/video/logic/$@.check.ts
