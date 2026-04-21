#!/bin/bash
# Start ymir MCP server in background, restart on crash
YMIR_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$YMIR_DIR/ymir_mcp.log"
PID_FILE="$YMIR_DIR/ymir_mcp.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "ymir MCP already running (pid $(cat "$PID_FILE"))"
    exit 0
fi

nohup python3 "$YMIR_DIR/ymir_mcp.py" >> "$LOG" 2>&1 &
echo $! > "$PID_FILE"
echo "ymir MCP started (pid $!), log: $LOG"
