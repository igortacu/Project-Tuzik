from second_brain.parsing.frontmatter import normalize_tags, parse_frontmatter


def test_no_frontmatter_block():
    raw = "# Just a note\n\nSome body text.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is False
    assert result.metadata == {}
    assert result.body == raw
    assert result.parse_error is None


def test_empty_frontmatter_block():
    raw = "---\n---\nBody text.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    assert result.metadata == {}
    assert result.body == "Body text.\n"
    assert result.parse_error is None


def test_malformed_yaml_never_raises():
    raw = "---\ntags: [unclosed\n---\nBody text.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    assert result.metadata == {}
    assert result.parse_error is not None


def test_unterminated_frontmatter_block_treated_as_no_frontmatter():
    raw = "---\ntags: [a, b]\nNo closing delimiter here.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is False
    assert result.metadata == {}
    assert result.body == raw
    assert result.parse_error is None


def test_yaml_not_a_mapping():
    raw = "---\n- a\n- b\n---\nBody text.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    assert result.metadata == {}
    assert result.parse_error is not None


def test_all_comments_block():
    raw = "---\n# just a comment\n---\nBody text.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    assert result.metadata == {}
    assert result.parse_error is None


def test_crlf_line_endings_normalized():
    raw = "---\r\ntags: [a, b]\r\n---\r\nBody text.\r\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    assert result.metadata == {"tags": ["a", "b"]}
    assert "\r" not in result.body


def test_valid_frontmatter_extracts_metadata_and_body():
    import datetime

    raw = "---\ntags: [work, career]\ndate: 2026-01-01\n---\n# Heading\n\nBody.\n"
    result = parse_frontmatter(raw)

    assert result.has_frontmatter is True
    # PyYAML auto-resolves ISO-8601-looking scalars to datetime.date.
    assert result.metadata == {
        "tags": ["work", "career"],
        "date": datetime.date(2026, 1, 1),
    }
    assert result.body == "# Heading\n\nBody.\n"
    assert result.parse_error is None


def test_normalize_tags_missing_key():
    assert normalize_tags({}) == []


def test_normalize_tags_yaml_list():
    assert normalize_tags({"tags": ["work", "career", 2026]}) == ["work", "career", "2026"]


def test_normalize_tags_single_scalar():
    assert normalize_tags({"tags": "career"}) == ["career"]


def test_normalize_tags_comma_separated_string():
    assert normalize_tags({"tags": "work, career"}) == ["work", "career"]


def test_normalize_tags_space_separated_string():
    assert normalize_tags({"tags": "work career"}) == ["work", "career"]


def test_normalize_tags_strips_leading_hash():
    assert normalize_tags({"tags": ["#work", "career"]}) == ["work", "career"]


def test_normalize_tags_dedupes_preserving_order():
    assert normalize_tags({"tags": ["work", "career", "work"]}) == ["work", "career"]


def test_normalize_tags_empty_list():
    assert normalize_tags({"tags": []}) == []
