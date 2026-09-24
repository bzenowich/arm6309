/* xroar_stubs.c - the dozen symbols XRoar's hd6309.c needs from the rest of
 * XRoar (its part framework, serialisation and debugger), as nothing.
 * ⭐ Ours, not XRoar's: none of this is on the instruction path.  If any of it
 * were, the oracle would not build, which is the failure mode wanted. */
#include "top-config.h"
#include <stdlib.h>
#include <string.h>
#include "delegate.h"
#include "part.h"
#include "debug.h"
#include "serialise.h"
#include "mc6809.h"

void *part_new(size_t psize) { void *p = calloc(1, psize); if (!p) abort(); return p; }
bool mc6809_is_a(struct part *p, const char *name) { (void)p; return strcmp(name, "MC6809") == 0; }
bool mc6809_get_flag(void *sptr, int n) { (void)sptr; (void)n; return 0; }
void mc6809_set_flag(void *sptr, int n, bool v) { (void)sptr; (void)n; (void)v; }
const struct ser_struct_data mc6809_ser_struct_data;
const struct debug_feature m6809_core_feature;
const struct debug_feature_type debug_feature_type_uint8;
const struct debug_feature_type debug_feature_type_uint16;
void ser_write_vuint32(struct ser_handle *sh, int tag, uint32_t v) { (void)sh; (void)tag; (void)v; }
uint32_t ser_read_vuint32(struct ser_handle *sh) { (void)sh; return 0; }
DELEGATE_DEF_FUNC2(void, void, bool, bool, uint16_t, uint16, )
