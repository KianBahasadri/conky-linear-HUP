import json
import os
import shutil
import signal
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

import install_webdav_service as webdav


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE_HELPER = ROOT / "scripts" / "conky_lifecycle.sh"
OVERLAY_KEYS = (
    "linear",
    "rate-limit-panel",
    "minecraft",
    "github",
    "weather",
    "resource-monitor",
    "billing",
    "git",
    "sessions",
)


def write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def lifecycle_status(pid_file: Path, script: Path, project_root: Path) -> str:
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; classify_fetch_loop_pid "$2" "$3" "$4"; '
            'printf "%s\\n" "$FETCH_LOOP_PID_STATUS"',
            "bash",
            str(LIFECYCLE_HELPER),
            str(pid_file),
            str(script),
            str(project_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_launcher_repo(tmp_path: Path, xrandr_output: str = "") -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    conky = repo / "conky"
    bin_dir = tmp_path / "bin"
    cache = repo / "cache"
    scripts.mkdir(parents=True)
    conky.mkdir()
    bin_dir.mkdir()
    cache.mkdir()

    shutil.copy2(ROOT / "scripts" / "start_conky_overlays.sh", scripts)
    shutil.copy2(LIFECYCLE_HELPER, scripts)
    template = textwrap.dedent(
        """
        conky.config = {
          alignment = 'bottom_left',
          gap_x = 1,
          gap_y = 1,
          minimum_height = 100,
          minimum_width = 400,
          maximum_width = 400,
          lua_load = './conky/overlay-entrypoint.lua',
        }
        conky.text = [[demo]]
        """
    ).lstrip()
    for key in OVERLAY_KEYS:
        (conky / f"{key}-overlay.conkyrc").write_text(template, encoding="utf-8")

    xrandr_path = tmp_path / "xrandr-output"
    xrandr_path.write_text(xrandr_output, encoding="utf-8")
    write_executable(
        bin_dir / "xrandr",
        """
        #!/usr/bin/env bash
        cat "$XRANDR_TEST_OUTPUT"
        """,
    )
    write_executable(
        bin_dir / "uv",
        """
        #!/usr/bin/env bash
        case "$*" in
          *--print-rate-limit-panel-frame-width*) printf '1000\\n' ;;
          *--print-rate-limit-panel-frame-height*) printf '296\\n' ;;
          *--print-rate-limit-panel-height*) printf '320\\n' ;;
          *--print-overlay-height*)
            if [[ "$*" == *fetch_sessions.py* ]]; then printf '790\\n'; else printf '292\\n'; fi
            ;;
          *" - "*) exec python "${@: -2}" ;;
          *) printf '292\\n' ;;
        esac
        """,
    )
    write_executable(
        bin_dir / "pgrep",
        """
        #!/usr/bin/env bash
        printf 'pgrep %s\\n' "$*" >> "$PROCESS_CALLS"
        exit 1
        """,
    )
    write_executable(
        bin_dir / "pkill",
        """
        #!/usr/bin/env bash
        printf 'pkill %s\\n' "$*" >> "$PROCESS_CALLS"
        exit 0
        """,
    )
    write_executable(
        bin_dir / "conky",
        """
        #!/usr/bin/env bash
        printf 'conky %s\\n' "$*" >> "$PROCESS_CALLS"
        """,
    )
    return repo, bin_dir


def launcher_env(repo: Path, bin_dir: Path, tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "XRANDR_TEST_OUTPUT": str(tmp_path / "xrandr-output"),
        "PROCESS_CALLS": str(tmp_path / "process-calls"),
        "CONKY_LIFECYCLE_LOCKED": "0",
    }


def test_fetch_pid_classifier_requires_the_exact_sets_id_loop_shape(tmp_path):
    script = tmp_path / "fetch_demo.py"
    project_root = tmp_path / "repo"
    pid_file = tmp_path / "loop.pid"
    body = 'project_root="$8"; while true; do sleep 10; done'
    process = subprocess.Popen(
        [
            "bash",
            "-c",
            body,
            "bash",
            str(script),
            str(tmp_path / "demo.log"),
            "60",
            "",
            "60",
            "300",
            "600",
            str(project_root),
        ],
        start_new_session=True,
    )
    try:
        pid_file.write_text(f"{process.pid}\n", encoding="utf-8")
        assert lifecycle_status(pid_file, script, project_root) == "owned"
        assert lifecycle_status(pid_file, tmp_path / "other.py", project_root) == "foreign"
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)


