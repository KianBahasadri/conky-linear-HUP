from datetime import date, timedelta

import fetch_linear_tasks as linear


def test_linear_overlay_height_scales_with_rows():
    # 4 cards/row at the default 1540px overlay width.
    assert linear.linear_overlay_height(0) == linear.EMPTY_HEIGHT
    assert linear.linear_overlay_height(1) == 138
    assert linear.linear_overlay_height(4) == 138
    assert linear.linear_overlay_height(5) == 268
    assert linear.linear_overlay_height(12) == 398
    assert linear.linear_overlay_height(13) == 528
    assert linear.linear_overlay_height(16) == 528
    assert linear.linear_overlay_height(17) == 658


def test_linear_overlay_height_uses_window_width():
    # Narrower window packs fewer cards per row, so needs more height.
    assert linear.linear_overlay_height(4, window_width=700) > linear.linear_overlay_height(
        4, window_width=1540
    )


def _issue(identifier, title, state_name, *, due_date=None, project=None, state_type="unstarted"):
    return {
        "identifier": identifier,
        "title": title,
        "completedAt": None,
        "dueDate": due_date,
        "priorityLabel": "No priority",
        "url": f"https://linear.app/issue/{identifier}",
        "project": {"name": project} if project else None,
        "state": {"name": state_name, "type": state_type},
    }


def test_is_due_soon_backlog_accepts_next_three_days():
    today = date(2026, 8, 7)
    assert linear.is_due_soon_backlog(
        _issue("ABC-1", "Soon", "Backlog", due_date="2026-08-07"), today
    )
    assert linear.is_due_soon_backlog(
        _issue("ABC-2", "In three days", "Backlog", due_date="2026-08-10"), today
    )
    assert not linear.is_due_soon_backlog(
        _issue("ABC-3", "Too far", "Backlog", due_date="2026-08-11"), today
    )
    assert not linear.is_due_soon_backlog(
        _issue("ABC-4", "No due", "Backlog"), today
    )
    assert not linear.is_due_soon_backlog(
        _issue("ABC-5", "Wrong state", "Todo", due_date="2026-08-08"), today
    )
    assert not linear.is_due_soon_backlog(
        _issue(
            "ABC-6",
            "Done",
            "Backlog",
            due_date="2026-08-08",
            state_type="completed",
        ),
        today,
    )


def test_collect_tasks_includes_due_soon_backlog():
    today = date.today()
    due_soon = (today + timedelta(days=2)).isoformat()
    due_far = (today + timedelta(days=10)).isoformat()
    response = {
        "data": {
            "workflowStates": {
                "nodes": [
                    {
                        "name": "Backlog",
                        "type": "backlog",
                        "issues": {
                            "nodes": [
                                _issue("ABC-1", "Soon from states", "Backlog", due_date=due_soon),
                                _issue("ABC-2", "Far from states", "Backlog", due_date=due_far),
                            ]
                        },
                    },
                    {
                        "name": "Todo",
                        "type": "unstarted",
                        "issues": {
                            "nodes": [
                                _issue("ABC-3", "Active", "Todo"),
                            ]
                        },
                    },
                ]
            },
            "competitionIssues": {"nodes": []},
            "backlogDueSoon": {
                "nodes": [
                    _issue("ABC-4", "Soon from query", "Backlog", due_date=due_soon),
                    # Name still "Backlog" but type marks them cancelled/duplicate.
                    _issue(
                        "ABC-5",
                        "Cancelled backlog",
                        "Backlog",
                        due_date=due_soon,
                        state_type="canceled",
                    ),
                    _issue(
                        "ABC-6",
                        "Duplicate backlog",
                        "Backlog",
                        due_date=due_soon,
                        state_type="duplicate",
                    ),
                ]
            },
        }
    }

    tasks = linear.collect_tasks(response, {"Todo", "In Progress"})
    identifiers = {task["identifier"] for task in tasks}
    assert identifiers == {"ABC-1", "ABC-3", "ABC-4"}


def test_render_cards_includes_backlog_due_soon_flag():
    today = date.today()
    due_soon = (today + timedelta(days=1)).isoformat()
    due_today = today.isoformat()
    tasks = [
        _issue("ABC-1", "Backlog soon", "Backlog", due_date=due_soon),
        _issue("ABC-2", "Active work", "Todo"),
        _issue("ABC-3", "Backlog today", "Backlog", due_date=due_today),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert "ABC-1" in cards_by_id
    assert cards_by_id["ABC-1"]["backlogDueSoon"] is True
    assert cards_by_id["ABC-1"]["state"] == "Backlog"
    assert cards_by_id["ABC-1"]["dueDate"] != ""
    assert cards_by_id["ABC-1"]["dueToday"] is False
    assert cards_by_id["ABC-2"]["backlogDueSoon"] is False
    assert cards_by_id["ABC-3"]["backlogDueSoon"] is True
    assert cards_by_id["ABC-3"]["dueToday"] is True
