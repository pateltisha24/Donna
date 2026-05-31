"""Tests for control-token extraction and JSON repair (IMPROVEMENTS.md #4)."""

from agent.parsing import (
    extract_block,
    find_ids,
    has_token,
    loads_loose,
    parse_profile_update,
    parse_tasks,
    strip_block,
)


# ---------------------------------------------------------------------------
# extract_block / strip_block
# ---------------------------------------------------------------------------

def test_extract_block_paired():
    text = "Sure! <TASKS_CONFIRMED>[{\"title\": \"X\"}]</TASKS_CONFIRMED> done."
    assert extract_block(text, "TASKS_CONFIRMED") == '[{"title": "X"}]'


def test_extract_block_missing_closing_tag():
    text = "Sure! <TASKS_CONFIRMED>[{\"title\": \"X\"}]"
    assert extract_block(text, "TASKS_CONFIRMED") == '[{"title": "X"}]'


def test_extract_block_absent_returns_none():
    assert extract_block("no tokens here", "TASKS_CONFIRMED") is None


def test_extract_block_case_insensitive():
    text = "<profile_update>{\"name\": \"A\"}</profile_update>"
    assert extract_block(text, "PROFILE_UPDATE") == '{"name": "A"}'


def test_strip_block_paired():
    text = "Got it. <TASKS_CONFIRMED>[{\"title\": \"X\"}]</TASKS_CONFIRMED>"
    assert strip_block(text, "TASKS_CONFIRMED") == "Got it."


def test_strip_block_dangling_open():
    text = "Got it. <TASKS_CONFIRMED>[{junk"
    assert strip_block(text, "TASKS_CONFIRMED") == "Got it."


def test_strip_block_bare_token():
    assert strip_block("Welcome! <ONBOARDING_COMPLETE>", "ONBOARDING_COMPLETE") == "Welcome!"


def test_has_token():
    assert has_token("done <ONBOARDING_COMPLETE>", "<onboarding_complete>")
    assert not has_token("nothing", "<ONBOARDING_COMPLETE>")


def test_find_ids():
    text = "done <MARK_DONE>3</MARK_DONE> and <MARK_DONE> 7 </MARK_DONE>"
    assert find_ids(text, "MARK_DONE") == [3, 7]
    assert find_ids(text, "MOVE_TASK") == []


# ---------------------------------------------------------------------------
# loads_loose repairs
# ---------------------------------------------------------------------------

def test_loads_loose_plain():
    assert loads_loose('{"a": 1}') == {"a": 1}


def test_loads_loose_code_fence():
    assert loads_loose('```json\n{"a": 1}\n```') == {"a": 1}


def test_loads_loose_trailing_comma():
    assert loads_loose('[{"a": 1},]') == [{"a": 1}]


def test_loads_loose_prose_around_json():
    assert loads_loose('Here you go: [{"a": 1}] hope that helps') == [{"a": 1}]


def test_loads_loose_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        loads_loose("")


def test_loads_loose_garbage_raises():
    import pytest
    with pytest.raises(ValueError):
        loads_loose("not json at all")


# ---------------------------------------------------------------------------
# parse_tasks
# ---------------------------------------------------------------------------

def test_parse_tasks_valid():
    r = parse_tasks('[{"title": "Email Bob", "priority": "high"}]')
    assert r.ok
    assert r.value[0]["title"] == "Email Bob"


def test_parse_tasks_single_object_coerced_to_list():
    r = parse_tasks('{"title": "Solo"}')
    assert r.ok and len(r.value) == 1


def test_parse_tasks_drops_titleless_entries():
    r = parse_tasks('[{"title": "Keep"}, {"priority": "low"}]')
    assert r.ok and len(r.value) == 1


def test_parse_tasks_all_titleless_fails():
    r = parse_tasks('[{"priority": "low"}]')
    assert not r.ok and r.error


def test_parse_tasks_malformed_fails():
    r = parse_tasks("[{title: nope")
    assert not r.ok and "invalid JSON" in r.error


# ---------------------------------------------------------------------------
# parse_profile_update
# ---------------------------------------------------------------------------

def test_parse_profile_update_filters_unknown_fields():
    r = parse_profile_update('{"name": "Tisha", "bogus": 1}')
    assert r.ok and r.value == {"name": "Tisha"}


def test_parse_profile_update_non_object_fails():
    r = parse_profile_update('["not", "an", "object"]')
    assert not r.ok


def test_parse_profile_update_malformed_fails():
    r = parse_profile_update("{name: ")
    assert not r.ok
