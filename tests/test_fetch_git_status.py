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
