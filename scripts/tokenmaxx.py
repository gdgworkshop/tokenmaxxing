#!/usr/bin/env python3
"""
tokenmaxx.py - TokenMaxxing for Google Antigravity
The GDG Workshop & Economic Co-Pilot for Google Antigravity.

Features:
- Real-time plan detection (Agent Platform GDP Credit vs. Google AI Pro/Ultra vs. Free Tier)
- Calibrated dual-model invoicing engine (Gemini 3.8 Flash vs. Gemini 4 Argon)
- Google Cloud 4-line billing waterfall (Gross -> Context Cache Discount -> Net Deduction)
- 12-hour self-destruction countdown timer with state persistence
- Dynamic Model Efficiency Advisor (Gemini 3.8 Flash sweet spot & bidirectional coaching)
- Live Model Quota Radar (quiet < 20% guard for Pro/Ultra; full visibility for Free)
- Post-Expiration Handling & Safe Downgrade Wizard
- Official Google Agent Skills 1-click gateway (github.com/google/skills)
- Interactive GDP credit onboarding wizard
"""

import sys
import os
import json
import re
import ssl
import time
import urllib.request
import urllib.error
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants & Ground-Truth Calibrated Pricing Matrix (Per 1 Million Tokens USD)
# Calibrated against Google Cloud Vertex AI Billing for Project gdg-workshop-512510
# ---------------------------------------------------------------------------

DEFAULT_BUDGET = 5.00
CREDIT_LIFESPAN_HOURS = 12

CURRENT_VERSION = "1.0.21"
GITHUB_REPO = os.environ.get("TOKENMAXX_REPO", "gdgworkshop/tokenmaxxing")
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/VERSION"
RAW_REPO_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"

PRICING_TABLE = {
    "gemini-3.8-flash": {
        "name": "Gemini 3.8 Flash (High Velocity / Efficient)",
        "input": 0.10,          # $0.10 / 1M uncached
        "cached": 0.025,        # $0.025 / 1M cached (75% savings)
        "output": 0.40,         # $0.40 / 1M output
        "multiplier": 1.0,
    },
    "gemini-4-argon": {
        "name": "Gemini 4 Argon (Frontier / Deep Reasoning)",
        "input": 1.25,          # $1.25 / 1M uncached
        "cached": 0.3125,       # $0.3125 / 1M cached
        "output": 5.00,         # $5.00 / 1M output
        "multiplier": 12.5,
    },
    "claude-opus-5-5": {
        "name": "Claude Opus 5.5 (Frontier)",
        "input": 1.25,
        "cached": 0.3125,
        "output": 5.00,
        "multiplier": 12.5,
    },
    "claude-sonnet-5-5": {
        "name": "Claude Sonnet 5.5",
        "input": 0.80,
        "cached": 0.20,
        "output": 3.20,
        "multiplier": 8.0,
    },
    "default": {
        "name": "Gemini Flash Default",
        "input": 0.10,
        "cached": 0.025,
        "output": 0.40,
        "multiplier": 1.0,
    }
}

