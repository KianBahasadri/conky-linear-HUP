import json
import os
import subprocess
from pathlib import Path

import pytest

import fetch_git_status as git_status


def init_repo(path: Path, branch="main"):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def test_split_path_list_accepts_colons_commas_and_newlines():
    assert git_status.split_path_list("~/a:~/b,~/c\n~/d") == ["~/a", "~/b", "~/c", "~/d"]


def test_parse_repo_paths_expands_and_dedupes(tmp_path, monkeypatch):
    a = tmp_path / "alpha"
    b = tmp_path / "beta"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    # Use absolute paths so expanduser is not required for uniqueness.
    raw = f"{a}:{b}:{a}"
    paths = git_status.parse_repo_paths(raw)
    assert paths == [a.resolve(), b.resolve()]


def test_parse_porcelain_v2_counts_and_branch():
    output = "\n".join(
        [
            "# branch.oid abc",
            "# branch.head feature/x",
            "# branch.upstream origin/feature/x",
            "# branch.ab +2 -1",
            "1 M. N... 100644 100644 100644 aaa bbb staged.txt",
            "1 .M N... 100644 100644 100644 ccc ddd dirty.txt",
            "1 MM N... 100644 100644 100644 eee fff both.txt",
            "u UU N... 100644 100644 100644 ggg hhh conflict.txt",
            "? untracked.txt",
            "",
        ]
    )
    parsed = git_status.parse_porcelain_v2(output)
    assert parsed["branch"] == "feature/x"
    assert parsed["upstream"] == "origin/feature/x"
    assert parsed["ahead"] == 2
    assert parsed["behind"] == 1
    assert parsed["staged"] == 2  # M. and MM
    assert parsed["modified"] == 2  # .M and MM
    assert parsed["untracked"] == 1
    assert parsed["conflicted"] == 1
    assert parsed["detached"] is False
    assert parsed["changed_paths"] == [
        "staged.txt",
        "dirty.txt",
        "both.txt",
        "conflict.txt",
        "untracked.txt",
    ]


def test_porcelain_v2_path_reads_rename_dest():
    line = "2 R. N... 100644 100644 100644 aaa bbb R100 new.txt\told.txt"
    assert git_status.porcelain_v2_path(line) == "new.txt"


def test_parse_porcelain_detached():
    parsed = git_status.parse_porcelain_v2("# branch.head (detached)\n")
    assert parsed["detached"] is True
    assert parsed["branch"] == "DETACHED"


def test_inspect_repo_clean(tmp_path):
    repo = init_repo(tmp_path / "clean-repo")
    status = git_status.inspect_repo(repo, timeout=5)
    assert status["ok"] is True
    assert status["state"] == "clean"
    assert status["clean"] is True
    assert status["branch"] == "main"
    assert status["name"] == "clean-repo"
    assert status["lastModifiedEpoch"] > 0


def test_inspect_repo_dirty_and_untracked(tmp_path):
    repo = init_repo(tmp_path / "dirty-repo")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    status = git_status.inspect_repo(repo, timeout=5)
    assert status["ok"] is True
    assert status["state"] == "dirty"
    assert status["modified"] >= 1
    assert status["untracked"] >= 1
    assert status["severity"] >= git_status.SEVERITY_DIRTY


def test_inspect_repo_last_modified_uses_dirty_file_mtime(tmp_path):
    repo = init_repo(tmp_path / "touched")
    _rewrite_head_date(repo, 1_700_000_000)
    target = repo / "README.md"
    target.write_text("changed\n", encoding="utf-8")
    later = 1_800_000_000
    os.utime(target, (later, later))
    status = git_status.inspect_repo(repo, timeout=5)
    assert status["ok"] is True
    assert status["lastModifiedEpoch"] == later


def test_inspect_repo_missing_path(tmp_path):
    status = git_status.inspect_repo(tmp_path / "nope", timeout=2)
    assert status["ok"] is False
    assert status["state"] == "error"
    assert "not found" in status["error"]


