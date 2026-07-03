import os
import struct
import subprocess
import tempfile

from gateway.routes.voice import _to_wav_16k_mono

FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")


def _make_silent_webm(path: str, seconds: float = 1.0) -> None:
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"anullsrc=r=48000:cl=mono", "-t", str(seconds), path],
        check=True,
    )


def test_to_wav_produces_16k_mono_pcm():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.webm")
        _make_silent_webm(src)
        wav = _to_wav_16k_mono(src)
        assert os.path.exists(wav)
        assert os.path.getsize(wav) > 44
        with open(wav, "rb") as f:
            header = f.read(12)
            assert header[:4] == b"RIFF"
            assert header[8:12] == b"WAVE"
            f.seek(22)
            channels = struct.unpack("<H", f.read(2))[0]
            sample_rate = struct.unpack("<I", f.read(4))[0]
            assert channels == 1, channels
            assert sample_rate == 16000, sample_rate
