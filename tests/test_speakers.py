from ssmdconvert.enrich.speakers import discover


def test_local_speaker_discovery_is_deterministic() -> None:
    text = "Alice said, “We should leave.” Bob replied, “Agreed.” Then “Who knows?”"
    turns, speakers = discover(text)
    assert [s.id for s in speakers] == ["narrator", "alice", "bob"]
    assert turns[0].speaker_id == "alice"
    assert turns[1].speaker_id == "bob"
    assert turns[2].speaker_id is None