def test_stop_launcher_finds_and_stops_owned_fetch_loop_without_pid_file(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "cache").mkdir()
    (repo / "conky" / "generated").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "stop_conky_overlays.sh", repo / "scripts")
    shutil.copy2(LIFECYCLE_HELPER, repo / "scripts")
    script = repo / "scripts" / "fetch_linear_tasks.py"
    body = 'project_root="$8"; while true; do sleep 10; done'
    process = subprocess.Popen(
        [
            "bash",
            "-c",
            body,
            "bash",
            str(script),
            str(repo / "cache" / "conky-linear.log"),
            "60",
            "",
            "60",
            "300",
            "600",
            str(repo),
        ],
        start_new_session=True,
    )
    try:
        subprocess.run(
            [str(repo / "scripts" / "stop_conky_overlays.sh")],
            check=True,
            env={**os.environ, "CONKY_LIFECYCLE_LOCKED": "0"},
            timeout=20,
        )
        process.wait(timeout=5)
        log = (repo / "cache" / "conky-linear.log").read_text(encoding="utf-8")
        assert f"stopped Linear fetch loop pid={process.pid}" in log
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)


def test_stop_launcher_removes_foreign_pid_file_without_signaling(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "cache").mkdir()
    (repo / "conky" / "generated").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "stop_conky_overlays.sh", repo / "scripts")
    shutil.copy2(LIFECYCLE_HELPER, repo / "scripts")
    foreign_config = repo / "conky" / "generated" / "linear-overlay-0.conkyrc"
    sleeper = subprocess.Popen(
        ["bash", "-c", "sleep 60 & wait", "bash", str(foreign_config)],
        start_new_session=True,
    )
    try:
        pid_file = repo / "cache" / "linear-fetch-loop.pid"
        pid_file.write_text(f"{sleeper.pid}\n", encoding="utf-8")
        subprocess.run(
            [str(repo / "scripts" / "stop_conky_overlays.sh")],
            check=True,
            env={**os.environ, "CONKY_LIFECYCLE_LOCKED": "0"},
        )
        assert sleeper.poll() is None
        assert not pid_file.exists()
        log = (repo / "cache" / "conky-linear.log").read_text(encoding="utf-8")
        assert "without signaling" in log
    finally:
        os.killpg(sleeper.pid, signal.SIGTERM)
        sleeper.wait(timeout=5)


def test_log_rotation_caps_the_retained_tail_and_shifts_generations(tmp_path):
    log = tmp_path / "conky-demo.log"
    log.write_text("".join(f"line-{index:02d}\n" for index in range(30)), encoding="utf-8")
    (tmp_path / "conky-demo.log.1").write_text("older\n", encoding="utf-8")
    (tmp_path / "conky-demo.log.3").write_text("obsolete\n", encoding="utf-8")
    (tmp_path / "conky-demo.log.5").write_text("obsolete\n", encoding="utf-8")
    subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; rotate_log_file "$2" 50 2',
            "bash",
            str(LIFECYCLE_HELPER),
            str(log),
        ],
        check=True,
    )
    retained = tmp_path / "conky-demo.log.1"
    assert not log.exists()
    assert retained.stat().st_size <= 50
    assert retained.read_text(encoding="utf-8").startswith("line-")
    assert (tmp_path / "conky-demo.log.2").read_text(encoding="utf-8") == "older\n"
    assert not (tmp_path / "conky-demo.log.3").exists()
    assert not (tmp_path / "conky-demo.log.5").exists()


def test_generate_only_preserves_processes_logs_and_pid_files_and_honors_env(
    tmp_path,
):
    xrandr = (
        "Monitors: 2\n"
        " 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
        " 1: +DP-2 1920/1x1080/1-1920+0 DP-2\n"
    )
    repo, bin_dir = make_launcher_repo(tmp_path, xrandr)
    (repo / ".env").write_text(
        "MINECRAFT_GAP_X=123\nCONKY_LOG_MAX_BYTES=20\n",
        encoding="utf-8",
    )
    pid_file = repo / "cache" / "linear-fetch-loop.pid"
    pid_file.write_text("99999999\n", encoding="utf-8")
    log = repo / "cache" / "conky-linear.log"
    original_log = "an existing live log that is intentionally oversized\n"
    log.write_text(original_log, encoding="utf-8")
    env = launcher_env(repo, bin_dir, tmp_path)
    env["MINECRAFT_GAP_X"] = "77"

    result = subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), "--generate-only"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "Generated 18 overlay config(s) for 2 monitor(s)" in result.stdout
    assert pid_file.read_text(encoding="utf-8") == "99999999\n"
    assert not Path(env["PROCESS_CALLS"]).exists()
    assert not (repo / "cache" / "conky-linear.log.1").exists()
    assert log.read_text(encoding="utf-8").startswith(original_log)
    minecraft = (repo / "conky" / "generated" / "minecraft-overlay-0.conkyrc").read_text()
    assert "  gap_x = 77," in minecraft
    assert not list((repo / "conky" / "generated").glob("*.tmp.*"))