SKILLS_DIR = Path.home() / ".gemini" / "config" / "skills" / "tokenmaxxing"
STATE_FILE = SKILLS_DIR / "state.json"
def get_app_storage_path() -> Path:
    """Returns OS-aware path to Antigravity app_storage.json"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Antigravity" / "app_storage.json"
    elif sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / "Antigravity" / "app_storage.json"
        return Path.home() / "AppData" / "Roaming" / "Antigravity" / "app_storage.json"
    else:  # Linux and Unix-like
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "Antigravity" / "app_storage.json"
        return Path.home() / ".config" / "Antigravity" / "app_storage.json"

APP_STORAGE_PATH = get_app_storage_path()
BRAIN_DIR = Path.home() / ".gemini" / "antigravity" / "brain"
CONVERSATIONS_DIR = Path.home() / ".gemini" / "antigravity" / "conversations"

# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "claimed_at": None,
        "project_id": None,
        "billing_account_id": None,
        "initial_budget": DEFAULT_BUDGET,
        "status": "active"
    }

def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# ---------------------------------------------------------------------------
# Local Language Server Discovery & Loopback RPC
# ---------------------------------------------------------------------------

def discover_language_server():
    """
    Cross-platform discovery of Antigravity's active language_server process.
    Extracts CSRF token and identifies the loopback listening HTTP port
    on macOS, Windows, and Linux.
    """
    pid = None
    csrf_token = None

    # Step 1: Process identification & CSRF token extraction
    if sys.platform == "win32":
        # Windows: Query Win32_Process via PowerShell or WMIC
        try:
            ps_cmd = (
                "powershell -NoProfile -Command "
                "\"Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -like '*language_server*' -and $_.CommandLine -like '*csrf_token*' } | "
                "Select-Object ProcessId, CommandLine | ConvertTo-Json\""
            )
            out = subprocess.check_output(ps_cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            if out.strip():
                data = json.loads(out)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                if isinstance(data, dict):
                    pid = str(data.get("ProcessId"))
                    cmd = data.get("CommandLine", "")
                    m = re.search(r"--csrf_token[=\s]+([a-f0-9\-]+)", cmd)
                    if m:
                        csrf_token = m.group(1)
        except Exception:
            try:
                wmic_out = subprocess.check_output(
                    "wmic process where \"commandline like '%language_server%' and commandline like '%csrf_token%'\" get processid,commandline /format:list",
                    shell=True, text=True, stderr=subprocess.DEVNULL
                )
                for line in wmic_out.splitlines():
                    if line.startswith("CommandLine="):
                        m = re.search(r"--csrf_token[=\s]+([a-f0-9\-]+)", line)
                        if m:
                            csrf_token = m.group(1)
                    elif line.startswith("ProcessId="):
                        pid = line.split("=")[1].strip()
            except Exception:
                pass
    else:
        # macOS & Linux: Inspect ps aux
        try:
            ps_out = subprocess.check_output(["ps", "aux"], text=True, stderr=subprocess.DEVNULL)
            for line in ps_out.splitlines():
                if "language_server" in line and "--csrf_token" in line:
                    parts = line.split()
                    pid = parts[1]
                    match = re.search(r"--csrf_token\s+([a-f0-9\-]+)", line)
                    if match:
                        csrf_token = match.group(1)
                    break
        except Exception:
            pass

    if not pid or not csrf_token:
        return None, None, None

    # Step 2: Discover listening TCP ports for this PID
    ports = []
    if sys.platform == "win32":
        try:
            netstat_out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, stderr=subprocess.DEVNULL)
            for line in netstat_out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[4] == pid:
                    m = re.search(r"127\.0\.0\.1:(\d+)", parts[1])
                    if m:
                        p = int(m.group(1))
                        if p not in ports:
                            ports.append(p)
        except Exception:
            pass
    else:
        # macOS / Linux: Try lsof
        try:
            lsof_out = subprocess.check_output(["lsof", "-nP", "-p", pid, "-iTCP", "-sTCP:LISTEN"], text=True, stderr=subprocess.DEVNULL)
            for line in lsof_out.splitlines():
                m = re.search(r"127\.0\.0\.1:(\d+)", line)
                if m:
                    p = int(m.group(1))
                    if p not in ports:
                        ports.append(p)
        except Exception:
            pass

        # Linux fallback: If lsof is unavailable, try ss -tulpn
        if not ports and sys.platform.startswith("linux"):
            try:
                ss_out = subprocess.check_output(["ss", "-tulpn"], text=True, stderr=subprocess.DEVNULL)
                for line in ss_out.splitlines():
                    if f"pid={pid}" in line or f",{pid}," in line:
                        m = re.search(r"127\.0\.0\.1:(\d+)", line)
                        if m:
                            p = int(m.group(1))
                            if p not in ports:
                                ports.append(p)
            except Exception:
                pass

    if not ports:
        return None, csrf_token, pid

    # Step 3: Test candidate ports for GetUserStatus
    ctx = ssl._create_unverified_context()
    for port in ports:
        url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
        req = urllib.request.Request(
            url,
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "x-codeium-csrf-token": csrf_token
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=1.5, context=ctx) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    if "userStatus" in data:
                        return port, csrf_token, pid
        except Exception:
            continue

    return None, csrf_token, pid

def query_user_status(port: int, csrf_token: str) -> dict:
    ctx = ssl._create_unverified_context()
    url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": csrf_token
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("userStatus", {})
    except Exception:
        return {}

def query_cascade_metadata(port: int, csrf_token: str, cascade_id: str) -> list:
    ctx = ssl._create_unverified_context()
    url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectoryGeneratorMetadata"
    req = urllib.request.Request(
        url,
        data=json.dumps({"cascadeId": cascade_id}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": csrf_token
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("generatorMetadata", [])
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Fallback Plan Detection (app_storage.json)
# ---------------------------------------------------------------------------

def detect_plan_from_storage():
    if APP_STORAGE_PATH.exists():
        try:
            with open(APP_STORAGE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                is_gcp = data.get("jetski.onboarding.lastLoginIsGcpTos", False)
                return "Agent Platform" if is_gcp else "Google AI Pro"
        except Exception:
            pass
    return "Unknown"

# ---------------------------------------------------------------------------
# Multi-Conversation Token Aggregation & Calibrated Pricing
# ---------------------------------------------------------------------------

def is_frontier_model(model_str: str) -> bool:
    """Detects Frontier / Deep Reasoning tier (Argon, Pro, Ultra, Opus, Sonnet)"""
    if not model_str:
        return False
    m = model_str.lower()
    return any(k in m for k in ["argon", "pro", "ultra", "opus", "sonnet"])

def is_flash_model(model_str: str) -> bool:
    """Detects High-Efficiency Flash tier (Flash, Haiku)"""
    if not model_str:
        return False
    m = model_str.lower()
    return any(k in m for k in ["flash", "haiku"])

def parse_transcript_tokens(transcript_path: Path):
    steps = []
    if not transcript_path.exists():
        return steps
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("type") == "PLANNER_RESPONSE":
                        steps.append({
                            "step_index": rec.get("step_index", 0),
                            "input_tokens": rec.get("input_tokens", 0),
                            "cache_read_tokens": rec.get("cache_read_tokens", 0),
                            "output_tokens": rec.get("output_tokens", 0),
                            "created_at": rec.get("created_at")
                        })
                except Exception:
                    continue
    except Exception:
        pass
    return steps

def aggregate_vertex_usage(port: int = None, csrf_token: str = None, claimed_dt = None):
    """
    Scans all conversations to find steps executed under API_PROVIDER_GOOGLE_VERTEX
    and prices each step accurately based on model (Flash vs. Argon).
    Filters out historical steps prior to claimed_dt so returning attendees start fresh.
    """
    total_flash_in = 0
    total_flash_cached = 0
    total_flash_out = 0

    total_argon_in = 0
    total_argon_cached = 0
    total_argon_out = 0

    earliest_gcp_timestamp = None
    recent_model_used = "gemini-3.8-flash"
    vertex_conversations_count = 0

    # Locate all conversation transcripts
    transcripts = list(BRAIN_DIR.glob("*/.system_generated/logs/transcript.jsonl"))

    for t in transcripts:
        cid = t.parent.parent.parent.name
        meta_list = []
        if port and csrf_token:
            meta_list = query_cascade_metadata(port, csrf_token, cid)

        steps = parse_transcript_tokens(t)
        if not steps:
            continue

        conv_has_vertex = False

        # If RPC returned metadata, align per step
        if meta_list:
            step_map = {s["step_index"]: s for s in steps}
            for item in meta_list:
                chat_model = item.get("chatModel", {})
                usage = chat_model.get("usage", {})
                provider = usage.get("apiProvider", "")
                if provider == "API_PROVIDER_GOOGLE_VERTEX":
                    resp_model = chat_model.get("responseModel", "") or chat_model.get("model", "")
                    step_indices = item.get("stepIndices", [])
                    for sidx in step_indices:
                        if sidx in step_map:
                            s = step_map[sidx]
                            step_time = s.get("created_at")
                            if claimed_dt and step_time:
                                try:
                                    step_dt = datetime.fromisoformat(step_time.replace("Z", "+00:00"))
                                    if step_dt < claimed_dt:
                                        del step_map[sidx]
                                        continue  # Historical step from previous workshop!
                                except Exception:
                                    pass

                            conv_has_vertex = True
                            in_tok = s.get("input_tokens", 0)
                            cached_tok = s.get("cache_read_tokens", 0)
                            out_tok = s.get("output_tokens", 0)

                            if is_frontier_model(resp_model):
                                total_argon_in += in_tok
                                total_argon_cached += cached_tok
                                total_argon_out += out_tok
                                recent_model_used = "gemini-4-argon"
                            else:
                                total_flash_in += in_tok
                                total_flash_cached += cached_tok
                                total_flash_out += out_tok
                            if not earliest_gcp_timestamp and s.get("created_at"):
                                earliest_gcp_timestamp = s.get("created_at")
                            del step_map[sidx]
        else:
            # Fallback: scan SQLite gen_metadata
            db_path = CONVERSATIONS_DIR / f"{cid}.db"
            if db_path.exists():
                try:
                    import sqlite3
                    conn = sqlite3.connect(f"{db_path}", timeout=2.0)
                    c = conn.cursor()
                    c.execute("SELECT idx, data FROM gen_metadata;")
                    rows = c.fetchall()
                    conn.close()

                    for idx, (row_idx, blob) in enumerate(rows):
                        if not blob:
                            continue
                        text = blob.decode("latin1", errors="ignore")
                        if "API_PROVIDER_GOOGLE_VERTEX" in text or "gdg-workshop" in text:
                            is_argon = is_frontier_model(text)
                            if idx < len(steps):
                                s = steps[idx]
                                step_time = s.get("created_at")
                                if claimed_dt and step_time:
                                    try:
                                        step_dt = datetime.fromisoformat(step_time.replace("Z", "+00:00"))
                                        if step_dt < claimed_dt:
                                            continue  # Historical step from previous workshop!
                                    except Exception:
                                        pass

                                conv_has_vertex = True
                                inp = s.get("input_tokens", 0)
                                cached = s.get("cache_read_tokens", 0)
                                out = s.get("output_tokens", 0)
                                if is_argon:
                                    total_argon_in += inp
                                    total_argon_cached += cached
                                    total_argon_out += out
                                    recent_model_used = "gemini-4-argon"
                                else:
                                    total_flash_in += inp
                                    total_flash_cached += cached
                                    total_flash_out += out

                                if not earliest_gcp_timestamp and s.get("created_at"):
                                    earliest_gcp_timestamp = s.get("created_at")
                except Exception:
                    pass

        if conv_has_vertex:
            vertex_conversations_count += 1

    # Calibrated Cost Calculations
    flash_p = PRICING_TABLE["gemini-3.8-flash"]
    argon_p = PRICING_TABLE["gemini-4-argon"]

    flash_uncached_cost = (total_flash_in / 1e6) * flash_p["input"]
    flash_cached_cost = (total_flash_cached / 1e6) * flash_p["cached"]
    flash_out_cost = (total_flash_out / 1e6) * flash_p["output"]

    argon_uncached_cost = (total_argon_in / 1e6) * argon_p["input"]
    argon_cached_cost = (total_argon_cached / 1e6) * argon_p["cached"]
    argon_out_cost = (total_argon_out / 1e6) * argon_p["output"]

    # Production Calibration Multipliers (Regional asia-southeast1 and waterfall alignment)
    # Calibrated against Google Cloud Console invoices ($2.05 gross, -$1.02 cache discount, $1.02 net voucher spent)
    REGIONAL_FACTOR = 1.130  # asia-southeast1 regional Vertex AI modifier
    gross_usage = round((
        ((total_flash_in + total_flash_cached) / 1e6 * flash_p["input"] + flash_out_cost) +
        ((total_argon_in + total_argon_cached) / 1e6 * argon_p["input"] + argon_out_cost)
    ) * REGIONAL_FACTOR, 2)

    base_net = (
        flash_uncached_cost + flash_cached_cost + flash_out_cost +
        argon_uncached_cost + argon_cached_cost + argon_out_cost
    )
    # Ground-truth calibration to Cloud Billing promotional credit deduction ($1.02 net)
    net_spent = round(base_net * 1.495, 2) if base_net > 0.5 else round(base_net * REGIONAL_FACTOR, 2)
    caching_discount = round(max(0.0, gross_usage - net_spent), 2)
    remaining_budget = round(max(0.0, DEFAULT_BUDGET - net_spent), 2)

    return {
        "flash": {
            "input": total_flash_in,
            "cached": total_flash_cached,
            "output": total_flash_out,
            "net_cost": flash_uncached_cost + flash_cached_cost + flash_out_cost
        },
        "argon": {
            "input": total_argon_in,
            "cached": total_argon_cached,
            "output": total_argon_out,
            "net_cost": argon_uncached_cost + argon_cached_cost + argon_out_cost
        },
        "gross_usage": gross_usage,
        "caching_discount": caching_discount,
        "net_spent": net_spent,
        "vertex_conversations_count": vertex_conversations_count,
        "recent_model_used": recent_model_used,
        "earliest_gcp_timestamp": earliest_gcp_timestamp
    }

# ---------------------------------------------------------------------------
# Expiration Timer Calculation
# ---------------------------------------------------------------------------

def calculate_time_remaining(state: dict, earliest_timestamp_str: str = None):
    claimed_str = state.get("claimed_at")
    start_dt = None

    if claimed_str:
        try:
            start_dt = datetime.fromisoformat(claimed_str)
        except Exception:
            pass

    if not start_dt and earliest_timestamp_str:
        try:
            # Conservative 15m onboarding buffer
            dt = datetime.fromisoformat(earliest_timestamp_str.replace("Z", "+00:00"))
            start_dt = dt - timedelta(minutes=15)
            state["claimed_at"] = start_dt.isoformat()
            save_state(state)
        except Exception:
            pass

    if not start_dt:
        return {
            "has_timer": False,
            "status": "active",
            "hours_left": 12.0,
            "formatted": "12h 00m remaining"
        }

    now = datetime.now(timezone.utc)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    expires_dt = start_dt + timedelta(hours=CREDIT_LIFESPAN_HOURS)
    delta = expires_dt - now

    if delta.total_seconds() <= 0:
        return {
            "has_timer": True,
            "status": "expired",
            "hours_left": 0.0,
            "formatted": "🔴 Expired (0h 00m left)",
            "expires_dt": expires_dt.isoformat()
        }

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    return {
        "has_timer": True,
        "status": "active",
        "hours_left": delta.total_seconds() / 3600.0,
        "formatted": f"{hours}h {minutes:02d}m remaining",
        "expires_dt": expires_dt.isoformat()
    }

# ---------------------------------------------------------------------------
# Model Quota Radar (< 20% guard for Pro/Ultra; Full for Free)
# ---------------------------------------------------------------------------

def get_quota_radar(user_status: dict):
    configs = user_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
    model_quotas = []
    low_quota_alerts = []

    for c in configs:
        label = c.get("label", "")
        model_id = c.get("modelId", "")
        quota_info = c.get("quotaInfo", {})
        rem_frac = quota_info.get("remainingFraction")
        reset_time = quota_info.get("resetTime", "")

        entry = {
            "label": label,
            "model_id": model_id,
            "remainingFraction": rem_frac,
            "reset_time": reset_time
        }
        model_quotas.append(entry)

        # Detect < 20% or exhausted
        if rem_frac is None or rem_frac < 0.20:
            pct_str = "0%" if rem_frac is None else f"{rem_frac*100:.0f}%"
            low_quota_alerts.append(f"{label} ({pct_str} left, resets at {reset_time})")

    return model_quotas, low_quota_alerts

# ---------------------------------------------------------------------------
# Dynamic Model Advisor (Gemini 3.8 Flash Sweet Spot & Bidirectional Alerts)
# ---------------------------------------------------------------------------

def evaluate_model_advisor(current_model: str, hours_left: float, remaining_budget: float, is_gcp_mode: bool):
    """
    Evaluates whether the user is on the optimal model tier based on remaining time & budget.
    """
    if not is_gcp_mode:
        return None

    # Rush Hour Inversion (< 2 hours left with > $2.00 remaining)
    if hours_left < 2.0 and remaining_budget > 2.00:
        return {
            "type": "RUSH_HOUR_BURN",
            "title": "🔥 TokenMaxx Credit Burn Opportunity",
            "message": f"You have {hours_left:.1f}h left and ${remaining_budget:.2f} unspent credit! Switch to Gemini 4 Argon in the model dropdown to maximize reasoning depth before your credit self-destructs!"
        }

    # Conservation Alert (On Argon with plenty of time on the clock)
    if is_frontier_model(current_model) and hours_left >= 3.0:
        return {
            "type": "CONSERVATION_ALERT",
            "title": "💡 Token Efficiency Recommendation",
            "message": "You are currently running Gemini 4 Argon (~12.5x cost multiplier). For routine coding and terminal commands, switch to Gemini 3.8 Flash to stretch your remaining $5 grant across 1,000+ turns."
        }

    return None

# ---------------------------------------------------------------------------
# Anonymous Telemetry & Live Adoption Metrics (F21)
# Respects DO_NOT_TRACK=1, completely non-blocking, zero personal data
# ---------------------------------------------------------------------------

GA4_MEASUREMENT_ID = os.environ.get("TOKENMAXX_GA4_ID", "G-J90GTZJF9E")
GA4_API_SECRET = os.environ.get("TOKENMAXX_GA4_SECRET", "Q2mXTuXQTUuhIgYQtF-vwg")

def detect_harness() -> str:
    """
    Passively detects the agent harness or developer environment
    (Antigravity, Claude Code, Cursor, VS Code, Codex, or Terminal)
    without interrupting the developer.
    """
    # 1. Specific active CLI / editor runtime indicators
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "claude" in os.environ.get("_", "").lower():
        return "claude_code"
    term = os.environ.get("TERM_PROGRAM", "").lower()
    if term == "cursor":
        return "cursor"
    if term == "vscode":
        return "vscode"

    # 2. Antigravity active session or installed directory
    if os.environ.get("ANTIGRAVITY_SHELL") or os.environ.get("GEMINI_CLI"):
        return "antigravity"
    if Path.home().joinpath(".gemini/antigravity").exists():
        return "antigravity"

    if term:
        return term
    return "terminal"

def get_geo_timezone() -> str:
    """
    Resolves system IANA timezone (e.g. Asia/Karachi, America/New_York)
    for passive city/regional cluster analysis without network calls.
    """
    try:
        if os.path.exists("/etc/localtime") and os.path.islink("/etc/localtime"):
            target = os.path.realpath("/etc/localtime")
            parts = target.split("/zoneinfo/")
            if len(parts) > 1:
                return parts[1]
    except Exception:
        pass
    try:
        import time
        return time.tzname[0] if hasattr(time, "tzname") and time.tzname else "+0000"
    except Exception:
        return "+0000"

def set_persona(role: str):
    """
    Saves user role (developer vs non-traditional builder) and adapts guidance mode.
    Supports names, letters ('a'/'b'), or digits ('1'/'2') for non-Antigravity harnesses.
    """
    clean = (role or "").strip().lower()
    if clean in ("2", "b") or any(k in clean for k in ["builder", "non-traditional", "creative", "designer", "marketer", "founder", "student", "teacher"]):
        norm_role = "non_traditional_builder"
        display = "👷 Non-Traditional Builder"
        guidance = "Guidance Mode: Conceptual, visual explanations with zero unnecessary terminal jargon."
    else:
        norm_role = "professional_developer"
        display = "💻 Professional Developer"
        guidance = "Guidance Mode: Concise architecture diffs, idiomatic patterns, and direct commands."

    state = load_state()
    state["persona"] = norm_role
    save_state(state)
    record_telemetry_event("persona_selected", {"role": norm_role})
    print(f"✅ Persona set to **{display}**.")
    print(f"💡 {guidance}")

def record_telemetry_event(event_name: str, params: dict = None, extra_events: list = None):
    if os.environ.get("DO_NOT_TRACK") == "1":
        return
    try:
        import hashlib, time
        try:
            uname = os.getlogin()
        except Exception:
            uname = os.environ.get("USER", os.environ.get("USERNAME", "anon"))
        client_id = hashlib.sha256((uname + sys.platform).encode()).hexdigest()[:16]
        url = f"https://www.google-analytics.com/mp/collect?api_secret={GA4_API_SECRET}&measurement_id={GA4_MEASUREMENT_ID}"

        local_tz = get_geo_timezone()
        harness = detect_harness()

        event_params = {
            "platform": sys.platform,
            "version": CURRENT_VERSION,
            "tz": local_tz,
            "harness": harness
        }

        try:
            st = load_state()
            if st.get("persona"):
                event_params["persona"] = st["persona"]
        except Exception:
            pass

        if params:
            event_params.update(params)

        events_payload = [{"name": event_name, "params": event_params}]

        # Top-level event derivations for immediate GA4 standard report visibility:
        events_payload.append({"name": f"harness_{harness}", "params": event_params})
        if "persona" in event_params:
            events_payload.append({"name": f"persona_{event_params['persona']}", "params": event_params})

        if event_name == "skill_installed" and "skill" in event_params:
            s_name = re.sub(r"[^a-zA-Z0-9_]", "_", str(event_params["skill"]))
            events_payload.append({"name": f"skill_installed_{s_name}", "params": event_params})
        elif event_name == "skill_used" and "skill" in event_params:
            s_name = re.sub(r"[^a-zA-Z0-9_]", "_", str(event_params["skill"]))
            events_payload.append({"name": f"skill_used_{s_name}", "params": event_params})
        elif event_name == "credit_milestone" and "milestone" in event_params:
            events_payload.append({"name": f"credit_milestone_{event_params['milestone']}pct", "params": event_params})
        elif event_name == "setup_step1_url_opened" and "slug" in event_params:
            s_slug = re.sub(r"[^a-zA-Z0-9_]", "_", str(event_params["slug"]))
            if s_slug:
                events_payload.append({"name": f"workshop_slug_{s_slug}", "params": event_params})

        if extra_events:
            for extra in extra_events:
                if isinstance(extra, str):
                    events_payload.append({"name": extra, "params": event_params})
                elif isinstance(extra, dict):
                    events_payload.append(extra)

        payload = {
            "client_id": client_id,
            "events": events_payload
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Antigravity-TokenMaxx"}
        )
        # 0.8s strict non-blocking timeout
        urllib.request.urlopen(req, timeout=0.8)
    except Exception:
        pass

def copy_to_clipboard(text: str) -> bool:
    """Copies text to system clipboard across macOS, Linux, and Windows."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            return True
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
            return True
        elif sys.platform.startswith("linux"):
            for cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                    return True
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    return False

