/* software/emu/sdl_app.c -- Interactive SDL2 application for arm6309.
 *
 * Full-system interactive emulator:
 *   - Hitachi HD6309E CPU running at 2.097917 MHz (cycle-accurate)
 *   - 2 MB MMU memory paging, Tasks 0 & 1
 *   - Video3: 640x480 / 640x400 VGA (cell, tile, bitmap, 2D blitter, sprite)
 *   - Audio: 4-channel PCM sound card with analog RC and LED filters (44.1 kHz stereo)
 *   - Storage: SPI SD controller mounting system.img (read/write)
 *   - Input: PS/2 Keyboard (Set 2) and Mouse (3-byte packets) in SDL window
 *   - Terminal: Interactive serial console (UART) bidirectional with host terminal
 *   - Exact 2.098 MHz real-time clock pacing (with Turbo mode option)
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>

#include <SDL.h>

#define SDL_APP 1
volatile int sdl_frame_ready = 0;

/* Hook into audio model */
#include "../../hardware/audio/refplayer/render.h"
static render_t sdl_render;

#define AUDIO_RING_SIZE 65536
static int16_t audio_ring[AUDIO_RING_SIZE];
static volatile int audio_ring_w = 0;
static volatile int audio_ring_r = 0;

static void sdl_audio_sample_cb(int16_t l, int16_t r, void *user)
{
    (void)user;
    int next_w = (audio_ring_w + 2) % AUDIO_RING_SIZE;
    if (next_w != audio_ring_r) {
        audio_ring[audio_ring_w] = l;
        audio_ring[audio_ring_w + 1] = r;
        audio_ring_w = next_w;
    }
}

void sdl_audio_step(void);

/* Include machine implementation */
#include "machine.c"

void sdl_audio_step(void)
{
    int l, r;
    card_dac(&m->card, &l, &r);
    render_push(&sdl_render, l, r);
}

/* --------------------------------------------------- Terminal Raw Mode for Serial */
static struct termios orig_termios;
static int termios_modified = 0;

static void restore_terminal(void)
{
    if (termios_modified) {
        tcsetattr(STDIN_FILENO, TCSANOW, &orig_termios);
        termios_modified = 0;
    }
}

static void setup_terminal(void)
{
    if (isatty(STDIN_FILENO)) {
        tcgetattr(STDIN_FILENO, &orig_termios);
        struct termios raw = orig_termios;
        raw.c_lflag &= ~(ICANON | ECHO); /* Raw: deliver keystrokes immediately without echo */
        tcsetattr(STDIN_FILENO, TCSANOW, &raw);
        termios_modified = 1;
        atexit(restore_terminal);

        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    }
}

/* --------------------------------------------------- PS/2 Set 2 Keyboard Mapping */
typedef struct {
    uint8_t code;
    uint8_t ext;
} ps2_key_t;

static ps2_key_t scancode_map[SDL_NUM_SCANCODES];