@pytest.mark.parametrize(
    "arguments",
    [("--generateonly",), ("foo", "--generate-only"), ("--generate-only", "extra")],
)
def test_start_launcher_rejects_unknown_or_extra_arguments_without_mutation(
    tmp_path, arguments
):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )

    result = subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), *arguments],
        capture_output=True,
        text=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert not list((repo / "cache").glob("conky-*.log"))
    assert not (repo / "conky" / "generated").exists()
    assert not Path(launcher_env(repo, bin_dir, tmp_path)["PROCESS_CALLS"]).exists()


def test_stop_launcher_rejects_arguments_without_stopping(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "cache").mkdir()
    shutil.copy2(ROOT / "scripts" / "stop_conky_overlays.sh", repo / "scripts")
    shutil.copy2(LIFECYCLE_HELPER, repo / "scripts")

    result = subprocess.run(
        [str(repo / "scripts" / "stop_conky_overlays.sh"), "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "CONKY_LIFECYCLE_LOCKED": "0"},
    )

    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert not list((repo / "cache").glob("conky-*.log"))


def test_generate_only_uses_cached_negative_coordinate_layout(tmp_path):
    repo, bin_dir = make_launcher_repo(tmp_path)
    (repo / "cache" / "monitor-layout.json").write_text(
        json.dumps(
            [
                {"index": 0, "name": "DP-1", "x": 0, "y": 0,
                 "width": 1920, "height": 1080},
                {"index": 1, "name": "DP-2", "x": -1920, "y": -200,
                 "width": 1920, "height": 1080},
            ]
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), "--generate-only"],
        check=True,
        capture_output=True,
        text=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )
    assert "for 2 monitor(s)" in result.stdout
    assert (repo / "conky" / "generated" / "sessions-overlay-1.conkyrc").is_file()


@pytest.mark.parametrize("generate_only", [True, False])
def test_failed_generation_preserves_live_state_and_last_usable_configs(
    tmp_path, generate_only
):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )
    generated = repo / "conky" / "generated"
    generated.mkdir()
    earlier_last_good = generated / "linear-overlay-0.conkyrc"
    earlier_last_good.write_text("earlier last known good\n", encoding="utf-8")
    last_good = generated / "weather-overlay-0.conkyrc"
    last_good.write_text("last known good\n", encoding="utf-8")
    stale_but_usable = generated / "sessions-overlay-9.conkyrc"
    stale_but_usable.write_text("previous layout\n", encoding="utf-8")
    (repo / "conky" / "weather-overlay.conkyrc").unlink()
    pid_file = repo / "cache" / "linear-fetch-loop.pid"
    pid_file.write_text("99999999\n", encoding="utf-8")
    command = [str(repo / "scripts" / "start_conky_overlays.sh")]
    if generate_only:
        command.append("--generate-only")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )

    assert result.returncode != 0
    assert earlier_last_good.read_text(encoding="utf-8") == "earlier last known good\n"
    assert last_good.read_text(encoding="utf-8") == "last known good\n"
    assert stale_but_usable.read_text(encoding="utf-8") == "previous layout\n"
    assert pid_file.read_text(encoding="utf-8") == "99999999\n"
    assert not list(generated.glob("*.tmp.*"))
    assert not list(generated.glob(".generation.*"))