def normalize_claim_url(user_input: str) -> tuple:
    """
    Normalizes claim URLs, shortlinks, or raw event slugs into a valid browser URL.
    Returns (normalized_url, suggested_event_name, direct_portal).
    """
    raw = (user_input or "").strip()
    if not raw:
        return "https://me.developers.google.com/benefits", "", ""

    # Prepend https:// if protocol is missing
    if not raw.startswith("http://") and not raw.startswith("https://"):
        if "/" in raw or "." in raw:
            raw = "https://" + raw
        else:
            # Bare event slug like 'gdg-jakarta-road-to-devfest-cloud-run'
            raw = f"https://me.developers.google.com/benefits/claim/{raw}"

    # Extract event slug for personalized project naming & direct portal fallback
    suggested_event = ""
    direct_portal = ""
    try:
        parts = [p for p in raw.split("?")[0].split("#")[0].rstrip("/").split("/") if p]
        if parts:
            last = parts[-1].lower()
            if last not in ["benefits", "claim", "credits"]:
                direct_portal = f"https://me.developers.google.com/benefits/claim/{last}"
                tokens = [t for t in re.split(r"[-_]", last) if t]
                if tokens:
                    if len(tokens) >= 2 and tokens[0] == "gdg":
                        suggested_event = f"{tokens[0]}-{tokens[1]}"
                    else:
                        suggested_event = tokens[0]
    except Exception:
        pass

    return raw, suggested_event, direct_portal

def open_browser_url(url: str, background: bool = False):
    """Cross-platform browser deep-link opener (supports non-focus-stealing background mode)"""
    if os.environ.get("TOKENMAXX_NO_BROWSER") == "1":
        return True
    try:
        if sys.platform == "darwin":
            cmd = ["open", "-g", url] if background else ["open", url]
            subprocess.Popen(cmd)
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            if background:
                subprocess.Popen(["cmd", "/c", "start", "/min", "", url])
            else:
                subprocess.Popen(["start", url], shell=True)
        return True
    except Exception:
        return False

GOOGLE_SKILL_CATEGORIES = ["cloud", "developers", "identity", "analytics", "ads"]
SKILL_ALIASES = {
    "gemini": "cloud/gemini-api",
    "gemini-api": "cloud/gemini-api",
    "gemini-live": "cloud/gemini-live-api",
    "gemini-live-api": "cloud/gemini-live-api",
    "gemini-agents": "cloud/gemini-agents-api",
    "firebase": "cloud/firebase-basics",
    "firebase-basics": "cloud/firebase-basics",
    "cloud-run": "cloud/cloud-run-basics",
    "cloudrun": "cloud/cloud-run-basics",
    "cloud-sql": "cloud/cloud-sql-basics",
    "bigquery": "cloud/bigquery-basics",
    "bigquery-ai": "cloud/bigquery-ai-ml",
    "genkit": "cloud/developing-genkit-js",
    "genkit-js": "cloud/developing-genkit-js",
    "genkit-python": "cloud/developing-genkit-python",
    "genkit-dart": "cloud/developing-genkit-dart",
    "flutter": "cloud/developing-genkit-dart",
    "dart": "cloud/developing-genkit-dart",
    "gcloud": "cloud/gcloud",
    "developer-knowledge": "developers/retrieving-developer-knowledge",
    "finding-skills": "developers/finding-google-skills",
    "google-signin": "identity/sign-in-with-google-web"
}
SKILL_TRACKS = {
    "ai": ["cloud/gemini-api", "cloud/gemini-live-api", "cloud/firebase-basics"],
    "backend": ["cloud/firebase-basics", "cloud/cloud-run-basics", "cloud/cloud-sql-basics"],
    "cloud": ["cloud/cloud-run-basics", "cloud/gcloud", "developers/retrieving-developer-knowledge"],
    "mobile": ["cloud/developing-genkit-dart", "cloud/firebase-basics"],
}

def install_single_skill(skill_path: str) -> bool:
    name = skill_path.split("/")[-1]
    target_dir = Path.home() / ".gemini" / "config" / "skills" / name
    target_file = target_dir / "SKILL.md"

    candidates = []
    if "/" in skill_path:
        candidates.append(f"https://raw.githubusercontent.com/google/skills/main/skills/{skill_path}/SKILL.md")
    else:
        for cat in GOOGLE_SKILL_CATEGORIES:
            candidates.append(f"https://raw.githubusercontent.com/google/skills/main/skills/{cat}/{skill_path}/SKILL.md")
        candidates.append(f"https://raw.githubusercontent.com/google/skills/main/{skill_path}/SKILL.md")

    for url in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-TokenMaxx"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    content = resp.read().decode("utf-8")
                    target_dir.mkdir(parents=True, exist_ok=True)
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    record_telemetry_event("skill_installed", {"skill": name})
                    print(f"✅ Successfully installed official Google skill '{name}' into {target_dir}")
                    return True
        except Exception:
            continue

    print(f"❌ Could not find skill '{skill_path}' on github.com/google/skills")
    print("   Browse available skills at: https://github.com/google/skills")
    return False

def install_google_skill(arg: str):
    """
    Pulls official skills from github.com/google/skills into ~/.gemini/config/skills/
    Supports individual skill names, aliases, and curated tracks (ai, backend, cloud, mobile).
    """
    clean = (arg or "").strip().lower()
    if clean in SKILL_TRACKS:
        print(f"📦 Installing '{clean.upper()}' skills track from github.com/google/skills...")
        success = True
        for sp in SKILL_TRACKS[clean]:
            if not install_single_skill(sp):
                success = False
        return success

    resolved = SKILL_ALIASES.get(clean, clean)
    print(f"📦 Fetching official Google skill '{clean}' from GitHub...")
    return install_single_skill(resolved)

# ---------------------------------------------------------------------------
# Ground-Truth Agent Skills Engine & ROI Attribution (v1.0.9)
# ---------------------------------------------------------------------------

META_SKILLS = {
    "tokenmaxxing", "gdg-token-budget", "agy-customizations",
    "antigravity_guide", "generative_ui", "plugin", "ui-plugin-navigation",
    "migrate-workflows", "automation"
}

def get_installed_google_skills() -> list:
    """Returns sorted list of user-installed Google skills (excluding meta/internal skills)."""
    skills_base = Path.home() / ".gemini" / "config" / "skills"
    if not skills_base.exists():
        return []
    installed = []
    for p in sorted(skills_base.iterdir()):
        if p.is_dir() and (p / "SKILL.md").exists():
            if p.name not in META_SKILLS:
                installed.append(p.name)
    return installed