static void init_scancode_map(void)
{
    memset(scancode_map, 0, sizeof(scancode_map));

    /* Letters */
    scancode_map[SDL_SCANCODE_A] = (ps2_key_t){0x1C, 0};
    scancode_map[SDL_SCANCODE_B] = (ps2_key_t){0x32, 0};
    scancode_map[SDL_SCANCODE_C] = (ps2_key_t){0x21, 0};
    scancode_map[SDL_SCANCODE_D] = (ps2_key_t){0x23, 0};
    scancode_map[SDL_SCANCODE_E] = (ps2_key_t){0x24, 0};
    scancode_map[SDL_SCANCODE_F] = (ps2_key_t){0x2B, 0};
    scancode_map[SDL_SCANCODE_G] = (ps2_key_t){0x34, 0};
    scancode_map[SDL_SCANCODE_H] = (ps2_key_t){0x33, 0};
    scancode_map[SDL_SCANCODE_I] = (ps2_key_t){0x43, 0};
    scancode_map[SDL_SCANCODE_J] = (ps2_key_t){0x3B, 0};
    scancode_map[SDL_SCANCODE_K] = (ps2_key_t){0x42, 0};
    scancode_map[SDL_SCANCODE_L] = (ps2_key_t){0x4B, 0};
    scancode_map[SDL_SCANCODE_M] = (ps2_key_t){0x3A, 0};
    scancode_map[SDL_SCANCODE_N] = (ps2_key_t){0x31, 0};
    scancode_map[SDL_SCANCODE_O] = (ps2_key_t){0x44, 0};
    scancode_map[SDL_SCANCODE_P] = (ps2_key_t){0x4D, 0};
    scancode_map[SDL_SCANCODE_Q] = (ps2_key_t){0x15, 0};
    scancode_map[SDL_SCANCODE_R] = (ps2_key_t){0x2D, 0};
    scancode_map[SDL_SCANCODE_S] = (ps2_key_t){0x1B, 0};
    scancode_map[SDL_SCANCODE_T] = (ps2_key_t){0x2C, 0};
    scancode_map[SDL_SCANCODE_U] = (ps2_key_t){0x3C, 0};
    scancode_map[SDL_SCANCODE_V] = (ps2_key_t){0x2A, 0};
    scancode_map[SDL_SCANCODE_W] = (ps2_key_t){0x1D, 0};
    scancode_map[SDL_SCANCODE_X] = (ps2_key_t){0x22, 0};
    scancode_map[SDL_SCANCODE_Y] = (ps2_key_t){0x35, 0};
    scancode_map[SDL_SCANCODE_Z] = (ps2_key_t){0x1A, 0};

    /* Numbers */
    scancode_map[SDL_SCANCODE_1] = (ps2_key_t){0x16, 0};
    scancode_map[SDL_SCANCODE_2] = (ps2_key_t){0x1E, 0};
    scancode_map[SDL_SCANCODE_3] = (ps2_key_t){0x26, 0};
    scancode_map[SDL_SCANCODE_4] = (ps2_key_t){0x25, 0};
    scancode_map[SDL_SCANCODE_5] = (ps2_key_t){0x2E, 0};
    scancode_map[SDL_SCANCODE_6] = (ps2_key_t){0x36, 0};
    scancode_map[SDL_SCANCODE_7] = (ps2_key_t){0x3D, 0};
    scancode_map[SDL_SCANCODE_8] = (ps2_key_t){0x3E, 0};
    scancode_map[SDL_SCANCODE_9] = (ps2_key_t){0x46, 0};
    scancode_map[SDL_SCANCODE_0] = (ps2_key_t){0x45, 0};

    /* Punctuation & Controls */
    scancode_map[SDL_SCANCODE_RETURN]     = (ps2_key_t){0x5A, 0};
    scancode_map[SDL_SCANCODE_ESCAPE]     = (ps2_key_t){0x76, 0};
    scancode_map[SDL_SCANCODE_BACKSPACE]  = (ps2_key_t){0x66, 0};
    scancode_map[SDL_SCANCODE_TAB]        = (ps2_key_t){0x0D, 0};
    scancode_map[SDL_SCANCODE_SPACE]      = (ps2_key_t){0x29, 0};
    scancode_map[SDL_SCANCODE_MINUS]      = (ps2_key_t){0x4E, 0};
    scancode_map[SDL_SCANCODE_EQUALS]     = (ps2_key_t){0x55, 0};
    scancode_map[SDL_SCANCODE_LEFTBRACKET]= (ps2_key_t){0x54, 0};
    scancode_map[SDL_SCANCODE_RIGHTBRACKET]=(ps2_key_t){0x5B, 0};
    scancode_map[SDL_SCANCODE_BACKSLASH]  = (ps2_key_t){0x5D, 0};
    scancode_map[SDL_SCANCODE_SEMICOLON]  = (ps2_key_t){0x4C, 0};
    scancode_map[SDL_SCANCODE_APOSTROPHE] = (ps2_key_t){0x52, 0};
    scancode_map[SDL_SCANCODE_GRAVE]      = (ps2_key_t){0x0E, 0};
    scancode_map[SDL_SCANCODE_COMMA]      = (ps2_key_t){0x41, 0};
    scancode_map[SDL_SCANCODE_PERIOD]     = (ps2_key_t){0x49, 0};
    scancode_map[SDL_SCANCODE_SLASH]      = (ps2_key_t){0x4A, 0};
    scancode_map[SDL_SCANCODE_CAPSLOCK]   = (ps2_key_t){0x58, 0};

    /* Modifiers */
    scancode_map[SDL_SCANCODE_LCTRL]      = (ps2_key_t){0x14, 0};
    scancode_map[SDL_SCANCODE_LSHIFT]     = (ps2_key_t){0x12, 0};
    scancode_map[SDL_SCANCODE_LALT]       = (ps2_key_t){0x11, 0};
    scancode_map[SDL_SCANCODE_LGUI]       = (ps2_key_t){0x1F, 1};
    scancode_map[SDL_SCANCODE_RCTRL]      = (ps2_key_t){0x14, 1};
    scancode_map[SDL_SCANCODE_RSHIFT]     = (ps2_key_t){0x59, 0};
    scancode_map[SDL_SCANCODE_RALT]       = (ps2_key_t){0x11, 1};
    scancode_map[SDL_SCANCODE_RGUI]       = (ps2_key_t){0x27, 1};

    /* Function Keys */
    scancode_map[SDL_SCANCODE_F1]         = (ps2_key_t){0x05, 0};
    scancode_map[SDL_SCANCODE_F2]         = (ps2_key_t){0x06, 0};
    scancode_map[SDL_SCANCODE_F3]         = (ps2_key_t){0x04, 0};
    scancode_map[SDL_SCANCODE_F4]         = (ps2_key_t){0x0C, 0};
    scancode_map[SDL_SCANCODE_F5]         = (ps2_key_t){0x03, 0};
    scancode_map[SDL_SCANCODE_F6]         = (ps2_key_t){0x0B, 0};
    scancode_map[SDL_SCANCODE_F7]         = (ps2_key_t){0x83, 0};
    scancode_map[SDL_SCANCODE_F8]         = (ps2_key_t){0x0A, 0};
    scancode_map[SDL_SCANCODE_F9]         = (ps2_key_t){0x01, 0};
    scancode_map[SDL_SCANCODE_F10]        = (ps2_key_t){0x09, 0};
    scancode_map[SDL_SCANCODE_F11]        = (ps2_key_t){0x78, 0};
    scancode_map[SDL_SCANCODE_F12]        = (ps2_key_t){0x07, 0};

    /* Extended Navigation / Editing */
    scancode_map[SDL_SCANCODE_INSERT]     = (ps2_key_t){0x70, 1};
    scancode_map[SDL_SCANCODE_HOME]       = (ps2_key_t){0x6C, 1};
    scancode_map[SDL_SCANCODE_PAGEUP]     = (ps2_key_t){0x7D, 1};
    scancode_map[SDL_SCANCODE_DELETE]     = (ps2_key_t){0x71, 1};
    scancode_map[SDL_SCANCODE_END]        = (ps2_key_t){0x69, 1};
    scancode_map[SDL_SCANCODE_PAGEDOWN]   = (ps2_key_t){0x7A, 1};
    scancode_map[SDL_SCANCODE_RIGHT]      = (ps2_key_t){0x74, 1};
    scancode_map[SDL_SCANCODE_LEFT]       = (ps2_key_t){0x6B, 1};
    scancode_map[SDL_SCANCODE_DOWN]       = (ps2_key_t){0x72, 1};
    scancode_map[SDL_SCANCODE_UP]         = (ps2_key_t){0x75, 1};

    /* Keypad */
    scancode_map[SDL_SCANCODE_NUMLOCKCLEAR] = (ps2_key_t){0x77, 0};
    scancode_map[SDL_SCANCODE_KP_DIVIDE]    = (ps2_key_t){0x4A, 1};
    scancode_map[SDL_SCANCODE_KP_MULTIPLY]  = (ps2_key_t){0x7C, 0};
    scancode_map[SDL_SCANCODE_KP_MINUS]     = (ps2_key_t){0x7B, 0};
    scancode_map[SDL_SCANCODE_KP_PLUS]      = (ps2_key_t){0x79, 0};
    scancode_map[SDL_SCANCODE_KP_ENTER]     = (ps2_key_t){0x5A, 1};
    scancode_map[SDL_SCANCODE_KP_1]         = (ps2_key_t){0x69, 0};
    scancode_map[SDL_SCANCODE_KP_2]         = (ps2_key_t){0x72, 0};
    scancode_map[SDL_SCANCODE_KP_3]         = (ps2_key_t){0x7A, 0};
    scancode_map[SDL_SCANCODE_KP_4]         = (ps2_key_t){0x6B, 0};
    scancode_map[SDL_SCANCODE_KP_5]         = (ps2_key_t){0x73, 0};
    scancode_map[SDL_SCANCODE_KP_6]         = (ps2_key_t){0x74, 0};
    scancode_map[SDL_SCANCODE_KP_7]         = (ps2_key_t){0x6C, 0};
    scancode_map[SDL_SCANCODE_KP_8]         = (ps2_key_t){0x75, 0};
    scancode_map[SDL_SCANCODE_KP_9]         = (ps2_key_t){0x7D, 0};
    scancode_map[SDL_SCANCODE_KP_0]         = (ps2_key_t){0x70, 0};
    scancode_map[SDL_SCANCODE_KP_PERIOD]    = (ps2_key_t){0x71, 0};
}

