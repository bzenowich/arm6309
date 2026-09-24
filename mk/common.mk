# mk/common.mk - what every component Makefile shares.
#
# Include it after setting ROOT (the repository root, relative to the including
# Makefile). Conventions, the same in every directory:
#
#   make            = make help
#   make help       every target, from the `## ` comment on its rule
#   make check      the component's fast checks (seconds to a minute or two)
#   make bench      its slow benches (minutes to an hour) - never part of `check`
#   make clean      removes build/, which is where EVERYTHING it writes goes
#
# Nothing a component writes goes anywhere but its own build/, except the
# design outputs this repository tracks on purpose (fitted .jed/.fit files, the
# generated Verilog and .pld, boot.bin) - those stay beside their sources.

ROOT   := $(abspath $(ROOT))
HW     := $(ROOT)/hardware
BUILD  := $(CURDIR)/build
BUN    := $(HW)/node_modules/.bin/bun
# the NitrOS-9 port - a sibling checkout on its arm6309 branch
NITROS9DIR ?= $(abspath $(ROOT)/../nitros9)
CMDSDIR    := $(NITROS9DIR)/level2/arm6309/cmds
export NITROS9DIR

MAKEFLAGS += --no-print-directory
.DEFAULT_GOAL := help
.PHONY: help clean

help: ## list the targets
	@printf '%s\n\n' "$$(sed -n 's/^# *\(.*\)$$/\1/p;/^[^#]/q' $(firstword $(MAKEFILE_LIST)))"
	@grep -hE '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) | sort -u \
	  | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

clean: ## remove build/
	rm -rf $(BUILD)

$(BUN):
	cd $(HW) && npm ci
