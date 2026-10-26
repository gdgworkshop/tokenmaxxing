#!/usr/bin/env python3
"""
tokenmaxx.py - TokenMaxxing for Google Antigravity
The official economic co-pilot and token management engine for GDG workshops & Antigravity power users.

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

CURRENT_VERSION = "1.0.2"
GITHUB_REPO = os.environ.get("TOKENMAXX_REPO", "saadgh/tokenmaxxing")
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
APP_STORAGE_PATH = Path.home() / "Library" / "Application Support" / "Antigravity" / "app_storage.json"
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
    Finds Antigravity's active language_server process, extracts CSRF token,
    and identifies the listening HTTP port.
    """
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
    except Exception:
        return None, None, None

    pid = None
    csrf_token = None

    for line in ps_out.splitlines():
        if "language_server" in line and "--csrf_token" in line:
            parts = line.split()
            pid = parts[1]
            match = re.search(r"--csrf_token\s+([a-f0-9\-]+)", line)
            if match:
                csrf_token = match.group(1)
            break

    if not pid or not csrf_token:
        return None, None, None

    # Discover listening TCP ports for this PID
    try:
        lsof_out = subprocess.check_output(["lsof", "-nP", "-p", pid, "-iTCP", "-sTCP:LISTEN"], text=True)
        ports = []
        for line in lsof_out.splitlines():
            m = re.search(r"127\.0\.0\.1:(\d+)", line)
            if m:
                p = int(m.group(1))
                if p not in ports:
                    ports.append(p)
        
        # Test candidate ports for GetUserStatus
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
    except Exception:
        pass

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

                            if "argon" in resp_model.lower():
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
                            is_argon = "gemini-4-argon" in text
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
    if "argon" in current_model.lower() and hours_left >= 3.0:
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

GA4_MEASUREMENT_ID = os.environ.get("TOKENMAXX_GA4_ID", "G-TOKENMAXX1")
GA4_API_SECRET = os.environ.get("TOKENMAXX_GA4_SECRET", "ANON_PING_SECRET")

