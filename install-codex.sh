#!/usr/bin/env bash
# ==============================================================================
# TOKENMAXXING FOR CODEX & CHATGPT — SAFE SANDBOX INSTALLER
# ==============================================================================
# Non-invasive file setup: strictly stays inside ~/.gemini/config/skills/tokenmaxxing.
# Does NOT modify shell startup files (.zshrc/.bashrc) or global AI configurations.
# ==============================================================================
set -e

CONFIG_DIR="${HOME}/.gemini/config"
SKILL_DIR="${CONFIG_DIR}/skills/tokenmaxxing"
SCRIPTS_DIR="${SKILL_DIR}/scripts"
REFS_DIR="${SKILL_DIR}/references"

mkdir -p "${SCRIPTS_DIR}" "${REFS_DIR}"

BASE_URL="https://raw.githubusercontent.com/gdgworkshop/tokenmaxxing/main"

# Download essential skill files into isolated sandbox
curl -fsSL "${BASE_URL}/SKILL.md" -o "${SKILL_DIR}/SKILL.md"
curl -fsSL "${BASE_URL}/scripts/tokenmaxx.py" -o "${SCRIPTS_DIR}/tokenmaxx.py"
curl -fsSL "${BASE_URL}/references/pricing_matrix.md" -o "${REFS_DIR}/pricing_matrix.md" 2>/dev/null || true
curl -fsSL "${BASE_URL}/references/whats_new.json" -o "${REFS_DIR}/whats_new.json" 2>/dev/null || true

chmod +x "${SCRIPTS_DIR}/tokenmaxx.py"

echo "⚡ TokenMaxxing sandbox ready."