static void send_kbd_down(SDL_Scancode scancode)
{
    if (scancode == SDL_SCANCODE_PAUSE) {
        uint8_t seq[] = {0xE1, 0x14, 0x77, 0xE1, 0xF0, 0x14, 0xF0, 0x77};
        for (int i = 0; i < 8; i++) ps2_send(&ps2[0], seq[i]);
        return;
    }
    if (scancode == SDL_SCANCODE_PRINTSCREEN) {
        ps2_send(&ps2[0], 0xE0); ps2_send(&ps2[0], 0x12);
        ps2_send(&ps2[0], 0xE0); ps2_send(&ps2[0], 0x7C);
        return;
    }
    if ((int)scancode < SDL_NUM_SCANCODES) {
        ps2_key_t k = scancode_map[scancode];
        if (k.code) {
            if (k.ext) ps2_send(&ps2[0], 0xE0);
            ps2_send(&ps2[0], k.code);
        }
    }
}

static void send_kbd_up(SDL_Scancode scancode)
{
    if (scancode == SDL_SCANCODE_PAUSE) return;
    if (scancode == SDL_SCANCODE_PRINTSCREEN) {
        ps2_send(&ps2[0], 0xE0); ps2_send(&ps2[0], 0xF0); ps2_send(&ps2[0], 0x7C);
        ps2_send(&ps2[0], 0xE0); ps2_send(&ps2[0], 0xF0); ps2_send(&ps2[0], 0x12);
        return;
    }
    if ((int)scancode < SDL_NUM_SCANCODES) {
        ps2_key_t k = scancode_map[scancode];
        if (k.code) {
            if (k.ext) ps2_send(&ps2[0], 0xE0);
            ps2_send(&ps2[0], 0xF0);
            ps2_send(&ps2[0], k.code);
        }
    }
}

