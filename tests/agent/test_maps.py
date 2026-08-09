from second_brain.agent import maps


def test_build_directions_link_destination_only():
    link = maps.build_directions_link("Chisinau Airport")
    assert link == "https://www.google.com/maps/dir/?api=1&destination=Chisinau%20Airport&travelmode=driving"


def test_build_directions_link_with_origin():
    link = maps.build_directions_link("Chisinau Airport", origin="Home")
    assert "destination=Chisinau%20Airport" in link
    assert "origin=Home" in link


def test_build_directions_link_respects_mode():
    link = maps.build_directions_link("Chisinau Airport", mode="walking")
    assert "travelmode=walking" in link


def test_build_directions_link_invalid_mode_falls_back_to_driving():
    link = maps.build_directions_link("Chisinau Airport", mode="teleport")
    assert "travelmode=driving" in link


def test_build_directions_link_urlencodes_special_characters():
    link = maps.build_directions_link("Strada Ștefan cel Mare & Sfânt")
    assert " " not in link
    assert "&Sf" not in link  # the literal & in the address must be encoded, not a param separator
