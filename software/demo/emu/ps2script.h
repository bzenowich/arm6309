/* ps2script.h -- a timed, semantic input script for the emulator's PS/2
 * keyboard and mouse.  machine.c includes it once, inside its PS/2 section;
 * it needs `m`, `rampage()` and `ps2_send()`, and nothing else.
 *
 *   PS2_SCRIPT=file        the script (below)
 *   PS2_SCRIPT_AT=secs     the script's time zero, in seconds of machine time
 *   PS2_SCRIPT_GATE=str    ...measured from when the serial port has
 *                          transmitted str, rather than from reset
 *   OUTDIR/ps2.txt         the log, in the shape of marks.txt
 *
 * ⚠ IT DOES NOT BYPASS THE LINE-LEVEL MODEL.  Everything here does is hand
 * ps2_send() the bytes a real keyboard or mouse would have sent; the device
 * state machine above still clocks them out at 80 us a bit, still backs off
 * when the host inhibits, and still refuses to say anything before the
 * host's F4.  So an event whose time has come but whose device is not yet
 * enabled, or whose previous bytes are still on the wire, is HELD - and the
 * log records when it actually went, not when the script asked.
 *
 * ------------------------------------------------------------------ format
 *
 * One event a line.  `#` or `;` starts a comment; blank lines are ignored.
 * A line is an optional TIME, then an ACTION:
 *
 *     at 2.500     move to 320 240      absolute: 2.5 s after time zero
 *     +0.050       click left           0.05 s after the PREVIOUS line
 *                  key tap enter        no time at all: same as +0
 *
 * ⚠ A relative time is relative to the previous line's NOMINAL time, not to
 * when the previous line was delivered.  The schedule is fixed when the
 * script is parsed; delivery can only ever be later.
 *
 * Actions:
 *
 *     move to X Y              the pointer ends up at X,Y
 *     move by DX DY            ...DX,DY from wherever it is
 *     down|up left|right|middle
 *     click left|right|middle          down, `gap`, up
 *     key press NAME[+NAME...]         make codes, in order
 *     key release NAME[+NAME...]       break codes, in REVERSE order
 *     key tap NAME[+NAME...]           press, `hold`, release
 *     type "some text"                 \n \t \\ \" understood
 *
 * Settings, which take effect from where they appear and carry no time:
 *
 *     origin X Y      where the pointer already is; emits nothing (default 0 0)
 *     rate MS         between the packets one `move` splits into (default 16.667)
 *     gap MS          between a click's down and up (default 50)
 *     hold MS         between a tap's make and break, and between the
 *                     characters of `type` (default 30)
 *
 * ------------------------------------------------------------- coordinates
 *
 * ⚠ THE SCRIPT IS IN SCREEN COORDINATES: X right, **Y DOWN**, which is what
 * a test author means by "move to 320 240".  A PS/2 mouse reports Y POSITIVE
 * UPWARD (ps2.md 11.3), so the encoder negates it.  Get this backwards and
 * every vertical assertion in a bench is upside down and still self-
 * consistent, which is why it is stated here rather than inferred.
 *
 * ⚠ AND THE MOUSE IS RELATIVE.  `move to` is turned into deltas against a
 * notional pointer this file tracks.  That pointer is the SCRIPT's belief,
 * and the machine's is whatever it accumulated out of the bytes it managed
 * to read - which is the `G` line below, and is not assumed to be the same.
 *
 * ------------------------------------------------------------- the splitting
 *
 * ps2.md 11.3's packet carries a 9-bit signed delta an axis: the sign in
 * byte 0 (b4 for X, b5 for Y) and the magnitude in bytes 1-2.  So one packet
 * can move -256..+255 and no further, and a driver that truncates a bigger
 * move produces a pointer that quietly drifts from where the script said.
 *
 * ⭐ WE SPLIT.  A move is emitted as ceil(max(|dx|,|dy|) / 255) packets,
 * `rate` ms apart, each carrying at most +-255 on each axis:
 *
 *     step = the remaining delta clamped to [-255, +255]
 *
 * -255 rather than -256 on purpose: the field would hold -256, but a
 * symmetric rule is one an independent re-implementation gets right, and
 * this encoding is checked by exactly such a re-implementation
 * (emu/test/ps2check.py).  The two axes are split together - the packet
 * count is whichever axis needs more, and the other axis contributes 0 once
 * it is exhausted - so the deltas of the whole burst sum to the requested
 * move EXACTLY, with no residue and no overflow.  Bits b6/b7 of byte 0, the
 * overflow flags, are therefore always 0, and their being 0 is a claim.
 *
 * ------------------------------------------------------------------- the log
 *
 * OUTDIR/ps2.txt, one line an event, timestamp first in PICOSECONDS of
 * machine time - the same clock and the same shape as marks.txt, so a
 * checker joins input to frames by sorting the two together:
 *
 *   <ps> K <make|break> <name> <hex bytes...>
 *   <ps> M <x> <y> <buttons> <hex bytes...>     x,y = the SCRIPT's pointer
 *                                               after this packet
 *   <ps> G <x> <y> <buttons>                    ⭐ the pointer rebuilt from
 *                                               the bytes the GUEST READ
 *   <ps> E <delivered> <undelivered> <sx> <sy> <gx> <gy>    at exit
 *
 * ⚠ The timestamp is when the bytes were handed to the device, which is one
 * frame time (about 1.1 ms a byte) before the last of them reaches the card.
 *
 * ---------------------------------------- the guest's pointer is not the script's
 *
 * ⚠ IF THE DRIVER DROPS A BYTE THE TWO DIVERGE, and nothing about the script
 * side can see that.  The card holds ONE byte (ps2.md 5): a guest that is
 * late reading `MDATA` loses the byte it was told about, and a three-byte
 * packet stream that loses one byte does not lose a packet - it loses
 * ALIGNMENT, and every delta after it is read out of the wrong field.
 *
 * ⭐ So the `G` line is built from the bytes the guest ACTUALLY READ off
 * `MDATA` at $FF31 - not from what the script sent and not from what the
 * device transmitted.  The decoder arms on the host's `F4` (skipping that
 * command's own ACK), starts at the script's origin, honours ps2.md 11.3's
 * "byte 1's b3 is always 1" as its resynchronisation rule, sign-extends each
 * delta from byte 0's b4/b5, and negates Y back into screen coordinates.  A
 * bench asserts `G` == `M`; it does not assume it.
 *
 * ⚠ THERE IS DELIBERATELY NO "PEEK THE DRIVER'S POINTER VARIABLE" KNOB.
 * When a GUI exists and keeps one, reading it back belongs here - but a
 * facility nothing checks is the thing CLAUDE.md's reach census is about,
 * and `G` answers the same question today out of evidence the machine
 * produced rather than out of an address somebody guessed.
 */

