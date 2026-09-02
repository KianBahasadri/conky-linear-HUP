#!/usr/bin/env bash
set -euo pipefail

# Provision the least-privilege IAM user the billing fetcher uses, then write
# its access key into .env. Bootstrap identity is whatever AWS credentials
# Terraform can already resolve (typically `aws login`); that identity is not
# stored or reused by the overlay.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$ROOT/terraform/aws-billing"
ENV_PATH="$ROOT/.env"

# Terraform state contains the generated access-key secret. Restrict the
# process umask before Terraform can create either state or backup files.
umask 077

secure_state_files() {
  local state_path
  for state_path in "$TF_DIR"/*.tfstate "$TF_DIR"/*.tfstate.*; do
    [[ -e "$state_path" ]] || continue
    chmod 0600 -- "$state_path"
  done
  return 0
}

# Terraform may update state even when apply later fails. Repair any existing
# files up front and again before returning control to the caller.
trap secure_state_files EXIT
secure_state_files

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is not installed\n' >&2
  exit 1
fi

if ! command -v terraform >/dev/null 2>&1; then
  printf 'terraform is not installed\n' >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  printf 'aws CLI is not installed (needed once to create the IAM user)\n' >&2
  exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  printf 'AWS session missing or expired. Run: aws login\n' >&2
  printf 'Terraform uses that identity once to create the billing-read IAM user.\n' >&2
  exit 1
fi

terraform -chdir="$TF_DIR" init -input=false
terraform -chdir="$TF_DIR" apply "$@"
secure_state_files

set +x
key_id="$(terraform -chdir="$TF_DIR" output -raw access_key_id)"
secret="$(terraform -chdir="$TF_DIR" output -raw secret_access_key)"
secure_state_files

if [[ -z "$key_id" || -z "$secret" ]]; then
  printf 'terraform did not return an access key\n' >&2
  exit 1
fi

export _BILLING_KEY_ID="$key_id"
export _BILLING_SECRET="$secret"
uv --project "$ROOT" run --no-dev python - "$ENV_PATH" "$SCRIPT_DIR" <<'PY'
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
from fetch_common import atomic_write_text

path = Path(sys.argv[1])
updates = {
    "BILLING_AWS_ENABLED": "1",
    "BILLING_AWS_ACCESS_KEY_ID": os.environ["_BILLING_KEY_ID"],
    "BILLING_AWS_SECRET_ACCESS_KEY": os.environ["_BILLING_SECRET"],
}

lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
seen = set()
out = []
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)

missing = [key for key in updates if key not in seen]
if missing:
    if out and out[-1] != "":
        out.append("")
    out.append("# AWS billing IAM user from terraform/aws-billing")
    for key in missing:
        out.append(f"{key}={updates[key]}")

mode = 0o600
if path.exists():
    mode = stat.S_IMODE(path.stat().st_mode) & 0o600 or 0o600

atomic_write_text(path, "\n".join(out) + "\n", mode=mode)
PY
unset _BILLING_KEY_ID _BILLING_SECRET key_id secret

printf 'Wrote BILLING_AWS_ACCESS_KEY_ID / BILLING_AWS_SECRET_ACCESS_KEY to %s\n' "$ENV_PATH"
printf 'IAM user can only call Cost Explorer, Budgets, and CloudWatch DescribeAlarms.\n'
