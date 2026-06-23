"""Tests for split-capable, frame-snapped override application in reframe_cache.

Covers the NEW behavior of `apply_overrides_to_regions` (domain: force-Tight/Wide
override that SPLITS a region at a frame-snapped boundary so the user can recolor an
arbitrary sub-range — a shot the detector/merge fused away). The old behavior only
recolored whole regions by midpoint and could never re-cut, so a missing boundary was
unrecoverable.

CRITICAL INVARIANT (REFRAME_FPS_GRID_INVARIANT.md): every split boundary MUST be
frame-snapped to the source NATIVE fps grid — t = round(t*fps)/fps — so render's
trim=start_frame=round(t0*fps) lands on an exact native frame (Δ=0, no flash on ≠25fps).
"""

from app.editor.reframe_cache import apply_overrides_to_regions
from app.models import CropOverride, SourceInterval
from app.pipeline.stage3_reframe import TrackPoint, TrackRegion

FPS_2997 = 30000.0 / 1001.0  # 29.97 — the classic ≠25fps case the invariant guards


# Sub-nanoframe tolerance: a snapped boundary t=round(x)/fps satisfies round(t*fps)==x, so the
# render trim (start_frame=round(t0*fps)) lands on the EXACT native frame. With exact-rational fps
# (30000/1001) the float roundtrip leaves ~1e-15 residue — well under any frame impact (DoD: <0.01).
_FRAME_EPS = 1e-9


def _frame_error(t: float, fps: float) -> float:
    """|t*fps - round(t*fps)| — ~0 means the boundary lands on an exact native frame."""
    return abs(t * fps - round(t * fps))


def _three_shots() -> list[TrackRegion]:
    # interval-relative: shot#1 [0,2) fill, shot#2 [2,4) fill, shot#3 [4,6) fit
    return [
        TrackRegion(t0=0.0, t1=2.0, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=0.4),)),
        TrackRegion(t0=2.0, t1=4.0, mode="fill", points=(TrackPoint(t=2.0, mode="fill", cx=0.6),)),
        TrackRegion(t0=4.0, t1=6.0, mode="fit", points=()),
    ]


def test_partial_override_splits_region_into_three_frame_snapped():
    # (a) A partial override STRICTLY inside a single region splits it into 3 pieces;
    # every resulting boundary is frame-snapped to the source native fps (29.97).
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    # One big fill region whose own boundaries are ALREADY on the native frame grid (exactly what
    # reframe_segment emits: t = cut_frame/fps). Frame 0 .. frame 180 at 29.97.
    region_end = 180 / FPS_2997  # ≈ 6.006s — on the grid
    regions = [
        TrackRegion(
            t0=0.0, t1=region_end, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=0.4),)
        )
    ]
    # Override covers an arbitrary mid sub-range (source 11.4..14.3, i.e. interval-relative
    # 1.4..4.3) — NOT aligned to any region boundary and NOT on the fps grid.
    ov = [CropOverride(source_start=11.4, source_end=14.3, mode="fit")]
    out = apply_overrides_to_regions(regions, ov, iv, fps=FPS_2997)

    assert len(out) == 3, "partial override must split the region into 3 pieces"
    # piece order + modes: keep | override | keep
    assert [r.mode for r in out] == ["fill", "fit", "fill"]
    # outer pieces retain the original mode AND points; outer edges = region's own (snapped) edges
    assert out[0].t0 == 0.0 and out[0].points == regions[0].points
    assert out[2].t1 == region_end and out[2].points == regions[0].points
    # contiguous, no gaps/overlaps
    assert out[0].t1 == out[1].t0
    assert out[1].t1 == out[2].t0
    # middle piece is the override mode with no fill trajectory (fit)
    assert out[1].mode == "fit" and out[1].points == ()
    # EVERY boundary is frame-snapped (Δ frame == 0) — the whole point of this change
    for r in out:
        assert _frame_error(r.t0, FPS_2997) < _FRAME_EPS, f"unsnapped t0={r.t0}"
        assert _frame_error(r.t1, FPS_2997) < _FRAME_EPS, f"unsnapped t1={r.t1}"
    # the inner boundaries are the snapped override edges (rel 1.4 / 4.3)
    a = round(1.4 * FPS_2997) / FPS_2997
    b = round(4.3 * FPS_2997) / FPS_2997
    assert out[1].t0 == a
    assert out[1].t1 == b