#define PS2S_HZ 2097917.0               /* E cycles a second */
#define PS2S_MAXB 12                    /* the longest single event: Pause */

typedef struct {
    uint64_t t;                         /* nominal time, E cycles from the base */
    int port;                           /* 0 keyboard, 1 mouse */
    uint8_t b[PS2S_MAXB]; int n;
    const char *kind;                   /* "make", "break", "move", "button" */
    char name[24];
    int x, y, btn;                      /* the script's pointer/buttons after it */
    int done;
} ps2ev;

static ps2ev *ps2s_ev;
static int ps2s_n, ps2s_cap;
static int ps2s_head[2];                /* the first undelivered event per port */
static uint64_t ps2s_base, ps2s_at;
static int ps2s_based;
static long ps2s_delivered;
static FILE *ps2s_log;
static char ps2s_err[256];
static int ps2s_ox, ps2s_oy, ps2s_ohave;        /* where the script's pointer started */
static int ps2s_sx, ps2s_sy;                    /* ...and where the delivered events left it */
/* the guest's pointer, rebuilt from the bytes it read off MDATA */
static int ps2g_arm, ps2g_skip, ps2g_n, ps2g_x, ps2g_y, ps2g_btn;
static uint8_t ps2g_p[3];

/* ---------------------------------------------------------- scan code set 2 */
/* ps2.md 11.1: raw set 2, F0 before a break, E0 before an extended key.  The
 * table is the make code; `ext` adds the E0 (and so E0 F0 xx for the break). */
