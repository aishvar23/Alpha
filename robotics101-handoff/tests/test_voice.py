"""M02.2: character voice layer — backends, content-hash cache, ElevenLabs key safety + budget, timeline, QA."""

import base64
import json
import shutil
import subprocess
import wave
from types import SimpleNamespace
from pathlib import Path

import pytest

from robotics101.characters import load_registry
from robotics101.cli import main
from robotics101.narration.captions import parse_srt, validate_srt
from robotics101.qa import QaReport
from robotics101.voice import ElevenLabsBackend, VoiceCache, VoiceError, select_backend, voice_episode
from robotics101.voice import backends as B
from robotics101.voice.dialogue import RATE, plan_lines
from robotics101.voice.qa import check_dialogue

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"
FAKE_KEY = "sk_test_FAKE_0123456789abcdef_DO_NOT_LEAK"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.fixture
def cartoon():
    return json.loads(CARTOON.read_text(encoding="utf-8"))


@pytest.fixture
def small(cartoon):
    """Two scenes, a few lines each: fast end-to-end runs."""
    s = json.loads(json.dumps(cartoon))
    s["scenes"] = s["scenes"][:2]
    for sc in s["scenes"]:
        lines = [b for b in sc["beats"] if b["type"] == "line"][:3]
        others = [b for b in sc["beats"] if b["type"] != "line"][:2]
        sc["beats"] = others[:1] + lines + others[1:]
    return s


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.delenv(B.KEY_ENV, raising=False)
    monkeypatch.setenv("ROBOTICS101_TTS_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(B.time, "sleep", lambda s: None)


class CountingFixture(B.FixtureBackend):
    calls = 0

    def render(self, req, out_path):
        type(self).calls += 1
        super().render(req, out_path)


def _wav_frames(p: Path) -> int:
    with wave.open(str(p), "rb") as w:
        return w.getnframes()


@needs_ffmpeg
def test_fixture_voice_run_timeline_stems_captions(small, tmp_path):
    reg, cache = load_registry(), VoiceCache(tmp_path / "c")
    CountingFixture.calls = 0
    doc = voice_episode(small, reg, tmp_path / "o", CountingFixture(), cache, log=lambda m: None)
    n_lines = sum(b["type"] == "line" for s in small["scenes"] for b in s["beats"])
    assert CountingFixture.calls == n_lines and doc["schemaVersion"] == "robotics101.timing/2"
    t = 0.0
    for s in doc["scenes"]:
        assert s["scene_start_s"] == pytest.approx(t, abs=1e-3)
        assert abs(s["scene_duration_s"] * 30 - round(s["scene_duration_s"] * 30)) < 1e-4    # whole frames
        assert _wav_frames(tmp_path / "o" / s["dialogue_wav"]) == round(s["scene_duration_s"] * RATE)
        lines = [b for b in s["beats"] if b["type"] == "line"]
        assert all(a["end_s"] <= b["start_s"] for a, b in zip(lines, lines[1:]))
        t = s["scene_end_s"]
    cues = parse_srt((tmp_path / "o" / "captions.srt").read_text())
    assert not validate_srt(cues) and cues[0].text.startswith(("Bolt: ", "Maya: "))
    # rerun: everything from cache, byte-identical outputs (determinism)
    before = (tmp_path / "o" / "timing.json").read_text(), (tmp_path / "o" / "captions.srt").read_bytes()
    stem = (tmp_path / "o" / doc["scenes"][0]["dialogue_wav"]).read_bytes()
    doc2 = voice_episode(small, reg, tmp_path / "o", CountingFixture(), cache, log=lambda m: None)
    assert CountingFixture.calls == n_lines and doc2["cost"]["cachedLines"] == n_lines
    after = (tmp_path / "o" / "timing.json").read_text(), (tmp_path / "o" / "captions.srt").read_bytes()
    assert json.loads(before[0])["scenes"] == json.loads(after[0])["scenes"] and before[1] == after[1]
    assert (tmp_path / "o" / doc["scenes"][0]["dialogue_wav"]).read_bytes() == stem
    rep = QaReport("ep", "voice", str(tmp_path / "o"))
    check_dialogue(rep, tmp_path / "o")
    assert not rep.failures, [c.message for c in rep.failures]
    assert any(c.id == "dialogue.production_voice" for c in rep.warnings)


def test_cache_key_tracks_text_voice_settings_not_fx():
    reg = load_registry()
    bolt = json.loads(json.dumps(reg.get("bolt").voice))
    el = ElevenLabsBackend()
    k = el.request(bolt, "Hello!").key
    assert el.request(bolt, "Hello!").key == k and el.request(bolt, "Hello !").key != k
    bolt2 = json.loads(json.dumps(bolt)); bolt2["elevenlabs"]["voiceId"] = "other"
    bolt3 = json.loads(json.dumps(bolt)); bolt3["elevenlabs"]["settings"]["stability"] = 0.9
    bolt4 = json.loads(json.dumps(bolt)); bolt4["elevenlabs"]["fx"] = []
    assert el.request(bolt2, "Hello!").key != k and el.request(bolt3, "Hello!").key != k
    assert el.request(bolt4, "Hello!").key == k        # fx is post-processing: changing it never re-bills
    assert B.EspeakBackend().request(bolt, "Hello!").key != k


def test_select_backend_auto_order(monkeypatch):
    monkeypatch.setattr(B.KokoroBackend, "available", lambda self: (False, "no model"))
    b, skipped = select_backend("auto")
    assert b.name == "espeak" and any("ELEVENLABS_API_KEY is not set" in x for x in skipped)
    monkeypatch.setattr(B.KokoroBackend, "available", lambda self: (True, "ok"))
    assert select_backend("auto")[0].name == "kokoro"
    with pytest.raises(VoiceError, match="unavailable"):
        select_backend("elevenlabs")
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    b, skipped = select_backend("auto")
    assert b.name == "elevenlabs" and skipped == []


def test_no_key_means_no_network(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(B, "_sdk_client", boom)
    assert main(["voices", "list"]) == 2
    assert "not set" in capsys.readouterr().err
    with pytest.raises(VoiceError, match="no ElevenLabs call"):
        ElevenLabsBackend().render(ElevenLabsBackend().request(load_registry().get("maya").voice, "Hi"), Path("x"))


@pytest.fixture(scope="module")
def mp3_bytes(tmp_path_factory):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg required")
    p = tmp_path_factory.mktemp("mp3") / "tone.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=1.2",
                    "-ar", "44100", "-b:a", "128k", str(p)], check=True)
    return p.read_bytes()


