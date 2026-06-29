# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable render-time benchmark & estimation for the Extended Matrix tools.

Engine/device/denoise-aware. Calibrate a machine ONCE (per engine + compute
device) with a few small cross-test renders, then estimate any multi-frame job:

    n_frames * (k_fixed + k_px*MP + [denoise](dn_fixed + dn_px*MP) + k_smp*MP*samples)

where MP = megapixels of the target resolution. The cross-tests separate the
costs that do NOT scale with samples (per-frame overhead + denoising) from the
per-sample cost, so estimates stay sensible as resolution/samples/denoise
change. A discarded warm-up render absorbs the one-time GPU kernel compile /
EEVEE shader build on a freshly launched Blender.

REUSE NOTES
-----------
This is intentionally generic: it knows nothing about orthogonal views,
sections, perspective scenes, etc. A consuming tool sets the engine/device and
calls `run_benchmark()` once, then `estimate()` with its own megapixels,
samples, denoise and frame count.

The functions ABOVE the "bpy-coupled layer" marker are pure Python (no bpy) and
could be lifted into a shared package later if this grows. The bpy-coupled
helpers require Blender and so this lives as an addon module (not a PyPI wheel,
which suits non-bpy deps only). To share with another EM addon today, copy this
file (the "SHIFT panel" model).