typedef struct { const char *name; uint8_t code; uint8_t ext; } ps2key;
static const ps2key ps2s_keys[] = {
    {"a",0x1C,0},{"b",0x32,0},{"c",0x21,0},{"d",0x23,0},{"e",0x24,0},{"f",0x2B,0},
    {"g",0x34,0},{"h",0x33,0},{"i",0x43,0},{"j",0x3B,0},{"k",0x42,0},{"l",0x4B,0},
    {"m",0x3A,0},{"n",0x31,0},{"o",0x44,0},{"p",0x4D,0},{"q",0x15,0},{"r",0x2D,0},
    {"s",0x1B,0},{"t",0x2C,0},{"u",0x3C,0},{"v",0x2A,0},{"w",0x1D,0},{"x",0x22,0},
    {"y",0x35,0},{"z",0x1A,0},
    {"0",0x45,0},{"1",0x16,0},{"2",0x1E,0},{"3",0x26,0},{"4",0x25,0},
    {"5",0x2E,0},{"6",0x36,0},{"7",0x3D,0},{"8",0x3E,0},{"9",0x46,0},
    {"`",0x0E,0},{"grave",0x0E,0},{"-",0x4E,0},{"minus",0x4E,0},
    {"=",0x55,0},{"equal",0x55,0},{"\\",0x5D,0},{"backslash",0x5D,0},
    {"[",0x54,0},{"lbracket",0x54,0},{"]",0x5B,0},{"rbracket",0x5B,0},
    {";",0x4C,0},{"semicolon",0x4C,0},{"'",0x52,0},{"quote",0x52,0},
    {",",0x41,0},{"comma",0x41,0},{".",0x49,0},{"period",0x49,0},
    {"/",0x4A,0},{"slash",0x4A,0},
    {"space",0x29,0},{"tab",0x0D,0},{"backspace",0x66,0},{"bksp",0x66,0},
    {"enter",0x5A,0},{"return",0x5A,0},{"esc",0x76,0},{"escape",0x76,0},
    {"capslock",0x58,0},{"numlock",0x77,0},{"scrolllock",0x7E,0},
    {"shift",0x12,0},{"lshift",0x12,0},{"rshift",0x59,0},
    {"ctrl",0x14,0},{"lctrl",0x14,0},{"rctrl",0x14,1},
    {"alt",0x11,0},{"lalt",0x11,0},{"ralt",0x11,1},
    {"lgui",0x1F,1},{"rgui",0x27,1},{"apps",0x2F,1},{"menu",0x2F,1},
    {"f1",0x05,0},{"f2",0x06,0},{"f3",0x04,0},{"f4",0x0C,0},{"f5",0x03,0},
    {"f6",0x0B,0},{"f7",0x83,0},{"f8",0x0A,0},{"f9",0x01,0},{"f10",0x09,0},
    {"f11",0x78,0},{"f12",0x07,0},
    {"insert",0x70,1},{"home",0x6C,1},{"pageup",0x7D,1},{"pgup",0x7D,1},
    {"delete",0x71,1},{"del",0x71,1},{"end",0x69,1},{"pagedown",0x7A,1},{"pgdn",0x7A,1},
    {"up",0x75,1},{"left",0x6B,1},{"down",0x72,1},{"right",0x74,1},
    {"kp0",0x70,0},{"kp1",0x69,0},{"kp2",0x72,0},{"kp3",0x7A,0},{"kp4",0x6B,0},
    {"kp5",0x73,0},{"kp6",0x74,0},{"kp7",0x6C,0},{"kp8",0x75,0},{"kp9",0x7D,0},
    {"kp.",0x71,0},{"kp+",0x79,0},{"kp-",0x7B,0},{"kp*",0x7C,0},
    {"kp/",0x4A,1},{"kpenter",0x5A,1},
    {NULL,0,0}
};

/* ps2.md 11.1: Pause is eight bytes of make and has no break at all */
static const uint8_t ps2s_pause[] = {0xE1,0x14,0x77,0xE1,0xF0,0x14,0xF0,0x77};
/* PrintScreen, the other irregular one */
static const uint8_t ps2s_psmake[] = {0xE0,0x12,0xE0,0x7C};
static const uint8_t ps2s_psbrk[]  = {0xE0,0xF0,0x7C,0xE0,0xF0,0x12};

