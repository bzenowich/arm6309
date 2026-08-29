"""Render a module through libopenmpt's Amiga/Paula resampler, for A/B use.

libopenmpt carries Antti Lankila's Paula emulation (`render.resampler.
emulate_amiga`), which is the closest thing to a reference Amiga renderer that
can be driven headlessly. It is used here as the OTHER SIDE of the comparison in
audio/docs/modplayer.md §8 build step 0 -- not as ground truth, but as an independent
implementation whose disagreements are worth explaining.

Driven through ctypes because the distro ships libopenmpt.so.0 without headers.
"""
import ctypes, ctypes.util, sys
import numpy as np

# libopenmpt.h
RENDER_MASTERGAIN_MILLIBEL        = 1
RENDER_STEREOSEPARATION_PERCENT   = 2
RENDER_INTERPOLATIONFILTER_LENGTH = 3
RENDER_VOLUMERAMPING_STRENGTH     = 4


def _lib():
    for name in ("libopenmpt.so.0", "libopenmpt.so", ctypes.util.find_library("openmpt")):
        if not name:
            continue
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    raise SystemExit("libopenmpt not found (need libopenmpt.so.0)")


def render(path, rate=48000, seconds=None, amiga="a500"):
    lib = _lib()
    lib.openmpt_module_create_from_memory.restype = ctypes.c_void_p
    lib.openmpt_module_create_from_memory.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.openmpt_module_read_interleaved_stereo.restype = ctypes.c_size_t
    lib.openmpt_module_read_interleaved_stereo.argtypes = [
        ctypes.c_void_p, ctypes.c_int32, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16)]
    lib.openmpt_module_get_duration_seconds.restype = ctypes.c_double
    lib.openmpt_module_get_duration_seconds.argtypes = [ctypes.c_void_p]
    lib.openmpt_module_set_render_param.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int32]
    lib.openmpt_module_ctl_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.openmpt_module_destroy.argtypes = [ctypes.c_void_p]

    data = open(path, "rb").read()
    buf = ctypes.create_string_buffer(data, len(data))
    mod = lib.openmpt_module_create_from_memory(buf, len(data), None, None, None)
    if not mod:
        raise SystemExit(f"libopenmpt could not open {path}")

    # Match the card, not libopenmpt's defaults:
    #   - Paula resampling with the A500 filter, rather than a modern interpolator
    #   - hard L/R panning: audio.md §1 requirement 5, and libopenmpt softens it
    #   - no volume ramping: Paula has none, and ramping smears note attacks
    if lib.openmpt_module_ctl_set(mod, b"render.resampler.emulate_amiga", b"1") != 1:
        print("warning: emulate_amiga not accepted by this libopenmpt", file=sys.stderr)
    lib.openmpt_module_ctl_set(mod, b"render.resampler.emulate_amiga_type", amiga.encode())
    # 200, not 100: in libopenmpt 100 % is the *normal* amount of separation,
    # which for MOD still crossfeeds a third of each channel into the other side.
    # Measured: at 100 a left-only note showed R/L = 0.333. Paula does not do
    # that (audio.md §1 requirement 5), so ask for the maximum.
    lib.openmpt_module_set_render_param(mod, RENDER_STEREOSEPARATION_PERCENT, 200)
    lib.openmpt_module_set_render_param(mod, RENDER_VOLUMERAMPING_STRENGTH, 0)

    duration = lib.openmpt_module_get_duration_seconds(mod)
    want = int((seconds if seconds else duration) * rate)
    out, chunk = [], 4096
    cbuf = (ctypes.c_int16 * (chunk * 2))()
    got = 0
    while got < want:
        n = lib.openmpt_module_read_interleaved_stereo(mod, rate, min(chunk, want - got), cbuf)
        if n == 0:
            break
        out.append(np.frombuffer(cbuf, dtype=np.int16, count=int(n) * 2).copy())
        got += int(n)
    lib.openmpt_module_destroy(mod)
    if not out:
        raise SystemExit("libopenmpt rendered nothing")
    a = np.concatenate(out).reshape(-1, 2).astype(np.float64)
    return a, duration


if __name__ == "__main__":
    import wave
    a, d = render(sys.argv[1], seconds=float(sys.argv[3]) if len(sys.argv) > 3 else None)
    print(f"libopenmpt: duration {d:.2f} s, rendered {len(a)/48000:.2f} s")
    w = wave.open(sys.argv[2], "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
    w.writeframes(np.clip(a, -32768, 32767).astype("<i2").tobytes()); w.close()
