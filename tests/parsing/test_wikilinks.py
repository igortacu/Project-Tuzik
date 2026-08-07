from second_brain.parsing.wikilinks import extract_wikilinks


def test_simple_link():
    links = extract_wikilinks("See [[Note Name]] for details.")
    assert len(links) == 1
    assert links[0].target == "Note Name"
    assert links[0].alias is None


def test_link_with_alias():
    links = extract_wikilinks("See [[Note Name|Display Text]] for details.")
    assert len(links) == 1
    assert links[0].target == "Note Name"
    assert links[0].alias == "Display Text"


def test_link_with_alias_extra_whitespace():
    links = extract_wikilinks("[[ Note Name | Display Text ]]")
    assert len(links) == 1
    assert links[0].target == "Note Name"
    assert links[0].alias == "Display Text"


def test_unclosed_brackets_produce_no_match():
    links = extract_wikilinks("This has [[Note Name that never closes.\nNext line [[Real Link]].")
    assert len(links) == 1
    assert links[0].target == "Real Link"


def test_nested_brackets_matches_inner_only():
    links = extract_wikilinks("[[Outer [[Inner]] ]]")
    assert len(links) == 1
    assert links[0].target == "Inner"


def test_empty_link_produces_no_match():
    assert extract_wikilinks("[[]]") == []


def test_empty_target_with_alias_is_skipped():
    assert extract_wikilinks("[[|alias]]") == []
    assert extract_wikilinks("[[   |alias]]") == []


def test_trailing_pipe_no_alias():
    links = extract_wikilinks("[[Note Name|]]")
    assert len(links) == 1
    assert links[0].target == "Note Name"
    assert links[0].alias is None


def test_multiple_pipes_splits_on_first_only():
    links = extract_wikilinks("[[Note Name|alias|extra]]")
    assert len(links) == 1
    assert links[0].target == "Note Name"
    assert links[0].alias == "alias|extra"


def test_heading_reference_truncates_target():
    links = extract_wikilinks("[[Note Name#Heading]]")
    assert len(links) == 1
    assert links[0].target == "Note Name"


def test_block_reference_truncates_target():
    links = extract_wikilinks("[[Note Name#^blockid]]")
    assert len(links) == 1
    assert links[0].target == "Note Name"


def test_unicode_note_name():
    links = extract_wikilinks("[[日本語ノート]]")
    assert len(links) == 1
    assert links[0].target == "日本語ノート"


def test_adjacent_links():
    links = extract_wikilinks("[[A]][[B]]")
    assert [link.target for link in links] == ["A", "B"]


def test_empty_body():
    assert extract_wikilinks("") == []


def test_raw_field_preserves_full_match():
    links = extract_wikilinks("[[Note Name#Heading]]")
    assert links[0].raw == "[[Note Name#Heading]]"


def test_start_end_offsets():
    body = "prefix [[Note]] suffix"
    links = extract_wikilinks(body)
    assert body[links[0].start : links[0].end] == "[[Note]]"