/* the printable characters `type` can reach: the key, and whether shifted */
static int ps2s_char_key(char c, const char **name, int *shift)
{
    static char one[2];
    static const char *shifted = ")!@#$%^&*(";
    *shift = 0;
    if (c >= 'a' && c <= 'z') { one[0] = c; one[1] = 0; *name = one; return 1; }
    if (c >= 'A' && c <= 'Z') { one[0] = (char)(c - 'A' + 'a'); one[1] = 0; *name = one; *shift = 1; return 1; }
    if (c >= '0' && c <= '9') { one[0] = c; one[1] = 0; *name = one; return 1; }
    for (int i = 0; i < 10; i++)
        if (c == shifted[i]) { one[0] = (char)('0' + i); one[1] = 0; *name = one; *shift = 1; return 1; }
    switch (c) {
    case ' ':  *name = "space"; return 1;
    case '\t': *name = "tab"; return 1;
    case '\n': *name = "enter"; return 1;
    case '\r': *name = "enter"; return 1;
    case '`': case '-': case '=': case '\\': case '[': case ']':
    case ';': case '\'': case ',': case '.': case '/':
        one[0] = c; one[1] = 0; *name = one; return 1;
    case '~': *name = "`";  *shift = 1; return 1;
    case '_': *name = "-";  *shift = 1; return 1;
    case '+': *name = "=";  *shift = 1; return 1;
    case '|': *name = "\\"; *shift = 1; return 1;
    case '{': *name = "[";  *shift = 1; return 1;
    case '}': *name = "]";  *shift = 1; return 1;
    case ':': *name = ";";  *shift = 1; return 1;
    case '"': *name = "'";  *shift = 1; return 1;
    case '<': *name = ",";  *shift = 1; return 1;
    case '>': *name = ".";  *shift = 1; return 1;
    case '?': *name = "/";  *shift = 1; return 1;
    }
    return 0;
}

static const ps2key *ps2s_find(const char *name)
{
    for (const ps2key *k = ps2s_keys; k->name; k++)
        if (!strcmp(k->name, name)) return k;
    return NULL;
}

/* ------------------------------------------------------------- the schedule */
static ps2ev *ps2s_push(double t_s, int port)
{
    if (ps2s_n == ps2s_cap) {
        ps2s_cap = ps2s_cap ? ps2s_cap * 2 : 256;
        ps2s_ev = (ps2ev *)realloc(ps2s_ev, (size_t)ps2s_cap * sizeof *ps2s_ev);
    }
    ps2ev *e = &ps2s_ev[ps2s_n++];
    memset(e, 0, sizeof *e);
    e->t = (uint64_t)(t_s < 0 ? 0 : t_s * PS2S_HZ);
    e->port = port;
    return e;
}

/* ---------------------------------------------------------------- the parser */
typedef struct {
    double t;                           /* the nominal clock, in seconds */
    int x, y, btn;                      /* the notional pointer and buttons */
    double rate, gap, hold;             /* seconds */
} ps2s_state;

static int ps2s_keybytes(const char *name, int make, uint8_t *out)
{
    int n = 0;
    if (!strcmp(name, "pause")) {
        if (!make) return 0;            /* no break sequence at all */
        memcpy(out, ps2s_pause, sizeof ps2s_pause); return (int)sizeof ps2s_pause;
    }
    if (!strcmp(name, "printscreen") || !strcmp(name, "prtsc")) {
        if (make) { memcpy(out, ps2s_psmake, sizeof ps2s_psmake); return (int)sizeof ps2s_psmake; }
        memcpy(out, ps2s_psbrk, sizeof ps2s_psbrk); return (int)sizeof ps2s_psbrk;
    }
    const ps2key *k = ps2s_find(name);
    if (!k) return -1;
    if (k->ext) out[n++] = 0xE0;
    if (!make) out[n++] = 0xF0;
    out[n++] = k->code;
    return n;
}

static int ps2s_key(ps2s_state *st, const char *name, int make)
{
    uint8_t b[PS2S_MAXB];
    int n = ps2s_keybytes(name, make, b);
    if (n < 0) { snprintf(ps2s_err, sizeof ps2s_err, "unknown key \"%s\"", name); return -1; }
    if (n == 0) return 0;               /* pause's break: nothing to send */
    ps2ev *e = ps2s_push(st->t, 0);
    memcpy(e->b, b, (size_t)n); e->n = n;
    e->kind = make ? "make" : "break";
    snprintf(e->name, sizeof e->name, "%s", name);
    e->x = st->x; e->y = st->y; e->btn = st->btn;
    return 0;
}