def test_collect_status_sorts_by_severity(tmp_path, monkeypatch):
    clean = init_repo(tmp_path / "aaa-clean")
    dirty = init_repo(tmp_path / "zzz-dirty")
    (dirty / "README.md").write_text("dirty\n", encoding="utf-8")

    monkeypatch.setenv("GIT_INCLUDE_STASH", "0")
    # Pass paths explicitly so home scan does not leak into the unit test.
    status = git_status.collect_status(
        repo_paths=[clean, dirty], timeout=5, hide_clean=False, max_repos=10
    )

    assert status["ok"] is True
    assert status["summary"]["total"] == 2
    assert status["summary"]["dirty"] == 1
    assert status["summary"]["clean"] == 1
    assert status["repos"][0]["name"] == "zzz-dirty"
    assert status["repos"][1]["name"] == "aaa-clean"


def test_sort_repos_uses_last_modified_before_name():
    repos = [
        {"name": "aaa-old", "severity": 40, "lastModifiedEpoch": 100},
        {"name": "zzz-new", "severity": 40, "lastModifiedEpoch": 200},
        {"name": "mid-new", "severity": 40, "lastModifiedEpoch": 200},
        {"name": "clean-newest", "severity": 0, "lastModifiedEpoch": 999},
    ]
    names = [repo["name"] for repo in git_status.sort_repos(repos)]
    assert names == ["mid-new", "zzz-new", "aaa-old", "clean-newest"]


def test_collect_status_sorts_same_severity_by_last_modified(tmp_path, monkeypatch):
    older = init_repo(tmp_path / "zzz-older")
    newer = init_repo(tmp_path / "aaa-newer")
    _rewrite_head_date(older, 1_700_000_000)
    _rewrite_head_date(newer, 1_800_000_000)

    monkeypatch.setenv("GIT_INCLUDE_STASH", "0")
    status = git_status.collect_status(
        repo_paths=[older, newer], timeout=5, hide_clean=False, max_repos=10
    )
    names = [repo["name"] for repo in status["repos"]]
    assert names == ["aaa-newer", "zzz-older"]
    assert status["repos"][0]["lastModifiedEpoch"] > status["repos"][1]["lastModifiedEpoch"]


def test_collect_status_hide_clean(tmp_path, monkeypatch):
    clean = init_repo(tmp_path / "clean")
    dirty = init_repo(tmp_path / "dirty")
    (dirty / "x.txt").write_text("x\n", encoding="utf-8")

    monkeypatch.setenv("GIT_INCLUDE_STASH", "0")
    status = git_status.collect_status(
        repo_paths=[clean, dirty], timeout=5, hide_clean=True, max_repos=10
    )
    names = [repo["name"] for repo in status["repos"]]
    assert names == ["dirty"]


def test_collect_status_requires_paths(monkeypatch):
    monkeypatch.delenv("GIT_REPO_PATHS", raising=False)
    status = git_status.collect_status(repo_paths=[], timeout=2)
    assert status["ok"] is False
    assert "No git repos" in status["error"] or "GIT_REPO_PATHS" in status["error"]