Calibration is stored at the ECOSYSTEM level (~/ExtendedMatrix), so a benchmark
run by one EM tool is reused by the others on the same machine.
"""

import os
import json
import time

# ---------------------------------------------------------------------------
# Pure core (NO bpy)
# ---------------------------------------------------------------------------

# Default cross-test design points. The sample spread must be wide enough that
# the per-sample cost rises above timing noise even on a fast GPU.
DEFAULT_RES_LO = 400
DEFAULT_RES_HI = 700
DEFAULT_SAMP_LO = 32
DEFAULT_SAMP_HI = 256


def em_home_base():
    """~/ExtendedMatrix — shared root of the Extended Matrix tool ecosystem."""
    return os.path.join(os.path.expanduser("~"), "ExtendedMatrix")


def calibration_path():
    return os.path.join(em_home_base(), "render_calibration.json")


_CACHE = None


def load_calibration(force=False):
    """Load the calibration dict (cached). Keys are 'CYCLES:GPU' etc."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    try:
        with open(calibration_path(), "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    except Exception:
        _CACHE = {}
    return _CACHE


def save_calibration(data):
    global _CACHE
    os.makedirs(em_home_base(), exist_ok=True)
    with open(calibration_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _CACHE = data


def calib_key(engine, device):
    """Calibration key: Cycles timings depend on the device, EEVEE does not."""
    if engine == 'CYCLES':
        return f"CYCLES:{device}"
    return engine


def fit_affine_v2(res_lo, res_hi, samp_lo, samp_hi, cur_dn, t1, t2, t3, t4, t5):
    """Fit the affine model from the cross-test timings (pure math).

    t1=(res_lo, samp_lo, cur_dn)  t2=(res_lo, samp_hi, cur_dn)
    t3=(res_hi, samp_lo, cur_dn)  t4=(res_lo, samp_lo, !cur_dn)
    t5=(res_hi, samp_lo, !cur_dn)   (t4/t5 None when denoise is N/A, e.g. EEVEE)
    Coefficients are clamped to >= 0 to absorb timing noise.
    """
    mp1 = (res_lo ** 2) / 1e6
    mp2 = (res_hi ** 2) / 1e6
    k_smp = max(0.0, (t2 - t1) / ((samp_hi - samp_lo) * mp1))

    if t4 is not None and t5 is not None:
        d_lo = (t1 - t4) if cur_dn else (t4 - t1)   # denoise on-off at res_lo
        d_hi = (t3 - t5) if cur_dn else (t5 - t3)   # denoise on-off at res_hi
        dn_px = max(0.0, (d_hi - d_lo) / (mp2 - mp1))
        dn_fixed = max(0.0, d_lo - dn_px * mp1)
        t_off_lo = t4 if cur_dn else t1
        t_off_hi = t5 if cur_dn else t3
    else:
        dn_px = dn_fixed = 0.0
        t_off_lo, t_off_hi = t1, t3

    base_lo = t_off_lo - k_smp * mp1 * samp_lo
    base_hi = t_off_hi - k_smp * mp2 * samp_lo
    k_px = max(0.0, (base_hi - base_lo) / (mp2 - mp1))
    k_fixed = max(0.0, base_lo - k_px * mp1)
    return {"k_fixed": k_fixed, "k_px": k_px, "k_smp": k_smp,
            "dn_fixed": dn_fixed, "dn_px": dn_px}


def per_view_seconds(rec, mpx, samples, denoise):
    """Predicted seconds for ONE frame from a calibration record."""
    if not rec:
        return 0.0
    model = rec.get("model")
    if model == "affine_v2":
        t = (rec.get("k_fixed", 0.0)
             + rec.get("k_px", 0.0) * mpx
             + rec.get("k_smp", 0.0) * mpx * samples)
        if denoise:
            t += rec.get("dn_fixed", 0.0) + rec.get("dn_px", 0.0) * mpx
        return max(0.0, t)
    if model == "affine_v1":  # legacy: denoise as k_dn*MP
        t = (rec.get("k_fixed", 0.0)
             + rec.get("k_px", 0.0) * mpx
             + (rec.get("k_dn", 0.0) * mpx if denoise else 0.0)
             + rec.get("k_smp", 0.0) * mpx * samples)
        return max(0.0, t)
    spm = rec.get("sec_per_mpx_sample", 0.0)  # oldest single-point model
    return spm * mpx * samples if spm > 0 else 0.0


def total_seconds(rec, mpx, samples, denoise, n_frames):
    pv = per_view_seconds(rec, mpx, samples, denoise)
    return pv * n_frames if pv > 0 else 0.0


def format_duration(seconds):
    """Human-friendly duration: '<1s', '45s', '3m 20s', '1h 05m'."""
    if seconds is None:
        return "?"
    s = int(round(seconds))
    if s < 1:
        return "<1s"
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


# ---------------------------------------------------------------------------
# bpy-coupled layer (requires Blender)
# ---------------------------------------------------------------------------

import bpy  # noqa: E402


def cycles_gpu_available():
    """True if Cycles has an active non-CPU compute device configured."""
    try:
        cp = bpy.context.preferences.addons['cycles'].preferences
        return (cp.compute_device_type not in ('NONE', '')) and cp.has_active_device()
    except Exception:
        return False


def effective_device(scene, device_setting):
    """Resolve the device Cycles will actually use ('GPU' or 'CPU').

    AUTO resolves to GPU when the scene is set to GPU and one is configured,
    else CPU. Keying on the *effective* device means AUTO and an explicit
    matching choice share one calibration record.
    """
    if device_setting == 'GPU':
        return 'GPU'
    if device_setting == 'CPU':
        return 'CPU'
    try:
        if scene.cycles.device == 'GPU' and cycles_gpu_available():
            return 'GPU'
    except Exception:
        pass
    return 'CPU'


def make_key(scene, engine, device_setting):
    return calib_key(engine, effective_device(scene, device_setting))


def estimate(scene, engine, device_setting, megapixels, samples, denoise, n_frames):
    """Estimate seconds for a job, or None if not calibrated for this combo."""
    rec = load_calibration().get(make_key(scene, engine, device_setting))
    if not rec:
        return None
    total = total_seconds(rec, megapixels, samples, denoise, n_frames)
    return total if total > 0 else None


def get_record(scene, engine, device_setting):
    return load_calibration().get(make_key(scene, engine, device_setting), {})


def _timed_render(scene, engine, res, samples, denoise):
    import tempfile
    r = scene.render
    r.resolution_x = res
    r.resolution_y = res
    r.resolution_percentage = 100
    if engine == 'CYCLES':
        scene.cycles.samples = samples
        scene.cycles.use_denoising = denoise
    else:
        scene.eevee.taa_render_samples = samples
    r.filepath = os.path.join(tempfile.gettempdir(), "em_render_bench.png")
    t0 = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    return time.perf_counter() - t0


def run_benchmark(scene, device_setting, *, res_lo=DEFAULT_RES_LO, res_hi=DEFAULT_RES_HI,
                  samp_lo=DEFAULT_SAMP_LO, samp_hi=DEFAULT_SAMP_HI, frame=None, obj=None):
    """Warm-up + cross-test renders on the CURRENT engine/device; fit and save.

    The caller is responsible for having set the engine/device/denoise on the
    scene before calling. Returns (record, total_measured_seconds).
    """
    engine = scene.render.engine
    r = scene.render
    saved = {
        "rx": r.resolution_x, "ry": r.resolution_y, "pct": r.resolution_percentage,
        "filepath": r.filepath, "film": r.film_transparent, "frame": scene.frame_current,
        "fmt": r.image_settings.file_format,
        "samples": (scene.cycles.samples if engine == 'CYCLES'
                    else getattr(scene.eevee, "taa_render_samples", 64)),
        "denoise": (scene.cycles.use_denoising if engine == 'CYCLES' else False),
    }
    cur_dn = saved["denoise"] if engine == 'CYCLES' else False

    try:
        r.film_transparent = True
        r.image_settings.file_format = 'PNG'
        if frame is not None:
            scene.frame_set(frame)

        # Discarded warm-up: absorbs first-launch kernel compile / shader build.
        t_warm = _timed_render(scene, engine, res_lo, samp_lo, cur_dn)
        t1 = _timed_render(scene, engine, res_lo, samp_lo, cur_dn)
        kernel_warmup = max(0.0, t_warm - t1)
        t2 = _timed_render(scene, engine, res_lo, samp_hi, cur_dn)
        t3 = _timed_render(scene, engine, res_hi, samp_lo, cur_dn)
        t4 = t5 = None
        if engine == 'CYCLES':
            t4 = _timed_render(scene, engine, res_lo, samp_lo, not cur_dn)
            t5 = _timed_render(scene, engine, res_hi, samp_lo, not cur_dn)
    finally:
        r.resolution_x = saved["rx"]
        r.resolution_y = saved["ry"]
        r.resolution_percentage = saved["pct"]
        r.filepath = saved["filepath"]
        r.film_transparent = saved["film"]
        r.image_settings.file_format = saved["fmt"]
        scene.frame_set(saved["frame"])
        if engine == 'CYCLES':
            scene.cycles.samples = saved["samples"]
            scene.cycles.use_denoising = saved["denoise"]
        else:
            try:
                scene.eevee.taa_render_samples = saved["samples"]
            except Exception:
                pass

    coeffs = fit_affine_v2(res_lo, res_hi, samp_lo, samp_hi, cur_dn, t1, t2, t3, t4, t5)
    dev = effective_device(scene, device_setting) if engine == 'CYCLES' else 'GPU/EEVEE'

    points = [
        {"res": res_lo, "samples": samp_lo, "denoise": cur_dn, "seconds": round(t1, 3)},
        {"res": res_lo, "samples": samp_hi, "denoise": cur_dn, "seconds": round(t2, 3)},
        {"res": res_hi, "samples": samp_lo, "denoise": cur_dn, "seconds": round(t3, 3)},
    ]
    if t4 is not None:
        points.append({"res": res_lo, "samples": samp_lo, "denoise": (not cur_dn), "seconds": round(t4, 3)})
        points.append({"res": res_hi, "samples": samp_lo, "denoise": (not cur_dn), "seconds": round(t5, 3)})

    rec = {
        "model": "affine_v2", "engine": engine, **coeffs,
        "kernel_warmup": round(kernel_warmup, 3),
        "device_setting": device_setting, "device_effective": dev,
        "points": points,
        "object": obj.name if obj else "",
        "polycount": len(obj.data.polygons) if obj and obj.type == 'MESH' else 0,
        "blender": bpy.app.version_string,
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
    }
    data = dict(load_calibration())
    data[make_key(scene, engine, device_setting)] = rec
    save_calibration(data)

    total_measured = t_warm + t1 + t2 + t3 + (t4 or 0.0) + (t5 or 0.0)
    return rec, total_measured
