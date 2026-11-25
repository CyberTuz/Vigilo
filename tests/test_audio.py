"""G.711 decoding and the DVRIP audio format."""
import math

import numpy as np

from vigilo_app.audio import decode_g711, dvrip_audio_format

ALAW, ULAW = 0x0E, 0x0A     # media bytes used by the cameras


def pcm(data, media):
    return np.frombuffer(decode_g711(bytes(data), media), np.int16).tolist()


def test_alaw_reference_values():
    assert pcm([0xD5, 0x55, 0xAA, 0x2A], ALAW) == [8, -8, 32256, -32256]


def test_ulaw_reference_values():
    assert pcm([0xFF, 0x7F, 0x80, 0x00], ULAW) == [0, 0, 32124, -32124]


def alaw_encode(sample):
    """ITU G.711 A-law encoder (the same one the fake camera uses)."""
    sign = 0x80 if sample >= 0 else 0
    if sample < 0:
        sample = -sample - 1
    sample = min(sample, 32635) >> 3
    if sample >= 32:
        seg = int(math.log2(sample)) - 4
        val = (seg << 4) | ((sample >> seg) & 0x0F)
    else:
        val = sample >> 1
    return (val | sign) ^ 0x55


def test_reference_encoder_matches_g711():
    assert [alaw_encode(s) for s in (8, -8, 32767, -32768)] == [0xD5, 0x55, 0xAA, 0x2A]


def test_alaw_round_trip_of_a_tone():
    samples = [int(12000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(400)]
    decoded = pcm([alaw_encode(s) for s in samples], ALAW)
    assert all(abs(d - s) <= max(32, abs(s) * 0.07) for d, s in zip(decoded, samples))


def test_audio_format():
    assert dvrip_audio_format(ALAW, 2) == ("alaw", 8000)
    assert dvrip_audio_format(ULAW, 4) == ("mulaw", 16000)
    assert dvrip_audio_format(ALAW, 99) == ("alaw", 8000)     # unknown rate code: 8 kHz