def _rewrite_head_date(repo: Path, epoch: int):
    import os

    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = str(epoch)
    env["GIT_COMMITTER_DATE"] = str(epoch)
    subprocess.run(
        ["git", "commit", "--amend", "--no-edit", f"--date=@{epoch}"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def test_scan_home_for_recent_repos_filters_by_commit_age(tmp_path):
    init_repo(tmp_path / "recent-app")
    old = init_repo(tmp_path / "old-app")
    not_repo = tmp_path / "notes"
    not_repo.mkdir()
    (not_repo / "readme.txt").write_text("hi\n", encoding="utf-8")

    # Two months ago — outside the default 14-day window.
    _rewrite_head_date(old, 1_700_000_000)

    paths = git_status.scan_home_for_recent_repos(
        root=tmp_path, since_days=14, max_depth=2, timeout=5
    )
    names = {path.name for path in paths}
    assert "recent-app" in names
    assert "old-app" not in names
    assert "notes" not in names


def test_scan_home_includes_dirty_repo_regardless_of_commit_age(tmp_path):
    recent = init_repo(tmp_path / "recent-app")
    old = init_repo(tmp_path / "old-app")
    # Two months ago — outside the 14-day window.
    _rewrite_head_date(old, 1_700_000_000)
    # But old-app has an untracked file, so it is dirty and should be surfaced.
    (old / "scratch.txt").write_text("wip\n", encoding="utf-8")

    paths = git_status.scan_home_for_recent_repos(
        root=tmp_path, since_days=14, max_depth=2, timeout=5
    )
    names = {path.name for path in paths}
    assert "recent-app" in names
    assert "old-app" in names


def test_scan_home_excludes_clean_old_repo(tmp_path):
    clean_old = init_repo(tmp_path / "stale-clean")
    _rewrite_head_date(clean_old, 1_700_000_000)

    paths = git_status.scan_home_for_recent_repos(
        root=tmp_path, since_days=14, max_depth=2, timeout=5
    )
    names = {path.name for path in paths}
    assert "stale-clean" not in names


def test_resolve_repo_paths_merges_pinned_and_scanned(tmp_path, monkeypatch):
    pinned = init_repo(tmp_path / "pinned")
    scanned = init_repo(tmp_path / "scanned")
    # Old pinned-only repo would still be included via GIT_REPO_PATHS.
    stale = init_repo(tmp_path / "stale-pin")
    _rewrite_head_date(stale, 1_700_000_000)

    discovery = tmp_path / "discovery.json"
    monkeypatch.setattr(git_status, "DISCOVERY_PATH", discovery)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_ROOT", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_TTL_SECONDS", "60")
    monkeypatch.setenv("GIT_REPO_PATHS", f"{pinned}:{stale}")
    monkeypatch.delenv("GIT_REPO_BLACKLIST", raising=False)

    paths = [path.resolve() for path in git_status.resolve_repo_paths(timeout=5)]
    assert paths[0] == pinned.resolve()
    assert stale.resolve() in paths  # pinned even though old
    assert scanned.resolve() in paths  # from scan
    assert discovery.exists()


def test_resolve_repo_paths_auto_discovers_when_unset(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "auto-found")
    discovery = tmp_path / "discovery.json"
    monkeypatch.setattr(git_status, "DISCOVERY_PATH", discovery)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_ROOT", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_TTL_SECONDS", "60")
    monkeypatch.delenv("GIT_REPO_PATHS", raising=False)
    monkeypatch.delenv("GIT_REPO_BLACKLIST", raising=False)

    paths = git_status.resolve_repo_paths(timeout=5)
    assert repo.resolve() in [path.resolve() for path in paths]
    assert discovery.exists()


def test_blacklist_filters_by_basename_and_path(tmp_path, monkeypatch):
    keep = init_repo(tmp_path / "keep-me")
    drop_name = init_repo(tmp_path / "drop-me")
    drop_path = init_repo(tmp_path / "also-drop")

    discovery = tmp_path / "discovery.json"
    monkeypatch.setattr(git_status, "DISCOVERY_PATH", discovery)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_ROOT", str(tmp_path))
    monkeypatch.setenv("GIT_SCAN_TTL_SECONDS", "60")
    # Pinned drop-name is still removed by basename blacklist.
    monkeypatch.setenv("GIT_REPO_PATHS", str(drop_name))
    monkeypatch.setenv("GIT_REPO_BLACKLIST", f"drop-me:{drop_path}")

    paths = {path.resolve() for path in git_status.resolve_repo_paths(timeout=5)}
    assert keep.resolve() in paths
    assert drop_name.resolve() not in paths
    assert drop_path.resolve() not in paths


def test_parse_blacklist_accepts_names_and_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    rules = git_status.parse_blacklist(f"noise:~/secret:{tmp_path / 'abs'}")
    assert "noise" in rules
    assert any(isinstance(rule, Path) for rule in rules)