def _alignment(text: str, per_char: float = 0.05) -> dict:
    return {"characters": list(text), "character_start_times_seconds": [i * per_char for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * per_char for i in range(len(text))]}


class FakeClient:
    """Stands in for ``elevenlabs.ElevenLabs``: records calls, returns audio + alignment, can fail first."""

    def __init__(self, payload: bytes, fail: list | None = None):
        self.payload, self.calls, self.fail = payload, [], list(fail or [])
        self.text_to_speech = SimpleNamespace(convert_with_timestamps=self._tts, convert=self._no_plain_convert)
        self.voices = SimpleNamespace(get_all=lambda: SimpleNamespace(voices=[SimpleNamespace(
            voice_id="v1", name="Ember", category="professional", labels={"age": "young"}, preview_url=None)]))
        self.user = SimpleNamespace(subscription=SimpleNamespace(get=lambda: SimpleNamespace(model_dump=lambda: {
            "tier": "creator", "status": "active", "character_count": 1000, "character_limit": 131000,
            "next_character_count_reset_unix": 1})))
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(model_dump=lambda: {
            "model_id": "eleven_v4", "name": "Eleven v4", "can_do_text_to_speech": True,
            "model_rates": {"character_cost_multiplier": 1.0}})])

    def _no_plain_convert(self, *a, **k):
        raise AssertionError("use convert_with_timestamps (one billed call gives audio + timings)")

    def _tts(self, voice_id, **kw):
        self.calls.append((voice_id, kw))
        if self.fail:
            raise self.fail.pop(0)
        al = _alignment(kw["text"])
        return SimpleNamespace(audio_base_64=base64.b64encode(self.payload).decode(),
                               alignment=SimpleNamespace(model_dump=lambda: al))


def _api_error(code: int, body):
    from elevenlabs.core.api_error import ApiError
    return ApiError(status_code=code, body=body)


def approved_registry():
    reg = load_registry()
    for cid in ("bolt", "maya"):
        reg.get(cid).voice["elevenlabs"]["approved"] = True
    return reg


def test_unapproved_elevenlabs_voices_block_full_episode(small, tmp_path, monkeypatch, mp3_bytes):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes)
    with pytest.raises(VoiceError, match="not owner-approved"):
        voice_episode(small, load_registry(), tmp_path / "o", ElevenLabsBackend(client_factory=lambda: fake),
                      VoiceCache(tmp_path / "c"), log=lambda m: None)
    assert fake.calls == []


