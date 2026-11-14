import os
import math
import wave
import tempfile
import subprocess
from typing import List, Dict, Any
import numpy as np
import imageio_ffmpeg
from faster_whisper import WhisperModel

_whisper_model = None

def get_whisper_model() -> WhisperModel:
    """Lazy loads faster-whisper small model on CPU with int8 compute."""
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper_model


def format_seconds(seconds: float) -> str:
    """Formats seconds into HH:MM:SS."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def convert_audio_to_wav(input_bytes: bytes, original_ext: str = "mp3") -> str:
    """
    Uses ffmpeg (via imageio-ffmpeg) to convert audio to 16kHz mono 16-bit PCM WAV.
    Returns path to temporary WAV file.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Create temporary input and output files
    with tempfile.NamedTemporaryFile(suffix=f".{original_ext}", delete=False) as in_file:
        in_file.write(input_bytes)
        in_path = in_file.name

    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)

    try:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", in_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            out_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio conversion failed: {result.stderr.decode('utf-8', errors='ignore')}")
        return out_path
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)


def process_audio(audio_bytes: bytes, original_ext: str = "mp3") -> List[Dict[str, Any]]:
    """
    Processes audio by:
    1. Converting to 16kHz mono WAV via ffmpeg.
    2. Reading PCM samples into numpy array (bypassing PyAV version conflicts).
    3. Transcribing with faster-whisper (small model).
    4. Returning structured segments with timestamps and confidence scores.
    """
    wav_path = convert_audio_to_wav(audio_bytes, original_ext)
    try:
        # Read 16kHz mono PCM frames into numpy float32 array
        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            duration = wf.getnframes() / float(wf.getframerate())
            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        model = get_whisper_model()
        segments, info = model.transcribe(audio_np, beam_size=5)

        results: List[Dict[str, Any]] = []
        for idx, seg in enumerate(segments, start=1):
            text = seg.text.strip()
            if not text:
                continue

            start_ts = format_seconds(seg.start)
            end_ts = format_seconds(seg.end)
            timestamp_str = f"{start_ts} - {end_ts}"

            # Convert avg_logprob to confidence percentage
            try:
                confidence = round(math.exp(seg.avg_logprob) * 100.0, 2)
                confidence = max(0.0, min(100.0, confidence))
            except Exception:
                confidence = 85.0

            results.append({
                "text": text,
                "page_or_segment": f"s{idx}",
                "line_number": idx,
                "timestamp_str": timestamp_str,
                "confidence": confidence,
                "engine": "faster_whisper",
            })

        # If audio has no spoken words (e.g. ambient tone or tone test), record an audio segment entry
        if len(results) == 0:
            results.append({
                "text": "[Audio recorded - no speech detected]",
                "page_or_segment": "s1",
                "line_number": 1,
                "timestamp_str": f"00:00 - {format_seconds(duration)}",
                "confidence": 100.0,
                "engine": "faster_whisper",
            })

        return results
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
