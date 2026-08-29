/* Host test for the Phase 1 stub state table.
 *
 * The stub only has to do one thing: make the next address genuinely depend on
 * the data byte, so the table lookup cannot be hoisted out of the critical
 * path. If entries collided or fell into a sequential pattern, the measurement
 * would flatter itself. */

#include <stdio.h>
#include <stdint.h>
#include <string.h>

extern uint32_t stub_next_addr[256];
void stub_core_init(void);

static int failures;

static void check(int cond, const char *what)
{
    if (!cond) { printf("FAIL: %s\n", what); failures++; }
}

int main(void)
{
    memset(stub_next_addr, 0, sizeof stub_next_addr);
    stub_core_init();

    /* Every entry must be a valid 16-bit address. */
    int in_range = 1;
    for (int i = 0; i < 256; i++) {
        if (stub_next_addr[i] > 0xFFFFu) { in_range = 0; }
    }
    check(in_range, "all entries fit in 16 bits");

    /* Not sequential, not constant: a degenerate table would let the branch
     * predictor and the compiler make the lookup look cheaper than it is. */
    int distinct = 0;
    for (int i = 0; i < 256; i++) {
        int seen = 0;
        for (int j = 0; j < i; j++) {
            if (stub_next_addr[j] == stub_next_addr[i]) { seen = 1; break; }
        }
        if (!seen) { distinct++; }
    }
    check(distinct > 240, "entries are near-distinct (got enough spread)");

    int sequential = 1;
    for (int i = 1; i < 256; i++) {
        if (stub_next_addr[i] != stub_next_addr[i - 1] + 1) { sequential = 0; break; }
    }
    check(!sequential, "entries are not a sequential ramp");

    /* Deterministic: Phase 6 re-runs this against the real core and the
     * comparison is only meaningful if the stub is reproducible. */
    uint32_t first_pass[256];
    memcpy(first_pass, stub_next_addr, sizeof first_pass);
    memset(stub_next_addr, 0, sizeof stub_next_addr);
    stub_core_init();
    check(memcmp(first_pass, stub_next_addr, sizeof first_pass) == 0,
          "stub_core_init is deterministic");

    if (failures == 0) {
        printf("ok: stub core table (%d distinct of 256)\n", distinct);
        return 0;
    }
    printf("%d failure(s)\n", failures);
    return 1;
}