def test_voices_samples_need_explicit_yes_then_write_two_short_lines(tmp_path, monkeypatch, mp3_bytes, capsys):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes)
    monkeypatch.setattr(B, "_sdk_client", lambda: fake)
    assert main(["voices", "samples", "--out-dir", str(tmp_path / "s")]) == 2       # no --yes: nothing spent
    assert fake.calls == [] and not (tmp_path / "s").exists() and "--yes" in capsys.readouterr().err
    assert main(["voices", "audition", "bolt", "--out", str(tmp_path / "a.wav")]) == 2
    assert fake.calls == []
    assert main(["voices", "samples", "--out-dir", str(tmp_path / "s"), "--yes"]) == 0
    assert sorted(p.name for p in (tmp_path / "s").iterdir()) == ["elevenlabs-sample-bolt.wav",
                                                                  "elevenlabs-sample-maya.wav"]
    assert len(fake.calls) == 2 and sum(len(kw["text"]) for _, kw in fake.calls) < 250


def test_voices_account_is_non_speech(monkeypatch, mp3_bytes, capsys):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes)
    monkeypatch.setattr(B, "_sdk_client", lambda: fake)
    assert main(["voices", "account"]) == 0
    out = capsys.readouterr().out
    assert "130000 remaining" in out and "eleven_v4" in out and fake.calls == []
    assert FAKE_KEY not in out


def test_key_is_loaded_from_project_dotenv_without_exporting_it_first(tmp_path, monkeypatch, mp3_bytes):
    env = tmp_path / ".env"
    env.write_text(f"{B.KEY_ENV}={FAKE_KEY}\n")
    monkeypatch.setenv(B.DOTENV_ENV, str(env))
    seen = {}

    def factory():
        import os
        seen["key"] = os.environ.get(B.KEY_ENV)
        return FakeClient(mp3_bytes)
    el = ElevenLabsBackend(client_factory=factory)
    assert el.available()[0] is True
    el.list_voices()
    assert seen["key"] == FAKE_KEY
    assert FAKE_KEY not in repr(el)
    monkeypatch.delenv(B.KEY_ENV)
    monkeypatch.setenv(B.DOTENV_ENV, str(tmp_path / "missing.env"))
    assert ElevenLabsBackend().available()[0] is False


def test_v4_request_uses_only_supported_settings_and_default_model():
    voice = {"elevenlabs": {"voiceId": "abc", "modelId": "eleven_v4",
                            "settings": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.5, "speed": 1.1}}}
    r = ElevenLabsBackend().request(voice, "Hi!")
    assert r.params["modelId"] == "eleven_v4" and r.params["settings"] == {"stability": 0.3, "similarity_boost": 0.8}
    assert r.params["timestamps"] is True and r.params["outputFormat"] == "mp3_44100_192"
    v2 = {"elevenlabs": {**voice["elevenlabs"], "modelId": "eleven_multilingual_v2"}}
    assert ElevenLabsBackend().request(v2, "Hi!").params["settings"]["style"] == 0.5
    nomodel = {"elevenlabs": {"voiceId": "abc", "settings": {}}}
    assert ElevenLabsBackend().request(nomodel, "Hi!").params["modelId"] == B.EL_DEFAULT_MODEL == "eleven_v4"
    for cid in ("bolt", "maya"):                                   # registry: v4 candidates, still unapproved
        el = load_registry().get(cid).voice["elevenlabs"]
        assert el["modelId"] == "eleven_v4" and el["voiceId"] and el["approved"] is False


def test_words_from_alignment_skips_audio_tags():
    w = B.words_from_alignment(_alignment("[excited] Hi Bolt!", 0.1))
    assert [x["text"] for x in w] == ["Hi", "Bolt!"]
    assert w[0]["start_s"] == pytest.approx(1.0) and w[1]["end_s"] == pytest.approx(1.8)
    assert B.words_from_alignment(None) == []


