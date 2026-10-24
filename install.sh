#!/usr/bin/env bash
# ==============================================================================
# TokenMaxxing for Google Antigravity — One-Line Instant Installer (F20)
# Installs the official economic co-pilot and token management engine for GDG
# workshops, hackathons, and Antigravity developers.
#
# Usage:
#   curl -fsSL https://g.dev/events/tokenmaxxing | bash
# ==============================================================================

set -e

# Visual formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

echo ""
echo -e "${CYAN}${BOLD}  ⚡ TOKENMAXXING FOR GOOGLE ANTIGRAVITY${RESET}"
echo -e "${CYAN}  The Economic Co-Pilot & Token Management Engine${RESET}"
echo -e "  --------------------------------------------------"
echo ""

# Check python3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Warning: Python 3 was not found on your PATH.${RESET}"
    echo "   Please install Python 3 (3.8+) to run tokenmaxxing."
fi

# Define paths
CONFIG_DIR="${HOME}/.gemini/config"
SKILL_DIR="${CONFIG_DIR}/skills/tokenmaxxing"
SCRIPTS_DIR="${SKILL_DIR}/scripts"
REFS_DIR="${SKILL_DIR}/references"
RULES_DIR="${CONFIG_DIR}/rules"

echo -e "📦 Creating installation directories..."
mkdir -p "${SCRIPTS_DIR}" "${REFS_DIR}" "${RULES_DIR}"

BASE_URL="https://raw.githubusercontent.com/saadgh/tokenmaxxing/main"

# Download files (or copy if run locally from git repo)
if [ -f "./SKILL.md" ] && [ -f "./scripts/tokenmaxx.py" ]; then
    echo -e "📁 Installing from local repository..."
    cp "./SKILL.md" "${SKILL_DIR}/SKILL.md"
    cp "./scripts/tokenmaxx.py" "${SCRIPTS_DIR}/tokenmaxx.py"
    [ -f "./references/pricing_matrix.md" ] && cp "./references/pricing_matrix.md" "${REFS_DIR}/pricing_matrix.md"
else
    echo -e "🌐 Downloading latest release from GitHub..."
    curl -fsSL "${BASE_URL}/SKILL.md" -o "${SKILL_DIR}/SKILL.md"
    curl -fsSL "${BASE_URL}/scripts/tokenmaxx.py" -o "${SCRIPTS_DIR}/tokenmaxx.py"
    curl -fsSL "${BASE_URL}/references/pricing_matrix.md" -o "${REFS_DIR}/pricing_matrix.md" 2>/dev/null || true
fi

chmod +x "${SCRIPTS_DIR}/tokenmaxx.py"

# Clean up legacy prototype files if present
rm -rf "${CONFIG_DIR}/skills/gdg-token-budget" "${RULES_DIR}/gdg-token-budget.md" 2>/dev/null || true

# Install production global rule
echo -e "🛡️  Configuring Antigravity global rule..."
cat << 'EOF' > "${RULES_DIR}/tokenmaxxing.md"
---
trigger: always_on
---
# TokenMaxxing — Economic Co-Pilot & Token Management Rule

1. **Pre-Execution Check:** If an operation or prompt involves reading massive un-indexed repositories, unconstrained subagent recursions, or heavy multimodal files that could consume >50,000 tokens, proactively warn the user with a Token Burn Alert before executing.
2. **Plan-Aware Output Behavior:**
   - **On Google AI Pro / Ultra Mode (`isGcpTos: false`):** NEVER display token or dollar expenditure receipts! Personal turns are unlimited. Only surface an alert if the active model quota drops below `< 20%` or an active background GDP credit is expiring.
   - **On GDP Credit Mode (`Agent Platform` / `isGcpTos: true`):** Provide a concise TokenMaxx receipt tracking consumption against the $5.00 GDP grant, showing the 12-hour countdown timer, prompt caching savings, and purchasing power.
   - **Dynamic Model Efficiency Advisor:** Recommend **Gemini 3.8 Flash** as the sweet spot for rapid, token-efficient development (~1,000+ turns per $5 grant). Alert users when running routine tasks on Gemini 4 Argon to preserve their runway, but invert the alert when < 2 hours remain to burn unspent credits before expiration.
   - **Post-Expiration Guard:** When a GDP credit expires, display a post-mortem summary and guide the user to switch back to Pro or Free tier to prevent 403 prompt lockouts.
EOF

# Setup shell aliases for easy terminal access
ALIAS_CMD='alias tokenmaxx="python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py"'
ALIAS_MAX='alias tokenmax="tokenmaxx"'
ALIAS_MAXXING='alias tokenmaxing="tokenmaxx"'

setup_shell_rc() {
    local rc_file="$1"
    if [ -f "$rc_file" ]; then
        if ! grep -q "alias tokenmaxx=" "$rc_file"; then
            echo "" >> "$rc_file"
            echo "# TokenMaxxing Aliases" >> "$rc_file"
            echo "$ALIAS_CMD" >> "$rc_file"
            echo "$ALIAS_MAX" >> "$rc_file"
            echo "$ALIAS_MAXXING" >> "$rc_file"
            echo -e "   Added aliases to ${BOLD}${rc_file}${RESET}"
        fi
    fi
}

setup_shell_rc "${HOME}/.zshrc"
setup_shell_rc "${HOME}/.bashrc"

# Anonymous Telemetry Ping (F21) - Non-blocking, respects DO_NOT_TRACK
if [ "${DO_NOT_TRACK}" != "1" ]; then
    (curl -s -X POST "https://www.google-analytics.com/mp/collect?api_secret=ANON_PING_SECRET&measurement_id=G-TOKENMAXX1" \
          -H "Content-Type: application/json" \
          -d "{\"client_id\":\"$(whoami | shasum | cut -c1-16)\",\"events\":[{\"name\":\"installer_executed\",\"params\":{\"platform\":\"$(uname)\"}}]}" \
          --max-time 1 >/dev/null 2>&1 &) || true
fi

echo ""
echo -e "${GREEN}${BOLD}🎉 Installation Complete!${RESET}"
echo -e "   Skill installed to: ${CYAN}${SKILL_DIR}${RESET}"
echo ""
echo -e "${BOLD}Next Steps:${RESET}"
echo -e " 1. ${BOLD}In Antigravity chat:${RESET} Simply say:"
echo -e "    ${CYAN}\"Help me set up my GDG workshop credits\"${RESET}"
echo -e "    The agent will guide you through claiming your \$5 credit and pre-enabling the API!"
echo ""
echo -e " 2. ${BOLD}In your terminal:${RESET} Run:"
echo -e "    ${CYAN}python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py${RESET}"
echo -e "    (or restart your terminal to use the ${BOLD}tokenmaxx${RESET} shortcut)"
echo ""
echo -e "  --------------------------------------------------"
echo -e "  🚀 Happy TokenMaxxing at your Google Developer Group event!"
echo ""
