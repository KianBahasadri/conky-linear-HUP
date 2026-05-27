#!/usr/bin/env python3
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "linear-tasks.txt"
CARDS_PATH = CACHE_DIR / "linear-cards.json"
LOG_PATH = CACHE_DIR / "conky-linear.log"
API_URL = "https://api.linear.app/graphql"


QUERY = """
query IssuesByWorkflowState($first: Int!, $competitionFirst: Int!) {
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
  }
  state {
    name
    type
  }
}
"""


def load_env(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def log_event(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] fetch_linear_tasks: {message}\n")


def atomic_write_text(path, content):
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def atomic_write_json(path, data):
    atomic_write_text(path, json.dumps(data, indent=2))


def linear_request(api_key, limit, competition_limit):
    payload = json.dumps(
        {"query": QUERY, "variables": {"first": limit, "competitionFirst": competition_limit}}
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


def parse_linear_datetime(value):
    if not value:
        return None

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_recently_done(task, now, lookback_hours):
    completed_at = parse_linear_datetime(task.get("completedAt"))
    if not completed_at:
        return False

    return completed_at >= now - timedelta(hours=lookback_hours)


def is_due_now(task):
    due_date = task.get("dueDate")
    if not due_date:
        return False

    return due_date <= datetime.now().date().isoformat()


def parse_linear_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def format_due_date(value, now_date=None):
    due_date = parse_linear_date(value)
    if not due_date:
        return ""

    today = now_date or datetime.now().date()
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


def is_upcoming_competition(task, now_date=None):
    if is_cancelled_or_duplicate(task):
        return False

    if is_completed(task):
        return False

    project_name = (task.get("project") or {}).get("name", "")
    if project_name != "Competitions":
        return False

    due_date = parse_linear_date(task.get("dueDate"))
    if not due_date:
        return False

    today = now_date or datetime.now().date()
    return today <= due_date <= today + timedelta(days=3)


def render(tasks, state_names, lookback_hours):
    timestamp = datetime.now().strftime("%a %H:%M")
    now = datetime.now(timezone.utc)
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


def render_cards(tasks, state_names, lookback_hours):
    now = datetime.now(timezone.utc)
    today = datetime.now().date()
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
    upcoming_competitions = [
        task
        for task in tasks
        if is_upcoming_competition(task, today) and task not in active and task not in recently_done
    ]
    cards = []
    cards_by_title_and_done = {}

    for task in active + upcoming_competitions + recently_done:
        title = task.get("title", "Untitled")
        identifier = task.get("identifier", "")
        task_done = task in recently_done
        competition_upcoming = is_upcoming_competition(task, today)
        group_key = (title, task_done)
        card = cards_by_title_and_done.get(group_key)

        if not card:
            card = {
                "identifier": identifier,
                "identifiers": [],
                "state": task.get("state", {}).get("name", ""),
                "title": title,
                "done": task_done,
                "dueToday": is_due_now(task),
                "dueIso": task.get("dueDate") or "",
                "dueDate": format_due_date(task.get("dueDate"), today),
                "competitionUpcoming": competition_upcoming,
                "competitionDueIso": task.get("dueDate") if competition_upcoming else "",
                "competitionDueDate": format_due_date(task.get("dueDate"), today)
                if competition_upcoming
                else "",
            }
            cards_by_title_and_done[group_key] = card
            cards.append(card)

        if identifier and identifier not in card["identifiers"]:
            card["identifiers"].append(identifier)

        if len(card["identifiers"]) > 1:
            card["identifier"] = "   ".join(card["identifiers"])

        card["done"] = card["done"] and task_done
        card["dueToday"] = card["dueToday"] or is_due_now(task)
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

        if task.get("state", {}).get("name") == "In Progress" and not task_done:
            card["state"] = "In Progress"

    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "cards": cards,
    }


def collect_tasks(response, state_names):
    tasks_by_identifier = {}
    states = response["data"]["workflowStates"]["nodes"]

    for state in states:
        for task in state["issues"]["nodes"]:
            if is_cancelled_or_duplicate(task) or (
                state.get("name") not in state_names
                and state.get("type") != "completed"
                and not is_upcoming_competition(task)
            ):
                continue

            tasks_by_identifier[task["identifier"]] = task

    for task in response["data"].get("competitionIssues", {}).get("nodes", []):
        if not is_cancelled_or_duplicate(task) and is_upcoming_competition(task):
            tasks_by_identifier[task["identifier"]] = task

    return sorted(
        tasks_by_identifier.values(),
        key=lambda task: (task.get("state", {}).get("name", ""), task.get("identifier", "")),
    )


def write_error(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
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


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    load_env(ENV_PATH)
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

    try:
        limit = int(os.environ.get("LINEAR_TASK_LIMIT", "20"))
    except ValueError:
        limit = 20

    try:
        competition_limit = int(os.environ.get("LINEAR_COMPETITION_TASK_LIMIT", "50"))
    except ValueError:
        competition_limit = 50

    try:
        lookback_hours = int(os.environ.get("LINEAR_DONE_LOOKBACK_HOURS", "18"))
    except ValueError:
        lookback_hours = 18

    state_list = ",".join(sorted(state_names)) or "none"
    log_event(
        f"querying {API_URL} operation=IssuesByWorkflowState first={limit} "
        f"competition_first={competition_limit} active_states={state_list} "
        f"done_lookback_hours={lookback_hours}"
    )

    try:
        response = linear_request(api_key, limit, competition_limit)
    except urllib.error.HTTPError as error:
        write_error(f"Linear API error: HTTP {error.code}")
        return 1
    except Exception as error:
        write_error(f"Linear fetch failed: {error}")
        return 1

    if response.get("errors"):
        write_error("Linear API returned GraphQL errors")
        print(json.dumps(response["errors"], indent=2), file=sys.stderr)
        return 1

    tasks = collect_tasks(response, state_names)
    now = datetime.now(timezone.utc)
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
        1 for task in tasks if is_due_now(task) and not is_cancelled_or_duplicate(task)
    )
    workflow_state_count = len(response.get("data", {}).get("workflowStates", {}).get("nodes", []))
    output = render(tasks, state_names, lookback_hours)
    atomic_write_text(OUTPUT_PATH, output)
    atomic_write_json(CARDS_PATH, render_cards(tasks, state_names, lookback_hours))
    log_event(
        f"completed fetch workflow_states={workflow_state_count} collected_tasks={len(tasks)} "
        f"active={active_count} recently_done={done_count} due_now={due_now_count} "
        f"wrote={OUTPUT_PATH.name},{CARDS_PATH.name}"
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
