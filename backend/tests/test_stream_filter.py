"""Tests for the control-token-safe streaming filter (IMPROVEMENTS.md #1)."""

from utils.stream_filter import StreamFilter


def _run(deltas):
    f = StreamFilter()
    out = "".join(f.feed(d) for d in deltas)
    return out + f.flush()


def test_plain_text_passes_through():
    assert _run(["Hello ", "there", "!"]) == "Hello there!"


def test_suppresses_control_block():
    out = _run(["Got it! ", "<TASKS_CONFIRMED>", '[{"title":"x"}]', "</TASKS_CONFIRMED>"])
    assert out == "Got it! "


def test_suppresses_tag_split_across_deltas():
    # The opening tag is fragmented across several deltas.
    out = _run(["Done. <TAS", "KS_CON", "FIRMED>[", "junk]"])
    assert out == "Done. "


def test_emits_literal_less_than():
    assert _run(["I love ", "<3 ", "coding"]) == "I love <3 coding"


def test_literal_less_than_at_boundary():
    assert _run(["a ", "<", "3 b"]) == "a <3 b"


def test_bare_onboarding_token_suppressed():
    assert _run(["Welcome aboard! ", "<ONBOARDING_COMPLETE>"]) == "Welcome aboard! "


def test_partial_tag_at_end_is_flushed_if_not_a_token():
    # Ends with "<MO" which is a prefix of <MOVE_TASK> but never completes.
    # It stays buffered and is emitted on flush (best-effort, rare).
    assert _run(["text ", "<MO"]) == "text <MO"


def test_profile_update_block_suppressed():
    out = _run(["Noted. <PROFILE_UPDATE>", '{"name":"A"}', "</PROFILE_UPDATE>"])
    assert out == "Noted. "


def test_events_confirmed_block_suppressed():
    out = _run(["Booked it. <EVENTS_CONFIRMED>", '[{"title":"x"}]', "</EVENTS_CONFIRMED>"])
    assert out == "Booked it. "


def test_events_confirmed_split_across_deltas():
    out = _run(["Done. <EVENTS_CON", "FIRMED>[junk]"])
    assert out == "Done. "
