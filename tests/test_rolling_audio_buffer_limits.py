from __future__ import annotations

import numpy as np

from voice_comms_dcs.stt_whisper_engine import RollingAudioBuffer


def test_pre_roll_preserved():
    buffer = RollingAudioBuffer(sample_rate=10, pre_roll_ms=500, max_context_ms=2000)
    buffer.append(np.arange(10, dtype=np.float32), source_rate=10)
    buffer.start_ptt()
    utterance = buffer.stop_ptt()
    assert utterance.size == 5


def test_active_recording_capped_to_max_context():
    buffer = RollingAudioBuffer(sample_rate=10, pre_roll_ms=0, max_context_ms=1000)
    buffer.start_ptt()
    for value in range(5):
        buffer.append(np.full(5, value, dtype=np.float32), source_rate=10)
    assert buffer.active_seconds <= 1.0
    utterance = buffer.stop_ptt()
    assert utterance.size <= 10
    assert utterance.size == buffer.max_context_samples
    assert buffer.active_seconds == 0.0


def test_empty_stop_returns_empty_and_resets():
    buffer = RollingAudioBuffer(sample_rate=10, pre_roll_ms=0, max_context_ms=1000)
    buffer.start_ptt()
    utterance = buffer.stop_ptt()
    assert utterance.size == 0
    assert not buffer.recording