def test_whole_region_override_recolors_without_split():
    # (b) An override fully covering a region recolors it in place — NO split, same
    # boundaries, same count. Proves backward-compat (existing clips/tests unaffected).
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    # override fully covers shot#2 [2,4) (source 12..14)
    ov = [CropOverride(source_start=12.0, source_end=14.0, mode="fit")]
    out = apply_overrides_to_regions(regions, ov, iv, fps=FPS_2997)

    assert len(out) == 3, "whole-region override must NOT split — same region count"
    assert (out[0].t0, out[0].t1, out[0].mode) == (0.0, 2.0, "fill")
    assert out[0].points == regions[0].points
    assert (out[1].t0, out[1].t1, out[1].mode) == (2.0, 4.0, "fit")  # recolored, boundaries kept
    assert out[1].points == ()
    assert (out[2].t0, out[2].t1, out[2].mode) == (4.0, 6.0, "fit")
    assert out[2].points == regions[2].points


def test_override_on_exact_boundary_no_zero_length_slivers():
    # (c) An override whose edges coincide with region boundaries must not produce
    # zero/negative-length pieces. Override = exactly shot#2 [2,4) (source 12..14).
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [CropOverride(source_start=12.0, source_end=14.0, mode="fit")]
    out = apply_overrides_to_regions(regions, ov, iv, fps=FPS_2997)

    # exactly 3 regions — no slivers from the touching boundaries of shot#1 / shot#3
    assert len(out) == 3
    for r in out:
        assert r.t1 > r.t0, f"zero/negative-length sliver: ({r.t0}, {r.t1})"
    # shot#2 fully covered → recolored (not re-cut)
    assert out[1].mode == "fit"
    assert (out[1].t0, out[1].t1) == (2.0, 4.0)
    # shots #1/#3 untouched (no slivers introduced)
    assert out[0] == regions[0]
    assert out[2] == regions[2]


def test_partial_override_last_wins_across_overlap():
    # last-wins: when two overrides hit the SAME region, the LAST one defines the recolor.
    # Here the override partially overlaps a single fill region → split, middle uses the
    # LAST override's mode/center.
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = [
        TrackRegion(t0=0.0, t1=6.0, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=0.4),))
    ]
    ov = [
        CropOverride(source_start=12.0, source_end=14.0, mode="fit"),
        CropOverride(source_start=12.0, source_end=14.0, mode="fill", center=0.9),
    ]
    out = apply_overrides_to_regions(regions, ov, iv, fps=FPS_2997)
    # middle piece (source 12..14 → rel 2..4, both interior to [0,6)) recolored by the LAST
    # override. Its boundaries are frame-snapped to the 29.97 grid (rel 2.0/4.0 are NOT on it).
    mid = [r for r in out if r.mode == "fill" and r.points and r.points[0].cx == 0.9]
    assert len(mid) == 1, "last override must win on the covered sub-range"
    # the recolored sub-range's (interior, new) boundaries are frame-snapped to the native grid
    assert mid[0].t0 == round(2.0 * FPS_2997) / FPS_2997
    assert mid[0].t1 == round(4.0 * FPS_2997) / FPS_2997
    assert _frame_error(mid[0].t0, FPS_2997) < _FRAME_EPS
    assert _frame_error(mid[0].t1, FPS_2997) < _FRAME_EPS


def test_multiple_overrides_on_one_region_each_applies():
    # Regression: a single "last override wins for the WHOLE region" would silently DROP every
    # edit but the last. The editor "Split here" flow emits exactly this — two NON-overlapping
    # sub-range overrides on one detector-fused region — so BOTH must survive (each its own mode).
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    region_end = 180 / FPS_2997  # on the 29.97 grid (cut_frame/fps), like reframe_segment emits
    regions = [
        TrackRegion(
            t0=0.0, t1=region_end, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=0.5),)
        )
    ]
    ov = [
        CropOverride(source_start=10.5, source_end=11.5, mode="fit"),  # rel 0.5..1.5
        CropOverride(source_start=13.0, source_end=14.0, mode="fill", center=0.9),  # rel 3.0..4.0
    ]
    out = apply_overrides_to_regions(regions, ov, iv, fps=FPS_2997)
    modes = [r.mode for r in out]
    assert "fit" in modes, "the FIRST override must not be dropped by the second"
    fill09 = [r for r in out if r.mode == "fill" and r.points and r.points[0].cx == 0.9]
    assert len(fill09) == 1, "the SECOND, non-overlapping override must also apply"
    # contiguous tiling of the original region, every boundary frame-snapped (no flash)
    assert out[0].t0 == 0.0 and out[-1].t1 == region_end
    for prev, nxt in zip(out, out[1:], strict=False):
        assert prev.t1 == nxt.t0  # no gaps/overlaps
    for r in out:
        assert _frame_error(r.t0, FPS_2997) < _FRAME_EPS, f"unsnapped t0={r.t0}"
        assert _frame_error(r.t1, FPS_2997) < _FRAME_EPS, f"unsnapped t1={r.t1}"
