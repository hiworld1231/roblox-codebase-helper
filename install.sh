#!/bin/sh
# One command: curl -fsSL https://raw.githubusercontent.com/hiworld1231/roblox-codebase-helper/main/install.sh | sh
set -eu
case "$(uname -s)" in Linux) ;; *) echo 'This command supports Linux. Use install.ps1 on Windows.' >&2; exit 1;; esac
case "$(uname -m)" in x86_64|amd64) asset=codebase-helper-linux-x86_64;; *) echo 'Ready-made binary supports Linux x86_64. Use Python 3.11+ source setup for other architectures.' >&2; exit 1;; esac
base=https://github.com/hiworld1231/roblox-codebase-helper/releases/latest/download
task_dir=$(mktemp -d)
trap 'rm -rf "$task_dir"' EXIT HUP INT TERM
curl -fL --retry 2 "$base/$asset" -o "$task_dir/$asset"
curl -fsSL --retry 2 "$base/$asset.sha256" -o "$task_dir/$asset.sha256"
(cd "$task_dir" && sha256sum -c "$asset.sha256")
chmod +x "$task_dir/$asset"
"$task_dir/$asset" --cli "$@"
