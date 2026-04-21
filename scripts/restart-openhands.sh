#!/bin/bash
# Restart OpenHands on Albert with GITHUB_TOKEN injected.
# Token is read from openhands.crd (gitignored, laptop-only).

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/openhands.crd"

ssh -i /home/claude/.ssh/id_ed25519 -o StrictHostKeyChecking=no juan@100.95.7.96 "
  docker stop openhands 2>/dev/null || true
  docker rm openhands 2>/dev/null || true
  # Clean up stale sandbox runtime containers from previous OpenHands sessions
  docker ps -aq --filter 'name=openhands-runtime-' | xargs -r docker rm -f
  docker run -d --name openhands \
    --restart unless-stopped \
    -e SANDBOX_RUNTIME_CONTAINER_IMAGE=ghcr.io/all-hands-ai/runtime:0.40-nikolaik \
    -e WORKSPACE_BASE=/opt/workspace_base \
    -e SANDBOX_VOLUMES=/home/dev/projects:/workspace:rw \
    -e SANDBOX_USER_ID=1002 \
    -e HIDE_LLM_SETTINGS=true \
    -e OPENHANDS_USER_ID=42420 \
    -e SANDBOX_LOCAL_RUNTIME_URL=http://host.docker.internal \
    -e GITHUB_TOKEN=$GITHUB_TOKEN \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /home/dev/projects:/opt/workspace_base \
    -v /home/juan/openhands/config.toml:/app/config.toml:ro \
    -v /home/juan/openhands/state:/.openhands-state \
    -p 3000:3000 \
    --add-host host.docker.internal:host-gateway \
    ghcr.io/all-hands-ai/openhands:0.40
"
echo "OpenHands restarted with GITHUB_TOKEN"
