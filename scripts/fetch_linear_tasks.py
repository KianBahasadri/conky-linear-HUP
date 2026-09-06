#!/usr/bin/env python3
import json
import os
import re
import sys
import textwrap
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import fetch_common as common

from fetch_common import parse_iso_epoch


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "linear-tasks.txt"
CARDS_PATH = CACHE_DIR / "linear-cards.json"
LOG_PATH = CACHE_DIR / "conky-linear.log"
API_URL = "https://api.linear.app/graphql"

# Keep in sync with conky/linear-card-renderer.lua layout constants.
CARD_WIDTH = 252
CARD_HEIGHT = 104
CARD_GAP = 12
ROW_GAP = 12
TOP_PADDING = 40
BOTTOM_PADDING = 0
EMPTY_HEIGHT = 144
OVERLAY_WIDTH = 1136
MAX_QUERY_DEPTH = 25
DEFAULT_TASK_LIMIT = 25
DEFAULT_COMPETITION_LIMIT = 25
DEFAULT_BACKLOG_LIMIT = 25


QUERY = """
query IssuesByWorkflowState($first: Int!, $competitionFirst: Int!, $backlogFirst: Int!) {
  workflowStates {
    nodes {
      name
      type
      issues(first: $first, orderBy: updatedAt) {
        nodes {
          ...IssueFields
        }
      }
    }
  }
  competitionIssues: issues(
    first: $competitionFirst,
    filter: {
      project: { name: { eq: "Competitions" } }
      dueDate: { gte: "P0D", lte: "P3D" }
      state: { type: { neq: "completed" } }
    }
  ) {
    nodes {
      ...IssueFields
    }
  }
  backlogDueSoon: issues(
    first: $backlogFirst,
    filter: {
      state: {
        name: { eq: "Backlog" }
        type: { neq: "completed" }
      }
      dueDate: { gte: "P0D", lte: "P3D" }
    }
  ) {
    nodes {
      ...IssueFields
    }
  }
}

fragment IssueFields on Issue {
  identifier
  title
  completedAt
  dueDate
  priorityLabel
  url
  project {
    name
    icon
  }
  state {
    name
    type
  }
  labels {
    nodes {
      name
      color
    }
  }
}
"""


# A Linear project icon is either an emoji shortcode (":trophy:") or the name of a
# built-in Linear icon ("Users"). Only shortcodes can be drawn on a card.
EMOJI_SHORTCODE_PATTERN = re.compile(r"^:([a-z0-9_+-]+):$")

# Most shortcodes are the Unicode character name with underscores for spaces, so
# unicodedata resolves them. These are the common ones where the two disagree.
EMOJI_SHORTCODE_ALIASES = {
    "+1": "👍", "-1": "👎", "100": "💯", "alien": "👽", "apple": "🍎", "art": "🎨", "beer": "🍺",
    "blush": "😊", "book": "📖", "boom": "💥", "bulb": "💡", "car": "🚗", "clap": "👏", "coffee": "☕",
    "computer": "💻", "construction": "🚧", "dart": "🎯", "dna": "🧬", "earth_americas": "🌎",
    "eggplant": "🍆", "email": "📧", "gem": "💎", "gift": "🎁", "headphones": "🎧", "heart": "❤",
    "heart_eyes": "😍", "house": "🏠", "iphone": "📱", "laughing": "😆", "link": "🔗", "mag": "🔍",
    "medal": "🏅", "mega": "📣", "moneybag": "💰", "mortar_board": "🎓", "ocean": "🌊",
    "office": "🏢", "ok_hand": "👌", "pencil": "📝", "phone": "☎", "pizza": "🍕",
    "point_right": "👉", "poop": "💩", "pray": "🙏", "recycle": "♻", "rotating_light": "🚨",
    "smile": "😄", "smiley": "😃", "sob": "😭", "star": "⭐", "sunny": "☀", "tada": "🎉", "tv": "📺",
    "warning": "⚠", "wave": "👋", "white_check_mark": "✅", "x": "❌", "zap": "⚡",
}


def project_acronym(name):
    """Compact a project name to an acronym for the card header.

    Uppercase letters are kept even without a preceding space (camelCase). An
    all-caps word contributes only its first letter. Digits, dashes, and other
    non-letters are kept; lowercase letters are dropped.
    """
    if not name:
        return ""

    parts = []
    for word in name.split():
        letters = [char for char in word if char.isalpha()]
        if not letters:
            parts.append(word)
            continue

        keep_first_letter_only = all(char.isupper() for char in letters)
        chars = []
        seen_letter = False
        for char in word:
            if char.isalpha():
                if keep_first_letter_only:
                    if not seen_letter:
                        chars.append(char)
                        seen_letter = True
                elif char.isupper():
                    chars.append(char)
            else:
                chars.append(char)
        if chars:
            parts.append("".join(chars))
    return "".join(parts)