/* ----------------------------------------------------------------- Mouse State */
static int mouse_grabbed = 0;
static int mouse_dx = 0;
static int mouse_dy = 0;
static int mouse_btn = 0;
static int last_mouse_btn = 0;

static void flush_mouse(void)
{
    if (!ps2[1].enabled || !ps2[1].f4_seen) {
        mouse_dx = 0;
        mouse_dy = 0;
        return;
    }
    /* Throttle packets if PS/2 device output FIFO has bytes pending */
    if (ps2[1].out_n > 4) return;

    if (mouse_dx != 0 || mouse_dy != 0 || mouse_btn != last_mouse_btn) {
        int sx = mouse_dx > 127 ? 127 : (mouse_dx < -127 ? -127 : mouse_dx);
        int sy = mouse_dy > 127 ? 127 : (mouse_dy < -127 ? -127 : mouse_dy);
        mouse_dx -= sx;
        mouse_dy -= sy;
        last_mouse_btn = mouse_btn;

        /* PS/2 mouse packet format:
         * Byte 0: [Yovf Xovf Ysign Xsign 1 MidBtn RightBtn LeftBtn]
         * Byte 1: 8-bit X delta
         * Byte 2: 8-bit Y delta (positive upward) */
        uint8_t b0 = (uint8_t)(0x08 | (mouse_btn & 7) |
                               (((sx >> 8) & 1) << 4) |
                               (((sy >> 8) & 1) << 5));
        uint8_t b1 = (uint8_t)(sx & 0xFF);
        uint8_t b2 = (uint8_t)(sy & 0xFF);

        ps2_send(&ps2[1], b0);
        ps2_send(&ps2[1], b1);
        ps2_send(&ps2[1], b2);
    }
}

/* ---------------------------------------------------------------- Machine Init */
static void init_machine(const char *rom_path, const char *sd_path, int coldboot, int force_6809, int simms)
{
    static M mm;
    m = &mm;
    memset(m, 0, sizeof(*m));

    /* Load ROM */
    FILE *f = fopen(rom_path, "rb");
    if (!f) {
        fprintf(stderr, "FAIL  cannot read ROM %s\n", rom_path);
        exit(1);
    }
    size_t nr = fread(m->rom, 1, sizeof(m->rom), f);
    fclose(f);
    fprintf(stderr, "emu: Loaded ROM %s (%zu bytes)\n", rom_path, nr);

    m->mk_ck = 0xC600; m->mk_ph = 0xC602; m->mk_camk = 0xC208; m->mk_herok = 0xC20A; m->mk_missed = 0xC225;

    /* PS/2 powerup */
    ps2[1].mouse = 1;
    for (int p = 0; p < 2; p++) {
        ps2[p].enabled = !ps2[p].mouse;
        ps2_send(&ps2[p], 0xAA);
        if (ps2[p].mouse) ps2_send(&ps2[p], 0x00);
        ps2[p].t = 104895; /* 50 ms after reset */
    }

    gate_init(&ser_gate, "SERIAL_GATE");
    gate_init(&kbd_gate, "PS2_KBD_GATE");
    gate_init(&mouse_gate, "PS2_MOUSE_GATE");
    gate_init(&scr_gate, "PS2_SCRIPT_GATE");

    if (getenv("SERIAL_IN")) {
        FILE *si = fopen(getenv("SERIAL_IN"), "rb");
        if (si) {
            static uint8_t sbuf[1 << 16];
            m->ser_in_n = (long)fread(sbuf, 1, sizeof sbuf, si);
            fclose(si);
            m->ser_in = sbuf;
            m->ser_at = (uint64_t)(atof(getenv("SERIAL_AT") ? getenv("SERIAL_AT") : "0") * 2097917.0);
        }
    }
    m->ser_type = (uint64_t)(atof(getenv("SERIAL_TYPE") ? getenv("SERIAL_TYPE") : "0") * 2097.917);
    m->ser_think = (uint64_t)(atof(getenv("SERIAL_THINK") ? getenv("SERIAL_THINK") : "0") * 2097.917);

    m->v3 = 1;
    card_reset(&m->card, m->sram, CARD_SRAM_BYTES);
    m->cur = calloc(640 * 512, 2);
    m->prv = calloc(640 * 512, 2);

    /* Storage */
    if (sd_path && *sd_path) {
        setenv("SDIMG", sd_path, 1);
        sd_reset();
    }

    /* Memory map */
    for (int i = 0; i < 16; i++) { m->maphi[i] = 0x02; m->maplo[i] = (uint8_t)i; }
    m->maphi[4] = 1; m->maplo[4] = 1;
    m->maphi[5] = 1; m->maplo[5] = 2;
    m->maphi[7] = 1; m->maplo[7] = 0;

    /* SIMM descriptor at logical $0000 */
    uint8_t *p0 = rampage(0x02, 0x00);
    p0[0] = (uint8_t)((1 << simms) - 1);
    p0[1] = (uint8_t)((simms * 512) >> 8);
    p0[2] = (uint8_t)((simms * 512) & 0xFF);

    m->irq_line_due = -1;
    m->cpu.ctx = m;
    m->cpu.read = rd;
    m->cpu.write = wr;

    if (!force_6809) cpu6309_enable(&m->cpu);
    cpu6809_reset(&m->cpu);

    if (coldboot) {
        fprintf(stderr, "emu: ⭐ COLDBOOT - entering at reset vector ($%04X)\n", m->cpu.pc);
    } else {
        m->cpu.pc = 0x8004;
        fprintf(stderr, "emu: Fast boot - entering at $8004\n");
    }
}