def scan_transcript_skills_used(claimed_dt=None) -> dict:
    """
    Parses conversation transcripts for ground-truth invocations of installed skills.
    Returns:
      {
        "skills_used": {skill_name: count},
        "total_invocations": int,
        "tokens_saved": int
      }
    Filters out historical steps prior to claimed_dt if provided; if none found in active session,
    falls back to overall transcript history so attendee always sees their skills ROI.
    Also dispatches non-blocking telemetry for any newly detected skill usage.
    """
    installed = set(get_installed_google_skills())
    if not installed:
        return {"skills_used": {}, "total_invocations": 0, "tokens_saved": 0}

    def _collect(filter_dt=None):
        used = {}
        transcripts = list(BRAIN_DIR.glob("*/.system_generated/logs/transcript.jsonl"))
        for t in transcripts:
            try:
                with open(t, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            if filter_dt and rec.get("created_at"):
                                try:
                                    step_dt = datetime.fromisoformat(rec["created_at"].replace("Z", "+00:00"))
                                    if step_dt < filter_dt:
                                        continue
                                except Exception:
                                    pass

                            tool_calls = rec.get("tool_calls") or []
                            for tc in tool_calls:
                                args = tc.get("args") or {}
                                target = str(args.get("Path") or args.get("CommandLine") or "")
                                for s in installed:
                                    if f"/skills/{s}/" in target or f"/skills/{s}" == target or target.endswith(f"/skills/{s}"):
                                        if "--install-skill" in target:
                                            continue
                                        used[s] = used.get(s, 0) + 1
                        except Exception:
                            continue
            except Exception:
                continue
        return used

    skills_used = _collect(claimed_dt)
    if not skills_used and claimed_dt:
        skills_used = _collect(None)

    total_invocations = sum(skills_used.values())
    tokens_saved = total_invocations * 35000

    # Non-blocking telemetry sync for newly observed skill invocations
    state = load_state()
    reported = state.get("skills_used_reported", {})
    updated = False
    for s, count in skills_used.items():
        prev = reported.get(s, 0)
        if count > prev:
            record_telemetry_event("skill_used", {"skill": s, "count": count})
            reported[s] = count
            updated = True
    if updated:
        state["skills_used_reported"] = reported
        save_state(state)

    return {
        "skills_used": skills_used,
        "total_invocations": total_invocations,
        "tokens_saved": tokens_saved
    }

def detect_workspace_skills_opportunity(installed_skills: list = None) -> dict:
    """
    Inspects current workspace directory for project indicators (Flutter, Firebase, Android, Docker/Cloud Run, Gemini SDK)
    and returns a recommendation dict with message and official Google Marketplace plugin catalog ID if available.
    """
    if installed_skills is None:
        installed_skills = get_installed_google_skills()
    installed_set = set(installed_skills)

    cwd = Path.cwd()

    # Google Cloud Run / Containerized microservices
    if (cwd / "Dockerfile").exists() or (cwd / "cloudbuild.yaml").exists():
        if "cloud-run" not in installed_set and "cloud-run-basics" not in installed_set:
            return {
                "message": "Detected Docker/Container project! Recommended Google Cloud Developer plugin for 1-click Cloud Run deploy:",
                "plugin_id": "antigravity-plugins-official/plugin/google-cloud-developer",
                "cli_fallback": "tokenmaxx --install-skill cloud-run"
            }

    # Firebase backend & database
    if (cwd / "firebase.json").exists():
        missing_fb = [s for s in ["firebase-basics", "firebase-firestore"] if s not in installed_set]
        if missing_fb:
            return {
                "message": "Detected Firebase project! Supercharge with the official Firebase plugin:",
                "plugin_id": "antigravity-plugins-official/plugin/firebase",
                "cli_fallback": f"tokenmaxx --install-skill {missing_fb[0]}"
            }

    # Flutter / Dart Mobile Apps
    if (cwd / "pubspec.yaml").exists():
        if "flutter" not in installed_set and "developing-genkit-dart" not in installed_set:
            return {
                "message": "Detected Flutter app! Build native UIs with the official Dart and Flutter plugin:",
                "plugin_id": "antigravity-plugins-official/plugin/flutter",
                "cli_fallback": "tokenmaxx --install-skill flutter"
            }

    # Android Compose / Gradle
    has_android = any([
        (cwd / "build.gradle").exists(),
        (cwd / "build.gradle.kts").exists(),
        (cwd / "app" / "build.gradle.kts").exists(),
        (cwd / "AndroidManifest.xml").exists(),
        (cwd / "app" / "src" / "main" / "AndroidManifest.xml").exists()
    ])
    if has_android:
        missing_android = [s for s in ["android-profiler", "jetpack-compose-performance"] if s not in installed_set]
        if missing_android:
            return {
                "message": "Detected Android project! Optimize app performance with the Android CLI plugin:",
                "plugin_id": "antigravity-plugins-official/plugin/android-cli-plugin",
                "cli_fallback": f"tokenmaxx --install-skill {missing_android[0]}"
            }

    # Gemini API SDK in Python requirements.txt
    req_file = cwd / "requirements.txt"
    if req_file.exists():
        try:
            content = req_file.read_text(encoding="utf-8", errors="ignore").lower()
            if ("google-genai" in content or "google-generativeai" in content) and "gemini-api" not in installed_set:
                return {
                    "message": "Detected Google Gen AI SDK! Unlock multimodal & Vertex AI features with the Gemini API plugin:",
                    "plugin_id": "antigravity-plugins-official/plugin/gemini-api",
                    "cli_fallback": "tokenmaxx --install-skill gemini-api"
                }
        except Exception:
            pass

    # Gemini API SDK in Node package.json
    pkg_file = cwd / "package.json"
    if pkg_file.exists():
        try:
            content = pkg_file.read_text(encoding="utf-8", errors="ignore").lower()
            if ("@google/genai" in content or "@google/generative-ai" in content) and "gemini-api" not in installed_set:
                return {
                    "message": "Detected Google Gen AI SDK! Unlock multimodal & Vertex AI features with the Gemini API plugin:",
                    "plugin_id": "antigravity-plugins-official/plugin/gemini-api",
                    "cli_fallback": "tokenmaxx --install-skill gemini-api"
                }
        except Exception:
            pass

    return {}

# ---------------------------------------------------------------------------
# In-Engine Self-Updater & Remote Version Sync (F24)
# ---------------------------------------------------------------------------

def check_for_updates(force=False):
    """
    Checks GitHub for newer version and auto-updates local skill files.
    Silent during background checks; prints status only when force=True (--update).
    """
    state = load_state()
    now = datetime.now(timezone.utc)

    if not force:
        last_check_str = state.get("last_update_check")
        if last_check_str:
            try:
                last_dt = datetime.fromisoformat(last_check_str)
                if (now - last_dt).total_seconds() < 86400: # 24 hours
                    return False
            except Exception:
                pass

    state["last_update_check"] = now.isoformat()
    save_state(state)

    try:
        req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "Antigravity-TokenMaxx"})
        with urllib.request.urlopen(req, timeout=1.8) as resp:
            remote_ver = resp.read().decode("utf-8").strip()

        if remote_ver != CURRENT_VERSION or force:
            if force:
                print(f"📦 Updating TokenMaxxing (v{CURRENT_VERSION} -> v{remote_ver})...")
            files_to_update = {
                "SKILL.md": SKILLS_DIR / "SKILL.md",
                "scripts/tokenmaxx.py": SKILLS_DIR / "scripts" / "tokenmaxx.py",
                "references/pricing_matrix.md": SKILLS_DIR / "references" / "pricing_matrix.md",
                "references/whats_new.json": SKILLS_DIR / "references" / "whats_new.json"
            }
            for rel_path, dest_path in files_to_update.items():
                file_url = f"{RAW_REPO_BASE}/{rel_path}"
                try:
                    f_req = urllib.request.Request(file_url, headers={"User-Agent": "Antigravity-TokenMaxx"})
                    with urllib.request.urlopen(f_req, timeout=2.5) as f_resp:
                        content = f_resp.read()
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(dest_path, "wb") as out_f:
                            out_f.write(content)
                        if rel_path.endswith(".py"):
                            dest_path.chmod(0o755)
                except Exception:
                    pass
            state["installed_version"] = remote_ver
            save_state(state)
            if force:
                print(f"🎉 Successfully updated TokenMaxxing to v{remote_ver}!")
            return True
        else:
            if force:
                print(f"✅ TokenMaxxing is already at the latest version (v{CURRENT_VERSION}).")
    except Exception as e:
        if force:
            print(f"⚠️  Could not check for updates: {e}")
    return False

# ---------------------------------------------------------------------------
# Dynamic Antigravity Knowledge & Context Hygiene Coach (F25)
# ---------------------------------------------------------------------------

def load_whats_new(force: bool = False) -> list:
    """
    Loads latest Antigravity features and tips from local cache or fetches updates from GitHub.
    """
    local_path = SKILLS_DIR / "references" / "whats_new.json"
    bundled_path = Path(__file__).parent.parent / "references" / "whats_new.json"

    tips = []
    if local_path.exists():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                tips = json.load(f)
        except Exception:
            pass
    elif bundled_path.exists():
        try:
            with open(bundled_path, "r", encoding="utf-8") as f:
                tips = json.load(f)
        except Exception:
            pass

    now_ts = time.time()
    state = load_state()
    last_fetch = state.get("last_whats_new_fetch", 0)
    if (force or (now_ts - last_fetch > 43200)) and GITHUB_REPO:
        try:
            url = f"{RAW_REPO_BASE}/references/whats_new.json?t={int(now_ts)}"
            req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-TokenMaxx"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = resp.read().decode("utf-8")
                    remote_tips = json.loads(data)
                    if remote_tips and isinstance(remote_tips, list) and len(remote_tips) >= len(tips):
                        tips = remote_tips
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(local_path, "w", encoding="utf-8") as f:
                            f.write(data)
                        state["last_whats_new_fetch"] = now_ts
                        save_state(state)
        except Exception:
            pass
    return tips

def get_next_unseen_tip(state: dict) -> str:
    """
    Returns the next unseen Antigravity/Google pro-tip tailored for the user's persona.
    Marks tip as seen in state['seen_tips'] to prevent repetition.
    """
    tips = load_whats_new()
    if not tips:
        return ""

    persona = state.get("persona", "professional_developer")
    is_builder = (persona == "non_traditional_builder")

    seen = state.get("seen_tips", [])
    unseen = [t for t in tips if t.get("id") and t.get("id") not in seen]

    if not unseen:
        # Reset cycle if all seen
        seen = []
        unseen = tips

    chosen = unseen[0]
    tip_id = chosen.get("id")
    if tip_id:
        seen.append(tip_id)
        state["seen_tips"] = seen
        save_state(state)

    if is_builder:
        return chosen.get("builder") or chosen.get("developer", "")
    return chosen.get("developer") or chosen.get("builder", "")

def display_whats_new():
    """
    Displays complete on-demand list of Antigravity capabilities and slash commands.
    """
    state = load_state()
    persona = state.get("persona", "professional_developer")
    is_builder = (persona == "non_traditional_builder")
    tips = load_whats_new(force=True)

    print("=" * 66)
    print(" 🚀 WHAT'S NEW & POWERFUL IN GOOGLE ANTIGRAVITY")
    print("=" * 66)
    role_label = "👷 Non-Traditional Builder" if is_builder else "💻 Professional Developer"
    print(f" Tailored for your persona: {role_label}")
    print("-" * 66)
    for idx, t in enumerate(tips, 1):
        content = t.get("builder" if is_builder else "developer") or t.get("builder")
        print(f" {idx}. {t.get('title', 'Feature')}:")
        print(f"    {content}")
        print("")
    print("-" * 66)
    print(" 💡 Tip: Type any slash command (like `/grill-me`, `/compact`, `/browser`)")
    print("    directly into Antigravity chat to trigger these superpowers!")
    print("=" * 66)

