"""Parent-facing media: a spoken notice, and one explainer video.

Districts already write these letters. The letters go unread -- wrong reading
level, wrong language, and a family that most needs them is often the least
able to parse a statutory notice. Voice and video are not decoration here; they
are the difference between a notice sent and a notice received.

Cost discipline is deliberate and load-bearing:

  Chirp  runs per notice. It is cheap enough to.
  Veo    runs ONCE for the whole district and is cached on disk. The timeline
         explanation is identical for every family, so generating it per case
         would be pure waste. Never call it from a demo loop.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import settings
from .telemetry import span

VEO_MODEL = "veo-3.1-fast-generate-001"
MEDIA_DIR = Path("data/media")

# Chirp3-HD, by language. A district serves a fixed set of home languages, so
# this is a lookup rather than anything clever.
VOICES = {
    "en-US": "en-US-Chirp3-HD-Achernar",
    "es-US": "es-US-Chirp3-HD-Achernar",
    "vi-VN": "vi-VN-Chirp3-HD-Achernar",
    "zh-CN": "cmn-CN-Chirp3-HD-Achernar",
}


class MediaUnavailable(RuntimeError):
    """Generation failed. Callers fall back to text; they never fake a file."""


def speak(text: str, *, language: str = "es-US", out: Path | None = None) -> Path:
    """Render a notice as speech with a Chirp3-HD voice.

    Cached by content hash: the same notice in the same language is never
    synthesised twice, which matters when a tick re-runs.
    """
    from google.api_core.client_options import ClientOptions
    from google.cloud import texttospeech as tts

    voice_name = VOICES.get(language, VOICES["en-US"])
    digest = hashlib.sha256(f"{language}|{voice_name}|{text}".encode()).hexdigest()[:16]
    path = out or MEDIA_DIR / f"notice-{language}-{digest}.mp3"

    with span("media.speak", language=language, voice=voice_name) as s:
        if path.exists():
            s.set_attribute("cached", True)
            return path
        # Bill and quota against OUR project, not whatever the local ADC file
        # happens to name. Without this the call fails against a completely
        # unrelated project and the error names that project, not this one --
        # a genuinely confusing five minutes.
        client = tts.TextToSpeechClient(client_options=ClientOptions(
            quota_project_id=settings.project_id or None))
        resp = client.synthesize_speech(
            input=tts.SynthesisInput(text=text),
            voice=tts.VoiceSelectionParams(language_code=language, name=voice_name),
            audio_config=tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.MP3,
                # Slightly slow: this is a legal notice being read to someone
                # who may be hearing the terms for the first time.
                speaking_rate=0.92,
            ),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.audio_content)
        s.set_attribute("cached", False)
        s.set_attribute("bytes", len(resp.audio_content))
        return path



def _bucket_name() -> str:
    return os.environ.get("MEDIA_BUCKET", "").strip()


def persist(path: Path) -> str:
    """Put generated media somewhere it will still exist on the next request.

    Chirp runs inside the TICK, in a Cloud Run job container, and wrote to that
    container's local disk. The container is destroyed when the job finishes,
    so the path survived in Firestore while the bytes did not -- and the
    dashboard, a different container entirely, offered a player for twenty
    notices that could only ever 404.

    With MEDIA_BUCKET set the object is uploaded and a gs:// URI returned.
    Without it the local path is returned unchanged, which is correct for a
    laptop where the file really is still there.
    """
    bucket = _bucket_name()
    if not bucket:
        return str(path)
    from google.cloud import storage

    client = storage.Client(project=settings.project_id or None)
    blob = client.bucket(bucket).blob(f"notices/{path.name}")
    if not blob.exists():
        blob.upload_from_filename(str(path), content_type="audio/mpeg")
    return f"gs://{bucket}/notices/{path.name}"


def media_exists(ref: str | None) -> bool:
    """Whether there are actually bytes behind a recorded reference."""
    if not ref:
        return False
    if ref.startswith("gs://"):
        from google.cloud import storage

        bucket, _, name = ref[5:].partition("/")
        try:
            client = storage.Client(project=settings.project_id or None)
            return client.bucket(bucket).blob(name).exists()
        except Exception:
            return False
    return Path(ref).is_file()


def media_bytes(ref: str) -> bytes:
    """Read media from wherever it was persisted."""
    if ref.startswith("gs://"):
        from google.cloud import storage

        bucket, _, name = ref[5:].partition("/")
        client = storage.Client(project=settings.project_id or None)
        return client.bucket(bucket).blob(name).download_as_bytes()
    return Path(ref).read_bytes()


EXPLAINER_PROMPT = (
    "A calm, plain animated explainer for parents. A simple horizontal timeline "
    "on a light background shows four labelled milestones left to right: "
    "'You sign consent', 'District evaluates', 'Team meets', 'Plan agreed'. "
    "A soft green marker moves along the line and pauses at each milestone. "
    "Clean flat design, no text beyond the four labels, no people, warm and "
    "reassuring, institutional but human."
)


def explainer(*, out: Path | None = None, prompt: str = EXPLAINER_PROMPT) -> Path:
    """Generate the district-wide timeline explainer. Once. Ever.

    Returns the cached file if it exists. The evaluation timeline is the same
    for every family, so this is district infrastructure, not per-case output.
    """
    path = out or MEDIA_DIR / "evaluation-timeline.mp4"
    with span("media.explainer", model=VEO_MODEL) as s:
        if path.exists():
            s.set_attribute("cached", True)
            return path

        import time

        from .genai import client

        c = client()
        from google.genai import types

        # Shortest useful clip, one video, no audio -- the Chirp narration is
        # generated separately per language, so a baked-in English soundtrack
        # would be worse than none.
        op = c.models.generate_videos(
            model=VEO_MODEL, prompt=prompt,
            config=types.GenerateVideosConfig(
                duration_seconds=6, number_of_videos=1,
                aspect_ratio="16:9", resolution="720p",
                person_generation="dont_allow", generate_audio=False,
            ),
        )
        waited = 0
        while not op.done and waited < 300:
            time.sleep(10)
            waited += 10
            op = c.operations.get(op)
        if not op.done:
            raise MediaUnavailable(f"{VEO_MODEL} did not finish in {waited}s")

        videos = getattr(getattr(op, "response", None), "generated_videos", None) or []
        if not videos:
            raise MediaUnavailable(f"{VEO_MODEL} returned no video: {op}")

        path.parent.mkdir(parents=True, exist_ok=True)
        video = videos[0].video

        # Vertex and the Gemini Developer API return the result differently, and
        # files.download() raises "only supported in the Gemini Developer client"
        # on Vertex -- after the expensive generation has already succeeded.
        data = getattr(video, "video_bytes", None)
        if data:
            path.write_bytes(data)
        elif getattr(video, "uri", None):
            uri = video.uri
            if uri.startswith("gs://"):
                from google.cloud import storage
                bucket, _, blob = uri[5:].partition("/")
                storage.Client(project=settings.project_id).bucket(bucket) \
                    .blob(blob).download_to_filename(str(path))
            else:
                raise MediaUnavailable(f"unrecognised video uri: {uri}")
        else:
            raise MediaUnavailable(
                f"video returned neither bytes nor uri: {dir(video)}")
        s.set_attribute("cached", False)
        s.set_attribute("seconds", waited)
        return path