def test_launcher_validates_every_configurable_fetch_interval(tmp_path):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )
    variables = (
        "RATE_LIMIT_CHANGED_INTERVAL",
        "RATE_LIMIT_UNCHANGED_INTERVAL",
        "RATE_LIMIT_RECENT_CHANGE_WINDOW",
        "MINECRAFT_REFRESH_SECONDS",
        "GITHUB_REFRESH_SECONDS",
        "WEATHER_REFRESH_SECONDS",
        "WORKOUTS_REFRESH_SECONDS",
        "BILLING_REFRESH_SECONDS",
        "GIT_REFRESH_SECONDS",
        "SESSIONS_REFRESH_SECONDS",
    )
    (repo / ".env").write_text(
        "".join(f"{variable}=0\n" for variable in variables), encoding="utf-8"
    )
    subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), "--generate-only"],
        check=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )
    combined_logs = "".join(
        path.read_text(encoding="utf-8")
        for path in (repo / "cache").glob("conky-*.log")
    )
    for variable in variables:
        assert f"invalid {variable}=0" in combined_logs


def test_launcher_validates_every_arithmetic_geometry_input(tmp_path):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )
    variables = (
        "RATE_LIMIT_PANEL_GAP_Y",
        "GITHUB_SKYLINE_HEIGHT",
        "GITHUB_SKYLINE_MIN_HEIGHT",
        "GITHUB_LINEAR_CLEARANCE",
        "GITHUB_ROOF_CLEARANCE",
        "MINECRAFT_GAP_X",
        "MINECRAFT_GAP_Y",
        "GITHUB_GAP_X",
        "GITHUB_GAP_Y",
        "SESSIONS_GAP_X",
        "SESSIONS_GAP_Y",
        "WEATHER_GAP_X",
        "WEATHER_GAP_Y",
        "RESOURCE_MONITOR_GAP_X",
        "RESOURCE_MONITOR_GAP_Y",
        "GIT_GAP_X",
        "GIT_GAP_Y",
    )
    (repo / ".env").write_text(
        "".join(f"{variable}=not-a-number\n" for variable in variables),
        encoding="utf-8",
    )

    subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), "--generate-only"],
        check=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )

    combined_logs = "".join(
        path.read_text(encoding="utf-8")
        for path in (repo / "cache").glob("conky-*.log")
    )
    for variable in variables:
        assert f"invalid {variable}=not-a-number" in combined_logs


def test_launcher_rejects_zero_padded_bash_arithmetic_values(tmp_path):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )
    variables = (
        "RATE_LIMIT_PANEL_GAP_Y",
        "GITHUB_LINEAR_CLEARANCE",
        "LINEAR_PRIMARY_MONITOR_INDEX",
        "PRIMARY_WAIT_SECONDS",
    )
    (repo / ".env").write_text(
        "".join(f"{variable}=08\n" for variable in variables), encoding="utf-8"
    )

    subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh"), "--generate-only"],
        check=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )

    combined_logs = "".join(
        path.read_text(encoding="utf-8")
        for path in (repo / "cache").glob("conky-*.log")
    )
    for variable in variables:
        assert f"invalid {variable}=08" in combined_logs


def test_live_start_rotates_logs_but_launches_nothing_when_overlays_disabled(tmp_path):
    repo, bin_dir = make_launcher_repo(
        tmp_path, "Monitors: 1\n 0: +*DP-1 1920/1x1080/1+0+0 DP-1\n"
    )
    disabled = "\n".join(
        (
            "LINEAR_OVERLAY_ENABLED=0",
            "RATE_LIMIT_PANEL_ENABLED=0",
            "MINECRAFT_OVERLAY_ENABLED=0",
            "GITHUB_OVERLAY_ENABLED=0",
            "WEATHER_OVERLAY_ENABLED=0",
            "RESOURCE_MONITOR_OVERLAY_ENABLED=0",
            "BILLING_OVERLAY_ENABLED=0",
            "GIT_OVERLAY_ENABLED=0",
            "SESSIONS_OVERLAY_ENABLED=0",
            "CONKY_LOG_MAX_BYTES=80",
        )
    )
    (repo / ".env").write_text(disabled + "\n", encoding="utf-8")
    log = repo / "cache" / "conky-linear.log"
    log.write_text("old line\n" * 100, encoding="utf-8")

    subprocess.run(
        [str(repo / "scripts" / "start_conky_overlays.sh")],
        check=True,
        env=launcher_env(repo, bin_dir, tmp_path),
    )

    assert (repo / "cache" / "conky-linear.log.1").stat().st_size <= 80
    calls_path = Path(launcher_env(repo, bin_dir, tmp_path)["PROCESS_CALLS"])
    calls = calls_path.read_text(encoding="utf-8") if calls_path.exists() else ""
    assert "conky " not in calls
    assert "pkill " not in calls