def emoji_from_project_icon(icon):
    """Return the emoji for a Linear project icon, or "" when it is not an emoji."""
    if not icon:
        return ""

    match = EMOJI_SHORTCODE_PATTERN.match(icon.strip().lower())
    if not match:
        return ""

    shortcode = match.group(1)
    if shortcode in EMOJI_SHORTCODE_ALIASES:
        return EMOJI_SHORTCODE_ALIASES[shortcode]

    try:
        character = unicodedata.lookup(shortcode.replace("_", " ").upper())
    except KeyError:
        return ""

    # unicodedata also resolves control-character and letter names, so keep only
    # symbols the emoji font can actually draw.
    if unicodedata.category(character) != "So" and ord(character) < 0x1F000:
        return ""

    return character


log_event = common.make_logger(LOG_PATH, "fetch_linear_tasks")
atomic_write_text = common.atomic_write_text
atomic_write_json = common.atomic_write_json


def linear_request(api_key, limit, competition_limit, backlog_limit):
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "first": limit,
                "competitionFirst": competition_limit,
                "backlogFirst": backlog_limit,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def linear_http_error_message(error):
    """Return a bounded Linear error without exposing request credentials."""
    detail = ""
    try:
        payload = json.loads(error.read().decode("utf-8", errors="replace"))
        messages = [
            re.sub(r"\s+", " ", str(item.get("message", ""))).strip()
            for item in payload.get("errors", [])
            if isinstance(item, dict) and item.get("message")
        ]
        detail = "; ".join(messages)[:240]
    except (OSError, ValueError, AttributeError):
        pass
    suffix = f": {detail}" if detail else ""
    return f"HTTP {error.code}{suffix}"


def parse_linear_datetime(value):
    if not value:
        return None

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_recently_done(task, now, lookback_hours):
    completed_at = parse_linear_datetime(task.get("completedAt"))
    if not completed_at:
        return False

    return completed_at >= now - timedelta(hours=lookback_hours)


def is_due_now(task, now_date=None):
    due_date = task.get("dueDate")
    if not due_date:
        return False

    today = now_date or datetime.now().astimezone().date()
    return due_date <= today.isoformat()


def parse_linear_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def format_due_date(value, now_date=None):
    due_date = parse_linear_date(value)
    if not due_date:
        return ""

    today = now_date or datetime.now().astimezone().date()
    if due_date == today:
        return "Today"
    if due_date == today + timedelta(days=1):
        return "Tomorrow"

    return due_date.strftime("%b %d")


def is_completed(task):
    return task.get("state", {}).get("type") == "completed" or bool(task.get("completedAt"))


def is_cancelled_or_duplicate(task):
    state = task.get("state") or {}
    state_name = state.get("name", "").strip().lower()
    state_type = state.get("type", "").strip().lower()
    return state_name in {"canceled", "cancelled", "duplicate"} or state_type in {
        "canceled",
        "cancelled",
        "duplicate",
    }


def is_due_within_days(task, days=3, now_date=None):
    if is_cancelled_or_duplicate(task) or is_completed(task):
        return False

    due_date = parse_linear_date(task.get("dueDate"))
    if not due_date:
        return False

    today = now_date or datetime.now().astimezone().date()
    return today <= due_date <= today + timedelta(days=days)


def is_urgent(task):
    return (task.get("priorityLabel") or "").strip() == "Urgent"


def is_upcoming_competition(task, now_date=None):
    project_name = (task.get("project") or {}).get("name", "")
    if project_name != "Competitions":
        return False

    return is_due_within_days(task, days=3, now_date=now_date)


def is_due_soon_backlog(task, now_date=None):
    state_name = (task.get("state") or {}).get("name", "").strip()
    if state_name != "Backlog":
        return False

    return is_due_within_days(task, days=3, now_date=now_date)