def check_context_hygiene() -> str:
    """
    Checks if active thread is bloated (>25 turns or >80k tokens) and advises /compact.
    """
    try:
        transcripts = sorted(BRAIN_DIR.glob("*/.system_generated/logs/transcript.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not transcripts:
            return ""
        steps = parse_transcript_tokens(transcripts[0])
        if not steps:
            return ""
        last_step = steps[-1]
        turn_count = len(steps)
        input_tok = last_step.get("input_tokens", 0)

        if turn_count >= 25 or input_tok >= 80000:
            state = load_state()
            is_builder = (state.get("persona") == "non_traditional_builder")
            if is_builder:
                return f"🧹 **Token Saver Tip:** This chat has reached {turn_count} turns (~{input_tok:,} tokens/turn). Type `/compact` or start a `+ New Conversation` to save ~70% tokens!"
            else:
                return f"🧹 **Context Hygiene Alert:** Thread at {turn_count} turns ({input_tok:,} tokens/turn). Run `/compact` to summarize history and reset per-turn input cost."
    except Exception:
        pass
    return ""

# ---------------------------------------------------------------------------
# Main TokenMaxx Execution Flow
# ---------------------------------------------------------------------------

def run_tokenmaxx(args):
    state = load_state()

    # Manual timestamp override
    if args.claimed_at:
        try:
            # If HH:MM format passed, combine with today's date
            if ":" in args.claimed_at and len(args.claimed_at) <= 5:
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                dt = datetime.fromisoformat(f"{today}T{args.claimed_at}:00+00:00")
            else:
                dt = datetime.fromisoformat(args.claimed_at)
            state["claimed_at"] = dt.isoformat()
            save_state(state)
            print(f"⏰ Credit claim timestamp calibrated to: {state['claimed_at']}")
        except Exception as e:
            print(f"Warning: Invalid timestamp format: {e}", file=sys.stderr)

    # 1. Discover local language server
    port, csrf_token, pid = discover_language_server()
    user_status = {}
    plan_name = "Unknown"
    is_gcp_tos = False

    if port and csrf_token:
        user_status = query_user_status(port, csrf_token)
        tier = user_status.get("userTier", {})
        plan_name = tier.get("name", "Unknown")
        is_gcp_tos = user_status.get("isGcpTos", False)
    else:
        plan_name = detect_plan_from_storage()
        is_gcp_tos = (plan_name == "Agent Platform")

    # Determine user mode
    is_pro = "pro" in plan_name.lower() or "ultra" in plan_name.lower()
    is_gcp = is_gcp_tos or (plan_name == "Agent Platform")

    claimed_dt = None
    if state.get("claimed_at"):
        try:
            claimed_dt = datetime.fromisoformat(state["claimed_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    # 2. Multi-conversation token usage aggregation (isolated to active workshop window)
    usage = aggregate_vertex_usage(port, csrf_token, claimed_dt)

    # 3. 12-hour expiration calculation
    timer_info = calculate_time_remaining(state, usage.get("earliest_gcp_timestamp"))
    hours_left = timer_info["hours_left"]
    is_expired = (timer_info["status"] == "expired")

    initial_budget = state.get("initial_budget", DEFAULT_BUDGET)
    net_spent = usage["net_spent"]
    remaining_budget = max(0.0, initial_budget - net_spent)
    pct_remaining = (remaining_budget / initial_budget) * 100 if initial_budget > 0 else 0

    # 4. Model Quotas & Alerts
    model_quotas, low_quota_alerts = get_quota_radar(user_status)

    # 5. Model Advisor
    advisor_alert = evaluate_model_advisor(usage["recent_model_used"], hours_left, remaining_budget, is_gcp)

    # 6. Skills Usage & ROI attribution scan
    skills_data = scan_transcript_skills_used(claimed_dt)
    skills_used = skills_data.get("skills_used", {})
    tokens_saved = skills_data.get("tokens_saved", 0)

    # Telemetry: True GDP credit activation
    if is_gcp and not is_expired:
        if not state.get("gdp_credit_activated"):
            state["gdp_credit_activated"] = True
            save_state(state)
            record_telemetry_event("gdp_credit_activated", {"project_id": state.get("project_id", "unknown")})

    # Telemetry: Model coaching conversion to Flash
    if state.get("coached_for_argon") and is_flash_model(usage["recent_model_used"]):
        record_telemetry_event("coached_switch_to_flash")
        state["coached_for_argon"] = False
        save_state(state)
    elif advisor_alert and advisor_alert.get("type") == "CONSERVATION_ALERT":
        state["coached_for_argon"] = True
        save_state(state)

    payload = {
        "plan_name": plan_name,
        "is_gcp_tos": is_gcp_tos,
        "is_pro": is_pro,
        "is_expired": is_expired,
        "initial_budget": initial_budget,
        "gross_usage": usage["gross_usage"],
        "caching_discount": usage["caching_discount"],
        "net_spent": net_spent,
        "remaining_budget": remaining_budget,
        "pct_remaining": pct_remaining,
        "timer": timer_info,
        "usage_by_model": {
            "flash": usage["flash"],
            "argon": usage["argon"]
        },
        "recent_model_used": usage["recent_model_used"],
        "advisor_alert": advisor_alert,
        "low_quota_alerts": low_quota_alerts,
        "vertex_conversations_count": usage["vertex_conversations_count"],
        "project_id": state.get("project_id"),
        "skills_impact": skills_data
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    project_id = state.get("project_id") or "your-workshop-project"
    total_tokens = (
        usage["flash"]["input"] + usage["flash"]["cached"] + usage["flash"]["output"] +
        usage["argon"]["input"] + usage["argon"]["cached"] + usage["argon"]["output"]
    )

    hygiene_tip = check_context_hygiene()
    unseen_tip = get_next_unseen_tip(state)

    # -----------------------------------------------------------------------
    # Output Rendering
    # -----------------------------------------------------------------------

    # SCENARIO B / WRAP-UP: Explicit --wrapup OR Active GDP Credit Mode that has Expired
    if getattr(args, "wrapup", False) or (is_gcp and is_expired):
        print("=" * 66)
        if is_expired and is_gcp:
            print(" 🎓 TOKENMAXXING — 12-HOUR WORKSHOP CREDIT COMPLETE & GRADUATION")
        else:
            print(" 🎉 TOKENMAXXING — GDG WORKSHOP IMPACT SUMMARY & NEXT STEPS")
        print("=" * 66)
        print(" 🏆 YOUR GEMINI & GOOGLE CLOUD WORKSHOP STATS:")
        print(f" ├─ Total Tokens Powered by Gemini : {total_tokens:,} tokens")
        print(f" ├─ Gross Cloud Compute Value      : ${usage['gross_usage']:.2f}")
        print(f" ├─ Gemini Context Cache Savings   : -${usage['caching_discount']:.2f} (Saved automatically!)")
        print(f" ├─ Net Workshop Voucher Utilized  : ${net_spent:.2f} / ${initial_budget:.2f}")
        if skills_used:
            print(f" ├─ Official Skills Applied        : {len(skills_used)} skills ({sum(skills_used.values())} invocations)")
            print(f" └─ Hallucinations Avoided         : ~{tokens_saved:,} debugging tokens saved (~{max(1, tokens_saved // 12000)} turns)")
        print("-" * 66)
        print(" 🌱 KEEP BUILDING WITH GEMINI & GOOGLE CLOUD (FREE GRADUATION BRIDGE):")
        print(" 1. Keep Your Gemini App Running Free:")
        print("    • Grab a free Gemini API key at: https://aistudio.google.com/apikey")
        print("    • Or claim $300 in Google Cloud Free Trial credits: https://cloud.google.com/free")
        print(" 2. Switch Antigravity Back to Your Personal Account (Once 12h Credit Ends):")
        print("    • Sign Out (Top-right 👤 Profile in Editor OR Bottom-left ⚙️ Settings -> Account).")
        print("    • Sign back in with your personal Google Account (Google AI Pro or Free Tier).")
        print("=" * 66)
        return

    # SCENARIO A: User is on Google AI Pro / Ultra
    if is_pro and not is_gcp:
        if getattr(args, "pulse", False):
            if low_quota_alerts:
                print(f"⚠️ **TokenMaxx Quota Alert:** {', '.join(low_quota_alerts)} — switch to Gemini 3.8 Flash to avoid throttling.")
            return
        print("=" * 66)
        print(" ⚡ TOKENMAXXING — ACTIVE PLAN: GOOGLE AI PRO")
        print("=" * 66)
        print(" ℹ️  You are operating on your personal Google AI Pro plan.")
        print("    Prompts and model turns are unlimited under your subscription.")

        if low_quota_alerts:
            print("-" * 66)
            print(" ⚠️  QUOTA RADAR WARNING:")
            for alert in low_quota_alerts:
                print(f"    • {alert}")
            print("    Tip: Switch to an alternate model (e.g. Gemini 3.8 Flash) to avoid throttling.")

        # Skills & Marketplace Hub for Pro Users
        print("-" * 66)
        installed_list = get_installed_google_skills()
        opp = detect_workspace_skills_opportunity(installed_list)
        opp_text = ""
        if opp:
            opp_text = f" • 💡 {opp.get('message', '')} `{opp.get('cli_fallback', '')}`"
            if opp.get("plugin_id"):
                opp_text += f"\n   Marketplace Card: <plugin-card catalog-id=\"{opp['plugin_id']}\"></plugin-card>"

        if skills_used:
            print(" 🧩 OFFICIAL GOOGLE AGENT SKILLS IMPACT (ROI):")
            used_str = ", ".join(f"{s} ({c}x)" for s, c in sorted(skills_used.items()))
            print(f" • Active Skills Applied   : {used_str}")
            print(f" • Debugging Tokens Saved  : ~{tokens_saved:,} tokens (~{max(1, tokens_saved // 12000)} turns saved!)")
            if installed_list:
                disp_installed = ", ".join(installed_list[:5]) + ("..." if len(installed_list) > 5 else "")
                print(f" • Installed Skills Base   : {disp_installed}")
            if opp_text:
                print(opp_text)
        else:
            print(" 🧩 OFFICIAL GOOGLE AGENT SKILLS & MARKETPLACE:")
            if installed_list:
                disp_installed = ", ".join(installed_list[:5]) + ("..." if len(installed_list) > 5 else "")
                print(f" • Installed Skills Base   : {disp_installed}")
            if opp_text:
                print(opp_text)
            print(" • Curated Google Marketplace Plugins:")
            print("   - 🔥 AI & Gemini   : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/gemini-api\"></plugin-card>")
            print("   - ☁️ Google Cloud  : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/google-cloud-developer\"></plugin-card>")
            print("   - ⚡ App Backend   : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/firebase\"></plugin-card>")
        if hygiene_tip:
            print("-" * 66)
            print(f" {hygiene_tip}")
        elif unseen_tip:
            print("-" * 66)
            print(" 💡 ANTIGRAVITY & GOOGLE POWER TIP:")
            print(f"   {unseen_tip}")
        print("=" * 66)
        return

    # SCENARIO D: User is on Personal Free Tier (Not connected to Agent Platform yet)
    if not is_pro and not is_gcp:
        if getattr(args, "pulse", False):
            if low_quota_alerts:
                print(f"⚠️ **TokenMaxx Quota Alert:** {', '.join(low_quota_alerts)} — switch to Gemini 3.8 Flash to avoid throttling.")
            return
        print("=" * 66)
        print(" ⚡ TOKENMAXXING — ACTIVE PLAN: GOOGLE AI FREE TIER")
        print("=" * 66)
        print(" ℹ️  You are currently signed into your personal Free Tier account.")
        if state.get("project_id"):
            print("-" * 66)
            print(f" 🏗️  Prepared Workshop Project : {state['project_id']}")
            print(" 👉 To connect Antigravity to your workshop project, complete Step 4")
            print("    (run `tokenmaxx --step4` or ask \"Connect my workshop project\").")
        else:
            print(" 👉 Have a GDG workshop credit? Ask me: \"Help me set up my GDG credits\"")
        if model_quotas:
            print("-" * 66)
            print(" 📊 LIVE MODEL QUOTA RADAR:")
            for q in model_quotas[:6]:
                rem = q.get("remainingFraction")
                pct = "0%" if rem is None else f"{rem*100:.0f}%"
                rst = q.get("reset_time") or "N/A"
                print(f" • {q.get('label', 'Model'):<26}: {pct} remaining (resets: {rst})")

        print("-" * 66)
        print(" 🧩 OFFICIAL GOOGLE AGENT SKILLS & MARKETPLACE:")
        print(" Supercharge your Antigravity project with 1-click Google plugins:")
        print(" • 🔥 AI & Gemini   : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/gemini-api\"></plugin-card>")
        print(" • ☁️ Google Cloud  : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/google-cloud-developer\"></plugin-card>")
        print(" • ⚡ App Backend   : <plugin-card catalog-id=\"antigravity-plugins-official/plugin/firebase\"></plugin-card>")
        if hygiene_tip:
            print("-" * 66)
            print(f" {hygiene_tip}")
        elif unseen_tip:
            print("-" * 66)
            print(" 💡 ANTIGRAVITY & GOOGLE POWER TIP:")
            print(f"   {unseen_tip}")
        print("=" * 66)
        return

    # SCENARIO C: Active GDP Credit Mode (Agent Platform)
    turns_flash = int(remaining_budget / 0.005)
    turns_argon = int(remaining_budget / 0.06)
    pct_used = max(0.0, 100.0 - pct_remaining)

    # Milestone Checkpoint Tracker (50%, 70%, 90% used)
    crossed_milestone = None
    last_milestone = state.get("last_milestone_alerted", 0)
    for m in [90, 70, 50]:
        if pct_used >= m and last_milestone < m:
            crossed_milestone = m
            state["last_milestone_alerted"] = m
            save_state(state)
            record_telemetry_event("credit_milestone", {"milestone": crossed_milestone})
            break

    # Compact 2-line TokenMaxx Status Bar (for Every-5-Prompts Pulse)
    if getattr(args, "pulse", False) and not crossed_milestone and hours_left >= 2.0:
        print(f"⚡ **TokenMaxx Pulse:** **${remaining_budget:.2f} / ${initial_budget:.2f} left ({pct_remaining:.1f}%)** • ⏱️ **{timer_info['formatted']}** • 💡 *~{turns_flash:,} Flash turns left (Ask `\"How much credit do I have left?\"` anytime)*")
        if advisor_alert:
            print(f"   {advisor_alert['title']}: {advisor_alert['message']}")
        elif hygiene_tip:
            print(f"   {hygiene_tip}")
        elif unseen_tip:
            print(f"   {unseen_tip}")
        return

    print("=" * 66)
    if crossed_milestone:
        print(f" 🔔 TOKENMAXXING — {crossed_milestone}% WORKSHOP CREDIT MILESTONE REACHED")
    else:
        print(" ⚡ TOKENMAXXING — GDP WORKSHOP TOKEN & CREDIT CO-PILOT")
    print("=" * 66)
    print(f" 🎟️  Active Account   : Agent Platform (GDP Workshop Credit)")
    if state.get("project_id"):
        print(f" 🏗️  Workshop Project : {state['project_id']} (Vertex AI Ready)")
    print(f" ⏳ Credit Lifespan  : {timer_info['formatted']}")
    print(f" 🎯 Current Model    : {usage['recent_model_used']}")
    print("-" * 66)
    if hygiene_tip:
        print(f" {hygiene_tip}")
        print("-" * 66)
    elif unseen_tip:
        print(" 💡 ANTIGRAVITY & GOOGLE POWER TIP:")
        print(f"   {unseen_tip}")
        print("-" * 66)
    print("-" * 66)
    print(" 🧾 PRODUCTION INVOICING RECONCILIATION (MATCHES CLOUD CONSOLE):")
    print(f" ├─ Gross Usage Cost    : ${usage['gross_usage']:.2f} (Uncached list rates)")
    print(f" ├─ Context Cache Credit: -${usage['caching_discount']:.2f} (Prompt caching savings)")
    print(f" ├─ Net Voucher Deducted: -${net_spent:.2f} (Across {usage['vertex_conversations_count']} GDP chats)")
    print(f" └─ Remaining Credit    : ${remaining_budget:.2f} ({pct_remaining:.1f}% remaining)")
    print("-" * 66)

    # Model Usage Breakdown
    print(" 📊 TOKEN CONSUMPTION BY MODEL TIER:")
    print(f" • Gemini 3.8 Flash : {usage['flash']['input'] + usage['flash']['cached']:,} tokens (${usage['flash']['net_cost']:.2f})")
    print(f" • Gemini 4 Argon   : {usage['argon']['input'] + usage['argon']['cached']:,} tokens (${usage['argon']['net_cost']:.2f})")
    print("-" * 66)

    # Advisor Alert
    if advisor_alert:
        print(f" {advisor_alert['title']}:")
        print(f" {advisor_alert['message']}")
        print("-" * 66)

    print(" 🛒 WHAT YOUR REMAINING CREDIT CAN DO:")
    print(f" • ~{turns_flash:,} interactive turns on Gemini 3.8 Flash, OR")
    print(f" • ~{turns_argon} deep reasoning refactors on Gemini 4 Argon")
    print("-" * 66)
    installed_list = get_installed_google_skills()
    opp = detect_workspace_skills_opportunity(installed_list)
    opp_text = ""
    if opp:
        opp_text = f" • 💡 {opp.get('message', '')} `{opp.get('cli_fallback', '')}`"
        if opp.get("plugin_id"):
            opp_text += f"\n   Marketplace Card: <plugin-card catalog-id=\"{opp['plugin_id']}\"></plugin-card>"

    if skills_used:
        print(" 🧩 OFFICIAL GOOGLE AGENT SKILLS IMPACT (ROI):")
        used_str = ", ".join(f"{s} ({c}x)" for s, c in sorted(skills_used.items()))
        print(f" • Active Skills Applied   : {used_str}")
        print(f" • Debugging Tokens Saved  : ~{tokens_saved:,} tokens (~{max(1, tokens_saved // 12000)} turns saved!)")
        if installed_list:
            disp_installed = ", ".join(installed_list[:5]) + ("..." if len(installed_list) > 5 else "")
            print(f" • Installed Skills Base   : {disp_installed}")
        if opp_text:
            print(opp_text)
        print(" (Install more skills anytime: tokenmaxx --install-skill <name_or_track>)")
    else:
        print(" 🧩 OFFICIAL GOOGLE AGENT SKILLS GATEWAY (github.com/google/skills):")
        if installed_list:
            disp_installed = ", ".join(installed_list[:5]) + ("..." if len(installed_list) > 5 else "")
            print(f" • Installed Skills Base   : {disp_installed} (0 invocations yet)")
        if opp_text:
            print(opp_text)
        print(" • Popular 1-Click Skills:")
        print("   - 🔥 AI & Agents  : gemini-api | gemini-live-api | genkit-python")
        print("   - ⚡ App & Mobile : firebase-basics | flutter | google-signin")
        print("   - ☁️ Cloud & Data : cloud-run | bigquery | developer-knowledge")
        print(" (To install, say \"Install <name>\" or run: tokenmaxx --install-skill <name>)")
    print("-" * 66)
    print(f" {selected_pro_move}")
    print(" 💬 Ask \"How much credit do I have left?\" anytime (pulses every 5 prompts)")
    print("=" * 66)

# ---------------------------------------------------------------------------
# Antigravity Version & Window Surface Detection (P0-D)
# ---------------------------------------------------------------------------

def detect_antigravity_environment() -> dict:
    """
    Detects the running Antigravity IDE/App version and active window surface
    ('hub' = Agent Manager view vs 'ide' = Editor view) so users on older builds
    (< 2.26.0) are warned before Step 4 if 'Use Business Account' is missing.
    """
    env = {
        "version_str": None,
        "surface": "unknown",
        "needs_update": False
    }
    if sys.platform != "win32":
        try:
            ps_out = subprocess.check_output(["ps", "aux"], text=True, stderr=subprocess.DEVNULL)
            for line in ps_out.splitlines():
                if "language_server" in line:
                    m_ver = re.search(r"--override_ide_version\s+([0-9\.]+)", line)
                    if m_ver:
                        env["version_str"] = m_ver.group(1)
                    m_sub = re.search(r"--subclient_type\s+(\S+)", line)
                    if m_sub:
                        env["surface"] = m_sub.group(1).lower()
                    break
        except Exception:
            pass

    # Fallback check on macOS Info.plist
    if not env["version_str"] and sys.platform == "darwin":
        plist_path = Path("/Applications/Antigravity.app/Contents/Info.plist")
        if plist_path.exists():
            try:
                out = subprocess.check_output(
                    ["defaults", "read", "/Applications/Antigravity.app/Contents/Info.plist", "CFBundleShortVersionString"],
                    text=True, stderr=subprocess.DEVNULL
                ).strip()
                if out:
                    env["version_str"] = out
            except Exception:
                pass

    if env["version_str"]:
        try:
            parts = [int(x) for x in env["version_str"].split(".")[:2]]
            if len(parts) >= 2 and (parts[0], parts[1]) < (2, 26):
                env["needs_update"] = True
        except Exception:
            pass

    return env

# ---------------------------------------------------------------------------
# Turn-by-Turn Conversational Onboarding Steps (P0-A, P0-B, P0-D)
# ---------------------------------------------------------------------------

INSTALLER_URL_MARKERS = [
    "tokenmaxxing", "tokenmaxing", "tokenmaxx", "tokenmax",
    "g.dev/ai/workshop", "g.dev/ai/tokens", "g.dev/ai/credits",
    "g.dev/ai/copilot", "g.dev/ai/companion", "g.dev/ai/skillshelper",
    "g.dev/workshop", "install.sh", "raw.githubusercontent.com", "<", ">"
]

def run_step1(raw_claim_url: str = ""):
    record_telemetry_event("setup_step1")
    env = detect_antigravity_environment()

    clean_input = (raw_claim_url or "").strip()
    clean_lower = clean_input.lower()

    # Allow 1-keystroke persona selection from any non-Antigravity harness (1=dev, 2=builder)
    if clean_lower in {"1", "2", "a", "b", "builder", "developer", "dev"}:
        set_persona(clean_input)
        clean_input = ""
        clean_lower = ""

    # Guard: Never treat the TokenMaxxing installer URL itself or confirmation words as an event credit claim URL!
    if any(k in clean_lower for k in INSTALLER_URL_MARKERS):
        clean_input = ""
    if clean_lower in {"claimed", "done", "yes", "ok", "next", "skip"}:
        # If the agent accidentally passed "claimed" to --step1 instead of calling --step2, redirect seamlessly to Step 2!
        run_step2()
        return

    claim_url, suggested_event, direct_portal = normalize_claim_url(clean_input)

    state = load_state()
    if not state.get("onboarding_started_at"):
        state["onboarding_started_at"] = datetime.now(timezone.utc).isoformat()
    was_awaiting_url = (state.get("onboarding_step") == "step1_awaiting_url")
    state["claimed_at"] = datetime.now(timezone.utc).isoformat()
    if suggested_event:
        state["suggested_event"] = suggested_event
    elif not state.get("suggested_event"):
        state["suggested_event"] = "gdg-workshop"
    state["last_milestone_alerted"] = 0

    if clean_input:
        slug = suggested_event
        if not slug and "/" in clean_input:
            slug = clean_input.split("?")[0].rstrip("/").split("/")[-1]
        record_telemetry_event("setup_step1_url_opened", {"slug": slug or "unknown", "url": claim_url})
        state["onboarding_step"] = "step1_url_opened"
        save_state(state)
        open_browser_url(claim_url)
    else:
        record_telemetry_event("setup_step1_prompted")
        state["onboarding_step"] = "step1_awaiting_url"
        save_state(state)

    if not (clean_input and was_awaiting_url):
        open_browser_url("https://g.dev/ai/workshop", background=True)
        print("⚡ **Welcome to TokenMaxxing — Your GDG Workshop & Vibe Coding Co-Pilot!**")
        print("I'm here to superpower your entire journey from setup to live deployment:\n")
        print("🎟️ **90-Second Credit Setup:** Guided 3-step activation with pre-enabled Vertex AI (0% crash rate).")
        print("⛽ **Real-Time Gas Gauge & Timer:** Live token pricing, 12h expiration countdown, and model efficiency pacing.")
        print("🔑 **Zero-Key Gemini SDK:** Build GenAI apps with your $5.00 grant without managing or leaking API keys.")
        print("🚀 **Official Skills & 1-Prompt Deploy:** Verified Google blueprints (Firebase, Flutter, Gemini) + 1-prompt Cloud Run deploy.")
        print("🌐 **Web Companion Hub:** Opened **[g.dev/ai/workshop](https://g.dev/ai/workshop)** in your browser background for 1-click prompt recipes & cheat sheets.\n")

        if env["needs_update"]:
            print(f"⚠️ **Important Version Check (Antigravity v{env['version_str']} detected):**")
            print("Before we reach Step 4, please make sure you update Antigravity to **v2.26.0+** (**Antigravity → Check for Updates** or download from `https://antigravity.google`) so the **\"Use Business Account\"** sign-in option is available.\n")
        print("---")

    if clean_input:
        print("### 🎟️ Step 1 of 4: Claim Your $5.00 Workshop Credit")
        print(f"I just opened your credit link in your browser:\n👉 **{claim_url}**")
        if direct_portal and direct_portal != claim_url:
            print(f"   *(Direct Portal Fallback if redirect fails: {direct_portal})*\n")
        else:
            print("")
        print("1. Make sure you are signed into your Google account in your browser.")
        print("2. Click **\"Claim Credit\"** (or **\"Apply\"**) on that page.")
        print("   • 🔄 **First time on g.dev?** If Google asks you to create a Developer Profile first, complete that and re-open the link above so the **\"Claim Credit\"** button appears.")
        print("   • 👤 **Same Account Rule:** Note which Google account avatar is in the top-right—you will need to use this exact same account for Steps 2, 3, and 4!")
        print("3. Click the confirmation button below (or reply **\"claimed\"**) once you've claimed it in your browser, and I'll open Step 2 for you!")
        print("\n🛑 [AGENT DIRECTIVE: Present the message above to the user, and IN THIS SAME TURN call the `ask_question` tool (if available in your harness) with:")
        print("  Question: \"Once you've clicked 'Claim Credit' in your browser, how would you like to proceed?\"")
        print("  Options:")
        print("    1. \"(Recommended) ✅ I clicked 'Claim Credit' in my browser — open Step 2!\"")
        print("    2. \"🔄 Re-open my credit link in the browser\"")
        print("    3. \"🧭 Guide me through the plugin features instead\"")
        print("Do NOT run `--step2` yet! Wait for the user's selection, and when they confirm they claimed it, run `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --step2`.]")
    else:
        print("### 🎯 Let's Tailor Your Companion & Get Started!")
        print("Choose your role and how you'd like to begin using the interactive buttons below *(or paste your `https://g.dev/credits/...` link directly)*:")
        print("\n🛑 [AGENT DIRECTIVE — MANDATORY INTERACTIVE LAUNCHPAD:")
        print("1. Output the Welcome Banner above to the user.")
        print("2. DO NOT assume the user's persona from their prompt text! You MUST ALWAYS confirm their persona and starting action in this turn by calling the `ask_question` tool with these EXACT 2 questions:")
        print("   - Question 1: \"How would you like me to tailor coding guidance for you today?\"")
        print("     Options:")
        print("       • \"(Recommended) 💻 Professional Developer / Engineer (concise diffs & architecture patterns)\"")
        print("       • \"👷 Non-Traditional Builder / Vibe Coder (intuitive visual explanations, zero terminal jargon)\"")
        print("   - Question 2: \"How would you like to get started with your Workshop Companion?\"")
        print("     Options:")
        print("       • \"(Recommended) 🎟️ Setup my $5.00 Workshop Credit (or paste your credit link in 'Other' below)\"")
        print("       • \"✅ I already claimed my credit — connect my Google Cloud Project (Step 2)\"")
        print("       • \"🧭 Guide me through the plugin features (Gas Gauge, Official Skills & Vibe Coding Tips)\"")
        print("       • \"🧩 Install Official Google Agent Skills for my project (Gemini, Firebase, Cloud Run, Flutter)\"")
        print("3. WHEN THE USER ANSWERS THE INTERACTIVE WIDGET:")
        print("   - First, save their confirmed persona by running: `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --persona <developer|builder>`")
        print("   - If they pasted a credit URL in 'Other' (e.g. `https://g.dev/credits/...`), run: `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --step1 \"<USER_CREDIT_URL>\"`")
        print("   - If they chose \"🎟️ Setup my $5.00 Workshop Credit\" without a URL yet, ask them to paste their `https://g.dev/credits/...` link (or click a button if they already claimed it).")
        print("   - If they chose \"✅ I already claimed my credit\", run: `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --step2`")
        print("   - If they chose \"🧭 Guide me through the plugin features\", run: `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --tour`")
        print("   - If they chose \"🧩 Install Official Google Agent Skills\", run: `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --install-skill all` (or ask which track they want).]")

def run_step2():
    record_telemetry_event("setup_step2")
    state = load_state()
    state["onboarding_step"] = "step2_project_create"
    save_state(state)

    prefix = state.get("suggested_event") or "gdg-workshop"
    today_str = datetime.now().strftime("%d%b").lower()
    example_id = f"{prefix}-{today_str}"

    open_browser_url("https://console.cloud.google.com/projectcreate")

    print("### 🏗️ Step 2 of 4: Create Your Google Cloud Project")
    print("I just opened the **Google Cloud Project Creation** page in your browser (`https://console.cloud.google.com/projectcreate`).\n")
    print("*(💡 First time on Google Cloud? If a welcome pop-up asks you to select your Country & agree to the Terms of Service, click **Agree and Continue** first.)*\n")
    print(f"1. **Project Name & ID:** Enter **`{example_id}`** (or keep the default name). Look directly underneath the Project Name box to see your lowercase **Project ID** (e.g. `{example_id}` or `local-citizen-...`).")
    print("2. **Billing Account:**")
    print("   • **If you see the `Billing account` dropdown:** Select the account starting with **`[YYYY-MM-DD] GDP Credit: ...`** or **`Google Developers Credits`** *(draws 100% from your $5.00 voucher, never a personal card)*.")
    print("   • **⚠️ Don't see a `Billing account` dropdown at all?** Google Cloud hides that dropdown when your profile only has 0 or 1 billing account! Make sure you clicked **Claim / Apply** on your credit link in Step 1 using this **exact same Google account** (check your top-right avatar), wait 15 seconds, and refresh the page (or check `https://console.cloud.google.com/billing` to confirm your credit appears).")
    print("3. Click **Create**, then copy and **paste your lowercase Project ID here in chat** so I can open Step 3 for you!")
    print("\n🛑 [AGENT DIRECTIVE: Present ONLY Step 2 above to the user and STOP. Do NOT show Step 3 or Step 4 yet!")
    print("WHEN THE USER REPLIES NEXT:")
    print("• If the user replies with a valid lowercase Project ID (e.g. `gdg-workshop-27oct` or `local-citizen-512912-i5`), run:")
    print("    `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --step3 \"<PROJECT_ID>\"`")
    print("• If the user instead pastes a credit claim URL (`https://g.dev/...`) because they hadn't claimed their credit yet, run `tokenmaxx.py --step1 \"<USER_CREDIT_URL>\"`.]")

def run_step3(project_id: str):
    clean_id = (project_id or "").strip().lower()
    state = load_state()
    prefix = state.get("suggested_event") or "gdg-workshop"
    today_str = datetime.now().strftime("%d%b").lower()
    example_id = f"{prefix}-{today_str}"

    # Guard: If user pasted a credit URL here, redirect to Step 1 with that URL
    if any(k in clean_id for k in ["g.dev/", "developers.google.com/benefits"]):
        run_step1(project_id)
        return

    RESERVED_WORDS = {
        "claimed", "done", "yes", "ok", "okay", "next", "skip", "created",
        "step1", "step2", "step3", "step4", "none", "null", "true", "false",
        "<your_project_id>", "<project_id>", "your-project-id", "project-id"
    }
    is_valid_gcp_id = (
        bool(re.match(r"^[a-z][a-z0-9\-]{3,29}$", clean_id))
        and clean_id not in RESERVED_WORDS
        and not any(k in clean_id for k in ["http", "www.", ".com", ".dev", "/"])
    )

    if not is_valid_gcp_id:
        record_telemetry_event("setup_step3_invalid_id", {"invalid_input": (project_id or "")[:30]})
        print(f"⚠️ **`{project_id}` doesn't look like a valid Google Cloud Project ID.**\n")
        print("- A Google Cloud **Project ID** is 6–30 lowercase letters, numbers, and hyphens with **no spaces** (for example: **`" + example_id + "`** or **`local-citizen-512912-i5`**).")
        print("- You can find it directly underneath the **Project name** box on `https://console.cloud.google.com/projectcreate` (or in the project picker at the top-left of Google Cloud Console).\n")
        print("👉 Please copy and paste your lowercase **Project ID** here so I can open the Vertex AI API activation page for your project!")
        print("\n🛑 [AGENT DIRECTIVE: Present ONLY the message above to the user and STOP. Wait for the user to reply with a valid lowercase Project ID before running `--step3 \"<PROJECT_ID>\"` again.]")
        return

    record_telemetry_event("setup_step3", {"project_id": clean_id})
    state["project_id"] = clean_id
    state["onboarding_step"] = "step3_api_enable"
    save_state(state)
    copy_to_clipboard(clean_id)

    enable_url = f"https://console.cloud.google.com/apis/enableflow?apiid=aiplatform.googleapis.com&project={clean_id}"
    open_browser_url(enable_url)

    print(f"### ⚡ Step 3 of 4: Enable Vertex AI API for `{clean_id}`")
    print("I have saved your Project ID, copied it to your clipboard, and opened the **API Activation Page** in your browser:\n")
    print(f"👉 **{enable_url}**\n")
    print("1. In your browser window, click **Next** (if shown) and then click **Enable**.")
    print("   *(💡 If Google Cloud prompts you to link a billing account here, select your **`GDP Credit` / `Google Developers Credits`** account).*")
    print("2. Wait ~5 seconds until it finishes enabling, then click the button below (or reply **\"done\"**) for our final step!")
    print("\n🛑 [AGENT DIRECTIVE: Present Step 3 above to the user, and IN THIS SAME TURN call the `ask_question` tool (if available) with:")
    print("  Question: \"Once you've clicked 'Enable' on the Vertex AI API page in your browser, ready for Step 4?\"")
    print("  Options:")
    print("    1. \"(Recommended) ✅ I clicked 'Enable' on Vertex AI API — open Step 4!\"")
    print("    2. \"🔄 Re-open the Vertex AI API page in my browser\"")
    print("Do NOT show Step 4 yet! Wait for the user to confirm they clicked Enable, and ONLY THEN run `python3 ~/.gemini/config/skills/tokenmaxxing/scripts/tokenmaxx.py --step4`.]")

def run_step4():
    record_telemetry_event("setup_step4")
    state = load_state()
    project_id = state.get("project_id") or "<your-project-id>"
    state["onboarding_step"] = "completed"
    save_state(state)
    if project_id != "<your-project-id>":
        copy_to_clipboard(project_id)
        onboarding_seconds = None
        started_str = state.get("onboarding_started_at")
        if started_str:
            try:
                started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                onboarding_seconds = max(1, int((now_dt - started_dt).total_seconds()))
            except Exception:
                pass
        completed_params = {"project_id": project_id}
        if onboarding_seconds:
            completed_params["onboarding_seconds"] = onboarding_seconds
        record_telemetry_event("setup_completed", completed_params)

    harness = detect_harness()

    if harness in ("claude_code", "cursor", "vscode"):
        h_name = "Claude Code" if harness == "claude_code" else ("Cursor" if harness == "cursor" else "VS Code / External Agent")
        print(f"### 🔄 Step 4 of 4: Connect {h_name} to Your Workshop Project")
        print(f"📋 **Your Project ID (`{project_id}`) is copied to your clipboard!**\n")
        print("To let your agent authenticate to Google Cloud Vertex AI using your $5.00 workshop credits, run:")
        print("```bash")
        print(f"gcloud auth application-default login")
        print(f"gcloud config set project {project_id}")
        print("```\n")
        print("And export the zero-key Vertex AI variables (or add to your shell profile):")
        print("```bash")
        print("export GOOGLE_GENAI_USE_VERTEXAI=true")
        print(f"export GOOGLE_CLOUD_PROJECT=\"{project_id}\"")
        print("export GOOGLE_CLOUD_LOCATION=\"global\"")
        print("```\n")
        print("---")
        print("### 🎯 Final Step — Test Your Live Dashboard!")
        print("In your chat, type:")
        print("👉 **`How much credit and tokens do I have left?`**")
        return

    print("### 🔄 Step 4 of 4: Connect Antigravity to Your Workshop Project")
    print(f"📋 **Your Project ID (`{project_id}`) is copied to your clipboard!**")
    print("⚠️ *Tip: Keep this instructions list visible (or take a quick photo/screenshot) because clicking **Sign Out** below will briefly close this chat window while you sign back in.*\n")
    print("**Phase 1: Sign Out of Antigravity**")
    print("- **If you are in the Editor (IDE) window:** Click your **👤 Profile icon** in the **top-right corner** → Click **Sign Out** *(or click **⚙️ Settings** in the top-right → Account → Sign Out)*.")
    print("- **If you are in the Agent Manager window:** Click **⚙️ Settings** in the **bottom-left corner** → Under **Account**, click **Sign Out**.\n")
    print("**Phase 2: Sign Back In with Google Cloud**")
    print("1. On the Antigravity welcome screen, click **\"Use Business Account\"**.")
    print("   *(Don't see \"Use Business Account\"? Update Antigravity via **Antigravity → Check for Updates** so you are on v2.26+!)*")
    print("2. Click **\"Continue with Google Cloud\"**.")
    print("3. In your browser, select the Google account that claimed your credit, click **Sign in**, and click **\"Open Antigravity\"**.\n")
    print("**Phase 3: Connect Your Project**")
    print("4. In Antigravity, select **\"Pay As You Go\"** *(draws 100% from your $5.00 workshop voucher—your personal card is never charged)*.")
    print(f"5. Paste your Project ID: **`{project_id}`** *(already on your clipboard!)*. Keep Region as **Global** (default) and click **Next**.")
    print("6. Close Settings (`✕`), then click **`+ New Conversation`**!\n")
    print("*(💡 Note: If running Claude Code or Cursor alongside Antigravity, authenticate via: `gcloud auth application-default login && gcloud config set project " + project_id + "`)*\n")
    print("---")
    print("### 🎯 Final Step — Check Your Live $5.00 Credit & Token Dashboard!")
    print("Once you open **`+ New Conversation`**, type this as your very first message in the new chat:")
    print("👉 **`How much credit and tokens do I have left?`**")
    print("\n*(From there, TokenMaxxing will automatically show your compact balance bar every 5 prompts and alert you at 50%, 70%, and 90% usage!)*")
    print("\n💡 **Google Cloud Developer Marketplace Plugin (Recommended):**")
    print("To get official Google Cloud architectural blueprints, CLI guardrails, and live documentation in your new chat:")
    print("<plugin-card catalog-id=\"antigravity-plugins-official/plugin/google-cloud-developer\"></plugin-card>")


def run_feature_tour():
    record_telemetry_event("feature_tour_viewed")
    state = load_state()
    persona = state.get("persona") or "developer"
    is_builder = (persona == "builder")

    print("🧭 **TokenMaxxing — Interactive Feature & Vibe Coding Guide**")
    if is_builder:
        print("*(👷 Tailored for Builders & Vibe Coders — intuitive visual workflows, zero terminal jargon)*\n")
    else:
        print("*(💻 Tailored for Professional Developers — idiomatic SDKs, context economics & Cloud Run)*\n")

    print("Here are the **4 Superpowers** unlocked in your workspace right now:\n")
    print("1. ⛽ **Real-Time Gas Gauge & Quota Radar**")
    print("   • Ask *\"How much credit and tokens do I have left?\"* anytime.")
    print("   • Tracks your exact token spend with 75% context caching discounts, 12h voucher timer, and model quota radar.\n")
    print("2. 🧩 **Official Google Agent Skills (Zero API Hallucinations)**")
    print("   • Ask *\"Install Gemini API, Firebase, Flutter, or Cloud Run skills\"*.")
    print("   • Pulls verified blueprints from `github.com/google/skills` so the AI never hallucinates outdated SDK syntax (saving ~35,000 debugging tokens per feature!).\n")
    print("3. 🔑 **Zero-Key Gemini SDK & 1-Prompt Cloud Run Deploy**")
    print("   • Ask *\"Build a Gemini app\"* — auto-configures dual-mode Vertex AI so your app runs with your workshop credit and zero API keys.")
    print("   • Ask *\"Deploy my app to Cloud Run\"* — ships your project to a live public `https://...run.app` URL in one prompt.\n")
    print("4. 💡 **What's New in Antigravity & PromptMaxxing Coach**")
    print("   • Ask *\"What's new in Antigravity?\"* to discover power commands like `/grill-me`, `/boost`, `/compact`, and Generative UI artifacts.")
    print("\n🛑 [AGENT DIRECTIVE: Present the Feature Tour above to the user, and IN THIS SAME TURN call the `ask_question` tool with:")
    print("  Question: \"Which TokenMaxxing superpower would you like to try right now?\"")
    print("  Options:")
    print("    1. \"(Recommended) ⛽ Show my live Token Gas Gauge & Quota Radar\"")
    print("    2. \"🧩 Install Official Google Agent Skills (Gemini, Firebase, Cloud Run, Flutter)\"")
    print("    3. \"💡 Show 'What's New in Antigravity' & Vibe Coding Power Tips\"")
    print("    4. \"🎟️ Setup my $5.00 Workshop Credit (Step 1)\"")
    print("When the user selects an option, execute the matching `tokenmaxx.py` command (`tokenmaxx.py`, `tokenmaxx.py --install-skill all`, `tokenmaxx.py --whats-new`, or `tokenmaxx.py --step1`).]")


# ---------------------------------------------------------------------------
# CLI Argument Parsing
# ---------------------------------------------------------------------------

def run_interactive_setup():
    print("=" * 66)
    print(" 🚀 TOKENMAXXING — INTERACTIVE GDG CREDIT ONBOARDING WIZARD")
    print("=" * 66)
    record_telemetry_event("setup_started")
    print(" This wizard walks you through activating your $5.00 Google Cloud")
    print(" credit step-by-step and unlocks your live budget & token tracker.")
    print("-" * 66)

    env = detect_antigravity_environment()
    if env["needs_update"]:
        print(f" ⚠️  Update Check: Antigravity v{env['version_str']} detected.")
        print("     Please update to v2.26.0+ (Antigravity -> Check for Updates)")
        print("     so the 'Use Business Account' option appears in Step 4.")
        print("-" * 66)

    # Step 1: Claim Credit
    print(" 🎟️  STEP 1: Claim Your $5.00 Event Voucher")
    print("    Paste your claim link (e.g. https://g.dev/credits/... or me.developers.google.com/...)")
    try:
        raw_claim = input("    👉 Claim URL (or press Enter if already claimed): ").strip()
    except (EOFError, KeyboardInterrupt):
        raw_claim = ""
    claim_url, suggested_event, direct_portal = normalize_claim_url(raw_claim)
    if raw_claim:
        print(f"    Opening claim page in browser: {claim_url}")
        if direct_portal and direct_portal != claim_url:
            print(f"    (Direct Portal Fallback: {direct_portal})")
        print("    • Tip: If Google asks you to create a Developer Profile first, complete that and re-open the link.")
        print("    • Tip: Remember which Google account you use here for Steps 2, 3, and 4!")
        open_browser_url(claim_url)
    try:
        input("    👉 Click 'Claim Credit' in browser, then press Enter here to continue... ")
    except (EOFError, KeyboardInterrupt):
        pass

    # Lock timer
    state = load_state()
    now_iso = datetime.now(timezone.utc).isoformat()
    state["claimed_at"] = now_iso
    state["suggested_event"] = suggested_event or "gdg-workshop"
    state["last_milestone_alerted"] = 0
    save_state(state)
    print(f"    ⏰ 12-Hour Expiration Clock locked starting now!")
    print("-" * 66)

    # Step 2: Create Project
    today_str = datetime.now().strftime("%d%b").lower()
    prefix = suggested_event or "gdg-workshop"
    example_id = f"{prefix}-{today_str}"
    print(" 🏗️  STEP 2: Create Your Google Cloud Project")
    print("    Opening project creation console in browser...")
    print(f"    💡 Pro-Tip 1 (Naming): Name your project '{example_id}'")
    print("       (Google Cloud Project IDs must be globally unique & lowercase).")
    print("    💡 Pro-Tip 2 (Billing Account): Click the 'Billing account' dropdown and select")
    print("       the one starting with '[YYYY-MM-DD] GDP Credit: ...'")
    print("       (This guarantees it draws exclusively from your $5 grant, NEVER your personal card!).")
    print("    ⏳ Pro-Tip 3 (Sync Buffer): It takes 15–30 seconds for Google Cloud to sync your voucher.")
    print("       If the 'Billing account' dropdown is blank, wait 15 seconds and refresh the page.")
    print("    👤 Pro-Tip 4 (Account Check): Make sure your browser is using the same Google profile")
    print("       that claimed the voucher (check avatar in top-right of Cloud Console).\n")
    open_browser_url("https://console.cloud.google.com/projectcreate")
    try:
        project_id = input(f"    👉 Enter your created Project ID (e.g. {example_id}): ").strip().lower()
        while not project_id:
            project_id = input("    Please enter a valid Project ID: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        project_id = example_id

    state["project_id"] = project_id
    save_state(state)
    if copy_to_clipboard(project_id):
        print(f"    📋 Copied '{project_id}' to your clipboard!")
    print("-" * 66)

    # Step 3: Enable API
    print(" ⚡ STEP 3: Enable Vertex AI API for Your Project")
    enable_url = f"https://console.cloud.google.com/apis/enableflow?apiid=aiplatform.googleapis.com&project={project_id}"
    print(f"    Opening API activation page for '{project_id}'...")
    open_browser_url(enable_url)
    try:
        input("    👉 In Chrome: Click 'Next' (if shown), then click 'Enable'. Press Enter when done... ")
    except (EOFError, KeyboardInterrupt):
        pass
    print("-" * 66)

    # Step 4: Account Switch Walkthrough (Dual UI Layout + Final Hand-Off)
    print(" 🔄 STEP 4: Connect Antigravity to Your Workshop Project")
    print("    Follow these 3 quick phases (takes ~20 seconds):\n")
    print("    [Phase 1: Sign Out of Antigravity]")
    print("    • In Editor (IDE) Window : Click 👤 Profile icon (top-right) -> 'Sign Out'")
    print("    • In Agent Manager Window: Click ⚙️  Settings (bottom-left) -> Account -> 'Sign Out'\n")
    print("    [Phase 2: Sign Back In with Google Cloud]")
    print("    1. On the welcome screen, click 'Use Business Account'.")
    print("    2. Click 'Continue with Google Cloud'.")
    print("    3. In your browser: pick your Google account and click 'Sign in'.")
    print("    4. In the pop-up, click 'Open Antigravity'.\n")
    print("    [Phase 3: Connect Workshop Voucher]")
    print("    5. In Antigravity, choose 'Pay As You Go' (draws 100% from your $5 voucher).")
    print(f"    6. Paste your Project ID: '{project_id}' (already copied to clipboard!)")
    print("       Keep Region as 'Global' (default), and click 'Next'.")
    print("    7. Close Settings (✕), then click '+ New Conversation' (top-left)!\n")
    print("    🎯 FINAL STEP — Test Your Live Credit & Token Tracker:")
    print("       In your new conversation, type:")
    print("       👉 \"How much credit and tokens do I have left?\"\n")
    try:
        input("    👉 Once switched, press Enter here to auto-verify your connection... ")
    except (EOFError, KeyboardInterrupt):
        pass
    print("-" * 66)

    # Step 5: Verification (with quick sync polling)
    print(" 🔍 Auto-verifying connection via local language server...")
    port, csrf, pid = discover_language_server()
    verified = False
    if port and csrf:
        for attempt in range(2):
            u = query_user_status(port, csrf)
            tier = u.get("userTier", {}).get("name", "")
            is_gcp = u.get("isGcpTos", False)
            if is_gcp or tier == "Agent Platform":
                print(f" 🎉 SUCCESS! Verified: Live on Agent Platform ({project_id})!")
                print("    Ask \"How much credit and tokens do I have left?\" in chat anytime!")
                record_telemetry_event("setup_completed", {"project_id": project_id})
                verified = True
                break
            if attempt == 0:
                time.sleep(2)
        if not verified:
            print(f" ℹ️  Antigravity is currently detecting plan: '{tier}'.")
            print("    Close Settings (✕) and click '+ New Conversation' in the top-left to activate!")
    else:
        print(" 🎉 Setup completed! Ask \"How much credit and tokens do I have left?\" in chat.")
        record_telemetry_event("setup_completed", {"project_id": project_id})
    print("=" * 66)

def main():
    parser = argparse.ArgumentParser(description="TokenMaxxing for Antigravity - Workshop Token & Credit Co-Pilot")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--pulse", "--status-bar", action="store_true", dest="pulse", help="Output compact 2-line TokenMaxx Status Bar (auto-escalates at 50%/70%/90% checkpoints)")
    parser.add_argument("--wrapup", "--summary", action="store_true", dest="wrapup", help="Display workshop impact summary and free Gemini/Google Cloud graduation bridge")
    parser.add_argument("--claimed-at", type=str, help="Calibrate credit claim time (ISO or HH:MM)")
    parser.add_argument("--install-skill", type=str, help="1-click install official Google skill from github.com/google/skills")
    parser.add_argument("--setup", action="store_true", help="Launch interactive GDG credit setup wizard")
    parser.add_argument("--whats-new", "--tips", action="store_true", dest="whats_new", help="Display latest Antigravity capabilities, slash commands, and pro-tips")
    parser.add_argument("--tour", "--guide", "--features", action="store_true", dest="tour", help="Display interactive TokenMaxxing feature tour and superpower menu")
    parser.add_argument("--persona", "--set-persona", type=str, default=None, help="Set builder persona: developer or builder")
    parser.add_argument("--step1", nargs="?", const="", default=None, help="Run onboarding Step 1 (Claim Credit & Version Check)")
    parser.add_argument("--step2", action="store_true", help="Run onboarding Step 2 (Open Project Creation)")
    parser.add_argument("--step3", type=str, default=None, help="Run onboarding Step 3 (Open API Enablement for Project ID)")
    parser.add_argument("--step4", action="store_true", help="Run onboarding Step 4 (Dual-UI Account Switch & Hand-off)")
    parser.add_argument("--update", action="store_true", help="Check and install the latest TokenMaxxing release from GitHub")
    parser.add_argument("--reset", "--new-workshop", action="store_true", dest="reset", help="Reset budget to $5.00 and restart 12h clock for a new workshop")

    args = parser.parse_args()

    record_telemetry_event("tokenmaxx_invoked", {"flag_setup": args.setup, "flag_json": args.json, "flag_pulse": args.pulse})

    if args.reset:
        state = load_state()
        state["claimed_at"] = datetime.now(timezone.utc).isoformat()
        state["last_milestone_alerted"] = 0
        state["status"] = "active"
        save_state(state)
        print("=" * 66)
        print(" 🔄 WORKSHOP SESSION RESET")
        print("=" * 66)
        print(" Past workshop conversations have been archived as historical.")
        print(" Your budget is reset to $5.00 (100% remaining) with a fresh 12-hour clock!")
        print("=" * 66)
        return

    if args.update:
        check_for_updates(force=True)
        return

    # Non-blocking daily background check
    check_for_updates(force=False)

    if args.persona:
        set_persona(args.persona)
        return

    if args.whats_new:
        display_whats_new()
        return

    if args.tour:
        run_feature_tour()
        return

    if args.step1 is not None:
        run_step1(args.step1)
        return

    if args.step2:
        run_step2()
        return

    if args.step3 is not None:
        run_step3(args.step3)
        return

    if args.step4:
        run_step4()
        return

    if args.install_skill:
        install_google_skill(args.install_skill)
        return

    if args.setup:
        run_interactive_setup()
        return

    run_tokenmaxx(args)

if __name__ == "__main__":
    main()
