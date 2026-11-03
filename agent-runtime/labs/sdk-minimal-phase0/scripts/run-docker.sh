#!/usr/bin/env bash
# Linux Docker runner for Phase 0; intentionally does not mount docker.sock.
set -euo pipefail

LAB="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$LAB/.local/dsh-home"
WORKSPACE="$LAB/.local/workspace"
RESULTS="$LAB/.local/results"
IMAGE="${DSH_LAB_IMAGE:-dsh-jd-agent-phase0:local}"
ACTION="${1:-help}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
need_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker CLI not installed"
  docker info >/dev/null 2>&1 || die "Docker daemon unavailable"
}
prepare() { mkdir -p -- "$STATE" "$WORKSPACE" "$RESULTS"; }
case "$ACTION" in
  build)
    need_docker
    docker build --build-arg "DSH_SDK_VERSION=${DSH_SDK_VERSION:-}" \
      -t "$IMAGE" -f "$LAB/docker/Dockerfile" "$LAB"
    ;;
  check)
    printf 'Lab: %s\nDocker: ' "$LAB"
    if command -v docker >/dev/null 2>&1; then docker --version; else echo 'not installed'; fi
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
      echo 'Docker daemon: available'
    else
      echo 'Docker daemon: unavailable'
    fi
    if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
      echo 'DEEPSEEK_API_KEY: configured (value hidden)'
    else
      echo 'DEEPSEEK_API_KEY: missing'
    fi
    echo "Image: $IMAGE"
    echo "Network: ${DSH_LAB_NETWORK:-bridge} (egress possible; limit via host firewall)"
    ;;
  run)
    need_docker
    [[ -n "${DEEPSEEK_API_KEY:-}" ]] || die "Export a dedicated DEEPSEEK_API_KEY first"
    prepare
    SESSION_ID="phase0-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    NETWORK="${DSH_LAB_NETWORK:-bridge}"
    [[ "$NETWORK" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid Docker network name"
    ARGS=(
      run --rm --init --read-only
      --cap-drop=ALL --security-opt=no-new-privileges
      --pids-limit=128 --memory=2g --cpus=2
      --user "$(id -u):$(id -g)"
      --network "$NETWORK"
      --tmpfs /tmp:rw,nosuid,nodev,size=64m
      --env DEEPSEEK_API_KEY
      --env "HOME=/sandbox/state" --env "DSH_HOME=/sandbox/state"
      --mount "type=bind,src=$LAB,dst=/sandbox/lab,readonly"
      --mount "type=bind,src=$STATE,dst=/sandbox/state"
      --mount "type=bind,src=$WORKSPACE,dst=/sandbox/workspace"
      --mount "type=bind,src=$RESULTS,dst=/sandbox/results"
    )
    if [[ -n "${DEEPSEEK_BASE_URL:-}" ]]; then ARGS+=(--env DEEPSEEK_BASE_URL); fi
    echo "Starting isolated Session: $SESSION_ID"
    docker "${ARGS[@]}" "$IMAGE" \
      python /sandbox/lab/src/run_phase0.py \
      --workspace /sandbox/workspace --dsh-home /sandbox/state \
      --patch /sandbox/lab/config/disable-session-upload.patch.yml \
      --output "/sandbox/results/$SESSION_ID.json" \
      --session-id "$SESSION_ID" --model "${DSH_MODEL:-deepseek-v4-flash}"
    echo "Inspect saved Session: bash scripts/run-docker.sh inspect"
    ;;
  inspect)
    prepare
    command -v python3 >/dev/null 2>&1 || die "python3 required"
    python3 "$LAB/src/session_report.py" --dsh-home "$STATE"
    ;;
  test)
    command -v python3 >/dev/null 2>&1 || die "python3 required"
    (cd "$LAB"; python3 -m unittest discover -s tests -v)
    ;;
  *)
    cat <<'HELP'
Usage: bash scripts/run-docker.sh {check|build|run|inspect|test}
  check   Show prerequisite status without revealing secrets
  build   Install SDK + matching runtime wheel in container (needs online Docker)
  run     Execute real agent (needs API key and network access)
  inspect Summarize native Session JSONL without printing payloads
  test    Local offline tests; no Docker, SDK or API key needed
Environment: DSH_SDK_VERSION, DSH_MODEL, DEEPSEEK_BASE_URL,
             DSH_LAB_NETWORK, DSH_LAB_IMAGE.
HELP
    ;;
esac
