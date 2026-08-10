from second_brain.bot.memory import ConversationMemory, SaveBuffer


def _make_conversation_memory(tmp_path, max_turns=3):
    return ConversationMemory(
        max_turns=max_turns, persist_path=str(tmp_path / "conversation_memory.json")
    )


def test_empty_history_for_unknown_chat(tmp_path):
    memory = _make_conversation_memory(tmp_path)
    assert memory.get(123) == []


def test_append_and_get_roundtrip(tmp_path):
    memory = _make_conversation_memory(tmp_path)
    memory.append(1, "hello", "hi there")

    assert memory.get(1) == [("user", "hello"), ("assistant", "hi there")]


def test_history_preserves_order_across_multiple_turns(tmp_path):
    memory = _make_conversation_memory(tmp_path)
    memory.append(1, "q1", "a1")
    memory.append(1, "q2", "a2")

    assert memory.get(1) == [
        ("user", "q1"),
        ("assistant", "a1"),
        ("user", "q2"),
        ("assistant", "a2"),
    ]


def test_window_truncates_oldest_turns_first(tmp_path):
    memory = _make_conversation_memory(tmp_path, max_turns=2)
    memory.append(1, "q1", "a1")
    memory.append(1, "q2", "a2")
    memory.append(1, "q3", "a3")

    # max_turns=2 -> keeps only the 2 most recent (user, assistant) pairs
    assert memory.get(1) == [
        ("user", "q2"),
        ("assistant", "a2"),
        ("user", "q3"),
        ("assistant", "a3"),
    ]


def test_different_chats_are_independent(tmp_path):
    memory = _make_conversation_memory(tmp_path)
    memory.append(1, "chat one question", "chat one answer")
    memory.append(2, "chat two question", "chat two answer")

    assert memory.get(1) == [("user", "chat one question"), ("assistant", "chat one answer")]
    assert memory.get(2) == [("user", "chat two question"), ("assistant", "chat two answer")]


def test_conversation_memory_survives_a_simulated_restart(tmp_path):
    persist_path = str(tmp_path / "conversation_memory.json")
    first = ConversationMemory(max_turns=3, persist_path=persist_path)
    first.append(1, "hello", "hi there")

    second = ConversationMemory(max_turns=3, persist_path=persist_path)
    assert second.get(1) == [("user", "hello"), ("assistant", "hi there")]


def test_conversation_memory_persists_the_bounded_window(tmp_path):
    persist_path = str(tmp_path / "conversation_memory.json")
    first = ConversationMemory(max_turns=2, persist_path=persist_path)
    first.append(1, "q1", "a1")
    first.append(1, "q2", "a2")
    first.append(1, "q3", "a3")

    second = ConversationMemory(max_turns=2, persist_path=persist_path)
    assert second.get(1) == [
        ("user", "q2"),
        ("assistant", "a2"),
        ("user", "q3"),
        ("assistant", "a3"),
    ]


# --- SaveBuffer ---


def _make_save_buffer(tmp_path):
    return SaveBuffer(persist_path=str(tmp_path / "save_buffer.json"))


def test_save_buffer_drain_empty_for_unknown_chat(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    assert buffer.drain(123) == []


def test_save_buffer_append_and_drain_roundtrip(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    buffer.append(1, "q1", "a1")
    buffer.append(1, "q2", "a2")

    assert buffer.drain(1) == [("q1", "a1"), ("q2", "a2")]


def test_save_buffer_drain_clears_the_buffer(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    buffer.append(1, "q1", "a1")
    buffer.drain(1)

    assert buffer.drain(1) == []


def test_save_buffer_peek_does_not_clear_the_buffer(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    buffer.append(1, "q1", "a1")

    assert buffer.peek(1) == [("q1", "a1")]
    assert buffer.peek(1) == [("q1", "a1")]


def test_save_buffer_clear_removes_buffered_turns(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    buffer.append(1, "q1", "a1")
    buffer.clear(1)

    assert buffer.peek(1) == []


def test_save_buffer_does_not_truncate_unlike_conversation_memory(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    for i in range(50):
        buffer.append(1, f"q{i}", f"a{i}")

    assert len(buffer.drain(1)) == 50


def test_save_buffer_chat_ids_lists_chats_with_pending_data(tmp_path):
    buffer = _make_save_buffer(tmp_path)
    buffer.append(1, "q", "a")
    buffer.append(2, "q", "a")

    assert set(buffer.chat_ids()) == {1, 2}
    buffer.drain(1)
    assert buffer.chat_ids() == [2]


def test_save_buffer_survives_a_simulated_restart(tmp_path):
    persist_path = str(tmp_path / "save_buffer.json")
    first = SaveBuffer(persist_path=persist_path)
    first.append(1, "remember X", "ok")

    # simulates a bot restart: a fresh instance pointed at the same file
    second = SaveBuffer(persist_path=persist_path)
    assert second.drain(1) == [("remember X", "ok")]


def test_save_buffer_drain_persists_the_removal(tmp_path):
    persist_path = str(tmp_path / "save_buffer.json")
    first = SaveBuffer(persist_path=persist_path)
    first.append(1, "q", "a")
    first.drain(1)

    second = SaveBuffer(persist_path=persist_path)
    assert second.drain(1) == []


def test_save_buffer_clear_persists_the_removal(tmp_path):
    persist_path = str(tmp_path / "save_buffer.json")
    first = SaveBuffer(persist_path=persist_path)
    first.append(1, "q", "a")
    first.clear(1)

    second = SaveBuffer(persist_path=persist_path)
    assert second.peek(1) == []
