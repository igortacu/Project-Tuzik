from datetime import datetime, timedelta

from second_brain.agent.reminders import ReminderStore


def _make_store(tmp_path):
    return ReminderStore(persist_path=str(tmp_path / "reminders.json"))


def test_add_returns_reminder_with_matching_fields(tmp_path):
    store = _make_store(tmp_path)
    fire_at = datetime(2026, 8, 10, 15, 20)

    reminder = store.add(chat_id=1, fire_at=fire_at, message="take out the roast")

    assert reminder.chat_id == 1
    assert reminder.fire_at == fire_at
    assert reminder.message == "take out the roast"
    assert reminder.id


def test_list_for_chat_is_isolated_per_chat(tmp_path):
    store = _make_store(tmp_path)
    store.add(1, datetime(2026, 8, 10, 15, 0), "chat one reminder")
    store.add(2, datetime(2026, 8, 10, 16, 0), "chat two reminder")

    assert [r.message for r in store.list_for_chat(1)] == ["chat one reminder"]
    assert [r.message for r in store.list_for_chat(2)] == ["chat two reminder"]


def test_cancel_removes_reminder_belonging_to_the_chat(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "cancel me")

    assert store.cancel(chat_id=1, reminder_id=reminder.id) is True
    assert store.list_for_chat(1) == []


def test_cancel_refuses_a_different_chats_reminder(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "not yours")

    assert store.cancel(chat_id=2, reminder_id=reminder.id) is False
    assert [r.id for r in store.list_for_chat(1)] == [reminder.id]


def test_cancel_unknown_id_returns_false(tmp_path):
    store = _make_store(tmp_path)
    assert store.cancel(chat_id=1, reminder_id="nonexistent") is False


def test_due_returns_reminders_at_or_before_now(tmp_path):
    store = _make_store(tmp_path)
    now = datetime(2026, 8, 10, 15, 20)
    due_reminder = store.add(1, now - timedelta(minutes=1), "already due")
    store.add(1, now + timedelta(minutes=1), "not yet due")

    assert [r.id for r in store.due(now)] == [due_reminder.id]


def test_due_at_exact_boundary_is_included(tmp_path):
    store = _make_store(tmp_path)
    now = datetime(2026, 8, 10, 15, 20)
    reminder = store.add(1, now, "exactly now")

    assert [r.id for r in store.due(now)] == [reminder.id]


def test_remove_deletes_the_reminder(tmp_path):
    store = _make_store(tmp_path)
    reminder = store.add(1, datetime(2026, 8, 10, 15, 0), "temp")

    store.remove(reminder.id)

    assert store.list_for_chat(1) == []


def test_remove_unknown_id_does_not_raise(tmp_path):
    store = _make_store(tmp_path)
    store.remove("nonexistent")


def test_survives_a_simulated_restart(tmp_path):
    persist_path = str(tmp_path / "reminders.json")
    first = ReminderStore(persist_path=persist_path)
    reminder = first.add(1, datetime(2026, 8, 10, 15, 20), "survive restart")

    second = ReminderStore(persist_path=persist_path)

    assert [r.id for r in second.list_for_chat(1)] == [reminder.id]
    assert second.list_for_chat(1)[0].fire_at == reminder.fire_at
    assert second.list_for_chat(1)[0].message == "survive restart"


def test_cancel_persists_the_removal(tmp_path):
    persist_path = str(tmp_path / "reminders.json")
    first = ReminderStore(persist_path=persist_path)
    reminder = first.add(1, datetime(2026, 8, 10, 15, 0), "temp")
    first.cancel(chat_id=1, reminder_id=reminder.id)

    second = ReminderStore(persist_path=persist_path)

    assert second.list_for_chat(1) == []
