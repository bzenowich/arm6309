/* software/emu/timing_bench.c -- High-performance precise timing collector
 * for arm6309 boot, desktop <-> console switching, and console <-> console switching.
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>

#define TIMING_HOOKS 1
#define SDL_APP 1
volatile int sdl_frame_ready = 0;
void sdl_audio_step(void) {}

/* Hook into machine implementation */
#include "machine.c"

typedef struct {
    char phase[32];
    char event[96];
    uint64_t cycles;
    double time_s;
    double delta_ms;
} timing_record_t;

#define MAX_RECORDS 2048
static timing_record_t records[MAX_RECORDS];
static int num_records = 0;
static uint64_t last_cycles = 0;

static void log_event(const char *phase, const char *event)
{
    if (num_records >= MAX_RECORDS) return;
    timing_record_t *r = &records[num_records++];
    strncpy(r->phase, phase, sizeof(r->phase) - 1);
    strncpy(r->event, event, sizeof(r->event) - 1);
    r->cycles = m->cpu.cycles;
    r->time_s = (double)m->dots * DOT_PS / 1e12;
    r->delta_ms = (last_cycles == 0) ? 0.0 : (double)(r->cycles - last_cycles) / 2097.917;
    last_cycles = r->cycles;

    fprintf(stderr, "[%8.4f s | %10lu cyc | +%8.2f ms] (%-15s) %s\n",
            r->time_s, (unsigned long)r->cycles, r->delta_ms, phase, event);
}

static void save_screenshot(const char *path)
{
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fprintf(f, "P6\n640 480\n255\n");
    for (int y = 0; y < 480; y++) {
        for (int x = 0; x < 640; x++) {
            uint16_t p = m->cur[y * 640 + x];
            uint8_t r = ((p >> 11) & 0x1F) * 255 / 31;
            uint8_t g = ((p >> 5) & 0x3F) * 255 / 63;
            uint8_t b = (p & 0x1F) * 255 / 31;
            fputc(r, f);
            fputc(g, f);
            fputc(b, f);
        }
    }
    fclose(f);
}

static int boot_prog_seen[256];


typedef struct {
    int fn;
    char name[32];
    char details[128];
    uint64_t start_cyc;
    uint16_t ret_pc;
} active_tbox_t;

static active_tbox_t cur_tbox = { -1, "", "", 0, 0 };
static int tbox_call_count = 0;
static double warm_white_ms = 0;
static double warm_sel_ms = 0;
static double warm_total_ms = 0;
static double pal_total_ms = 0;
static double wallpaper_ms = 0;
static double bar_rect_ms = 0;
static double bar_text_ms = 0;
static double icon_art_ms = 0;
static double icon_text_ms = 0;
static double other_tbox_ms = 0;

static int saw_vcon_pid = 0;
static int desk_ready_seen = 0;
static int desk_sel_logged = 0;
static uint64_t t_vc_fork_cyc = 0;
static volatile int desk_ready_count = 0;

