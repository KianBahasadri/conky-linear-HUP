import io
import json
import urllib.error
from datetime import date, datetime, timedelta, timezone

import pytest

import fetch_linear_tasks as linear


def test_linear_overlay_height_scales_with_rows():
    # 5 cards/row at the default 1540px overlay width.
    assert linear.linear_overlay_height(0) == linear.EMPTY_HEIGHT
    assert linear.linear_overlay_height(1) == 144
    assert linear.linear_overlay_height(4) == 144
    assert linear.linear_overlay_height(5) == 260
    assert linear.linear_overlay_height(6) == 260
    assert linear.linear_overlay_height(12) == 376
    assert linear.linear_overlay_height(13) == 376
    assert linear.linear_overlay_height(16) == 376
    assert linear.linear_overlay_height(17) == 376


def test_linear_overlay_height_uses_window_width():
    # Narrower window packs fewer cards per row, so needs more height.
    assert linear.linear_overlay_height(4, window_width=700) > linear.linear_overlay_height(
        4, window_width=1540
    )


def _issue(
    identifier,
    title,
    state_name,
    *,
    due_date=None,
    project=None,
    project_icon=None,
    state_type="unstarted",
    priority="No priority",
    labels=None,
):
    return {
        "identifier": identifier,
        "title": title,
        "completedAt": None,
        "dueDate": due_date,
        "priorityLabel": priority,
        "url": f"https://linear.app/issue/{identifier}",
        "project": {"name": project, "icon": project_icon} if project else None,
        "state": {"name": state_name, "type": state_type},
        "labels": {"nodes": [{"name": l} for l in labels]} if labels else {"nodes": []},
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
    today = date(2026, 8, 7)
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

    tasks = linear.collect_tasks(response, {"Todo", "In Progress"}, today)
    identifiers = {task["identifier"] for task in tasks}
    assert identifiers == {"ABC-1", "ABC-3", "ABC-4"}


@pytest.mark.parametrize("source", ["workflowStates", "dueIssues"])
def test_overdue_and_due_today_issues_reach_cards_outside_active_states(source):
    now = datetime(2026, 9, 17, 12).astimezone()
    tasks = [
        _issue("ABC-1", "Overdue reading", "Backlog", due_date="2026-09-10"),
        _issue("ABC-2", "Due today", "Triage", due_date="2026-09-17"),
        _issue("ABC-3", "Future triage", "Triage", due_date="2026-09-18"),
        _issue("ABC-4", "No deadline", "Backlog"),
        _issue("ABC-5", "Duplicate", "Duplicate", due_date="2026-09-10", state_type="duplicate"),
        _issue("ABC-6", "Canceled", "Canceled", due_date="2026-09-10", state_type="canceled"),
        _issue("ABC-7", "Completed", "Done", due_date="2026-09-10", state_type="completed"),
    ]
    response = {"data": {"workflowStates": {"nodes": []}}}
    if source == "workflowStates":
        response["data"][source]["nodes"] = [
            {**task["state"], "issues": {"nodes": [task]}} for task in tasks
        ]
    else:
        response["data"][source] = {"nodes": tasks}

    collected = linear.collect_tasks(response, {"Todo", "In Progress"}, now.date())
    cards = linear.render_cards(collected, {"Todo", "In Progress"}, 18, now)["cards"]

    assert {card["identifier"] for card in cards} == {"ABC-1", "ABC-2"}
    assert all(card["dueToday"] and not card["done"] for card in cards)
    assert next(card for card in cards if card["identifier"] == "ABC-1")["dueDate"] == "Overdue · Sep 10"


def test_render_cards_includes_backlog_due_soon_flag():
    today = date(2026, 8, 7)
    now = datetime(2026, 8, 7, 16, tzinfo=timezone.utc)
    due_soon = (today + timedelta(days=1)).isoformat()
    due_today = today.isoformat()
    tasks = [
        _issue("ABC-1", "Backlog soon", "Backlog", due_date=due_soon),
        _issue("ABC-2", "Active work", "Todo", project="Core"),
        _issue("ABC-3", "Backlog today", "Backlog", due_date=due_today),
    ]

    payload = linear.render_cards(
        tasks, {"Todo", "In Progress"}, lookback_hours=18, now=now
    )
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert "ABC-1" in cards_by_id
    assert cards_by_id["ABC-1"]["backlogDueSoon"] is True
    assert cards_by_id["ABC-1"]["state"] == "Backlog"
    assert cards_by_id["ABC-1"]["dueDate"] != ""
    assert cards_by_id["ABC-1"]["dueToday"] is False
    assert cards_by_id["ABC-2"]["backlogDueSoon"] is False
    assert cards_by_id["ABC-2"]["projectName"] == "C"
    assert cards_by_id["ABC-3"]["backlogDueSoon"] is True
    assert cards_by_id["ABC-3"]["dueToday"] is True


@pytest.mark.parametrize(
    "due_date, expected_label, due_now",
    [
        ("2025-12-31", "Overdue · Dec 31", True),
        ("2026-09-12", "Overdue · Sep 12", True),
        ("2026-09-13", "Today", True),
        ("2026-09-14", "Tomorrow", False),
        ("2026-09-15", "Sep 15", False),
        (None, "", False),
    ],
)
def test_render_cards_distinguishes_overdue_from_today(due_date, expected_label, due_now):
    now = datetime(2026, 9, 13, 12).astimezone()
    task = _issue("ABC-1", "Deadline", "Todo", due_date=due_date)

    card = linear.render_cards([task], {"Todo"}, lookback_hours=18, now=now)["cards"][0]

    assert card["dueDate"] == expected_label
    # This urgency flag keeps both overdue and due-today cards visible and red.
    assert card["dueToday"] is due_now


@pytest.mark.parametrize("reverse", [False, True])
def test_render_cards_merged_deadline_keeps_earliest_overdue_date(reverse):
    now = datetime(2026, 9, 13, 12).astimezone()
    tasks = [
        _issue("ABC-1", "Shared", "Todo", due_date="2026-09-13"),
        _issue("ABC-2", "Shared", "Todo", due_date="2026-09-12"),
        _issue("ABC-3", "Shared", "Todo", due_date="2026-09-10"),
    ]
    if reverse:
        tasks.reverse()

    cards = linear.render_cards(tasks, {"Todo"}, lookback_hours=18, now=now)["cards"]

    assert len(cards) == 1
    assert cards[0]["dueIso"] == "2026-09-10"
    assert cards[0]["dueDate"] == "Overdue · Sep 10"
    assert cards[0]["dueToday"] is True


def test_render_cards_flags_urgent_issues():
    tasks = [
        _issue("ABC-1", "Urgent work", "Todo", priority="Urgent"),
        _issue("ABC-2", "Calm work", "Todo", priority="High"),
        _issue("ABC-3", "Unset", "Todo"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert cards_by_id["ABC-1"]["urgent"] is True
    assert cards_by_id["ABC-2"]["urgent"] is False
    assert cards_by_id["ABC-3"]["urgent"] is False


def test_render_cards_merged_card_is_urgent_if_any_issue_is():
    tasks = [
        _issue("ABC-1", "Shared", "Todo", project="Core"),
        _issue("ABC-2", "Shared", "Todo", project="Competitions", priority="Urgent"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)

    assert payload["cards"][0]["urgent"] is True


def test_emoji_from_project_icon_resolves_shortcodes():
    # Shortcode that matches the Unicode character name.
    assert linear.emoji_from_project_icon(":trophy:") == "🏆"
    assert linear.emoji_from_project_icon(":radioactive_sign:") == "☢"
    # Shortcode that needs the alias table.
    assert linear.emoji_from_project_icon(":mortar_board:") == "🎓"
    assert linear.emoji_from_project_icon(":eggplant:") == "🍆"


def test_emoji_from_project_icon_ignores_non_emoji_icons():
    # Built-in Linear icon names are not emoji.
    assert linear.emoji_from_project_icon("Users") == ""
    assert linear.emoji_from_project_icon(None) == ""
    assert linear.emoji_from_project_icon("") == ""
    # Unknown shortcodes degrade to no icon rather than a placeholder glyph.
    assert linear.emoji_from_project_icon(":not_a_real_emoji:") == ""
    # Names that resolve to non-symbol characters are rejected.
    assert linear.emoji_from_project_icon(":latin_small_letter_a:") == ""


def _iso_at(moment):
    return moment.isoformat()


def _done_issue(identifier, title, completed_at, **kwargs):
    issue = _issue(identifier, title, "Done", state_type="completed", **kwargs)
    issue["completedAt"] = completed_at
    return issue


def test_render_cards_emits_completed_at_epoch():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    tasks = [
        _issue("ABC-1", "Still open", "Todo"),
        _done_issue(
            "ABC-2", "Freshly done", _iso_at(now - timedelta(hours=2))
        ),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)

    cards_by_id = {card["identifier"]: card for card in payload["cards"]}
    assert cards_by_id["ABC-1"]["completedAtEpoch"] == 0
    assert cards_by_id["ABC-2"]["completedAtEpoch"] == int((now - timedelta(hours=2)).timestamp())
    # Lifetime is exposed payload-wide for the renderer's fade math.
    assert payload["doneLookbackSeconds"] == 18 * 3600


def test_render_cards_lookback_drops_expired_completions():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    tasks = [
        _done_issue("ABC-1", "Long ago", _iso_at(now - timedelta(hours=30))),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)

    assert payload["cards"] == []


def test_render_cards_merged_card_keeps_newest_completion():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    same_title = "Shared done work"
    tasks = [
        _done_issue("ABC-1", same_title, _iso_at(now - timedelta(hours=3))),
        _done_issue("ABC-2", same_title, _iso_at(now - timedelta(hours=1))),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)

    card = payload["cards"][0]
    # Newest completion among merged issues drives the fade.
    assert card["completedAtEpoch"] == int((now - timedelta(hours=1)).timestamp())


def test_render_cards_orders_done_cards_newest_first():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    tasks = [
        _issue("ABC-1", "Still open", "Todo"),
        _done_issue("ABC-2", "Done first", _iso_at(now - timedelta(hours=5))),
        _done_issue("ABC-3", "Done last", _iso_at(now - timedelta(hours=1))),
        _done_issue("ABC-4", "Done middle", _iso_at(now - timedelta(hours=3))),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)

    done_identifiers = [
        card["identifier"] for card in payload["cards"] if card["done"]
    ]
    # Cards flow top-down, left-right, so newest completion must come first.
    assert done_identifiers == ["ABC-3", "ABC-4", "ABC-2"]


def test_render_cards_uses_project_acronym():
    tasks = [
        _issue("ABC-1", "Comp work", "Todo", project="Competitions"),
        _issue("ABC-2", "Research", "Todo", project="CISC 595 - ChainReactor Research"),
        _issue("ABC-3", "No project", "Todo"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert cards_by_id["ABC-1"]["projectName"] == "C"
    assert cards_by_id["ABC-1"]["projectNames"] == ["Competitions"]
    assert cards_by_id["ABC-2"]["projectName"] == "C595-CRR"
    assert cards_by_id["ABC-2"]["projectNames"] == ["CISC 595 - ChainReactor Research"]
    assert cards_by_id["ABC-3"]["projectName"] == ""


@pytest.mark.parametrize(
    "project, project_icon, expected_icon",
    [
        ("Competitions", ":trophy:", "🏆"),
        ("Parking Ticket", ":male-police-officer:", "👮‍♂️"),
    ],
)
def test_render_cards_carries_project_icon(project, project_icon, expected_icon):
    tasks = [
        _issue("ABC-1", "Project work", "Todo", project=project, project_icon=project_icon),
        _issue("ABC-2", "Icon-less", "Todo", project="Hangout Automator", project_icon="Users"),
        _issue("ABC-3", "No project", "Todo"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert cards_by_id["ABC-1"]["projectIcon"] == expected_icon
    assert cards_by_id["ABC-2"]["projectIcon"] == ""
    assert cards_by_id["ABC-3"]["projectIcon"] == ""


def test_render_cards_merges_to_first_available_icon():
    # Same title across projects collapses into one card; the icon follows.
    tasks = [
        _issue("ABC-1", "Shared", "Todo", project="Hangout Automator", project_icon="Users"),
        _issue("ABC-2", "Shared", "Todo", project="Competitions", project_icon=":trophy:"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    card = payload["cards"][0]

    assert card["projectName"] == "HA / C"
    assert card["projectIcon"] == "🏆"


def test_project_acronym_keeps_capitals_digits_and_dashes():
    assert linear.project_acronym("Clusterfork") == "C"
    assert linear.project_acronym("Reading List") == "RL"
    assert linear.project_acronym("Condition Assessment Report Generator") == "CARG"
    assert linear.project_acronym("Linux State Search") == "LSS"
    assert linear.project_acronym("Hangout Automator") == "HA"
    assert linear.project_acronym("ChainReactor") == "CR"
    assert linear.project_acronym("CISC 595 - ChainReactor Research") == "C595-CRR"
    assert linear.project_acronym("WebApp-2") == "WA-2"
    assert linear.project_acronym("ISO-9001") == "I-9001"
    assert linear.project_acronym("API Gateway") == "AG"
    assert linear.project_acronym("NASA") == "N"
    assert linear.project_acronym("Competitions") == "C"
    assert linear.project_acronym("") == ""


def test_render_cards_carries_first_label():
    tasks = [
        _issue("ABC-1", "With labels", "Todo", labels=["software-catalog", "backend"]),
        _issue("ABC-2", "No labels", "Todo"),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    cards_by_id = {card["identifier"]: card for card in payload["cards"]}

    assert cards_by_id["ABC-1"]["label"] == "software-catalog"
    assert cards_by_id["ABC-1"]["labels"] == ["software-catalog", "backend"]
    assert cards_by_id["ABC-2"]["label"] == ""
    assert cards_by_id["ABC-2"]["labels"] == []


def test_render_cards_merges_to_first_available_label():
    # Merged cards without a label in the first issue pick up the label from later issues.
    tasks = [
        _issue("ABC-1", "Shared", "Todo"),
        _issue("ABC-2", "Shared", "Todo", labels=["infra", "devops"]),
    ]

    payload = linear.render_cards(tasks, {"Todo", "In Progress"}, lookback_hours=18)
    card = payload["cards"][0]

    assert card["label"] == "infra"
    assert card["labels"] == ["infra", "devops"]


def test_write_error_keeps_last_successful_cards(monkeypatch, tmp_path):
    cards_path = tmp_path / "linear-cards.json"
    cards_path.write_text(
        json.dumps(
            {
                "updatedAt": "2026-01-01T00:00:00+00:00",
                "cards": [{"identifier": "ABC-1", "title": "Keep me"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(linear, "CARDS_PATH", cards_path)
    monkeypatch.setattr(linear, "OUTPUT_PATH", tmp_path / "linear-tasks.txt")
    monkeypatch.setattr(linear, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(linear, "log_event", lambda _message: None)

    linear.write_error("network down")

    cached = json.loads(cards_path.read_text(encoding="utf-8"))
    assert cached["cards"][0]["identifier"] == "ABC-1"
    assert cached["stale"] is True
    assert cached["error"] == "network down"


def test_write_error_without_cache_writes_empty(monkeypatch, tmp_path):
    cards_path = tmp_path / "linear-cards.json"
    output_path = tmp_path / "linear-tasks.txt"
    monkeypatch.setattr(linear, "CARDS_PATH", cards_path)
    monkeypatch.setattr(linear, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(linear, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(linear, "log_event", lambda _message: None)

    linear.write_error("Missing LINEAR_API_KEY in .env")

    cached = json.loads(cards_path.read_text(encoding="utf-8"))
    assert cached["cards"] == []
    assert cached["error"] == "Missing LINEAR_API_KEY in .env"
    assert "stale" not in cached
    assert output_path.read_text(encoding="utf-8") == "Linear\nMissing LINEAR_API_KEY in .env\n"


def test_linear_request_sends_configured_query_depths(monkeypatch):
    captured = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured.append(json.loads(request.data.decode("utf-8")))
        assert timeout == 20
        if len(captured) == 1:
            return Response({"data": {}})
        return Response({"data": {"dueIssues": {
            "nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}})

    monkeypatch.setattr(linear.urllib.request, "urlopen", fake_urlopen)

    linear.linear_request("secret", 73, 84, 95, date(2026, 9, 17))

    assert captured[0]["variables"] == {
        "first": 73,
        "competitionFirst": 84,
        "backlogFirst": 95,
    }
    assert captured[1]["variables"] == {
        "first": 25, "after": None, "today": "2026-09-17",
    }


def test_linear_request_includes_overdue_issues_beyond_the_first_page(monkeypatch):
    now = datetime(2026, 9, 17, 12).astimezone()
    overdue = [
        _issue(f"ABC-{i}", f"Reading {i}", "Backlog", due_date="2026-09-10")
        for i in range(26)
    ]
    cursors = []

    def fake_request(_api_key, query, variables):
        if query == linear.QUERY:
            # The workflow connection overlaps the supplemental deadline query.
            return {"data": {"workflowStates": {"nodes": [
                {"name": "Backlog", "type": "backlog", "issues": {"nodes": overdue[:1]}},
            ]}}}
        cursors.append(variables["after"])
        assert variables["first"] == 25
        assert variables["today"] == "2026-09-17"
        first_page = variables["after"] is None
        return {"data": {"dueIssues": {
            "nodes": overdue[:25] if first_page else overdue[25:],
            "pageInfo": {"hasNextPage": first_page, "endCursor": "page-1" if first_page else "page-2"},
        }}}

    monkeypatch.setattr(linear, "linear_graphql_request", fake_request)

    response = linear.linear_request("secret", 25, 25, 25, now.date())
    tasks = linear.collect_tasks(response, {"Todo", "In Progress"}, now.date())
    cards = linear.render_cards(tasks, {"Todo", "In Progress"}, 18, now)["cards"]

    assert cursors == [None, "page-1"]
    assert len(cards) == 26
    assert {card["identifier"] for card in cards} == {task["identifier"] for task in overdue}
    assert all(card["dueDate"] == "Overdue · Sep 10" and card["dueToday"] for card in cards)


@pytest.mark.parametrize("failure", ["graphql", "http", "stuck_cursor"])
def test_due_issue_page_failure_keeps_last_successful_cards(monkeypatch, tmp_path, failure):
    cards_path = tmp_path / "linear-cards.json"
    previous_cards = [{"identifier": "ABC-1", "title": "Keep me"}]
    cards_path.write_text(json.dumps({"cards": previous_cards}), encoding="utf-8")
    monkeypatch.setattr(linear.sys, "argv", ["fetch_linear_tasks.py"])
    monkeypatch.setattr(linear, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(linear, "OUTPUT_PATH", tmp_path / "linear-tasks.txt")
    monkeypatch.setattr(linear, "CARDS_PATH", cards_path)
    monkeypatch.setattr(linear, "log_event", lambda _message: None)
    monkeypatch.setattr(linear.common, "load_env", lambda: None)
    monkeypatch.setenv("LINEAR_API_KEY", "secret")

    def fake_request(_api_key, query, variables):
        if query == linear.QUERY:
            return {"data": {"workflowStates": {"nodes": []}}}
        if variables["after"] and failure == "graphql":
            return {"errors": [{"message": "Query failed"}]}
        if variables["after"] and failure == "http":
            raise urllib.error.HTTPError(linear.API_URL, 503, "Unavailable", {}, None)
        return {"data": {"dueIssues": {
            "nodes": [_issue("ABC-2", "Partial page", "Backlog", due_date="2026-09-10")],
            "pageInfo": {"hasNextPage": True, "endCursor": "page-1"},
        }}}

    monkeypatch.setattr(linear, "linear_graphql_request", fake_request)

    assert linear.main() == 1
    cached = json.loads(cards_path.read_text(encoding="utf-8"))
    assert cached["cards"] == previous_cards
    assert cached["stale"] is True
    assert cached["error"]


def test_main_caps_configured_depths_to_the_live_query_complexity_limit(
    monkeypatch, tmp_path
):
    captured = {}
    monkeypatch.setattr(linear.sys, "argv", ["fetch_linear_tasks.py"])
    monkeypatch.setattr(linear, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(linear, "OUTPUT_PATH", tmp_path / "linear-tasks.txt")
    monkeypatch.setattr(linear, "CARDS_PATH", tmp_path / "linear-cards.json")
    monkeypatch.setattr(linear, "log_event", lambda _message: None)
    monkeypatch.setattr(linear.common, "load_env", lambda: None)
    monkeypatch.setenv("LINEAR_API_KEY", "secret")
    monkeypatch.setenv("LINEAR_TASK_LIMIT", "73")
    monkeypatch.setenv("LINEAR_COMPETITION_TASK_LIMIT", "84")
    monkeypatch.setenv("LINEAR_BACKLOG_DUE_SOON_LIMIT", "95")

    def fake_request(_api_key, limit, competition_limit, backlog_limit, _today):
        captured["limits"] = (limit, competition_limit, backlog_limit)
        return {
            "data": {
                "workflowStates": {"nodes": []},
                "competitionIssues": {"nodes": []},
                "backlogDueSoon": {"nodes": []},
            }
        }

    monkeypatch.setattr(linear, "linear_request", fake_request)

    assert linear.main() == 0
    assert captured["limits"] == (25, 25, 25)


def test_query_depth_env_uses_defaults_and_caps_large_values(monkeypatch):
    monkeypatch.setenv("LINEAR_TASK_LIMIT", "0")
    assert linear.query_depth_env("LINEAR_TASK_LIMIT", 25) == 25
    monkeypatch.setenv("LINEAR_TASK_LIMIT", "not-a-number")
    assert linear.query_depth_env("LINEAR_TASK_LIMIT", 25) == 25
    monkeypatch.setenv("LINEAR_TASK_LIMIT", "100")
    assert linear.query_depth_env("LINEAR_TASK_LIMIT", 25) == 25


def test_linear_http_error_message_includes_safe_graphql_detail():
    error = urllib.error.HTTPError(
        linear.API_URL,
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"errors":[{"message":"Query too complex"}]}'),
    )

    assert linear.linear_http_error_message(error) == "HTTP 400: Query too complex"
