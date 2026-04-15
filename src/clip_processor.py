"""
Clip processor — takes a raw Dilani clip + its brief, produces platform-specific outputs.

Pipeline per clip:
  1. Transcribe with whisper CLI (word-level timestamps via SRT).
  2. Generate platform-specific outputs via ffmpeg:
       - 9:16 / 1080x1920 if not already (crop/pad as needed)
       - Burn-in captions (word-grouped, bottom-center, glassmorphic pill aesthetic)
       - Platform cuts:
           · tiktok.mp4       full length
           · ig-reels.mp4     full length (same file used for FB Reels cross-post)
           · yt-shorts-13s.mp4  first 13 seconds only
           · yt-shorts-60s.mp4  capped at 60 seconds

Dependencies:
  - ffmpeg (required)
  - whisper (CLI; openai-whisper pip package). If unavailable, captions are
    skipped and outputs are flagged caption_pending=True.

This is intentionally pragmatic. Full Remotion-based caption rendering is Tier 2
(deferred); ffmpeg drawtext with word-grouped subtitles gets us demo-ready output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).parent.parent


@dataclass
class ProcessedClip:
    clip_id: str
    source_path: str
    outputs: dict[str, str] = field(default_factory=dict)  # platform -> path
    transcript_srt: Optional[str] = None
    caption_pending: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "source_path": self.source_path,
            "outputs": self.outputs,
            "transcript_srt": self.transcript_srt,
            "caption_pending": self.caption_pending,
            "notes": self.notes,
        }


# ── Command helpers ──────────────────────────────────────────
def _run(cmd: list[str], stdin: Optional[bytes] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, input=stdin, check=False)


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


# ── Transcription via whisper CLI ────────────────────────────
def transcribe(video_path: Path, work_dir: Path, model: str = "base.en") -> Optional[Path]:
    """Returns path to SRT or None if transcription unavailable/failed.

    Respects SKIP_TRANSCRIBE=1 to bypass whisper entirely (faster demos).
    """
    if os.environ.get("SKIP_TRANSCRIBE") == "1":
        return None
    whisper = _which("whisper")
    if not whisper:
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    # whisper writes <name>.srt next to its --output_dir
    proc = _run(
        [
            whisper,
            str(video_path),
            "--model",
            model,
            "--language",
            "en",
            "--output_format",
            "srt",
            "--output_dir",
            str(work_dir),
            "--fp16",
            "False",
            "--verbose",
            "False",
            "--word_timestamps",
            "True",
        ]
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="ignore")[-500:]
        print(f"⚠️  whisper failed: {stderr}")
        return None

    srt = work_dir / (video_path.stem + ".srt")
    return srt if srt.exists() else None


# ── Probe ────────────────────────────────────────────────────
def ffprobe_duration(video_path: Path) -> float:
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )
    try:
        return float(proc.stdout.decode().strip())
    except (ValueError, AttributeError):
        return 0.0


# ── Core ffmpeg pipeline ─────────────────────────────────────
def _reframe_and_caption_cmd(
    src: Path,
    dst: Path,
    srt: Optional[Path],
    start: float = 0.0,
    max_duration: Optional[float] = None,
) -> list[str]:
    """Build an ffmpeg command that:
    - trims to [start, start+max_duration] if max_duration given
    - scales + pads to 1080x1920 (9:16)
    - optionally burns in SRT subtitles with TikTok-ish styling
    - re-encodes h264 + aac
    """
    # 9:16 scale-and-pad. Handles horizontal or vertical input.
    scale = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    if srt and srt.exists():
        # Subtitles filter needs an escaped path
        srt_escaped = str(srt).replace(":", "\\:").replace("'", "\\'")
        style = (
            "FontName=Helvetica,FontSize=14,PrimaryColour=&HFFFFFF&,"
            "BorderStyle=3,Outline=1,Shadow=1,BackColour=&H80000000&,"
            "Alignment=2,MarginV=60"
        )
        vf = f"{scale},subtitles='{srt_escaped}':force_style='{style}'"
    else:
        vf = scale

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start > 0:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(src)]
    if max_duration is not None:
        cmd += ["-t", str(max_duration)]
    cmd += [
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    return cmd


def _produce_platform_version(
    src: Path,
    dst: Path,
    srt: Optional[Path],
    *,
    max_duration: Optional[float] = None,
) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = _reframe_and_caption_cmd(src, dst, srt, max_duration=max_duration)
    proc = _run(cmd)
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="ignore")[-400:]
        print(f"⚠️  ffmpeg error for {dst.name}: {stderr}")
        return False
    return True


# ── Main entry ───────────────────────────────────────────────
PLATFORM_SPECS: list[tuple[str, Optional[float]]] = [
    ("tiktok", None),
    ("ig-reels", None),
    ("fb-reels", None),
    ("yt-shorts-60s", 60.0),
    ("yt-shorts-13s", 13.0),
]


def process_clip(
    source_path: Path,
    clip_id: str,
    clip_type: str,
    date_str: str,
    platforms_filter: Optional[list[str]] = None,
) -> ProcessedClip:
    out_dir = ROOT / "output" / date_str / clip_id
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    result = ProcessedClip(clip_id=clip_id, source_path=str(source_path))

    # 1. Transcribe
    srt_path = transcribe(source_path, work_dir)
    if srt_path:
        result.transcript_srt = str(srt_path)
    else:
        result.caption_pending = True
        result.notes.append(
            "whisper transcription unavailable — captions not burned in. "
            "Install openai-whisper or run with a faster transcription path."
        )

    # 2. Platform renders
    # fb-reels maps to the same file as ig-reels (cross-post from IG)
    specs = [(p, d) for (p, d) in PLATFORM_SPECS if p != "fb-reels"]
    for platform, max_dur in specs:
        if platforms_filter and platform not in platforms_filter:
            continue
        if clip_type == "avatar-explainer" and platform in {"ig-reels", "fb-reels"}:
            continue  # explainers skip IG/FB per channel plan
        dst = out_dir / f"{platform}.mp4"
        ok = _produce_platform_version(source_path, dst, srt_path, max_duration=max_dur)
        if ok:
            result.outputs[platform] = str(dst)

    # fb-reels = symlink/copy of ig-reels so downstream posters have a consistent key
    ig = result.outputs.get("ig-reels")
    if ig and (not platforms_filter or "fb-reels" in (platforms_filter or [])):
        fb = str(out_dir / "fb-reels.mp4")
        try:
            if Path(fb).exists() or Path(fb).is_symlink():
                Path(fb).unlink()
            os.symlink(Path(ig).name, fb)
        except OSError:
            shutil.copy2(ig, fb)
        result.outputs["fb-reels"] = fb

    # 3. Persist manifest
    (out_dir / "processed.json").write_text(json.dumps(result.to_dict(), indent=2))
    return result