/* a chord: "ctrl+alt+delete".  Make in order, break in reverse. */
static int ps2s_chord(ps2s_state *st, const char *spec, int make)
{
    char buf[128], *parts[8]; int np = 0;
    /* ⚠ `kp+` is a key name with a `+` in it.  A whole name always wins over
     * the chord split, or the numeric keypad's plus is unreachable. */
    { uint8_t t[PS2S_MAXB]; if (ps2s_keybytes(spec, make, t) >= 0) return ps2s_key(st, spec, make); }
    snprintf(buf, sizeof buf, "%s", spec);
    for (char *p = strtok(buf, "+"); p && np < 8; p = strtok(NULL, "+")) parts[np++] = p;
    /* "+" is itself a key name on the numeric keypad only, so a bare "+" or a
     * trailing "+" leaves an empty part: treat the whole spec as one name */
    if (np == 0) { snprintf(ps2s_err, sizeof ps2s_err, "empty key name"); return -1; }
    if (np == 1) return ps2s_key(st, parts[0], make);
    for (int i = 0; i < np; i++)
        if (ps2s_key(st, parts[make ? i : np - 1 - i], make) < 0) return -1;
    return 0;
}

/* one mouse packet.  dx/dy are already PS/2 deltas (Y positive UP). */
static void ps2s_packet(ps2s_state *st, int dx, int dy)
{
    ps2ev *e = ps2s_push(st->t, 1);
    e->b[0] = (uint8_t)(0x08 | (st->btn & 7) | (((dx >> 8) & 1) << 4) | (((dy >> 8) & 1) << 5));
    e->b[1] = (uint8_t)(dx & 0xFF);
    e->b[2] = (uint8_t)(dy & 0xFF);
    e->n = 3;
    e->kind = (dx || dy) ? "move" : "button";
    e->x = st->x; e->y = st->y; e->btn = st->btn;
}

static int ps2s_step(int v) { return v > 255 ? 255 : (v < -255 ? -255 : v); }

/* the pointer's starting place, for the guest-side reconstruction to match */
static void ps2s_mark_origin(const ps2s_state *st)
{
    if (ps2s_ohave) return;
    ps2s_ox = st->x; ps2s_oy = st->y; ps2s_ohave = 1;
}

/* move to X,Y in SCREEN coordinates, split into packets `rate` apart */
static void ps2s_move(ps2s_state *st, int tx, int ty)
{
    int dx = tx - st->x, dy = ty - st->y;
    while (dx || dy) {
        int sx = ps2s_step(dx), sy = ps2s_step(dy);
        dx -= sx; dy -= sy;
        st->x += sx; st->y += sy;
        ps2s_packet(st, sx, -sy);       /* ps2.md 11.3: Y is positive UPWARD */
        if (dx || dy) st->t += st->rate;
    }
}

static int ps2s_button(const char *w, int *mask)
{
    if (!strcmp(w, "left"))   { *mask = 1; return 0; }
    if (!strcmp(w, "right"))  { *mask = 2; return 0; }
    if (!strcmp(w, "middle")) { *mask = 4; return 0; }
    snprintf(ps2s_err, sizeof ps2s_err, "unknown button \"%s\"", w);
    return -1;
}

/* the quoted argument of `type`, with \n \t \\ \" */
static int ps2s_unquote(const char *p, char *out, size_t cap)
{
    while (*p == ' ' || *p == '\t') p++;
    if (*p != '"') { snprintf(ps2s_err, sizeof ps2s_err, "type wants a quoted string"); return -1; }
    p++;
    size_t n = 0;
    while (*p && *p != '"') {
        char c = *p++;
        if (c == '\\' && *p) {
            char e = *p++;
            c = e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e;
        }
        if (n + 1 >= cap) { snprintf(ps2s_err, sizeof ps2s_err, "type string too long"); return -1; }
        out[n++] = c;
    }
    if (*p != '"') { snprintf(ps2s_err, sizeof ps2s_err, "type string is not closed"); return -1; }
    out[n] = 0;
    return 0;
}

