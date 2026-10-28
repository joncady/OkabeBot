# Japanese-reference English voice experiment

This is an isolated comparison, not a deployed voice change or a trained model.
The installed four-character worker continues using its existing private English
and synthetic references. Private reference clips and generated comparison WAVs
are not committed or uploaded by this experiment.

## Approach

Qwen3-TTS Base can condition on a speaker embedding without including reference
speech tokens. In the tested MLX-Audio 0.6.1 implementation, passing `ref_audio`
with `ref_text=None` bypasses `_generate_icl` and extracts the speaker embedding.
Passing audio **and** its transcript selects ICL. This was checked in the installed
implementation, rather than assuming the upstream `x_vector_only_mode` keyword
works in the MLX API.

```python
model.generate(
    text=english_text,
    ref_audio=private_japanese_reference,
    ref_text=None,
    lang_code="English",
    stream=True,
    streaming_interval=0.32,
    temperature=0.3,
)
```

The comparison uses the existing 0.6B Base 4-bit model on the Mac, a fixed seed,
English output language, and three modes for each character: existing English
reference plus transcript; a short Japanese reference with speaker-only
conditioning; and three Japanese clips concatenated with speaker-only
conditioning. This requires no training or new cloud hardware.

Removing reference speech tokens does **not** guarantee accent removal, phoneme
independence or matching pitch/tone. A speaker embedding can still carry accent
and delivery characteristics. Longer references can change the result rather
than monotonically improve it. Fine-tuning is not justified by this small trial.

## Warm comparison observed 2026-10-27

All rows synthesize the same sentence, “Please bring the blue light closer, then
turn the volume down.” The model received a warm-up before measured generation.
Reference-specific conditioning cost remains included. First PCM is measured at
the generator, excluding button capture, transcription, conversation, transport
and speaker buffering. Total synthesis is not end-to-end response latency.

| Character | Reference mode | First PCM | Total synthesis | Audio length | ASR word error rate |
| --- | --- | ---: | ---: | ---: | ---: |
| Okabe | English ICL control | 0.753 s | 2.506 s | 3.44 s | 0% |
| Okabe | Japanese short, speaker only | 0.395 s | 3.247 s | 5.44 s | 0% |
| Okabe | Japanese expanded, speaker only | 0.858 s | 2.975 s | 4.64 s | 0% |
| Kurisu | English ICL control | 0.511 s | 2.313 s | 3.44 s | 0% |
| Kurisu | Japanese short, speaker only | 0.387 s | 2.426 s | 4.64 s | 9.1% |
| Kurisu | Japanese expanded, speaker only | 0.217 s | 2.529 s | 4.40 s | 0% |

Local base.en ASR added an extra trailing “you” on the short Kurisu sample. ASR
scores assess this one sentence's intelligibility, not accent or character
resemblance. These are single observations, not latency distributions. A separate
first comparison included a 6.487-second cold start on the first Okabe English
control; it must not be compared with subsequent warm rows as a mode advantage.

The private listening page includes both sentences and all three modes. Human
review must assess English accent, resemblance, tone, clarity and unwanted words
before choosing a mode. Keep the existing voices until that review. A broader
phonetic set and repeated warm runs are needed before claiming a stable quality
or latency improvement.

References: [official Qwen3-TTS cloning modes](https://github.com/QwenLM/Qwen3-TTS)
and [MLX-Audio Qwen implementation](https://github.com/Blaizzy/mlx-audio/tree/main/mlx_audio/tts/models/qwen3_tts).


Listening checkpoint: the user preferred the new speaker-only Japanese-reference
English samples and accepted the current latency tradeoff. The comparison page
also includes the original short, combined and individual Japanese clips for
reference. Voice-synthesis optimization is tracked in the GitHub project, including
repeatable cold/warm metrics, pronunciation coverage, caching and switching.
This evaluates candidates; it does not replace the installed reference manifest.