/* ------------------------------------------------------------- Main Application */
static void print_usage(const char *prog)
{
    fprintf(stderr,
            "Usage: %s [OPTIONS] [ROM.bin] [system.img]\n"
            "\n"
            "Interactive SDL2 emulator for the arm6309 personal computer.\n"
            "\n"
            "Options:\n"
            "  --coldboot         Cold reset: run boot ROM POST and Macintosh dialog\n"
            "  --handoff          Fast boot: skip POST straight to OS entry at $8004 (default)\n"
            "  --cpu6809          Force MC6809 emulation instead of native HD6309\n"
            "  --turbo            Start with 2 MHz speed throttling disabled\n"
            "  --simms N          Number of populated 512KB SIMM sockets (1-4, default 4)\n"
            "  --scale N          Window scale multiplier (1, 2, 3... default 1 = 640x480)\n"
            "  -h, --help         Show this help message\n"
            "\n"
            "Interactive Shortcuts:\n"
            "  F12, Ctrl+Alt+G    Toggle mouse capture (grab/release cursor)\n"
            "  F3                 Toggle Turbo mode (100%% 2 MHz vs unthrottled)\n"
            "  F5                 CPU Reset\n"
            "  Shift+F5           Coldboot Reset (runs POST)\n"
            "  F8                 Toggle Audio LED filter (A500 low-pass)\n"
            "  F10                Save screenshot (screenshot.bmp)\n"
            "  F11                Toggle Fullscreen\n"
            "  Alt+1, Alt+2, Alt+3 Set window scale: 1x (640x480), 2x (1280x960), or 3x\n"
            "\n"
            "Terminal Input:\n"
            "  You can type directly into the terminal running this emulator to interact\n"
            "  with the NitrOS-9 serial console (/dev/Term).\n"
            "\n", prog);
}