static int ps2s_parse(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { snprintf(ps2s_err, sizeof ps2s_err, "cannot read %s", path); return -1; }
    ps2s_state st;
    st.t = 0; st.x = 0; st.y = 0; st.btn = 0;
    st.rate = 1.0 / 60.0; st.gap = 0.050; st.hold = 0.030;
    char line[1024];
    int ln = 0, rc = 0;
    while (fgets(line, sizeof line, f)) {
        ln++;
        /* ⚠ A COMMENT INSIDE A STRING IS NOT A COMMENT.  `type "a#b;c"` is a
         * legitimate thing to want, and a two-pass strip that cut at the
         * first `#` would silently shorten it and then fail on the unclosed
         * quote.  One pass, quote-aware, escapes honoured - the same lesson
         * CLAUDE.md records for a line comment that opens a block one. */
        { int q = 0;
          for (char *s = line; *s; s++) {
            if (*s == '\\' && s[1]) { s++; continue; }
            if (*s == '"') { q = !q; continue; }
            if (!q && (*s == '#' || *s == ';')) { *s = 0; break; }
          } }
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        char *e = p + strlen(p);
        while (e > p && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ' || e[-1] == '\t')) *--e = 0;
        if (!*p) continue;

        /* the time */
        char word[64]; int nw = 0;
        if (sscanf(p, "%63s%n", word, &nw) != 1) continue;
        if (!strcmp(word, "at")) {
            double v; int n2;
            p += nw;
            if (sscanf(p, "%lf%n", &v, &n2) != 1) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: `at` wants seconds", ln); rc = -1; break; }
            st.t = v; p += n2;
        } else if (word[0] == '+') {
            double v = atof(word + 1);
            st.t += v; p += nw;
        }
        while (*p == ' ' || *p == '\t') p++;
        if (!*p) continue;              /* a time on its own: just advances the clock */

        /* the action */
        if (sscanf(p, "%63s%n", word, &nw) != 1) continue;
        p += nw;
        while (*p == ' ' || *p == '\t') p++;

        if (!strcmp(word, "origin")) {
            if (sscanf(p, "%d %d", &st.x, &st.y) != 2) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: origin wants X Y", ln); rc = -1; break; }
        } else if (!strcmp(word, "rate") || !strcmp(word, "gap") || !strcmp(word, "hold")) {
            double v;
            if (sscanf(p, "%lf", &v) != 1) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: %s wants milliseconds", ln, word); rc = -1; break; }
            if (word[0] == 'r') st.rate = v / 1000.0;
            else if (word[0] == 'g') st.gap = v / 1000.0;
            else st.hold = v / 1000.0;
        } else if (!strcmp(word, "move")) {
            char how[16]; int a, b;
            if (sscanf(p, "%15s %d %d", how, &a, &b) != 3) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: move wants `to X Y` or `by DX DY`", ln); rc = -1; break; }
            ps2s_mark_origin(&st);
            if (!strcmp(how, "to")) ps2s_move(&st, a, b);
            else if (!strcmp(how, "by")) ps2s_move(&st, st.x + a, st.y + b);
            else { snprintf(ps2s_err, sizeof ps2s_err, "line %d: move `%s`?", ln, how); rc = -1; break; }
        } else if (!strcmp(word, "down") || !strcmp(word, "up") || !strcmp(word, "click")) {
            char which[16]; int mask;
            if (sscanf(p, "%15s", which) != 1) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: %s wants a button", ln, word); rc = -1; break; }
            if (ps2s_button(which, &mask) < 0) { rc = -1; break; }
            ps2s_mark_origin(&st);
            if (!strcmp(word, "down")) { st.btn |= mask; ps2s_packet(&st, 0, 0); }
            else if (!strcmp(word, "up")) { st.btn &= ~mask; ps2s_packet(&st, 0, 0); }
            else {
                st.btn |= mask;  ps2s_packet(&st, 0, 0);
                st.t += st.gap;
                st.btn &= ~mask; ps2s_packet(&st, 0, 0);
            }
        } else if (!strcmp(word, "key")) {
            char how[16], name[128];
            if (sscanf(p, "%15s %127s", how, name) != 2) { snprintf(ps2s_err, sizeof ps2s_err, "line %d: key wants press|release|tap NAME", ln); rc = -1; break; }
            if (!strcmp(how, "press") || !strcmp(how, "down")) {
                if (ps2s_chord(&st, name, 1) < 0) { rc = -1; break; }
            } else if (!strcmp(how, "release") || !strcmp(how, "up")) {
                if (ps2s_chord(&st, name, 0) < 0) { rc = -1; break; }
            } else if (!strcmp(how, "tap")) {
                if (ps2s_chord(&st, name, 1) < 0) { rc = -1; break; }
                st.t += st.hold;
                if (ps2s_chord(&st, name, 0) < 0) { rc = -1; break; }
            } else { snprintf(ps2s_err, sizeof ps2s_err, "line %d: key `%s`?", ln, how); rc = -1; break; }
        } else if (!strcmp(word, "type")) {
            char s[512];
            if (ps2s_unquote(p, s, sizeof s) < 0) { rc = -1; break; }
            for (size_t i = 0; s[i]; i++) {
                const char *name; int shift;
                if (!ps2s_char_key(s[i], &name, &shift)) {
                    snprintf(ps2s_err, sizeof ps2s_err, "line %d: no key for '%c'", ln, s[i]); rc = -1; break;
                }
                if (shift && ps2s_key(&st, "lshift", 1) < 0) { rc = -1; break; }
                if (ps2s_key(&st, name, 1) < 0) { rc = -1; break; }
                st.t += st.hold;
                if (ps2s_key(&st, name, 0) < 0) { rc = -1; break; }
                if (shift && ps2s_key(&st, "lshift", 0) < 0) { rc = -1; break; }
                if (s[i + 1]) st.t += st.hold;
            }
            if (rc) break;
        } else {
            snprintf(ps2s_err, sizeof ps2s_err, "line %d: what is `%s`?", ln, word);
            rc = -1; break;
        }
    }
    fclose(f);
    return rc;
}

/* ------------------------------------------------------------------ the log */
static void ps2s_write(FILE *o, uint64_t ps, const ps2ev *e)
{
    if (e->port == 0) fprintf(o, "%llu K %s %s", (unsigned long long)ps, e->kind, e->name);
    else fprintf(o, "%llu M %d %d %d", (unsigned long long)ps, e->x, e->y, e->btn);
    for (int i = 0; i < e->n; i++) fprintf(o, " %02X", e->b[i]);
    fputc('\n', o);
}

/* PS2_SCRIPT_DUMP: the encoder alone, with no machine behind it */
static int ps2s_dump(void)
{
    if (ps2s_parse(getenv("PS2_SCRIPT")) < 0) { fprintf(stderr, "FAIL  PS2_SCRIPT: %s\n", ps2s_err); return 1; }
    const char *out = getenv("PS2_SCRIPT_DUMP");
    FILE *o = (!*out || !strcmp(out, "-")) ? stdout : fopen(out, "w");
    if (!o) { fprintf(stderr, "FAIL  cannot write %s\n", out); return 1; }
    fprintf(o, "# PS2_SCRIPT_DUMP of %s - NOMINAL times, no machine; see emu/ps2script.h\n", getenv("PS2_SCRIPT"));
    for (int i = 0; i < ps2s_n; i++)
        ps2s_write(o, (uint64_t)((double)ps2s_ev[i].t / PS2S_HZ * 1e12), &ps2s_ev[i]);
    fprintf(o, "0 E %d 0\n", ps2s_n);
    if (o != stdout) fclose(o);
    return 0;
}

static void ps2s_open_log(const char *outdir)
{
    char p[1024];
    snprintf(p, sizeof p, "%s/ps2.txt", outdir);
    ps2s_log = fopen(p, "w");
    if (!ps2s_log) return;
    fprintf(ps2s_log, "# ps2.txt - PS2_SCRIPT delivered.  ps, then K/M/G/E; see emu/ps2script.h\n");
    fprintf(ps2s_log, "# K <make|break> <name> <bytes>   M <x> <y> <btn> <bytes>   G <x> <y> <btn>\n");
}

static uint64_t ps2s_ps(void) { return m->dots * DOT_PS; }

/* ⭐ the guest's pointer: every byte it reads out of MDATA, decoded as
 * ps2.md 11.3's packet.  ps2_read() calls this; ps2_command() arms it. */
static void ps2s_guest_arm(void)
{
    ps2g_arm = 1; ps2g_skip = 1;        /* the F4's own ACK is not a packet byte */
    ps2g_n = 0; ps2g_btn = 0;
    ps2g_x = ps2s_ox; ps2g_y = ps2s_oy;
}

static void ps2s_guest_byte(uint8_t b)
{
    if (!ps2s_log || !ps2g_arm) return;
    if (ps2g_skip) { ps2g_skip--; return; }
    if (ps2g_n == 0 && !(b & 0x08)) return;     /* 11.3: byte 1's b3 is always 1 */
    ps2g_p[ps2g_n++] = b;
    if (ps2g_n < 3) return;
    ps2g_n = 0;
    int dx = ps2g_p[1] | ((ps2g_p[0] & 0x10) ? ~0xFF : 0);      /* sign-extended */
    int dy = ps2g_p[2] | ((ps2g_p[0] & 0x20) ? ~0xFF : 0);
    ps2g_x += dx; ps2g_y -= dy;                 /* back into screen coordinates */
    ps2g_btn = ps2g_p[0] & 7;
    fprintf(ps2s_log, "%llu G %d %d %d\n", (unsigned long long)ps2s_ps(), ps2g_x, ps2g_y, ps2g_btn);
}

/* ------------------------------------------------------------- the front end */
static void ps2s_init(const char *outdir)
{
    const char *path = getenv("PS2_SCRIPT");
    if (!path || !*path) return;
    if (ps2s_parse(path) < 0) { fprintf(stderr, "FAIL  PS2_SCRIPT: %s\n", ps2s_err); exit(1); }
    ps2s_at = (uint64_t)(atof(getenv("PS2_SCRIPT_AT") ? getenv("PS2_SCRIPT_AT") : "0") * PS2S_HZ);
    ps2s_sx = ps2g_x = ps2s_ox; ps2s_sy = ps2g_y = ps2s_oy;
    ps2s_open_log(outdir);
    fprintf(stderr, "emu: PS2_SCRIPT %s - %d events (%s)\n", path, ps2s_n,
            getenv("PS2_SCRIPT_GATE") ? "timed from the gate" : "timed from reset");
}

/* called from ps2_step, once the device for this port could accept bytes */
static void ps2s_feed(int p, ps2dev *d, uint64_t now)
{
    if (!ps2s_n) return;
    if (!ps2s_based) {
        if (!scr_gate.open) return;
        ps2s_base = now + ps2s_at; ps2s_based = 1;
    }
    if (now < ps2s_base) return;
    /* the first event for this port that has not gone: order within a port is
     * the script's order, always - a held event does not let the next one past */
    while (ps2s_head[p] < ps2s_n && (ps2s_ev[ps2s_head[p]].port != p || ps2s_ev[ps2s_head[p]].done))
        ps2s_head[p]++;
    if (ps2s_head[p] >= ps2s_n) return;
    ps2ev *e = &ps2s_ev[ps2s_head[p]];
    if (now < ps2s_base + e->t) return;
    /* ⚠ the line-level model decides, not us: a device that is not enabled,
     * or has not seen the host's F4, or still has bytes on the wire, waits */
    if (!d->enabled || !d->f4_seen) return;
    if (d->out_n + e->n > 64) return;
    for (int i = 0; i < e->n; i++) ps2_send(d, e->b[i]);
    e->done = 1; ps2s_delivered++;
    if (p == 1) { ps2s_sx = e->x; ps2s_sy = e->y; }
    if (ps2s_log) ps2s_write(ps2s_log, ps2s_ps(), e);
}

static void ps2s_finish(void)
{
    if (!ps2s_log) return;
    long left = 0;
    for (int i = 0; i < ps2s_n; i++) if (!ps2s_ev[i].done) left++;
    fprintf(ps2s_log, "%llu E %ld %ld %d %d %d %d\n", (unsigned long long)ps2s_ps(),
            ps2s_delivered, left, ps2s_sx, ps2s_sy, ps2g_x, ps2g_y);
    fclose(ps2s_log); ps2s_log = NULL;
    if (left) fprintf(stderr, "emu: ⚠ PS2_SCRIPT: %ld of %d events were never delivered\n", left, ps2s_n);
    else if (ps2s_n) fprintf(stderr, "emu: PS2_SCRIPT: all %d events delivered\n", ps2s_n);
}
