"""Short, quiet completion chime; local PCM, no TTS or network synthesis."""

import base64
import io
import math
import struct
import wave


def audio(gain=0.25):
    if type(gain) not in (int, float) or not 0 <= gain <= 1:
        raise ValueError("Chime gain must be 0..1")
    rate = 16000
    samples = []
    for i in range(int(rate * 0.65)):
        t = i / rate
        value = 0
        for start, frequency in ((0, 660), (0.18, 880)):
            age = t - start
            if 0 <= age < 0.45:
                envelope = min(age / 0.012, 1) * math.exp(-age * 10)
                value += math.sin(2 * math.pi * frequency * age) * envelope * 0.12 * gain
        samples.append(struct.pack("<h", int(32767 * value)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"".join(samples))
    return buf.getvalue()


def play():
    from .voice import rpc
    from .config import get_config

    gain = get_config()["notifications"]["chime_gain"]
    return rpc({"op": "play", "wav_base64": base64.b64encode(audio(gain)).decode()})