def render(tasks, state_names, lookback_hours):
    local_now = datetime.now().astimezone()
    timestamp = local_now.strftime("%a %H:%M")
    now = local_now.astimezone(timezone.utc)
    active = [
        task
        for task in tasks
        if task.get("state", {}).get("name") in state_names and not is_cancelled_or_duplicate(task)
    ]
    recently_done = [
        task
        for task in tasks
        if is_recently_done(task, now, lookback_hours) and not is_cancelled_or_duplicate(task)
    ]
    visible = active + recently_done

    lines = [
        "${font JetBrains Mono:bold:size=13}${color f8fafc}Linear Focus${font}",
        f"${{color 94a3b8}}Updated {timestamp}  |  {len(active)} open  |  {len(recently_done)} done${{color}}",
        "${color 334155}------------------------------------------${color}",
    ]

    if not visible:
        lines.append("${color 94a3b8}No active or recently done tasks.${color}")
        return "\n".join(lines) + "\n"

    for task in visible:
        state = task.get("state", {}).get("name", "Unknown")
        identifier = task.get("identifier", "")
        title = task.get("title", "Untitled")
        priority = task.get("priorityLabel") or "No priority"
        done = task in recently_done
        state_label = "Done" if done else state
        state_color = "22c55e" if done else "facc15" if state == "In Progress" else "38bdf8"
        priority_color = {
            "Urgent": "f87171",
            "High": "fb923c",
            "Medium": "facc15",
            "Low": "94a3b8",
        }.get(priority, "64748b")
        wrapped_title = textwrap.wrap(title, width=40) or [title]

        lines.append(f"${{color {state_color}}}{state_label}${{color}}  ${{color 94a3b8}}{identifier}${{color}}")
        lines.append(f"  ${{color f8fafc}}{wrapped_title[0]}${{color}}")
        for continuation in wrapped_title[1:]:
            lines.append(f"  ${{color f8fafc}}{continuation}${{color}}")
        if done:
            completed_at = parse_linear_datetime(task.get("completedAt"))
            completed_time = completed_at.astimezone().strftime("%H:%M") if completed_at else "recently"
            lines.append(f"  ${{color 86efac}}Completed {completed_time}${{color}}")
        else:
            lines.append(f"  ${{color {priority_color}}}{priority}${{color}}")
        lines.append("${color 1e293b}------------------------------------------${color}")

    return "\n".join(lines).rstrip() + "\n"