static const char *find_file(const char *candidates[])
{
    for (int i = 0; candidates[i]; i++) {
        FILE *f = fopen(candidates[i], "rb");
        if (f) {
            fclose(f);
            return candidates[i];
        }
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int coldboot = 0;
    int force_6809 = 0;
    int turbo = 0;
    int simms = 4;
    int scale = 1;
    const char *rom_path = NULL;
    const char *sd_path = NULL;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--coldboot")) coldboot = 1;
        else if (!strcmp(argv[i], "--handoff")) coldboot = 0;
        else if (!strcmp(argv[i], "--cpu6809")) force_6809 = 1;
        else if (!strcmp(argv[i], "--turbo")) turbo = 1;
        else if (!strcmp(argv[i], "--simms") && i + 1 < argc) simms = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) { print_usage(argv[0]); return 0; }
        else if (argv[i][0] != '-') {
            if (!rom_path) rom_path = argv[i];
            else if (!sd_path) sd_path = argv[i];
        }
    }

    if (!rom_path) {
        static const char *rom_candidates[] = {
            "software/nitros9/build/rom/arm6309_rom.bin",
            "software/desk/build/v3desk/arm6309_rom.bin",
            "software/desk/build/v3move/arm6309_rom.bin",
            "software/boot/boot.bin",
            NULL
        };
        rom_path = find_file(rom_candidates);
    }
    if (!sd_path) {
        static const char *sd_candidates[] = {
            "software/nitros9/build/rom/system.img",
            "software/desk/build/v3desk/system.img",
            "software/desk/build/v3move/system.img",
            NULL
        };
        sd_path = find_file(sd_candidates);
    }

    if (!rom_path) {
        fprintf(stderr, "FAIL  no ROM file found. Build one with 'make -C software/nitros9' or specify as argument.\n");
        return 1;
    }

    init_scancode_map();
    setup_terminal();

    /* SDL Init */
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "FAIL  SDL_Init: %s\n", SDL_GetError());
        return 1;
    }

    /* Video: 640x480 native 1x default window (or 640*scale x 480*scale) */
    if (scale < 1) scale = 1;
    SDL_Window *window = SDL_CreateWindow(
        "arm6309 Homebrew Computer (HD6309E @ 2.098 MHz)",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        640 * scale, 480 * scale,
        SDL_WINDOW_RESIZABLE
    );
    if (!window) {
        fprintf(stderr, "FAIL  SDL_CreateWindow: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }

    SDL_Renderer *renderer = SDL_CreateRenderer(
        window, -1,
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC
    );
    if (!renderer) {
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    }
    if (!renderer) {
        fprintf(stderr, "FAIL  SDL_CreateRenderer: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }
    SDL_RenderSetLogicalSize(renderer, 640, 480);

    SDL_Texture *texture = SDL_CreateTexture(
        renderer,
        SDL_PIXELFORMAT_RGB565,
        SDL_TEXTUREACCESS_STREAMING,
        640, 480
    );
    if (!texture) {
        fprintf(stderr, "FAIL  SDL_CreateTexture: %s\n", SDL_GetError());
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }

    /* Audio: 44.1 kHz 16-bit Stereo */
    SDL_AudioSpec wanted_spec;
    SDL_zero(wanted_spec);
    wanted_spec.freq = 44100;
    wanted_spec.format = AUDIO_S16SYS;
    wanted_spec.channels = 2;
    wanted_spec.samples = 1024;
    wanted_spec.callback = NULL; /* using SDL_QueueAudio */

    SDL_AudioDeviceID audio_dev = SDL_OpenAudioDevice(NULL, 0, &wanted_spec, NULL, 0);
    if (audio_dev) {
        SDL_PauseAudioDevice(audio_dev, 0);
    } else {
        fprintf(stderr, "WARNING  SDL_OpenAudioDevice failed: %s (continuing without audio)\n", SDL_GetError());
    }

    /* Init Audio filter renderer */
    render_open(&sdl_render, NULL, 44100, CARD_CC_PAL);
    render_set_callback(&sdl_render, sdl_audio_sample_cb, NULL);

    /* Initialize Machine */
    init_machine(rom_path, sd_path, coldboot, force_6809, simms);

    /* Grab mouse on start */
    mouse_grabbed = 1;
    SDL_SetRelativeMouseMode(SDL_TRUE);

    /* Timing */
    uint64_t perf_freq = SDL_GetPerformanceFrequency();
    double sec_per_cycle = 1.0 / 2097917.0;
    uint64_t t_frame_start = SDL_GetPerformanceCounter();
    uint64_t stat_t0 = t_frame_start;
    uint64_t stat_cycles0 = m->cpu.cycles;
    int stat_frames = 0;

    fprintf(stderr, "\n=== arm6309 running ===\n");
    fprintf(stderr, "Press F12 or Ctrl+Alt+G to release mouse capture.\n");
    fprintf(stderr, "Press F3 for Turbo mode, F5 to reset, F11 for fullscreen.\n");
    fprintf(stderr, "You can type directly into this terminal for NitrOS-9 serial shell.\n\n");

    bool running = true;
    while (running) {
        /* Process Host Terminal Input (UART RX) */
        if (m->rx_n < 16) {
            uint8_t tbuf[16];
            int max_read = 16 - m->rx_n;
            ssize_t n = read(STDIN_FILENO, tbuf, max_read);
            if (n > 0) {
                for (ssize_t i = 0; i < n; i++) {
                    uint8_t c = tbuf[i];
                    if (c == '\n') c = '\r'; /* NitrOS-9 uses CR */
                    m->rx[(m->rx_head + m->rx_n) & 15] = c;
                    m->rx_n++;
                    m->rx_last = m->cpu.cycles;
                }
            }
        }

        /* Process SDL Events */
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_QUIT:
                running = false;
                break;

            case SDL_KEYDOWN:
                if (ev.key.keysym.scancode == SDL_SCANCODE_F12 ||
                    ((ev.key.keysym.mod & KMOD_CTRL) && (ev.key.keysym.mod & KMOD_ALT) && ev.key.keysym.scancode == SDL_SCANCODE_G)) {
                    mouse_grabbed = !mouse_grabbed;
                    SDL_SetRelativeMouseMode(mouse_grabbed ? SDL_TRUE : SDL_FALSE);
                    break;
                }
                if (ev.key.keysym.scancode == SDL_SCANCODE_F3 && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_ALT))) {
                    turbo = !turbo;
                    fprintf(stderr, "\nemu: %s\n", turbo ? "TURBO MODE ON" : "Real-time 2.098 MHz ON");
                    break;
                }
                if (ev.key.keysym.scancode == SDL_SCANCODE_F5 && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_ALT))) {
                    if (ev.key.keysym.mod & KMOD_SHIFT) {
                        fprintf(stderr, "\nemu: Coldboot Reset\n");
                        init_machine(rom_path, sd_path, 1, force_6809, simms);
                    } else {
                        fprintf(stderr, "\nemu: CPU Reset\n");
                        cpu6809_reset(&m->cpu);
                    }
                    break;
                }
                if (ev.key.keysym.scancode == SDL_SCANCODE_F8 && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_ALT))) {
                    m->card.ctrl ^= ACTRL_LED;
                    int led_on = (m->card.ctrl & ACTRL_LED) != 0;
                    render_set_filter(&sdl_render, led_on, 0);
                    fprintf(stderr, "\nemu: Audio LED Filter %s\n", led_on ? "ON (3.3 kHz Sallen-Key low-pass)" : "OFF");
                    break;
                }
                if (ev.key.keysym.scancode == SDL_SCANCODE_F10 && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_ALT))) {
                    SDL_Surface *ss = SDL_CreateRGBSurfaceWithFormat(0, 640, 480, 16, SDL_PIXELFORMAT_RGB565);
                    if (ss) {
                        memcpy(ss->pixels, m->cur, 640 * 480 * 2);
                        SDL_SaveBMP(ss, "screenshot.bmp");
                        SDL_FreeSurface(ss);
                        fprintf(stderr, "\nemu: Saved screenshot.bmp\n");
                    }
                    break;
                }
                if (ev.key.keysym.scancode == SDL_SCANCODE_F11 && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_ALT))) {
                    Uint32 flags = SDL_GetWindowFlags(window);
                    SDL_SetWindowFullscreen(window, (flags & SDL_WINDOW_FULLSCREEN_DESKTOP) ? 0 : SDL_WINDOW_FULLSCREEN_DESKTOP);
                    break;
                }
                if ((ev.key.keysym.mod & KMOD_ALT) && !(ev.key.keysym.mod & (KMOD_CTRL | KMOD_GUI))) {
                    if (ev.key.keysym.scancode == SDL_SCANCODE_1) {
                        SDL_SetWindowSize(window, 640, 480);
                        break;
                    }
                    if (ev.key.keysym.scancode == SDL_SCANCODE_2) {
                        SDL_SetWindowSize(window, 1280, 960);
                        break;
                    }
                    if (ev.key.keysym.scancode == SDL_SCANCODE_3) {
                        SDL_SetWindowSize(window, 1920, 1440);
                        break;
                    }
                }
                send_kbd_down(ev.key.keysym.scancode);
                break;

            case SDL_KEYUP:
                send_kbd_up(ev.key.keysym.scancode);
                break;

            case SDL_MOUSEMOTION:
                if (mouse_grabbed) {
                    mouse_dx += ev.motion.xrel;
                    mouse_dy -= ev.motion.yrel; /* Invert Y for PS/2 */
                }
                break;

            case SDL_MOUSEBUTTONDOWN:
                if (!mouse_grabbed) {
                    mouse_grabbed = 1;
                    SDL_SetRelativeMouseMode(SDL_TRUE);
                } else {
                    if (ev.button.button == SDL_BUTTON_LEFT) mouse_btn |= 1;
                    else if (ev.button.button == SDL_BUTTON_RIGHT) mouse_btn |= 2;
                    else if (ev.button.button == SDL_BUTTON_MIDDLE) mouse_btn |= 4;
                }
                break;

            case SDL_MOUSEBUTTONUP:
                if (mouse_grabbed) {
                    if (ev.button.button == SDL_BUTTON_LEFT) mouse_btn &= ~1;
                    else if (ev.button.button == SDL_BUTTON_RIGHT) mouse_btn &= ~2;
                    else if (ev.button.button == SDL_BUTTON_MIDDLE) mouse_btn &= ~4;
                }
                break;
            }
        }

        /* Run machine until one video frame is emitted */
        uint64_t cyc_start = m->cpu.cycles;
        while (!sdl_frame_ready && running) {
            m->cpu.irq = (m->irq_pending && (m->ctrl & 0x40)) || uart_irq() || ps2_irq();
            audio_catchup();
            m->firq = card_firq(&m->card);
            m->cpu.firq = m->firq;

            cpu6809_step(&m->cpu);
            m->dots = m->cpu.cycles * DOTS_PER_E;
            raster();
            uart_step();
            ps2_step(0);
            ps2_step(1);
        }
        sdl_frame_ready = 0;
        uint64_t cyc_done = m->cpu.cycles - cyc_start;

        /* Deliver accumulated mouse input to line-level PS/2 interface */
        flush_mouse();

        /* Present Video */
        int act = active_lines();
        SDL_Rect srcrect = {0, 0, 640, act};
        SDL_Rect dstrect = {0, 0, 640, 480};
        SDL_UpdateTexture(texture, &srcrect, m->cur, 640 * sizeof(uint16_t));
        SDL_RenderClear(renderer);
        SDL_RenderCopy(renderer, texture, &srcrect, &dstrect);
        SDL_RenderPresent(renderer);

        if (getenv("SCREENSHOT_AT") && m->dots * DOT_PS >= (uint64_t)(atof(getenv("SCREENSHOT_AT")) * 1e12)) {
            static int shot_taken = 0;
            if (!shot_taken) {
                shot_taken = 1;
                const char *out_name = getenv("SCREENSHOT") ? getenv("SCREENSHOT") : "screenshot.bmp";
                SDL_Surface *ss = SDL_CreateRGBSurfaceWithFormat(0, 640, 480, 16, SDL_PIXELFORMAT_RGB565);
                if (ss) {
                    memcpy(ss->pixels, m->cur, 640 * 480 * 2);
                    SDL_SaveBMP(ss, out_name);
                    SDL_FreeSurface(ss);
                    fprintf(stderr, "\nemu: Saved automated %s at %.3f s\n", out_name, (double)m->dots * DOT_PS / 1e12);
                }
                if (getenv("SCREENSHOT_EXIT")) running = false;
            }
        }

        /* Push Audio */
        if (audio_dev) {
            int avail = (audio_ring_w - audio_ring_r + AUDIO_RING_SIZE) % AUDIO_RING_SIZE;
            if (avail > 0) {
                Uint32 queued = SDL_GetQueuedAudioSize(audio_dev);
                /* Target queue: 30-100 ms */
                if (queued < (Uint32)(44100 * 4 * 0.150)) {
                    int chunk = AUDIO_RING_SIZE - audio_ring_r;
                    if (chunk > avail) chunk = avail;
                    SDL_QueueAudio(audio_dev, &audio_ring[audio_ring_r], chunk * sizeof(int16_t));
                    audio_ring_r = (audio_ring_r + chunk) % AUDIO_RING_SIZE;
                    if (avail > chunk) {
                        int rem = avail - chunk;
                        SDL_QueueAudio(audio_dev, &audio_ring[audio_ring_r], rem * sizeof(int16_t));
                        audio_ring_r = (audio_ring_r + rem) % AUDIO_RING_SIZE;
                    }
                } else if (queued > (Uint32)(44100 * 4 * 0.300)) {
                    /* Lag drop: skip to prevent lag build up */
                    audio_ring_r = audio_ring_w;
                }
            }
        }

        /* Speed regulation: throttle to 2.097917 MHz */
        if (!turbo) {
            double frame_ideal_sec = (double)cyc_done * sec_per_cycle;
            uint64_t frame_ideal_ticks = (uint64_t)(frame_ideal_sec * (double)perf_freq);
            uint64_t target_t = t_frame_start + frame_ideal_ticks;
            uint64_t now = SDL_GetPerformanceCounter();

            if (now < target_t) {
                uint64_t diff = target_t - now;
                uint32_t ms = (uint32_t)((diff * 1000) / perf_freq);
                if (ms > 1) SDL_Delay(ms - 1);
                while (SDL_GetPerformanceCounter() < target_t) {
                    /* Spin wait for sub-millisecond precision */
                }
            }
            now = SDL_GetPerformanceCounter();
            /* Keep pace, avoid accumulating debt */
            if (now > target_t + frame_ideal_ticks * 3) {
                t_frame_start = now;
            } else {
                t_frame_start = target_t;
            }
        } else {
            t_frame_start = SDL_GetPerformanceCounter();
        }

        /* Periodic Status (once per second) */
        stat_frames++;
        uint64_t now_stat = SDL_GetPerformanceCounter();
        if (now_stat - stat_t0 >= perf_freq) {
            double elapsed = (double)(now_stat - stat_t0) / (double)perf_freq;
            double fps = (double)stat_frames / elapsed;
            uint64_t delta_cycles = m->cpu.cycles - stat_cycles0;
            double emu_mhz = (double)delta_cycles / (elapsed * 1e6);
            double speed_pct = (emu_mhz / 2.097917) * 100.0;

            char title[256];
            snprintf(title, sizeof(title),
                     "arm6309 Homebrew PC [%.0f%% (%.2f MHz)] - %.1f FPS - %s %s",
                     speed_pct, emu_mhz, fps,
                     turbo ? "[TURBO]" : "[2 MHz]",
                     mouse_grabbed ? "[Mouse: Captured]" : "[Mouse: Released (F12)]");
            SDL_SetWindowTitle(window, title);

            stat_t0 = now_stat;
            stat_cycles0 = m->cpu.cycles;
            stat_frames = 0;
        }
    }

    /* Cleanup */
    restore_terminal();
    if (audio_dev) SDL_CloseAudioDevice(audio_dev);
    render_close(&sdl_render);
    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();

    fprintf(stderr, "\nemu: Exited cleanly.\n");
    return 0;
}
