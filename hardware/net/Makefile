# hardware/net - specified, and drawn; there is no logic or simulation yet.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: check board

check: ## nothing to check yet
	@echo "hardware/net: specified only - its board is checked by `make -C .. check`"
board: ## render every board (tsci) - see `make -C .. boards`
	$(MAKE) -C $(HW) boards