def test_elevenlabs_request_cache_ledger_timings_and_key_never_persisted(small, tmp_path, monkeypatch, mp3_bytes):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes)
    el = ElevenLabsBackend(client_factory=lambda: fake)
    cache, reg = VoiceCache(tmp_path / "cache"), approved_registry()
    doc = voice_episode(small, reg, tmp_path / "o", el, cache, log=lambda m: None)
    n = len(fake.calls)
    assert n == doc["cost"]["lines"] > 0 and doc["isProductionVoice"] is True
    voice_id, kw = fake.calls[0]
    assert kw["model_id"] == "eleven_v4" and kw["output_format"] == "mp3_44100_192" and kw["seed"] == B.EL_SEED
    assert set(kw["voice_settings"].model_dump(exclude_none=True)) <= {"stability", "similarity_boost"}
    voice_ids = {reg.get(c).voice["elevenlabs"]["voiceId"] for c in ("bolt", "maya")}
    assert {v for v, _ in fake.calls} <= voice_ids
    assert cache.ledger_chars() == doc["cost"]["billableChars"] > 0
    assert doc["voices"]["bolt"]["voiceId"] in voice_ids
    # word timings: cached with the audio, written next to each line, referenced from timing.json
    line = next(b for s in doc["scenes"] for b in s["beats"] if b["type"] == "line")
    words = json.loads((tmp_path / "o" / line["words"]).read_text())["words"]
    assert [w["text"] for w in words] == line["text"].split()
    assert all(0 <= w["start_s"] <= w["end_s"] <= line["audio_s"] + 1e-6 for w in words)
    # rerun: zero new API calls, zero new billable chars, timings still there (from the cache)
    doc2 = voice_episode(small, reg, tmp_path / "o", el, cache, log=lambda m: None)
    assert len(fake.calls) == n and doc2["cost"]["billableChars"] == 0
    assert all("words" in b for s in doc2["scenes"] for b in s["beats"] if b["type"] == "line")
    # the key appears in no file anywhere (outputs, cache, ledger)
    for root in (tmp_path / "o", tmp_path / "cache"):
        for p in root.rglob("*"):
            if p.is_file():
                assert FAKE_KEY.encode() not in p.read_bytes(), p
    rep = QaReport("ep", "voice", str(tmp_path / "o"))
    check_dialogue(rep, tmp_path / "o", [tmp_path / "cache"])
    assert [c for c in rep.checks if c.id == "security.no_api_key"][0].ok
    # a later offline (fixture) run in the same folder drops the stale ElevenLabs word timings
    doc3 = voice_episode(small, reg, tmp_path / "o", B.FixtureBackend(), cache, log=lambda m: None)
    assert not any("words" in b for s in doc3["scenes"] for b in s["beats"] if b["type"] == "line")
    assert not list((tmp_path / "o").rglob("*.words.json"))


def test_budget_blocks_before_any_call(small, tmp_path, monkeypatch, mp3_bytes):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    monkeypatch.setenv("ROBOTICS101_ELEVENLABS_MAX_CHARS", "50")
    fake = FakeClient(mp3_bytes)
    with pytest.raises(VoiceError, match="exceed the per-run budget"):
        voice_episode(small, approved_registry(), tmp_path / "o", ElevenLabsBackend(client_factory=lambda: fake),
                      VoiceCache(tmp_path / "c"), log=lambda m: None)
    assert fake.calls == []


def test_http_errors_are_redacted_and_not_cached(tmp_path, monkeypatch, mp3_bytes):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes, fail=[_api_error(401, {"detail": f"invalid key {FAKE_KEY}"})])
    el, cache = ElevenLabsBackend(client_factory=lambda: fake), VoiceCache(tmp_path / "c")
    req = el.request(load_registry().get("maya").voice, "Hello there!")
    with pytest.raises(VoiceError) as ei:
        cache.get_or_render(el, req)
    assert FAKE_KEY not in str(ei.value) and "[REDACTED]" in str(ei.value) and "401" in str(ei.value)
    assert len(fake.calls) == 1                                   # 4xx: no retry
    assert not cache.has(req) and cache.ledger_chars() == 0


def test_retry_on_429_then_success(tmp_path, monkeypatch, mp3_bytes):
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    fake = FakeClient(mp3_bytes, fail=[_api_error(429, "slow down")])
    el = ElevenLabsBackend(client_factory=lambda: fake)
    cache = VoiceCache(tmp_path / "c")
    req = el.request(load_registry().get("bolt").voice, "Hi!")
    p, cached = cache.get_or_render(el, req)
    assert len(fake.calls) == 2 and not cached and p.stat().st_size == len(mp3_bytes)
    assert cache.alignment(req)["characters"] == list("Hi!")


def test_secret_scan_catches_leak(small, tmp_path, monkeypatch):
    out = tmp_path / "o"
    voice_episode(small, load_registry(), out, B.FixtureBackend(), VoiceCache(tmp_path / "c"), log=lambda m: None)
    monkeypatch.setenv(B.KEY_ENV, FAKE_KEY)
    (out / "debug.log").write_text(f"oops {FAKE_KEY}")
    rep = QaReport("ep", "voice", str(out))
    check_dialogue(rep, out)
    assert any(c.id == "security.no_api_key" for c in rep.failures)