def test_gh_run_list_command_includes_branch_only_when_real():
    assert git_status.gh_run_list_command("acme", "tools", "main") == [
        "gh",
        "run",
        "list",
        "--repo",
        "acme/tools",
        "--limit",
        "10",
        "--json",
        "status,conclusion,headBranch,name",
        "--branch",
        "main",
    ]
    assert "--branch" not in git_status.gh_run_list_command("acme", "tools", "DETACHED")


def test_parse_gh_run_list_accepts_array_payload():
    raw = '[{"status":"completed","conclusion":"success","headBranch":"main","name":"CI"}]'
    assert git_status.parse_gh_run_list(raw)[0]["conclusion"] == "success"
    assert git_status.parse_gh_run_list("[]") == []
    assert git_status.parse_gh_run_list("{}") == []


def test_fetch_workflow_runs_falls_back_to_repo_latest(monkeypatch):
    calls = []

    def fake_list(owner, repo, branch, timeout):
        calls.append(branch)
        if branch:
            return []
        return [{"status": "completed", "conclusion": "failure"}]

    monkeypatch.setattr(git_status, "_gh_run_list", fake_list)
    runs = git_status.fetch_workflow_runs("acme", "tools", "feature", 4)
    assert calls == ["feature", ""]
    assert runs[0]["conclusion"] == "failure"


def test_parse_github_remote_accepts_ssh_https_and_strips_git_suffix():
    assert git_status.parse_github_remote("git@github.com:KianBahasadri/conky-linear-HUP.git") == (
        "KianBahasadri",
        "conky-linear-HUP",
    )
    assert git_status.parse_github_remote("https://github.com/KianBahasadri/linux-state-search") == (
        "KianBahasadri",
        "linux-state-search",
    )
    assert git_status.parse_github_remote("ssh://git@github.com/acme/tools.git") == ("acme", "tools")
    assert git_status.parse_github_remote("git@gitlab.com:acme/tools.git") is None
    assert git_status.parse_github_remote("") is None


def test_classify_workflow_runs_prefers_active_then_latest_completed():
    assert git_status.classify_workflow_runs([]) == ""
    assert (
        git_status.classify_workflow_runs(
            [
                {"status": "in_progress", "conclusion": None},
                {"status": "completed", "conclusion": "failure"},
            ]
        )
        == "run"
    )
    assert (
        git_status.classify_workflow_runs(
            [
                {"status": "completed", "conclusion": "cancelled"},
                {"status": "completed", "conclusion": "failure"},
            ]
        )
        == "fail"
    )
    assert (
        git_status.classify_workflow_runs(
            [
                {"status": "completed", "conclusion": "skipped"},
                {"status": "completed", "conclusion": "success"},
            ]
        )
        == "ok"
    )
    assert git_status.classify_workflow_runs([{"status": "completed", "conclusion": "cancelled"}]) == ""


