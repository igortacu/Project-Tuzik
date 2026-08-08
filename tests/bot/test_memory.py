from second_brain.bot.memory import ConversationMemory


def test_empty_history_for_unknown_chat():
    memory = ConversationMemory(max_turns=3)
    assert memory.get(123) == []


def test_append_and_get_roundtrip():
    memory = ConversationMemory(max_turns=3)
    memory.append(1, "hello", "hi there")

    assert memory.get(1) == [("user", "hello"), ("assistant", "hi there")]


def test_history_preserves_order_across_multiple_turns():
    memory = ConversationMemory(max_turns=3)
    memory.append(1, "q1", "a1")
    memory.append(1, "q2", "a2")

    assert memory.get(1) == [
        ("user", "q1"),
        ("assistant", "a1"),
        ("user", "q2"),
        ("assistant", "a2"),
    ]


def test_window_truncates_oldest_turns_first():
    memory = ConversationMemory(max_turns=2)
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


def test_different_chats_are_independent():
    memory = ConversationMemory(max_turns=3)
    memory.append(1, "chat one question", "chat one answer")
    memory.append(2, "chat two question", "chat two answer")

    assert memory.get(1) == [("user", "chat one question"), ("assistant", "chat one answer")]
    assert memory.get(2) == [("user", "chat two question"), ("assistant", "chat two answer")]