def test_autostart_installer_writes_a_valid_direct_exec_entry(tmp_path):
    config_home = tmp_path / "config"
    subprocess.run(
        [str(ROOT / "scripts" / "install_autostart.sh")],
        check=True,
        env={**os.environ, "XDG_CONFIG_HOME": str(config_home)},
    )
    desktop_file = config_home / "autostart" / "linear-conky-overlay.desktop"
    content = desktop_file.read_text(encoding="utf-8")
    assert f'Exec="{ROOT / "scripts" / "start_conky_overlays.sh"}"' in content
    assert "bash -lc" not in content
    assert "X-GNOME-Autostart-Delay=5" in content
    validator = shutil.which("desktop-file-validate")
    if validator:
        subprocess.run([validator, str(desktop_file)], check=True)


def test_aws_bootstrap_creates_terraform_state_private_from_first_write(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    terraform_dir = repo / "terraform" / "aws-billing"
    bin_dir = tmp_path / "bin"
    scripts.mkdir(parents=True)
    terraform_dir.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / "apply_aws_billing_iam.sh", scripts)
    shutil.copy2(ROOT / "scripts" / "fetch_common.py", scripts)
    write_executable(bin_dir / "aws", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(bin_dir / "uv", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(
        bin_dir / "terraform",
        """
        #!/usr/bin/env bash
        terraform_dir="${1#-chdir=}"
        : > "$terraform_dir/terraform.tfstate"
        stat -c '%a' "$terraform_dir/terraform.tfstate" > "$STATE_MODE_RECORD"
        exit 1
        """,
    )
    mode_record = tmp_path / "state-mode"

    result = subprocess.run(
        [str(scripts / "apply_aws_billing_iam.sh")],
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "STATE_MODE_RECORD": str(mode_record),
        },
    )

    assert result.returncode != 0
    assert mode_record.read_text(encoding="utf-8").strip() == "600"
    assert stat.S_IMODE((terraform_dir / "terraform.tfstate").stat().st_mode) == 0o600


def test_aws_bootstrap_preserves_env_selector_symlink(tmp_path):
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    terraform_dir = repo / "terraform" / "aws-billing"
    bin_dir = tmp_path / "bin"
    scripts.mkdir(parents=True)
    terraform_dir.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / "apply_aws_billing_iam.sh", scripts)
    shutil.copy2(ROOT / "scripts" / "fetch_common.py", scripts)
    env_target = repo / "env.actual"
    env_target.write_text("KEEP_ME=yes\n", encoding="utf-8")
    env_target.chmod(0o600)
    (repo / ".env").symlink_to(env_target.name)
    write_executable(bin_dir / "aws", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(
        bin_dir / "uv",
        """
        #!/usr/bin/env bash
        while [[ "$1" != "python" ]]; do shift; done
        shift
        exec python "$@"
        """,
    )
    write_executable(
        bin_dir / "terraform",
        """
        #!/usr/bin/env bash
        if [[ "$*" == *"output -raw access_key_id"* ]]; then
          printf 'AKIATEST'
        elif [[ "$*" == *"output -raw secret_access_key"* ]]; then
          printf 'secret-test-value'
        fi
        """,
    )

    subprocess.run(
        [str(scripts / "apply_aws_billing_iam.sh"), "-auto-approve"],
        check=True,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert (repo / ".env").is_symlink()
    content = env_target.read_text(encoding="utf-8")
    assert "KEEP_ME=yes" in content
    assert "BILLING_AWS_ACCESS_KEY_ID=AKIATEST" in content
    assert "BILLING_AWS_SECRET_ACCESS_KEY=secret-test-value" in content
    assert stat.S_IMODE(env_target.stat().st_mode) == 0o600


def test_webdav_private_write_is_atomic_and_repairs_permissions(tmp_path):
    path = tmp_path / "secret"
    path.write_text("old", encoding="utf-8")
    path.chmod(0o644)
    webdav.write_private(path, "new\n")
    assert path.read_text(encoding="utf-8") == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".secret.*"))