def test_actions_cache_fresh_uses_shorter_ttl_while_running(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setenv("GIT_ACTIONS_TTL_SECONDS", "180")
    monkeypatch.setenv("GIT_ACTIONS_RUNNING_TTL_SECONDS", "20")
    now = datetime(2026, 8, 17, 1, 0, 0, tzinfo=timezone.utc)
    running = {
        "branch": "main",
        "actions": "run",
        "fetchedAtEpoch": int(now.timestamp()) - 25,
    }
    ok = {
        "branch": "main",
        "actions": "ok",
        "fetchedAtEpoch": int(now.timestamp()) - 25,
    }
    assert git_status.actions_cache_fresh(running, "main", now) is False
    assert git_status.actions_cache_fresh(ok, "main", now) is True
    assert git_status.actions_cache_fresh(ok, "feature", now) is False


def test_attach_actions_uses_cache_and_fetches_stale(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    repo = init_repo(tmp_path / "with-origin")
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:acme/with-origin.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    other = init_repo(tmp_path / "gitlab-only")
    subprocess.run(
        ["git", "remote", "add", "origin", "git@gitlab.com:acme/other.git"],
        cwd=other,
        check=True,
        capture_output=True,
    )

    cache_path = tmp_path / "git-actions-cache.json"
    monkeypatch.setattr(git_status, "ACTIONS_CACHE_PATH", cache_path)
    monkeypatch.setenv("GIT_ACTIONS_ENABLED", "1")
    monkeypatch.setenv("GIT_ACTIONS_TTL_SECONDS", "180")
    monkeypatch.setenv("GIT_ACTIONS_RUNNING_TTL_SECONDS", "20")
    monkeypatch.setattr(git_status, "log_event", lambda _message: None)

    now = datetime(2026, 8, 17, 1, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setenv("GIT_ACTIONS_TIMEOUT_SECONDS", "6")
    cache_path.write_text(
        json.dumps(
            {
                "repos": {
                    str(repo): {
                        "owner": "acme",
                        "repo": "with-origin",
                        "branch": "main",
                        "actions": "ok",
                        "fetchedAtEpoch": int(now.timestamp()) - 10,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    calls = []

    def fake_fetch(owner, name, branch, timeout):
        calls.append((owner, name, branch, timeout))
        return [{"status": "in_progress", "conclusion": None}]

    status = {
        "ok": True,
        "repos": [
            {"name": "with-origin", "path": str(repo), "branch": "main", "ok": True},
            {"name": "gitlab-only", "path": str(other), "branch": "main", "ok": True},
        ],
    }
    attached = git_status.attach_actions(status, now=now, fetch_runs=fake_fetch)
    assert attached["repos"][0]["actions"] == "ok"
    assert attached["repos"][1]["actions"] == ""
    assert calls == []

    # Stale running cache should refetch.
    cache_path.write_text(
        json.dumps(
            {
                "repos": {
                    str(repo): {
                        "owner": "acme",
                        "repo": "with-origin",
                        "branch": "main",
                        "actions": "run",
                        "fetchedAtEpoch": int(now.timestamp()) - 40,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    attached = git_status.attach_actions(status, now=now, fetch_runs=fake_fetch)
    assert attached["repos"][0]["actions"] == "run"
    assert calls == [("acme", "with-origin", "main", 6.0)]


def test_attach_actions_keeps_stale_pip_when_fetch_fails(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    repo = init_repo(tmp_path / "flaky")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/acme/flaky.git"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    cache_path = tmp_path / "git-actions-cache.json"
    monkeypatch.setattr(git_status, "ACTIONS_CACHE_PATH", cache_path)
    monkeypatch.setenv("GIT_ACTIONS_ENABLED", "1")
    monkeypatch.setenv("GIT_ACTIONS_TTL_SECONDS", "1")
    monkeypatch.setattr(git_status, "log_event", lambda _message: None)

    now = datetime(2026, 8, 17, 1, 0, 0, tzinfo=timezone.utc)
    cache_path.write_text(
        json.dumps(
            {
                "repos": {
                    str(repo): {
                        "owner": "acme",
                        "repo": "flaky",
                        "branch": "main",
                        "actions": "fail",
                        "fetchedAtEpoch": int(now.timestamp()) - 60,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def boom(_owner, _name, _branch, _timeout):
        raise TimeoutError("github down")

    status = {
        "ok": True,
        "repos": [{"name": "flaky", "path": str(repo), "branch": "main", "ok": True}],
    }
    attached = git_status.attach_actions(status, now=now, fetch_runs=boom)
    assert attached["repos"][0]["actions"] == "fail"


def test_attach_actions_disabled_clears_pips(monkeypatch):
    monkeypatch.setenv("GIT_ACTIONS_ENABLED", "0")
    status = {"ok": True, "repos": [{"name": "x", "path": "/tmp/x", "actions": "run"}]}
    attached = git_status.attach_actions(status)
    assert attached["repos"][0]["actions"] == ""
