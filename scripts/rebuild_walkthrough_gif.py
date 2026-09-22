"""Rebuild a faster walkthrough GIF with a live seconds counter overlay."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

FF = Path(
    r"C:\Users\Niku\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe"
)
ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
MP4 = MEDIA / "walkthrough.mp4"
GIF = MEDIA / "walkthrough.gif"
IMG = ROOT / "docs" / "images" / "walkthrough.gif"
PALETTE = MEDIA / "palette.png"
FONT = MEDIA / "_arial.ttf"


def main() -> None:
    if not FONT.exists():
        shutil.copy(Path(r"C:\Windows\Fonts\arial.ttf"), FONT)

    # Relative font path avoids Windows drive-letter colon parsing in drawtext.
    # Run ffmpeg with cwd=MEDIA so fontfile=_arial.ttf works.
    vf = (
        "setpts=0.5*PTS,fps=10,scale=880:-1:flags=lanczos,"
        "drawbox=x=14:y=14:w=150:h=44:color=black@0.65:t=fill,"
        r"drawtext=fontfile=_arial.ttf:fontsize=22:fontcolor=white:x=28:y=24:text='t\=%{eif\:t\:d}s'"
    )
    subprocess.check_call(
        [str(FF), "-y", "-i", "walkthrough.mp4", "-vf", vf + ",palettegen=stats_mode=diff", "palette.png"],
        cwd=MEDIA,
    )
    subprocess.check_call(
        [
            str(FF),
            "-y",
            "-i",
            "walkthrough.mp4",
            "-i",
            "palette.png",
            "-lavfi",
            vf + "[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5",
            "-loop",
            "0",
            "walkthrough_new.gif",
        ],
        cwd=MEDIA,
    )
    (MEDIA / "walkthrough_new.gif").replace(GIF)
    shutil.copy(GIF, IMG)
    PALETTE.unlink(missing_ok=True)
    # Don't commit the font copy.
    print(f"wrote {GIF} ({GIF.stat().st_size / 1e6:.2f} MB)")
    probe = subprocess.run([str(FF), "-i", str(GIF)], capture_output=True, text=True)
    for line in probe.stderr.splitlines():
        if "Duration" in line or "Video:" in line:
            print(line.strip())


if __name__ == "__main__":
    main()