def render_cards(tasks, state_names, lookback_hours, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone().date()
    active = [
        task
        for task in tasks
        if task.get("state", {}).get("name") in state_names and not is_cancelled_or_duplicate(task)
    ]
    recently_done = [
        task
        for task in tasks
        if is_recently_done(task, now, lookback_hours) and not is_cancelled_or_duplicate(task)
    ]
    # Green cards read newest-to-oldest, so most recently completed first.
    recently_done.sort(key=lambda task: parse_iso_epoch(task.get("completedAt")), reverse=True)
    upcoming_competitions = [
        task
        for task in tasks
        if is_upcoming_competition(task, today) and task not in active and task not in recently_done
    ]
    due_soon_backlog = [
        task
        for task in tasks
        if is_due_soon_backlog(task, today)
        and task not in active
        and task not in recently_done
        and task not in upcoming_competitions
    ]
    cards = []
    cards_by_title_and_done = {}

    for task in active + upcoming_competitions + due_soon_backlog + recently_done:
        title = task.get("title", "Untitled")
        identifier = task.get("identifier", "")
        project = task.get("project") or {}
        project_name = project.get("name", "")
        project_icon = emoji_from_project_icon(project.get("icon"))
        labels_nodes = (task.get("labels") or {}).get("nodes", [])
        task_labels = [
            node.get("name", "").strip()
            for node in labels_nodes
            if isinstance(node, dict) and node.get("name", "").strip()
        ]
        label = task_labels[0] if task_labels else ""
        task_done = task in recently_done
        urgent = is_urgent(task)
        competition_upcoming = is_upcoming_competition(task, today)
        backlog_due_soon = is_due_soon_backlog(task, today)
        group_key = (title, task_done)
        card = cards_by_title_and_done.get(group_key)

        if not card:
            card = {
                "identifier": identifier,
                "identifiers": [],
                "label": label,
                "labels": list(task_labels),
                "projectName": project_acronym(project_name),
                "projectNames": [],
                "projectIcon": project_icon,
                "state": task.get("state", {}).get("name", ""),
                "urgent": urgent,
                "title": title,
                "done": task_done,
                "dueToday": is_due_now(task, today),
                "dueIso": task.get("dueDate") or "",
                "dueDate": format_due_date(task.get("dueDate"), today),
                "competitionUpcoming": competition_upcoming,
                "competitionDueIso": task.get("dueDate") if competition_upcoming else "",
                "competitionDueDate": format_due_date(task.get("dueDate"), today)
                if competition_upcoming
                else "",
                "backlogDueSoon": backlog_due_soon,
                "completedAtEpoch": 0,
            }
            cards_by_title_and_done[group_key] = card
            cards.append(card)

        if identifier and identifier not in card["identifiers"]:
            card["identifiers"].append(identifier)

        if len(card["identifiers"]) > 1:
            card["identifier"] = "   ".join(card["identifiers"])

        if label and not card["label"]:
            card["label"] = label

        for item in task_labels:
            if item not in card["labels"]:
                card["labels"].append(item)

        if project_name and project_name not in card["projectNames"]:
            card["projectNames"].append(project_name)
            card["projectName"] = " / ".join(
                project_acronym(item) for item in card["projectNames"]
            )
            # Merged cards show one icon: the first project that has an emoji.
            if not card["projectIcon"]:
                card["projectIcon"] = project_icon

        card["done"] = card["done"] and task_done
        card["urgent"] = card["urgent"] or urgent
        card["dueToday"] = card["dueToday"] or is_due_now(task, today)
        current_due_date = parse_linear_date(card["dueIso"])
        task_due_date = parse_linear_date(task.get("dueDate"))
        if not current_due_date or (task_due_date and task_due_date < current_due_date):
            card["dueIso"] = task.get("dueDate") or ""
            card["dueDate"] = format_due_date(task.get("dueDate"), today)

        card["competitionUpcoming"] = card["competitionUpcoming"] or competition_upcoming
        if competition_upcoming:
            current_due_date = parse_linear_date(card["competitionDueIso"])
            if not current_due_date or (task_due_date and task_due_date < current_due_date):
                card["competitionDueIso"] = task.get("dueDate")
                card["competitionDueDate"] = format_due_date(task.get("dueDate"), today)

        card["backlogDueSoon"] = card.get("backlogDueSoon", False) or backlog_due_soon

        if task_done:
            # Fade timing keys off the newest completion among merged issues.
            completed_epoch = parse_iso_epoch(task.get("completedAt"))
            if completed_epoch > card["completedAtEpoch"]:
                card["completedAtEpoch"] = completed_epoch

        if task.get("state", {}).get("name") == "In Progress" and not task_done:
            card["state"] = "In Progress"

    return {
        "updatedAt": now.isoformat(),
        "doneLookbackSeconds": lookback_hours * 3600,
        "cards": cards,
    }


def collect_tasks(response, state_names, now_date=None):
    today = now_date or datetime.now().astimezone().date()
    tasks_by_identifier = {}
    states = response["data"]["workflowStates"]["nodes"]

    for state in states:
        for task in state["issues"]["nodes"]:
            if is_cancelled_or_duplicate(task) or (
                state.get("name") not in state_names
                and state.get("type") != "completed"
                and not is_upcoming_competition(task, today)
                and not is_due_soon_backlog(task, today)
            ):
                continue

            tasks_by_identifier[task["identifier"]] = task

    for task in response["data"].get("competitionIssues", {}).get("nodes", []):
        if not is_cancelled_or_duplicate(task) and is_upcoming_competition(task, today):
            tasks_by_identifier[task["identifier"]] = task

    for task in response["data"].get("backlogDueSoon", {}).get("nodes", []):
        if not is_cancelled_or_duplicate(task) and is_due_soon_backlog(task, today):
            tasks_by_identifier[task["identifier"]] = task

    return sorted(
        tasks_by_identifier.values(),
        key=lambda task: (task.get("state", {}).get("name", ""), task.get("identifier", "")),
    )


def load_cached_cards():
    try:
        payload = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        return None
    return payload


def write_error(message):
    # Keep the last good cards so a timeout or DNS blip does not blank the overlay.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    previous = load_cached_cards()
    if previous:
        previous["stale"] = True
        previous["error"] = message
        atomic_write_json(CARDS_PATH, previous)
        log_event(f"error: {message} (kept {len(previous['cards'])} cached cards)")
        return

    atomic_write_text(OUTPUT_PATH, f"Linear\n{message}\n")
    atomic_write_json(
        CARDS_PATH,
        {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": message,
            "cards": [],
        },
    )
    log_event(f"error: {message}")


def linear_overlay_height(card_count, window_width=OVERLAY_WIDTH):
    """Return the Conky minimum_height needed for the card grid.

    Must match the layout math in conky/linear-card-renderer.lua.
    """
    if card_count <= 0:
        return EMPTY_HEIGHT

    cards_per_row = max(1, (window_width + CARD_GAP) // (CARD_WIDTH + CARD_GAP))
    rows = min(3, (card_count + cards_per_row - 1) // cards_per_row)
    return TOP_PADDING + rows * CARD_HEIGHT + max(0, rows - 1) * ROW_GAP + BOTTOM_PADDING


def card_count_from_cache(cards_path=CARDS_PATH):
    path = Path(cards_path)
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    cards = payload.get("cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list):
        return 0
    cards = [card for card in cards if isinstance(card, dict) and card.get("title")]
    if any(card.get("dueToday") and not card.get("done") for card in cards):
        cards = [card for card in cards if any(card.get(key) for key in
                 ("done", "dueToday", "competitionUpcoming", "backlogDueSoon"))]
    return len(cards)


def positive_int_env(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def query_depth_env(name, default):
    # The three connections share one GraphQL operation. Although Linear allows
    # larger individual pages, this combined shape returns "Query too complex"
    # above 25 in the live workspace.
    return min(positive_int_env(name, default), MAX_QUERY_DEPTH)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--print-overlay-height":
        print(linear_overlay_height(card_count_from_cache()))
        return 0
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    log_event("starting Linear fetch")

    api_key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not api_key:
        write_error("Missing LINEAR_API_KEY in .env")
        return 1

    state_names = {
        item.strip()
        for item in os.environ.get("LINEAR_TASK_STATES", "Todo,In Progress").split(",")
        if item.strip()
    }

    limit = query_depth_env("LINEAR_TASK_LIMIT", DEFAULT_TASK_LIMIT)
    competition_limit = query_depth_env(
        "LINEAR_COMPETITION_TASK_LIMIT", DEFAULT_COMPETITION_LIMIT
    )
    backlog_limit = query_depth_env(
        "LINEAR_BACKLOG_DUE_SOON_LIMIT", DEFAULT_BACKLOG_LIMIT
    )

    try:
        lookback_hours = int(os.environ.get("LINEAR_DONE_LOOKBACK_HOURS", "18"))
    except ValueError:
        lookback_hours = 18

    state_list = ",".join(sorted(state_names)) or "none"
    log_event(
        f"querying {API_URL} operation=IssuesByWorkflowState first={limit} "
        f"competition_first={competition_limit} backlog_first={backlog_limit} "
        f"active_states={state_list} done_lookback_hours={lookback_hours}"
    )

    try:
        response = linear_request(api_key, limit, competition_limit, backlog_limit)
    except urllib.error.HTTPError as error:
        write_error(f"Linear API error: {linear_http_error_message(error)}")
        return 1
    except Exception as error:
        write_error(f"Linear fetch failed: {error}")
        return 1

    if response.get("errors"):
        write_error("Linear API returned GraphQL errors")
        print(json.dumps(response["errors"], indent=2), file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    today = now.astimezone().date()
    tasks = collect_tasks(response, state_names, today)
    active_count = sum(
        1
        for task in tasks
        if task.get("state", {}).get("name") in state_names and not is_cancelled_or_duplicate(task)
    )
    done_count = sum(
        1
        for task in tasks
        if is_recently_done(task, now, lookback_hours) and not is_cancelled_or_duplicate(task)
    )
    due_now_count = sum(
        1
        for task in tasks
        if is_due_now(task, today) and not is_cancelled_or_duplicate(task)
    )
    workflow_state_count = len(response.get("data", {}).get("workflowStates", {}).get("nodes", []))
    output = render(tasks, state_names, lookback_hours)
    cards_payload = render_cards(tasks, state_names, lookback_hours, now)
    atomic_write_text(OUTPUT_PATH, output)
    atomic_write_json(CARDS_PATH, cards_payload)
    card_count = len(cards_payload.get("cards") or [])
    # Height is ${lua_parse linear_height_spacer}. Do not rewrite generated
    # configs or SIGUSR1 Conky: that destroys the window and the cards vanish.
    overlay_height = linear_overlay_height(card_count)
    log_event(
        f"completed fetch workflow_states={workflow_state_count} collected_tasks={len(tasks)} "
        f"active={active_count} recently_done={done_count} due_now={due_now_count} "
        f"cards={card_count} overlay_height={overlay_height} "
        f"wrote={OUTPUT_PATH.name},{CARDS_PATH.name}"
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
