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

set +x
key_id="$(terraform -chdir="$TF_DIR" output -raw access_key_id)"
secret="$(terraform -chdir="$TF_DIR" output -raw secret_access_key)"

if [[ -z "$key_id" || -z "$secret" ]]; then
  printf 'terraform did not return an access key\n' >&2
  exit 1
fi

export _BILLING_KEY_ID="$key_id"
export _BILLING_SECRET="$secret"
uv --project "$ROOT" run --no-dev python - "$ENV_PATH" <<'PY'
import os
import sys
from pathlib import Path

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

path.write_text("\n".join(out) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY
unset _BILLING_KEY_ID _BILLING_SECRET key_id secret

printf 'Wrote BILLING_AWS_ACCESS_KEY_ID / BILLING_AWS_SECRET_ACCESS_KEY to %s\n' "$ENV_PATH"
printf 'IAM user can only call Cost Explorer, Budgets, and CloudWatch DescribeAlarms.\n'