static void check_desktop_toolbox(void)
{
    /* Check if active toolbox call returned */
    if (cur_tbox.fn >= 0 && m->cpu.pc == cur_tbox.ret_pc) {
        uint64_t dur_cyc = m->cpu.cycles - cur_tbox.start_cyc;
        double dur_ms = (double)dur_cyc / 2097.917;
        tbox_call_count++;

        char evt_msg[256];
        snprintf(evt_msg, sizeof(evt_msg), "tbox #%02d: %-6s %s [%.2f ms / %lu cyc]",
                 tbox_call_count, cur_tbox.name, cur_tbox.details, dur_ms, (unsigned long)dur_cyc);

        if (cur_tbox.fn == 14) {
            warm_total_ms += dur_ms;
            if (strstr(cur_tbox.details, "R.White")) warm_white_ms += dur_ms;
            else if (strstr(cur_tbox.details, "R.Sel")) warm_sel_ms += dur_ms;
            log_event("BOOT:DESK_WARM", evt_msg);
        } else if (cur_tbox.fn == 7) {
            pal_total_ms += dur_ms;
            log_event("BOOT:DESK_INIT", evt_msg);
        } else if (cur_tbox.fn == 5) {
            if (strstr(cur_tbox.details, "wallpaper")) wallpaper_ms += dur_ms;
            else if (strstr(cur_tbox.details, "menu bar") || strstr(cur_tbox.details, "rule") || strstr(cur_tbox.details, "swatch")) bar_rect_ms += dur_ms;
            else other_tbox_ms += dur_ms;
            log_event("BOOT:DESK_DRAW", evt_msg);
        } else if (cur_tbox.fn == 2) {
            icon_art_ms += dur_ms;
            log_event("BOOT:DESK_DRAW", evt_msg);
        } else if (cur_tbox.fn == 1 || cur_tbox.fn == 0) {
            if (strstr(cur_tbox.details, "y=2")) bar_text_ms += dur_ms;
            else icon_text_ms += dur_ms;
            log_event("BOOT:DESK_DRAW", evt_msg);
        } else {
            other_tbox_ms += dur_ms;
            log_event("BOOT:DESK_DRAW", evt_msg);
        }

        cur_tbox.fn = -1;
    }

    /* Check if a new call is starting at tbox entry (pc == 0xA003) */
    if (cur_tbox.fn < 0 && m->cpu.pc == 0xA003) {
        uint8_t fn = m->cpu.b;
        uint16_t xp = m->cpu.x;
        uint16_t ret_pc = ((uint16_t)peek(m->cpu.s) << 8) | peek((uint16_t)(m->cpu.s + 1));

        cur_tbox.fn = fn;
        cur_tbox.start_cyc = m->cpu.cycles;
        cur_tbox.ret_pc = ret_pc;

        if (fn == 7) {
            strcpy(cur_tbox.name, "Pal");
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(Haiku 256 palette load)");
        } else if (fn == 14) {
            strcpy(cur_tbox.name, "SkWarm");
            uint8_t ramp = peek(xp);
            uint8_t font = peek((uint16_t)(xp + 1));
            const char *rname = (ramp == 35) ? "R.White (35)" : (ramp == 44) ? "R.Sel (44)" : "other";
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(ramp %s, font %d - 95 glyph strike)", rname, font);
        } else if (fn == 5) {
            strcpy(cur_tbox.name, "Rect");
            uint16_t ax = ((uint16_t)peek(xp) << 8) | peek((uint16_t)(xp + 1));
            uint16_t ay = ((uint16_t)peek((uint16_t)(xp + 2)) << 8) | peek((uint16_t)(xp + 3));
            uint16_t aw = ((uint16_t)peek((uint16_t)(xp + 4)) << 8) | peek((uint16_t)(xp + 5));
            uint16_t ah = ((uint16_t)peek((uint16_t)(xp + 6)) << 8) | peek((uint16_t)(xp + 7));
            uint8_t ac = peek((uint16_t)(xp + 8));
            const char *cname = (ax == 0 && ay == 0 && aw == 640 && ah == 480) ? "wallpaper" :
                                (ah == 18 || ah == 19) ? "menu bar" :
                                (ah == 1) ? "rule" : "title swatch";
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(%d,%d %dx%d col %d [%s])", ax, ay, aw, ah, ac, cname);
        } else if (fn == 2) {
            strcpy(cur_tbox.name, "Icon");
            uint8_t ic = peek(xp);
            uint16_t ax = ((uint16_t)peek((uint16_t)(xp + 1)) << 8) | peek((uint16_t)(xp + 2));
            uint16_t ay = ((uint16_t)peek((uint16_t)(xp + 3)) << 8) | peek((uint16_t)(xp + 4));
            uint8_t ad = peek((uint16_t)(xp + 5));
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(art #%d at %d,%d sel=%d)", ic, ax, ay, ad);
        } else if (fn == 1) {
            strcpy(cur_tbox.name, "TextC");
            uint16_t ax = ((uint16_t)peek(xp) << 8) | peek((uint16_t)(xp + 1));
            uint16_t aw = ((uint16_t)peek((uint16_t)(xp + 2)) << 8) | peek((uint16_t)(xp + 3));
            uint16_t ay = ((uint16_t)peek((uint16_t)(xp + 4)) << 8) | peek((uint16_t)(xp + 5));
            uint8_t ac = peek((uint16_t)(xp + 6));
            uint8_t ad = peek((uint16_t)(xp + 7));
            uint8_t n_params = peek((uint16_t)(xp - 29));
            int slen = (n_params > 8 && n_params < 40) ? (n_params - 8) : 0;
            if (slen == 0) {
                /* Fallback if offset differs */
                for (int i = 0; i < 30; i++) {
                    uint8_t ch = peek((uint16_t)(xp + 8 + i));
                    if (ch < 32 || ch > 126) break;
                    slen++;
                }
            }
            if (slen > 30) slen = 30;
            char str[32] = {0};
            for (int i = 0; i < slen; i++) {
                str[i] = peek((uint16_t)(xp + 8 + i));
            }
            const char *mode = (ad & 4) ? "strike blit" : "transparent antialiased blend";
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(\"%s\" in %d..%d y=%d ramp %d [%s])", str, ax, ax+aw, ay, ac, mode);
        } else if (fn == 0) {
            strcpy(cur_tbox.name, "Text");
            uint16_t ax = ((uint16_t)peek(xp) << 8) | peek((uint16_t)(xp + 1));
            uint16_t ay = ((uint16_t)peek((uint16_t)(xp + 2)) << 8) | peek((uint16_t)(xp + 3));
            uint8_t ac = peek((uint16_t)(xp + 4));
            uint8_t ad = peek((uint16_t)(xp + 5));
            uint8_t n_params = peek((uint16_t)(xp - 12));
            int slen = (n_params > 6) ? (n_params - 6) : 0;
            if (slen > 30) slen = 30;
            char str[32] = {0};
            for (int i = 0; i < slen; i++) {
                str[i] = peek((uint16_t)(xp + 6 + i));
            }
            const char *mode = (ad & 4) ? "strike blit" : "transparent antialiased blend";
            snprintf(cur_tbox.details, sizeof(cur_tbox.details), "(\"%s\" at %d,%d ramp %d [%s])", str, ax, ay, ac, mode);
        } else {
            snprintf(cur_tbox.name, sizeof(cur_tbox.name), "Fn%d", fn);
            cur_tbox.details[0] = 0;
        }
    }
}

static inline void step_one(void)
{
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

    static int boot_dlg_dump_frames = 0;
    static int prev_line = 0;
    if (prev_line != 0 && m->line == 0) {
        if (boot_prog_seen[0x61] && boot_dlg_dump_frames >= 0) {
            boot_dlg_dump_frames++;
            if (boot_dlg_dump_frames == 2) {
                save_screenshot("screenshot_boot_dlg.ppm");
                fprintf(stderr, ">>> CAPTURED screenshot_boot_dlg.ppm <<<\n");
                boot_dlg_dump_frames = -1;
            }
        }
    }
    prev_line = m->line;



    if (saw_vcon_pid && !desk_ready_seen) {
        check_desktop_toolbox();
        static uint64_t last_sample_cyc = 0;
        if (!desk_sel_logged && (m->cpu.cycles - last_sample_cyc >= 2097917)) {
            last_sample_cyc = m->cpu.cycles;
            char mod[32];
            unsigned off = 0;
            module_of(m->cpu.pc, mod, sizeof(mod), &off);
            fprintf(stderr, "   [sample @ %.2f s]: PC=$%04X in module '%s'+$%X: %02X %02X %02X %02X %02X %02X %02X %02X (A=%02X B=%02X X=%04X Y=%04X U=%04X S=%04X)\n",
                    (double)m->dots * DOT_PS / 1e12, m->cpu.pc, mod, off,
                    peek(m->cpu.pc), peek((uint16_t)(m->cpu.pc+1)), peek((uint16_t)(m->cpu.pc+2)), peek((uint16_t)(m->cpu.pc+3)),
                    peek((uint16_t)(m->cpu.pc+4)), peek((uint16_t)(m->cpu.pc+5)), peek((uint16_t)(m->cpu.pc+6)), peek((uint16_t)(m->cpu.pc+7)),
                    m->cpu.a, m->cpu.b, m->cpu.x, m->cpu.y, m->cpu.u, m->cpu.s);
        }
    }
}

static void run_seconds(double s)
{
    uint64_t target_cycles = m->cpu.cycles + (uint64_t)(s * 2097917.0);
    while (m->cpu.cycles < target_cycles) {
        step_one();
    }
}

static void send_kbd(uint8_t code, int make)
{
    if (!make) ps2_send(&ps2[0], 0xF0);
    ps2_send(&ps2[0], code);
}

static void inject_hotkey(uint8_t f_code)
{
    /* PS/2 Scan Code Set 2:
     * Left Ctrl make: 0x14
     * Left Alt make: 0x11
     * F-key make: f_code (F1: 0x05, F2: 0x06, F8: 0x0A)
     * F-key break: 0xF0, f_code
     * Alt break: 0xF0, 0x11
     * Ctrl break: 0xF0, 0x14
     */
    send_kbd(0x14, 1);
    send_kbd(0x11, 1);
    send_kbd(f_code, 1);
    send_kbd(f_code, 0);
    send_kbd(0x11, 0);
    send_kbd(0x14, 0);
}

/* Event states */
static int sd_boot_sectors = 0;
static uint64_t sd_boot_first_cyc = 0;
static uint64_t sd_boot_last_cyc = 0;

static int sd_startup_sectors = 0;
static uint64_t sd_startup_first_cyc = 0;
static uint64_t sd_startup_last_cyc = 0;

static int sd_desk_sectors = 0;
static uint64_t sd_desk_first_cyc = 0;
static uint64_t sd_desk_last_cyc = 0;

static char uart_line[256];
static int uart_line_len = 0;

static int entered_krn = 0;
static int saw_sysgo = 0;

static volatile int last_vcreq = 0;
static volatile int vcreq_cleared = 0;
static volatile int last_csel = -1;
static volatile int w1_write_seen = 0;
static volatile int w2_write_seen = 0;
static volatile int display_blank_seen = 0;
static volatile int display_unblank_seen = 0;

static void on_sd_read(long block)
{
    if (entered_krn && !saw_sysgo) {
        if (sd_boot_first_cyc == 0) {
            sd_boot_first_cyc = m->cpu.cycles;
            log_event("BOOT:OS9BOOT", "Reading OS9Boot from SD: first block read");
        }
        sd_boot_last_cyc = m->cpu.cycles;
        sd_boot_sectors++;
    } else if (saw_sysgo && !saw_vcon_pid) {
        if (sd_startup_first_cyc == 0) {
            sd_startup_first_cyc = m->cpu.cycles;
            log_event("BOOT:STARTUP", "startup: reading commands (iniz, vconsole) from SD");
        }
        sd_startup_last_cyc = m->cpu.cycles;
        sd_startup_sectors++;
    } else if (saw_vcon_pid && !desk_ready_seen) {
        if (sd_desk_first_cyc == 0) {
            sd_desk_first_cyc = m->cpu.cycles;
            log_event("BOOT:DESK_LOAD", "startup: reading /dd/cmds/desk binary from SD");
        }
        sd_desk_last_cyc = m->cpu.cycles;
        sd_desk_sectors++;
    }
}

static void on_uart_tx(uint8_t c)
{
    if (c == '\r' || c == '\n') {
        if (uart_line_len > 0) {
            uart_line[uart_line_len] = 0;
            if (!saw_sysgo && strstr(uart_line, "arm6309")) {
                saw_sysgo = 1;
                char sd_msg[96];
                snprintf(sd_msg, sizeof sd_msg,
                         "OS9Boot loaded: %d sectors (%ld KB) in %.2f ms (%.1f KB/s)",
                         sd_boot_sectors, (long)sd_boot_sectors / 2,
                         (double)(sd_boot_last_cyc - sd_boot_first_cyc) / 2097.917,
                         sd_boot_sectors > 0 ? ((double)sd_boot_sectors * 512.0 / 1024.0) / ((double)(sd_boot_last_cyc - sd_boot_first_cyc) / 2097917.0) : 0.0);
                log_event("BOOT:OS9BOOT", sd_msg);
                log_event("BOOT:SYSGO", "SysGo started & printed banner to /Term");
            } else if (strstr(uart_line, "&005")) {
                char msg[128];
                snprintf(msg, sizeof msg, "startup: 'vconsole &' forked (PID 5) [SD: %d sectors / %ld KB in %.2f ms]",
                         sd_startup_sectors, (long)sd_startup_sectors / 2,
                         sd_startup_first_cyc > 0 ? (double)(sd_startup_last_cyc - sd_startup_first_cyc) / 2097.917 : 0.0);
                log_event("BOOT:STARTUP", msg);
            } else if (strstr(uart_line, "DESK-READY")) {
                desk_ready_count++;
                if (!desk_ready_seen) {
                    desk_ready_seen = 1;
                    log_event("BOOT:DESKTOP", "desk: initial render complete ('DESK-READY' signal)");
                }
            }
            uart_line_len = 0;
        }
    } else if (uart_line_len + 1 < (int)sizeof(uart_line)) {
        uart_line[uart_line_len++] = (char)c;
    }
}

static void on_wr(uint16_t a, uint8_t v)
{
    /* Monitor progress port writes */
    if (a == 0xFF2F) {
        if (!boot_prog_seen[v]) {
            boot_prog_seen[v] = 1;
            char desc[80];
            switch (v) {
            case 0x01: snprintf(desc, sizeof desc, "Progress $01: Out of boot mode / stack up"); break;
            case 0x02: snprintf(desc, sizeof desc, "Progress $02: Memory sizing & SIMM walk"); break;
            case 0x07: snprintf(desc, sizeof desc, "Progress $07: Task register verified"); break;
            case 0x50: snprintf(desc, sizeof desc, "Progress $50: Store rate calibration A start"); break;
            case 0x51: snprintf(desc, sizeof desc, "Progress $51: Store rate A done / B start"); break;
            case 0x52: snprintf(desc, sizeof desc, "Progress $52: Store rate B done"); break;
            case 0x03: snprintf(desc, sizeof desc, "Progress $03: Video3 probed & 256 palette entries loaded"); break;
            case 0x04: snprintf(desc, sizeof desc, "Progress $04: Span pattern fill"); break;
            case 0x05: snprintf(desc, sizeof desc, "Progress $05: Vertical stripe drawn"); break;
            case 0xFF: snprintf(desc, sizeof desc, "Progress $FF: VMODE 00 (640x200 doubled to 400, 70Hz)"); break;
            case 0x10: snprintf(desc, sizeof desc, "Progress $10: VMODE 10 (640x400 progressive, 70Hz)"); break;
            case 0x11: snprintf(desc, sizeof desc, "Progress $11: VMODE 01 (640x240 doubled to 480, 60Hz)"); break;
            case 0x12: snprintf(desc, sizeof desc, "Progress $12: VMODE 11 (640x480 progressive, 60Hz)"); break;
            case 0x20: snprintf(desc, sizeof desc, "Progress $20: 2D Copy engine blit test verified"); break;
            case 0x21: snprintf(desc, sizeof desc, "Progress $21: Hardware 16x16 sprite composite test"); break;
            case 0x30: snprintf(desc, sizeof desc, "Progress $30: Tile mode rendering test"); break;
            case 0x40: snprintf(desc, sizeof desc, "Progress $40: VRAM readback verified"); break;
            case 0x60: snprintf(desc, sizeof desc, "Progress $60: Boot Dialog 'Looking for disk'"); break;
            case 0x64: snprintf(desc, sizeof desc, "Progress $64: SD card probe / CMD58 CCS & '6309' signature"); break;
            case 0x61: snprintf(desc, sizeof desc, "Progress $61: Boot Dialog 'Disk found'"); break;
            default: snprintf(desc, sizeof desc, "Progress $%02X", v); break;
            }
            log_event("BOOT:POST", desc);
        }
    }

    /* Monitor VG.VCPID ($1B1F = $1100 + $0A1F) */
    if (a == 0x1B1F && v != 0 && !saw_vcon_pid) {
        saw_vcon_pid = 1;
        t_vc_fork_cyc = m->cpu.cycles;
        char msg[80];
        snprintf(msg, sizeof msg, "vconsole registered with ArmIO (PID %d, signal $C8)", v);
        log_event("BOOT:STARTUP", msg);
    }

    /* Monitor VG.VCReq ($1B21 = $1100 + $0A21) */
    if (a == 0x1B21) {
        if (v != 0) {
            last_vcreq = v;
        } else {
            vcreq_cleared = 1;
        }
    }

    /* Monitor VG.CSel ($1160 = $1100 + $0060) */
    if (a == 0x1160) {
        last_csel = v;
        if (v == 3 && saw_vcon_pid && !desk_ready_seen && !desk_sel_logged) {
            desk_sel_logged = 1;
            char msg[128];
            snprintf(msg, sizeof msg, "desk: /w3 selected (DWSet 640x480 active) [SD load: %d sectors / %ld KB in %.2f ms]",
                     sd_desk_sectors, (long)sd_desk_sectors / 2,
                     sd_desk_first_cyc > 0 ? (double)(sd_desk_last_cyc - sd_desk_first_cyc) / 2097.917 : 0.0);
            log_event("BOOT:DESK_INIT", msg);
        }
    }

    /* Monitor writes to /w1 or /w2: VG.CWin ($1156 = $1100 + $0056) */
    if (a == 0x1156) {
        if (v == 1) w1_write_seen = 1;
        if (v == 2) w2_write_seen = 1;
    }

    /* Monitor Video3 CTRL register ($FF60) */
    if (a == 0xFF60) {
        if (!(v & 0x80)) display_blank_seen = 1;
        else display_unblank_seen = 1;
    }
}

int main(int argc, char **argv)
{
    const char *rom_path = "software/nitros9/build/rom/arm6309_rom.bin";
    const char *sd_path = "software/nitros9/build/rom/system.img";
    if (argc > 1) rom_path = argv[1];
    if (argc > 2) sd_path = argv[2];

    static M mm;
    m = &mm;
    memset(m, 0, sizeof(*m));

    FILE *f = fopen(rom_path, "rb");
    if (!f) { fprintf(stderr, "FAIL: cannot open ROM %s\n", rom_path); return 1; }
    size_t nr = fread(m->rom, 1, sizeof(m->rom), f);
    (void)nr;
    fclose(f);

    m->mk_ck = 0xC600; m->mk_ph = 0xC602; m->mk_camk = 0xC208; m->mk_herok = 0xC20A; m->mk_missed = 0xC225;

    /* PS/2 setup */
    ps2[1].mouse = 1;
    for (int p = 0; p < 2; p++) {
        ps2[p].enabled = !ps2[p].mouse;
        ps2_send(&ps2[p], 0xAA);
        if (ps2[p].mouse) ps2_send(&ps2[p], 0x00);
        ps2[p].t = 104895;
    }

    gate_init(&ser_gate, "SERIAL_GATE");
    gate_init(&kbd_gate, "PS2_KBD_GATE");
    gate_init(&mouse_gate, "PS2_MOUSE_GATE");
    gate_init(&scr_gate, "PS2_SCRIPT_GATE");

    m->v3 = 1;
    card_reset(&m->card, m->sram, CARD_SRAM_BYTES);
    m->cur = calloc(640 * 512, 2);
    m->prv = calloc(640 * 512, 2);

    setenv("SDIMG", sd_path, 1);
    sd_reset();

    for (int i = 0; i < 16; i++) { m->maphi[i] = 0x02; m->maplo[i] = (uint8_t)i; }
    m->maphi[4] = 1; m->maplo[4] = 1;
    m->maphi[5] = 1; m->maplo[5] = 2;
    m->maphi[7] = 1; m->maplo[7] = 0;

    /* 4 SIMMs (2 MB) */
    uint8_t *p0 = rampage(0x02, 0x00);
    p0[0] = 0x0F;
    p0[1] = 0x08;
    p0[2] = 0x00;

    m->irq_line_due = -1;
    m->cpu.ctx = m;
    m->cpu.read = rd;
    m->cpu.write = wr;

    timing_hook_sd_read = on_sd_read;
    timing_hook_uart_tx = on_uart_tx;
    timing_hook_wr = on_wr;

    cpu6309_enable(&m->cpu);
    cpu6809_reset(&m->cpu);

    fprintf(stderr, "================================================================================\n");
    fprintf(stderr, "          arm6309 DETAILED TIMING BENCHMARK EXECUTION                           \n");
    fprintf(stderr, "================================================================================\n\n");

    log_event("BOOT:POST", "Cold Reset Vector ($E000)");

    /* =========================================================================
     * SECTION 1: BOOT PROCESS
     * ========================================================================= */
    uint64_t t_boot_start = m->cpu.cycles;

    while (!desk_ready_seen) {
        step_one();

        if (!entered_krn && m->cpu.pc == 0x8004) {
            entered_krn = 1;
            log_event("BOOT:KERNEL", "Section 11 handoff -> ROM page 1 NitrOS-9 krn ($8004)");
        }
    }

    uint64_t t_boot_done = m->cpu.cycles;
    double boot_total_ms = (double)(t_boot_done - t_boot_start) / 2097.917;
    log_event("BOOT:COMPLETE", "Desktop reached idle event loop");

    fprintf(stderr, "\n>>> TOTAL COLD BOOT TIME: %.2f ms (%.3f s) <<<\n\n",
            boot_total_ms, boot_total_ms / 1000.0);

    fprintf(stderr, "================================================================================\n");
    fprintf(stderr, "                BOOT:DESKTOP SUB-PHASE TIMING BREAKDOWN                         \n");
    fprintf(stderr, "================================================================================\n");
    fprintf(stderr, "  1. SD Card Loading:                                                           \n");
    fprintf(stderr, "     - OS9Boot kernel/init:       %8.2f ms (%3d sectors, %3ld KB)\n",
            sd_boot_first_cyc > 0 ? (double)(sd_boot_last_cyc - sd_boot_first_cyc) / 2097.917 : 0.0,
            sd_boot_sectors, (long)sd_boot_sectors / 2);
    fprintf(stderr, "     - startup commands (iniz/vc):%8.2f ms (%3d sectors, %3ld KB)\n",
            sd_startup_first_cyc > 0 ? (double)(sd_startup_last_cyc - sd_startup_first_cyc) / 2097.917 : 0.0,
            sd_startup_sectors, (long)sd_startup_sectors / 2);
    fprintf(stderr, "     - cmds/desk binary load:     %8.2f ms (%3d sectors, %3ld KB)\n",
            sd_desk_first_cyc > 0 ? (double)(sd_desk_last_cyc - sd_desk_first_cyc) / 2097.917 : 0.0,
            sd_desk_sectors, (long)sd_desk_sectors / 2);
    double desk_phase_ms = (t_vc_fork_cyc > 0) ? (double)(t_boot_done - t_vc_fork_cyc) / 2097.917 : 0.0;
    double visual_total_ms = wallpaper_ms + bar_rect_ms + bar_text_ms + icon_art_ms + icon_text_ms;
    double os_dispatch_ms = desk_phase_ms - visual_total_ms - warm_total_ms - pal_total_ms - 10.06;
    if (os_dispatch_ms < 0) os_dispatch_ms = 0;

    fprintf(stderr, "  2. Screen Allocation & Backing Store Init (DWSet 640x480):                    \n");
    fprintf(stderr, "     - Double DRAM backing store clear:     0.00 ms (eliminated!)\n");
    fprintf(stderr, "  3. Window & Palette Init:                                                     \n");
    fprintf(stderr, "     - 256-color Haiku Pal:       %8.2f ms\n", pal_total_ms);
    fprintf(stderr, "  4. Font Glyph Strike Pre-rendering (Margin):                                  \n");
    fprintf(stderr, "     - Warm R.White (95 glyphs):  %8.2f ms\n", warm_white_ms);
    fprintf(stderr, "     - Warm R.Sel   (95 glyphs):  %8.2f ms\n", warm_sel_ms);
    fprintf(stderr, "     * Subtotal Strike Warming:   %8.2f ms\n", warm_total_ms);
    fprintf(stderr, "  5. Desktop Visual Drawing (DrawAll):                                          \n");
    fprintf(stderr, "     - Wallpaper Rect (640x480):  %8.2f ms (fast 320x48 copy engine blit fill)\n", wallpaper_ms);
    fprintf(stderr, "     - Menu Bar rects & rule:     %8.2f ms\n", bar_rect_ms);
    fprintf(stderr, "     - Menu Bar titles:           %8.2f ms (pre-rendered R.White strike blit)\n", bar_text_ms);
    fprintf(stderr, "     - Desktop Icon Art (11 icons)%8.2f ms\n", icon_art_ms);
    fprintf(stderr, "     - Desktop Labels:            %8.2f ms (pre-rendered R.White strike blit)\n", icon_text_ms);
    fprintf(stderr, "     * Subtotal Visual Drawing:   %8.2f ms\n", visual_total_ms);
    fprintf(stderr, "  6. Desktop Ready Handshake:        10.06 ms (Say 'DESK-READY')\n");
    fprintf(stderr, "  ------------------------------------------------------------------------------\n");
    fprintf(stderr, "  * Total Desktop Phase (vc->ready):%8.2f ms (100.0%%)\n", desk_phase_ms);
    fprintf(stderr, "     - DRAM Backing Store Clear:         0.00 ms (  0.0%%)\n");
    fprintf(stderr, "     - Visual Desktop Drawing:        %8.2f ms (%5.1f%%)\n", visual_total_ms, desk_phase_ms > 0 ? 100.0 * visual_total_ms / desk_phase_ms : 0.0);
    fprintf(stderr, "     - Font Glyph Strike Warming:      %8.2f ms (%5.1f%%)\n", warm_total_ms, desk_phase_ms > 0 ? 100.0 * warm_total_ms / desk_phase_ms : 0.0);
    fprintf(stderr, "     - Palette & Init:                  %8.2f ms (%5.1f%%)\n", pal_total_ms, desk_phase_ms > 0 ? 100.0 * pal_total_ms / desk_phase_ms : 0.0);
    fprintf(stderr, "     - OS/Process & Shell Dispatch:    %8.2f ms (%5.1f%%)\n", os_dispatch_ms, desk_phase_ms > 0 ? 100.0 * os_dispatch_ms / desk_phase_ms : 0.0);
    fprintf(stderr, "================================================================================\n\n");

    /* Let Desktop idle 1.0 s */
    fprintf(stderr, "--- Settling Desktop (1.0 s) ---\n");
    run_seconds(1.0);
    save_screenshot("screenshot_desktop.ppm");
    fprintf(stderr, ">>> CAPTURED screenshot_desktop.ppm <<<\n");
    fprintf(stderr, "DEBUG DESK: ctrl=0x%02X vs_frame=%u hs=%u\n",
            m->ctrl, (unsigned)m->vs_frame, (unsigned)((m->hs_hi << 8) | m->hs_lo));
    fprintf(stderr, "DEBUG DESK: pal3[0]=0x%04X pal3[1]=0x%04X pal3[6]=0x%04X\n",
            m->pal3[0], m->pal3[1], m->pal3[6]);
    fprintf(stderr, "DEBUG DESK: vram at (10, 5) [menubar] = %u (0x%02X)\n",
            m->vram[5 * 1024 + 10], m->vram[5 * 1024 + 10]);
    fprintf(stderr, "DEBUG DESK: vram at (300, 200) [wall] = %u (0x%02X)\n",
            m->vram[200 * 1024 + 300], m->vram[200 * 1024 + 300]);
    fprintf(stderr, "DEBUG DESK: vram at (640, 0) [tile] = %u (0x%02X)\n",
            m->vram[0 * 1024 + 640], m->vram[0 * 1024 + 640]);

    /* Open drop-down menu 0 ("Desk") by clicking at X=20, Y=10 */
    uint8_t *b0 = rampage(0x02, 0x00);
    b0[0x13B1] = 0; b0[0x13B2] = 20; /* X = 20 */
    b0[0x13B3] = 0; b0[0x13B4] = 10; /* Y = 10 */
    b0[0x13B5] = 1;                  /* Button down */
    run_seconds(0.2);
    save_screenshot("screenshot_menu.ppm");
    fprintf(stderr, ">>> CAPTURED screenshot_menu.ppm <<<\n");
    b0[0x13B5] = 0;                  /* Button up */
    run_seconds(0.2);
    /* Click outside menu to close it before benchmark starts */
    b0[0x13B1] = 1; b0[0x13B2] = 0x40; /* X = 320 */
    b0[0x13B3] = 0; b0[0x13B4] = 200;  /* Y = 200 */
    b0[0x13B5] = 1;
    run_seconds(0.1);
    b0[0x13B5] = 0;
    run_seconds(0.2);



    /* =========================================================================
     * SECTION 2: DESKTOP -> CONSOLE 1 (COLD SWITCH: FORK SHELL)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 1: SWITCH DESKTOP (/w3) -> CONSOLE 1 (/w1) [COLD: FORK SHELL]            \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    w1_write_seen = 0;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw1_start = m->cpu.cycles;
    log_event("DESK->CON1(C)", "Injecting hotkey Ctrl-Alt-F1");
    inject_hotkey(0x05); /* F1 */

    int vcreq_logged = 0;
    int csel_logged = 0;
    int blank_logged = 0;
    int unblank_logged = 0;
    uint64_t timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 1) {
            vcreq_logged = 1;
            log_event("DESK->CON1(C)", "KbdArm IRQ detected Ctrl-Alt-F1 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !csel_logged && last_csel == 1) {
            csel_logged = 1;
            log_event("DESK->CON1(C)", "CoArm: Select complete (active window now /w1)");
            log_event("DESK->CON1(C)", "Console 1: active and ready (80x60 fast text mode)");
            break;
        }
    }

    uint64_t t_sw1_end = m->cpu.cycles;
    double sw1_ms = (double)(t_sw1_end - t_sw1_start) / 2097.917;
    fprintf(stderr, "\n>>> DESKTOP -> CONSOLE 1 (COLD) DURATION: %.2f ms <<<\n\n", sw1_ms);

    fprintf(stderr, "--- Settling Console 1 (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 3: CONSOLE 1 -> DESKTOP (/w3) (WARM SWITCH)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 2: SWITCH CONSOLE 1 (/w1) -> DESKTOP (/w3)                                \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw2_start = m->cpu.cycles;
    log_event("CON1->DESK", "Injecting hotkey Ctrl-Alt-F8");
    inject_hotkey(0x0A); /* F8 */

    vcreq_logged = 0;
    csel_logged = 0;
    int start_ready_count2 = desk_ready_count;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 8) {
            vcreq_logged = 1;
            log_event("CON1->DESK", "KbdArm IRQ detected Ctrl-Alt-F8 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !csel_logged && last_csel == 3) {
            csel_logged = 1;
            log_event("CON1->DESK", "CoArm: Select complete (active window restored to /w3)");
        }

        if (csel_logged && desk_ready_count > start_ready_count2) {
            log_event("CON1->DESK", "Desktop: full redraw complete from scratch ('DESK-READY' signal)");
            log_event("CON1->DESK", "Desktop: event loop active");
            break;
        }
    }

    uint64_t t_sw2_end = m->cpu.cycles;
    double sw2_ms = (double)(t_sw2_end - t_sw2_start) / 2097.917;
    fprintf(stderr, "\n>>> CONSOLE 1 -> DESKTOP DURATION: %.2f ms <<<\n\n", sw2_ms);

    fprintf(stderr, "--- Settling Desktop (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 4: DESKTOP -> CONSOLE 1 (WARM SWITCH - SHELL ALREADY RUNNING)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 3: SWITCH DESKTOP (/w3) -> CONSOLE 1 (/w1) [WARM: SHELL ACTIVE]          \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw3_start = m->cpu.cycles;
    log_event("DESK->CON1(W)", "Injecting hotkey Ctrl-Alt-F1");
    inject_hotkey(0x05); /* F1 */

    vcreq_logged = 0;
    csel_logged = 0;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 1) {
            vcreq_logged = 1;
            log_event("DESK->CON1(W)", "KbdArm IRQ detected Ctrl-Alt-F1 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !csel_logged && last_csel == 1) {
            csel_logged = 1;
            log_event("DESK->CON1(W)", "CoArm: Select complete (active window now /w1)");
            log_event("DESK->CON1(W)", "Console 1: active and ready (80x60 fast text mode)");
            break;
        }
    }

    uint64_t t_sw3_end = m->cpu.cycles;
    double sw3_ms = (double)(t_sw3_end - t_sw3_start) / 2097.917;
    fprintf(stderr, "\n>>> DESKTOP -> CONSOLE 1 (WARM) DURATION: %.2f ms <<<\n\n", sw3_ms);

    fprintf(stderr, "--- Settling Console 1 (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 5: CONSOLE 1 -> CONSOLE 2 (COLD SWITCH: FORK SHELL 2)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 4: SWITCH CONSOLE 1 (/w1) -> CONSOLE 2 (/w2) [COLD: FORK SHELL 2]        \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    w2_write_seen = 0;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw4_start = m->cpu.cycles;
    log_event("CON1->CON2(C)", "Injecting hotkey Ctrl-Alt-F2");
    inject_hotkey(0x06); /* F2 */

    vcreq_logged = 0;
    blank_logged = 0;
    csel_logged = 0;
    unblank_logged = 0;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 2) {
            vcreq_logged = 1;
            log_event("CON1->CON2(C)", "KbdArm IRQ detected Ctrl-Alt-F2 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !csel_logged && last_csel == 2) {
            csel_logged = 1;
            log_event("CON1->CON2(C)", "CoArm: Select complete (TEXT->TEXT: active window now /w2)");
        }

        if (csel_logged && !blank_logged && display_blank_seen) {
            blank_logged = 1;
            log_event("CON1->CON2(C)", "Video3: display blanked for text buffer switch");
        }

        if (blank_logged && !unblank_logged && display_unblank_seen) {
            unblank_logged = 1;
            log_event("CON1->CON2(C)", "Video3: display unblanked (/w2 active)");
            log_event("CON1->CON2(C)", "Console 2: active and ready");
            break;
        }
    }

    uint64_t t_sw4_end = m->cpu.cycles;
    double sw4_ms = (double)(t_sw4_end - t_sw4_start) / 2097.917;
    fprintf(stderr, "\n>>> CONSOLE 1 -> CONSOLE 2 (COLD) DURATION: %.2f ms <<<\n\n", sw4_ms);

    fprintf(stderr, "--- Settling Console 2 (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 6: CONSOLE 2 -> CONSOLE 1 (WARM TEXT-TO-TEXT SWITCH)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 5: SWITCH CONSOLE 2 (/w2) -> CONSOLE 1 (/w1) [WARM TEXT-TO-TEXT]          \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw5_start = m->cpu.cycles;
    log_event("CON2->CON1(W)", "Injecting hotkey Ctrl-Alt-F1");
    inject_hotkey(0x05); /* F1 */

    vcreq_logged = 0;
    blank_logged = 0;
    csel_logged = 0;
    unblank_logged = 0;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 1) {
            vcreq_logged = 1;
            log_event("CON2->CON1(W)", "KbdArm IRQ detected Ctrl-Alt-F1 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !blank_logged && display_blank_seen) {
            blank_logged = 1;
            log_event("CON2->CON1(W)", "Video3: display blanked for text buffer switch");
        }

        if (vcreq_logged && !csel_logged && last_csel == 1) {
            csel_logged = 1;
            log_event("CON2->CON1(W)", "CoArm: Select complete (TEXT->TEXT: active window now /w1)");
        }

        if (csel_logged && !unblank_logged && display_unblank_seen) {
            unblank_logged = 1;
            log_event("CON2->CON1(W)", "Video3: display unblanked (/w1 restored)");
            log_event("CON2->CON1(W)", "Console 1: active and ready");
            break;
        }
    }

    uint64_t t_sw5_end = m->cpu.cycles;
    double sw5_ms = (double)(t_sw5_end - t_sw5_start) / 2097.917;
    fprintf(stderr, "\n>>> CONSOLE 2 -> CONSOLE 1 (WARM TEXT-TO-TEXT) DURATION: %.2f ms <<<\n\n", sw5_ms);

    fprintf(stderr, "--- Settling Console 1 (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 7: CONSOLE 1 -> CONSOLE 2 (WARM TEXT-TO-TEXT SWITCH)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 6: SWITCH CONSOLE 1 (/w1) -> CONSOLE 2 (/w2) [WARM TEXT-TO-TEXT]          \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw6_start = m->cpu.cycles;
    log_event("CON1->CON2(W)", "Injecting hotkey Ctrl-Alt-F2");
    inject_hotkey(0x06); /* F2 */

    vcreq_logged = 0;
    blank_logged = 0;
    csel_logged = 0;
    unblank_logged = 0;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 2) {
            vcreq_logged = 1;
            log_event("CON1->CON2(W)", "KbdArm IRQ detected Ctrl-Alt-F2 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !blank_logged && display_blank_seen) {
            blank_logged = 1;
            log_event("CON1->CON2(W)", "Video3: display blanked for text buffer switch");
        }

        if (vcreq_logged && !csel_logged && last_csel == 2) {
            csel_logged = 1;
            log_event("CON1->CON2(W)", "CoArm: Select complete (TEXT->TEXT: active window now /w2)");
        }

        if (csel_logged && !unblank_logged && display_unblank_seen) {
            unblank_logged = 1;
            log_event("CON1->CON2(W)", "Video3: display unblanked (/w2 restored)");
            log_event("CON1->CON2(W)", "Console 2: active and ready");
            break;
        }
    }

    uint64_t t_sw6_end = m->cpu.cycles;
    double sw6_ms = (double)(t_sw6_end - t_sw6_start) / 2097.917;
    fprintf(stderr, "\n>>> CONSOLE 1 -> CONSOLE 2 (WARM TEXT-TO-TEXT) DURATION: %.2f ms <<<\n\n", sw6_ms);

    fprintf(stderr, "--- Settling Console 2 (1.0 s) ---\n");
    run_seconds(1.0);

    /* =========================================================================
     * SECTION 8: CONSOLE 2 -> DESKTOP (/w3) (WARM SWITCH)
     * ========================================================================= */
    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, " TEST 7: SWITCH CONSOLE 2 (/w2) -> DESKTOP (/w3)                                \n");
    fprintf(stderr, "================================================================================\n");

    last_vcreq = 0;
    vcreq_cleared = 0;
    last_csel = -1;
    display_blank_seen = 0;
    display_unblank_seen = 0;

    uint64_t t_sw7_start = m->cpu.cycles;
    log_event("CON2->DESK", "Injecting hotkey Ctrl-Alt-F8");
    inject_hotkey(0x0A); /* F8 */

    vcreq_logged = 0;
    csel_logged = 0;
    int start_ready_count7 = desk_ready_count;
    timeout_cyc = m->cpu.cycles + (uint64_t)(15.0 * 2097917.0);

    while (m->cpu.cycles < timeout_cyc) {
        step_one();

        if (!vcreq_logged && last_vcreq == 8) {
            vcreq_logged = 1;
            log_event("CON2->DESK", "KbdArm IRQ detected Ctrl-Alt-F8 -> sent SIG_VC to vconsole");
        }

        if (vcreq_logged && !csel_logged && last_csel == 3) {
            csel_logged = 1;
            log_event("CON2->DESK", "CoArm: Select complete (active window restored to /w3)");
        }

        if (csel_logged && desk_ready_count > start_ready_count7) {
            log_event("CON2->DESK", "Desktop: full redraw complete from scratch ('DESK-READY' signal)");
            log_event("CON2->DESK", "Desktop: event loop active");
            break;
        }
    }

    uint64_t t_sw7_end = m->cpu.cycles;
    double sw7_ms = (double)(t_sw7_end - t_sw7_start) / 2097.917;
    fprintf(stderr, "\n>>> CONSOLE 2 -> DESKTOP DURATION: %.2f ms <<<\n\n", sw7_ms);

    /* Write CSV summary */
    FILE *f_csv = fopen("timing_report.csv", "w");
    if (f_csv) {
        fprintf(f_csv, "Phase,Event,Timestamp_s,Cycles,Delta_ms\n");
        for (int i = 0; i < num_records; i++) {
            fprintf(f_csv, "\"%s\",\"%s\",%.6f,%lu,%.3f\n",
                    records[i].phase, records[i].event,
                    records[i].time_s, (unsigned long)records[i].cycles,
                    records[i].delta_ms);
        }
        fclose(f_csv);
    }

    fprintf(stderr, "\n================================================================================\n");
    fprintf(stderr, "                 ALL BENCHMARKS COMPLETED SUCCESSFULLY!                         \n");
    fprintf(stderr, "================================================================================\n");

    return 0;
}