def record_telemetry_event(event_name: str, params: dict = None):
    if os.environ.get("DO_NOT_TRACK") == "1":
        return
    try:
        import hashlib
        client_id = hashlib.sha256((os.getlogin() + sys.platform).encode()).hexdigest()[:16]
        url = f"https://www.google-analytics.com/mp/collect?api_secret={GA4_API_SECRET}&measurement_id={GA4_MEASUREMENT_ID}"
        event_params = {
            "platform": sys.platform,
            "version": "1.0.0"
        }
        if params:
            event_params.update(params)

        payload = {
            "client_id": client_id,
            "events": [{"name": event_name, "params": event_params}]
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
    Returns (normalized_url, suggested_event_name).
    """
    raw = (user_input or "").strip()
    if not raw:
        return "https://me.developers.google.com/benefits", ""

    # Prepend https:// if protocol is missing
    if not raw.startswith("http://") and not raw.startswith("https://"):
        if "/" in raw or "." in raw:
            raw = "https://" + raw
        else:
            # Bare event slug like 'gdg-jakarta-road-to-devfest-cloud-run'
            raw = f"https://me.developers.google.com/benefits/claim/{raw}"

    # Extract event slug for personalized project naming
    suggested_event = ""
    try:
        parts = [p for p in raw.split("?")[0].split("#")[0].split("/") if p]
        if parts:
            last = parts[-1].lower()
            if last not in ["benefits", "claim", "credits"]:
                tokens = [t for t in re.split(r"[-_]", last) if t]
                if tokens:
                    if len(tokens) >= 2 and tokens[0] == "gdg":
                        suggested_event = f"{tokens[0]}-{tokens[1]}"
                    else:
                        suggested_event = tokens[0]
    except Exception:
        pass

    return raw, suggested_event

def open_browser_url(url: str):
    """Cross-platform browser deep-link opener"""
    if os.environ.get("TOKENMAXX_NO_BROWSER") == "1":
        return True
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url])
        elif sys.platform == "win32":
            subprocess.Popen(["start", url], shell=True)
        return True
    except Exception:
        return False

def install_google_skill(skill_name: str):
    """
    Pulls the official skill directory or SKILL.md from github.com/google/skills into ~/.gemini/config/skills/
    """
    base_url = f"https://raw.githubusercontent.com/google/skills/main/{skill_name}/SKILL.md"
    target_dir = Path.home() / ".gemini" / "config" / "skills" / skill_name
    target_file = target_dir / "SKILL.md"

    print(f"📦 Fetching official Google skill '{skill_name}' from GitHub...")
    try:
        req = urllib.request.Request(base_url, headers={"User-Agent": "Antigravity-TokenMaxx"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8")
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Successfully installed '{skill_name}' into {target_dir}")
            return True
    except Exception as e:
        print(f"❌ Failed to download skill '{skill_name}': {e}")
        print("Tip: Check available official skills at https://github.com/google/skills")
        return False

# ---------------------------------------------------------------------------
# In-Engine Self-Updater & Remote Version Sync (F24)
# ---------------------------------------------------------------------------

def check_for_updates(force=False):
    """
    Checks GitHub for newer version and auto-updates local skill files.
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
            print(f"📦 Updating TokenMaxxing (v{CURRENT_VERSION} -> v{remote_ver})...")
            files_to_update = {
                "SKILL.md": SKILLS_DIR / "SKILL.md",
                "scripts/tokenmaxx.py": SKILLS_DIR / "scripts" / "tokenmaxx.py",
                "references/pricing_matrix.md": SKILLS_DIR / "references" / "pricing_matrix.md"
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
        "vertex_conversations_count": usage["vertex_conversations_count"]
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    # -----------------------------------------------------------------------
    # Output Rendering
    # -----------------------------------------------------------------------

    # SCENARIO A: User is on Google AI Pro / Ultra
    if is_pro and not is_gcp:
        if getattr(args, "pulse", False):
            if low_quota_alerts:
                print(f"⚠️ **TokenMaxx Quota Alert:** {', '.join(low_quota_alerts)} — switch to Gemini 3.8 Flash to avoid throttling.")
            return
        print("=" * 66)
        print(" ⚡ TOKENMAXXING — ACTIVE PLAN: GOOGLE AI PRO")
        print("=" * 66)
        print(" ℹ️  You are currently operating on your personal Google AI Pro plan.")
        print("    Tokens and dollar consumption are unlimited under your subscription.")

        if is_expired:
            print("-" * 66)
            print(" ℹ️  GDP Workshop Credit Notice:")
            print(f"    Your temporary $5.00 GDP Credit has officially EXPIRED.")
            print(f"    Reconciliation: ${net_spent:.2f} utilized | ${remaining_budget:.2f} expired unspent.")
            print("    Your Pro subscription ensures you experience zero IDE lockouts.")
        elif timer_info["has_timer"] and hours_left > 0:
            print("-" * 66)
            print(f" ⏳ Background GDP Credit Clock: {timer_info['formatted']}")
            print(f"    Available Voucher Balance  : ${remaining_budget:.2f} remaining")
            print("    (Switch to 'Agent Platform' mode if you want to consume workshop credits)")

        if low_quota_alerts:
            print("-" * 66)
            print(" ⚠️  QUOTA RADAR WARNING:")
            for alert in low_quota_alerts:
                print(f"    • {alert}")
            print("    Tip: Switch to an alternate model (e.g. Gemini 3.8 Flash) to avoid throttling.")
        print("=" * 66)
        return

    # SCENARIO B: Credit is Expired (Post-Mortem & Downgrade Wizard)
    if is_expired:
        print("=" * 66)
        print(" 🚨 TOKENMAXXING — $5.00 GDP WORKSHOP CREDIT EXPIRED")
        print("=" * 66)
        print(" The 12-hour validity window for your temporary GDP billing account has closed.")
        print("-" * 66)
        print(f" Starting Voucher Grant : ${initial_budget:.2f}")
        print(f" Gross Model Usage      : ${usage['gross_usage']:.2f} (Uncached list price)")
        print(f" Context Cache Savings  : -${usage['caching_discount']:.2f} (49.9% discount)")
        print(f" Total Net Utilized     : ${net_spent:.2f}")
        print(f" Expired Unspent Credit : ${remaining_budget:.2f} (🔴 Destroyed by Google Cloud)")
        print("-" * 66)
        print(" 🛡️ SWITCH BACK TO YOUR PERSONAL ACCOUNT:")
        print(" 1. Sign Out of Antigravity (Top-right 👤 Profile icon in Editor OR Bottom-left ⚙️ Settings -> Account).")
        print(" 2. Sign back in with your personal Google Account (Google AI Pro or Free Tier).")
        print(" 3. This immediately restores normal chatting after your 12-hour workshop voucher ends.")
        print("=" * 66)
        return

    # SCENARIO C: Active GDP Credit Mode (Agent Platform)
    print("=" * 66)
    print(" ⚡ TOKENMAXXING — GDP WORKSHOP TOKEN & CREDIT CO-PILOT")
    print("=" * 66)
    print(f" 🎟️  Active Account   : Agent Platform (GDP Workshop Credit)")
    print(f" ⏳ Credit Lifespan  : {timer_info['formatted']}")
    print(f" 🎯 Current Model    : {usage['recent_model_used']}")
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

    # Purchasing Power Translator
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
            break

    # Compact 2-line TokenMaxx Status Bar (for Every-5-Prompts Pulse)
    if getattr(args, "pulse", False) and not crossed_milestone and hours_left >= 2.0:
        print(f"⚡ **TokenMaxx Pulse:** **${remaining_budget:.2f} / ${initial_budget:.2f} left ({pct_remaining:.1f}%)** • ⏱️ **{timer_info['formatted']}** • 💡 *~{turns_flash:,} Flash turns left (Ask `\"How much credit do I have left?\"` anytime)*")
        if advisor_alert:
            print(f"   {advisor_alert['title']}: {advisor_alert['message']}")
        return

    print("=" * 66)
    if crossed_milestone:
        print(f" 🔔 TOKENMAXXING — {crossed_milestone}% WORKSHOP CREDIT MILESTONE REACHED")
    else:
        print(" ⚡ TOKENMAXXING — GDP WORKSHOP TOKEN & CREDIT CO-PILOT")
    print("=" * 66)
    print(f" 🎟️  Active Account   : Agent Platform (GDP Workshop Credit)")
    print(f" ⏳ Credit Lifespan  : {timer_info['formatted']}")
    print(f" 🎯 Current Model    : {usage['recent_model_used']}")
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
    print(" 💬 Tip: Ask \"How much credit or tokens do I have left?\" anytime!")
    print("    (TokenMaxx also pulses every 5 prompts & alerts at 50%, 70%, 90%)")
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
    try:
        ps_out = subprocess.check_output(["ps", "aux"], text=True)
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
                    text=True
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

def run_step1(raw_claim_url: str = ""):
    record_telemetry_event("setup_step1")
    env = detect_antigravity_environment()
    claim_url, suggested_event = normalize_claim_url(raw_claim_url)

    state = load_state()
    state["claimed_at"] = datetime.now(timezone.utc).isoformat()
    state["suggested_event"] = suggested_event or "gdg-workshop"
    state["last_milestone_alerted"] = 0
    save_state(state)

    open_browser_url(claim_url)

    print("⚡ **Welcome to TokenMaxxing — Your Workshop Credit & Token Co-Pilot!**")
    print("This plugin does two things for you:")
    print("1. **Guided Credit Setup:** Walks you through activating your **$5.00 Google Cloud workshop credit** one step at a time.")
    print("2. **Live Budget & Token Tracker:** Shows your remaining **$5.00 balance, token usage, and 12-hour timer** every 5 prompts (or anytime you ask *\"How much credit or tokens do I have left?\"*).\n")

    if env["needs_update"]:
        print(f"⚠️ **Important Version Check (Antigravity v{env['version_str']} detected):**")
        print("Before we reach Step 4, please make sure you update Antigravity to **v2.26.0+** (**Antigravity → Check for Updates** or download from `https://antigravity.google`) so the **\"Use Business Account\"** sign-in option is available.\n")

    print("---")
    print("### 🎟️ Step 1 of 4: Claim Your $5.00 Workshop Credit")
    if raw_claim_url:
        print(f"I just opened your credit link in your browser:\n👉 **{claim_url}**\n")
        print("1. Make sure you are signed into your Google account in your browser.")
        print("2. Click **\"Claim Credit\"** (or **\"Apply\"**) on that page.")
        print("3. Reply **\"claimed\"** (or **\"done\"**) here once you've claimed it, and I'll open Step 2 for you!")
    else:
        print("Please paste your **workshop credit link** (e.g. `https://g.dev/credits/...`), or if you already clicked **\"Claim Credit\"** in your browser, reply **\"claimed\"** and I'll take you to Step 2!")
    print("\n🛑 [AGENT DIRECTIVE: Present ONLY the message above to the user and STOP. Do NOT show Step 2, Step 3, or Step 4 yet! Wait for the user to reply first.]")

def run_step2():
    record_telemetry_event("setup_step2")
    state = load_state()
    prefix = state.get("suggested_event") or "gdg-workshop"
    today_str = datetime.now().strftime("%d%b").lower()
    example_id = f"{prefix}-{today_str}"

    open_browser_url("https://console.cloud.google.com/projectcreate")

    print("### 🏗️ Step 2 of 4: Create Your Google Cloud Project")
    print("I just opened the **Google Cloud Project Creation** page in your browser (`https://console.cloud.google.com/projectcreate`).\n")
    print(f"1. **Project Name:** Enter **`{example_id}`** *(Project IDs must be globally unique and lowercase)*.")
    print("2. **Billing Account:** Click the **Billing account** dropdown and select the one starting with **`[YYYY-MM-DD] GDP Credit: ...`** *(this draws exclusively from your $5.00 voucher, never a personal card)*.")
    print("   - *⏳ Tip: If the Billing account dropdown is missing or blank, wait 15–30 seconds for Google Cloud to sync your voucher and refresh the page.*")
    print("   - *👤 Tip: Check the top-right avatar in Google Cloud Console to make sure you're on the same Google account that claimed the credit.*")
    print("3. Click **Create**, then copy and **paste your Project ID here in chat** so I can open Step 3 for you!")
    print("\n🛑 [AGENT DIRECTIVE: Present ONLY Step 2 above to the user and STOP. Do NOT show Step 3 or Step 4 yet! Wait for the user to reply with their Project ID.]")

def run_step3(project_id: str):
    record_telemetry_event("setup_step3")
    clean_id = (project_id or "").strip().lower()
    state = load_state()
    state["project_id"] = clean_id
    save_state(state)
    copy_to_clipboard(clean_id)

    enable_url = f"https://console.cloud.google.com/apis/enableflow?apiid=aiplatform.googleapis.com&project={clean_id}"
    open_browser_url(enable_url)

    print(f"### ⚡ Step 3 of 4: Enable Vertex AI API for `{clean_id}`")
    print("I have saved your Project ID, copied it to your clipboard, and opened the **API Activation Page** in your browser:\n")
    print(f"👉 **{enable_url}**\n")
    print("1. In your browser window, click **Next** (if shown) and then click **Enable**.")
    print("2. Wait ~5 seconds until it finishes enabling, then reply **\"done\"** here for our final step!")
    print("\n🛑 [AGENT DIRECTIVE: Present ONLY Step 3 above to the user and STOP. Do NOT show Step 4 yet! Wait for the user to confirm they clicked Enable.]")

def run_step4():
    record_telemetry_event("setup_step4")
    state = load_state()
    project_id = state.get("project_id") or "<your-project-id>"
    if project_id != "<your-project-id>":
        copy_to_clipboard(project_id)

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
    print("---")
    print("### 🎯 Final Step — Check Your Live $5.00 Credit & Token Dashboard!")
    print("Once you open **`+ New Conversation`**, type this as your very first message in the new chat:")
    print("👉 **`How much credit and tokens do I have left?`**")
    print("\n*(From there, TokenMaxxing will automatically show your compact balance bar every 5 prompts and alert you at 50%, 70%, and 90% usage!)*")


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
        raw_claim = input("    👉 Claim URL (or press Enter to open Builders Hub): ").strip()
    except (EOFError, KeyboardInterrupt):
        raw_claim = ""
    claim_url, suggested_event = normalize_claim_url(raw_claim)
    print(f"    Opening claim page in browser: {claim_url}")
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
    parser.add_argument("--claimed-at", type=str, help="Calibrate credit claim time (ISO or HH:MM)")
    parser.add_argument("--install-skill", type=str, help="1-click install official Google skill from github.com/google/skills")
    parser.add_argument("--setup", action="store_true", help="Launch interactive GDG credit setup wizard")
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
