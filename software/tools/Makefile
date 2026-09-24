# software/tools - fetch and build the third-party tools, into the repository's .tools/.
#
# None of them is committed: A09 is GPL v2, LWTOOLS and ToolShed GPL v3, and
# ffmpeg is only needed for the demo video.
ROOT := ../..
include $(ROOT)/mk/common.mk
.PHONY: all a09 lwtools ffmpeg

all: a09 lwtools ## the assemblers
a09: ## A09, the boot ROM's assembler -> .tools/a09/
	sh fetch-a09.sh
lwtools: ## LWTOOLS and ToolShed, for NitrOS-9 -> .tools/bin/
	sh fetch-nitros9-tools.sh
ffmpeg: ## a static ffmpeg, for the demo video -> .tools/ffmpeg/
	sh fetch-ffmpeg.sh
