"""Create timed English Cartesia narration and mux the simulator walkthrough."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DURATION = 68


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=os.getenv("CARTESIA_ENV_FILE"))
    parser.add_argument("--reuse-audio", action="store_true")
    parser.add_argument("--video", type=Path, default=ROOT / "media/demo-silent.mp4")
    parser.add_argument("--output", type=Path, default=ROOT / "media/demo.mp4")
    args = parser.parse_args()
    settings = dict(os.environ)
    if args.env_file:
        for line in Path(args.env_file).read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                settings.setdefault(key.strip(), value.strip().strip("\"'"))
    key = settings.get("CARTESIA_API_KEY", "").strip()
    if not key:
        raise SystemExit("Set CARTESIA_API_KEY or pass --env-file with your credentials.")
    segments = json.loads((ROOT / "media/narration.json").read_text())
    inputs = []
    filters = []
    for index, segment in enumerate(segments):
        body = {
            "model_id": settings.get("CARTESIA_MODEL", "sonic-3.6"),
            "transcript": segment["text"],
            "voice": settings.get("CARTESIA_VOICE_ID", "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"),
            "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 44100},
            "language": "en", "generation_config": {"speed": 1.05, "volume": 1.0},
        }
        request = urllib.request.Request("https://api.cartesia.ai/tts/bytes", data=json.dumps(body).encode(), headers={
            "Authorization": f"Bearer {key}",
            "Cartesia-Version": settings.get("CARTESIA_API_VERSION", "2026-08-14"),
            "Content-Type": "application/json",
        })
        output = ROOT / f"media/narration-{index+1}.wav"
        if not (args.reuse_audio and output.exists()):
            with urllib.request.urlopen(request, timeout=120) as response:
                output.write_bytes(response.read())
        probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output)], text=True)
        # Slight time adjustment keeps words aligned with their demonstrated stage.
        speed = max(1, float(probe)/(segment["end"]-segment["start"]))
        inputs.extend(["-i", str(output)])
        filters.append(f"[{index+1}:a]atempo={speed:.4f},adelay={int(segment['start']*1000)}:all=1[a{index}]")
        print(f"Narration segment {index+1} generated ({float(probe):.1f}s).")
    chime_index = len(segments) + 1
    inputs.extend(["-f", "lavfi", "-i", "sine=frequency=660:duration=0.3:sample_rate=44100"])
    filters.append(f"[{chime_index}:a]volume=0.25,afade=t=in:d=0.04,afade=t=out:st=0.2:d=0.1,adelay=59500:all=1[chime]")
    streams = "".join(f"[a{i}]" for i in range(len(segments))) + "[chime]"
    filters.append(f"{streams}amix=inputs={len(segments)+1}:normalize=0,apad[audio]")
    subprocess.run(["ffmpeg", "-y", "-i", str(args.video), *inputs,
                    "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[audio]",
                    "-t", str(DURATION), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(args.output)], check=True)
    print("Narrated simulator demo ready (68s, Cartesia English voice).")


if __name__ == "__main__":
    main()