def test_cli_voice_fixture_and_plan_only(tmp_path, capsys):
    assert main(["voice", str(CARTOON), "--out", str(tmp_path / "o"), "--tts", "fixture", "--plan-only"]) == 0
    assert "billable" in capsys.readouterr().out and not (tmp_path / "o").exists()
    assert main(["voice", str(ROOT / "examples" / "episode-001.json"), "--out", str(tmp_path / "x"),
                 "--tts", "fixture"]) == 2


def test_plan_lines_covers_every_line_with_registry_voices(cartoon):
    plans = plan_lines(cartoon, load_registry(), B.EspeakBackend(), VoiceCache())
    assert len(plans) == sum(b["type"] == "line" for s in cartoon["scenes"] for b in s["beats"])
    assert {p.request.params["voice"] for p in plans} == {"en-us+m3", "en-us+f4"}
    assert sum(p.request.chars for p in plans) < 6000      # one episode stays well inside a Starter month


def test_voice_package_has_no_third_party_http_and_only_backends_reads_key():
    src = ROOT / "src" / "robotics101"
    for p in src.rglob("*.py"):
        t = p.read_text()
        assert "import requests" not in t and "import httpx" not in t, p
        reads_key = "environ" in t and ("KEY_ENV" in t or "ELEVENLABS_API_KEY" in t)
        if reads_key:   # only the backend (to call the API) and voice QA (to scan artifacts for leaks)
            assert p.relative_to(src).as_posix() in {"voice/backends.py", "voice/qa.py"}, p


@needs_ffmpeg
def test_sfx_anchor_to_actions(cartoon, tmp_path):
    """M02.6 timing fix: sfx after an action sync to it (start / impact / echo) and don't add dead time."""
    s = json.loads(json.dumps(cartoon))
    s["scenes"] = [s["scenes"][0], s["scenes"][3]]          # cold open (zoom/bonk/dizzy/stars) + sensor ping
    doc = voice_episode(s, load_registry(), tmp_path / "o", B.FixtureBackend(), VoiceCache(tmp_path / "c"),
                        log=lambda m: None)
    for sc in doc["scenes"]:
        beats = sc["beats"]
        for i, e in enumerate(beats):
            if e["type"] != "sfx":
                continue
            prev = beats[i - 1]
            assert e["sound_s"] > 0
            if prev["type"] == "action" or (prev["type"] == "sfx" and "anchorMode" in prev):
                a = beats[e["anchor"]] if e.get("anchor") is not None else None
                mode = e["anchorMode"]
                if mode == "end":
                    assert e["start_s"] == pytest.approx(a["end_s"])
                elif mode == "start":
                    assert e["start_s"] == pytest.approx(a["start_s"])
                else:
                    ping = next(b for b in reversed(beats[:i]) if b["type"] == "sfx" and b["id"] == "ping")
                    assert e["start_s"] == pytest.approx(ping["start_s"] + 0.4)
    b1 = doc["scenes"][0]["beats"]
    zoom_a = next(e for e in b1 if e["type"] == "action" and e["do"] == "zoom")
    bonk = next(e for e in b1 if e["type"] == "sfx" and e["id"] == "bonk")
    zoom_s = next(e for e in b1 if e["type"] == "sfx" and e["id"] == "zoom")
    dizzy = next(e for e in b1 if e["type"] == "action" and e["do"] == "dizzy")
    assert zoom_s["start_s"] == zoom_a["start_s"] and bonk["start_s"] == zoom_a["end_s"]
    assert dizzy["start_s"] == pytest.approx(zoom_a["end_s"])          # no dead air added by the two sfx


@needs_ffmpeg
def test_sequential_sfx_after_line_advances(cartoon, tmp_path):
    s = json.loads(json.dumps(cartoon))
    sc = s["scenes"][1]
    sc["beats"] = [{"type": "line", "speaker": "bolt", "text": "Hi there."}, {"type": "sfx", "id": "ding"},
                   {"type": "line", "speaker": "maya", "text": "Hello."}]
    s["scenes"] = [sc]
    doc = voice_episode(s, load_registry(), tmp_path / "o", B.FixtureBackend(), VoiceCache(tmp_path / "c"),
                        log=lambda m: None)
    l1, ding, l2 = doc["scenes"][0]["beats"]
    assert ding["start_s"] >= l1["end_s"] and l2["start_s"] >= ding["start_s"] + 0.45 - 1e-6
    assert "anchorMode" not in ding