def test_webdav_existing_hash_without_plaintext_password_is_rejected(tmp_path, monkeypatch):
    htpasswd = tmp_path / "webdav.htpasswd"
    password = tmp_path / "webdav-password.txt"
    htpasswd.write_text("kian:hash\n", encoding="utf-8")
    monkeypatch.setattr(webdav, "HTPASSWD_PATH", htpasswd)
    monkeypatch.setattr(webdav, "PASSWORD_PATH", password)
    try:
        webdav.ensure_auth()
    except RuntimeError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("orphaned htpasswd should require explicit rotation")


def test_webdav_service_environment_quotes_dynamic_paths(tmp_path, monkeypatch):
    service_env = tmp_path / "webdav-service.env"
    monkeypatch.setattr(webdav, "WORKOUTS_DIR", tmp_path / "workouts with space")
    monkeypatch.setattr(webdav, "HTPASSWD_PATH", tmp_path / 'auth "file"')
    monkeypatch.setattr(webdav, "SERVICE_ENV_PATH", service_env)
    webdav.write_service_environment()
    content = service_env.read_text(encoding="utf-8")
    assert 'RCLONE_WEBDAV_WORKOUTS_DIR="' in content
    assert "workouts with space" in content
    assert '\\"file\\"' in content
    assert stat.S_IMODE(service_env.stat().st_mode) == 0o600


def make_aws_apply_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "aws-repo"
    scripts = repo / "scripts"
    terraform_dir = repo / "terraform" / "aws-billing"
    bin_dir = tmp_path / "aws-bin"
    scripts.mkdir(parents=True)
    terraform_dir.mkdir(parents=True)
    bin_dir.mkdir()
    shutil.copy2(ROOT / "scripts" / "apply_aws_billing_iam.sh", scripts)
    shutil.copy2(ROOT / "scripts" / "fetch_common.py", scripts)
    write_executable(
        bin_dir / "aws",
        """
        #!/usr/bin/env bash
        exit 0
        """,
    )
    write_executable(
        bin_dir / "uv",
        """
        #!/usr/bin/env bash
        while (($#)); do
          if [[ "$1" == "python" ]]; then
            shift
            exec python "$@"
          fi
          shift
        done
        exit 2
        """,
    )
    write_executable(
        bin_dir / "terraform",
        """
        #!/usr/bin/env bash
        terraform_dir=""
        command_name=""
        output_name=""
        for argument in "$@"; do
          case "$argument" in
            -chdir=*) terraform_dir="${argument#-chdir=}" ;;
            init|apply|output) command_name="$argument" ;;
            access_key_id|secret_access_key) output_name="$argument" ;;
          esac
        done
        case "$command_name" in
          init) exit 0 ;;
          apply)
            printf '{"sensitive":"state"}\n' > "$terraform_dir/terraform.tfstate"
            chmod 0644 "$terraform_dir/terraform.tfstate"
            if [[ "${TF_FAKE_FAIL:-0}" == "1" ]]; then exit 1; fi
            ;;
          output)
            if [[ "$output_name" == "access_key_id" ]]; then
              printf 'AKIATEST'
            else
              printf 'test-secret-value'
            fi
            ;;
        esac
        exit 0
        """,
    )
    return repo, bin_dir


def test_aws_apply_secures_state_and_atomically_preserves_env(tmp_path):
    repo, bin_dir = make_aws_apply_repo(tmp_path)
    env_path = repo / ".env"
    env_path.write_text("KEEP=this line survives\n", encoding="utf-8")
    env_path.chmod(0o644)
    result = subprocess.run(
        [str(repo / "scripts" / "apply_aws_billing_iam.sh"), "-auto-approve"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    state_path = repo / "terraform" / "aws-billing" / "terraform.tfstate"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    content = env_path.read_text(encoding="utf-8")
    assert "KEEP=this line survives" in content
    assert "BILLING_AWS_ACCESS_KEY_ID=AKIATEST" in content
    assert "BILLING_AWS_SECRET_ACCESS_KEY=test-secret-value" in content
    assert "test-secret-value" not in result.stdout + result.stderr
    assert not list(repo.glob(".env.*"))


def test_aws_apply_secures_state_even_when_terraform_fails(tmp_path):
    repo, bin_dir = make_aws_apply_repo(tmp_path)
    result = subprocess.run(
        [str(repo / "scripts" / "apply_aws_billing_iam.sh")],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TF_FAKE_FAIL": "1",
        },
    )
    assert result.returncode != 0
    state_path = repo / "terraform" / "aws-billing" / "terraform.tfstate"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
