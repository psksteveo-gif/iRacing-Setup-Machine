"""
Natural Language Telemetry Agent.

Accepts a plain-English question about the loaded session and returns a
streaming answer grounded in *actual channel data* — not just the pre-built
analysis reports.

Architecture
------------
1. The agent receives the question + a TelemetryData object.
2. It calls Claude with a set of "tools" (function declarations):
     • get_channel_stats(channel, lap)   → min/max/mean/std for a channel
     • get_channel_slice(channel, lap, start_pct, end_pct) → resampled values
     • compare_laps(channel, lap_a, lap_b) → per-zone comparison
     • list_channels()                   → available channel names
3. Claude decides which tools to call, the agent executes them locally
   against TelemetryData, and feeds the results back.
4. Final answer streams back to the caller via a Generator[str].

No data ever leaves the local machine — all tool execution happens here.
"""
from __future__ import annotations

import json
import logging
import numpy as np
from typing import Generator, Optional

from core.ibt_parser import TelemetryData
from core.analysis_engine import AnalysisReport, format_laptime

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 6   # prevent runaway loops
_AGENT_MODEL = "claude-haiku-4-5-20251001"


# ── Tool implementations ──────────────────────────────────────────────────────

def _list_channels(data: TelemetryData) -> dict:
    channels = sorted(data._channels.keys()) if hasattr(data, '_channels') else []
    return {"channels": channels, "count": len(channels)}


def _get_channel_stats(data: TelemetryData, channel: str, lap: int | None = None) -> dict:
    if not hasattr(data, '_channels') or channel not in data._channels:
        return {"error": f"Channel '{channel}' not found. Call list_channels first."}
    arr = np.asarray(data._channels[channel], dtype=float)
    if lap is not None and hasattr(data, 'lap_boundaries') and data.lap_boundaries:
        bounds = data.lap_boundaries
        if 0 <= lap < len(bounds) - 1:
            arr = arr[bounds[lap]:bounds[lap + 1]]
        elif 0 <= lap < len(bounds):
            arr = arr[bounds[lap]:]
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"error": "No valid data for that channel/lap combination."}
    return {
        "channel": channel,
        "lap": lap,
        "min": round(float(np.min(arr)), 4),
        "max": round(float(np.max(arr)), 4),
        "mean": round(float(np.mean(arr)), 4),
        "std": round(float(np.std(arr)), 4),
        "samples": len(arr),
    }


def _get_channel_slice(
    data: TelemetryData,
    channel: str,
    lap: int | None = None,
    start_pct: float = 0.0,
    end_pct: float = 1.0,
    points: int = 50,
) -> dict:
    if not hasattr(data, '_channels') or channel not in data._channels:
        return {"error": f"Channel '{channel}' not found."}
    arr = np.asarray(data._channels[channel], dtype=float)
    if lap is not None and hasattr(data, 'lap_boundaries') and data.lap_boundaries:
        bounds = data.lap_boundaries
        if 0 <= lap < len(bounds) - 1:
            arr = arr[bounds[lap]:bounds[lap + 1]]
        elif 0 <= lap < len(bounds):
            arr = arr[bounds[lap]:]
    n = len(arr)
    si = max(0, int(start_pct * n))
    ei = min(n, int(end_pct * n))
    segment = arr[si:ei]
    if len(segment) == 0:
        return {"error": "Empty segment."}
    # Downsample to `points`
    indices = np.linspace(0, len(segment) - 1, min(points, len(segment)), dtype=int)
    sampled = segment[indices]
    dist = np.linspace(start_pct, end_pct, len(sampled))
    return {
        "channel": channel,
        "lap": lap,
        "dist_pct": [round(float(d), 3) for d in dist],
        "values": [round(float(v), 4) if np.isfinite(v) else None for v in sampled],
    }


def _compare_laps(
    data: TelemetryData,
    channel: str,
    lap_a: int,
    lap_b: int,
    zones: int = 10,
) -> dict:
    """Compare channel values between two laps, split into N equal zones."""
    if not hasattr(data, '_channels') or channel not in data._channels:
        return {"error": f"Channel '{channel}' not found."}
    arr = np.asarray(data._channels[channel], dtype=float)
    bounds = getattr(data, 'lap_boundaries', [])
    results = []
    for lap_idx in (lap_a, lap_b):
        if 0 <= lap_idx < len(bounds) - 1:
            seg = arr[bounds[lap_idx]:bounds[lap_idx + 1]]
        elif 0 <= lap_idx < len(bounds):
            seg = arr[bounds[lap_idx]:]
        else:
            return {"error": f"Lap {lap_idx} out of range (0–{len(bounds)-1})."}
        zone_means = []
        zone_size = max(1, len(seg) // zones)
        for z in range(zones):
            zs = z * zone_size
            ze = zs + zone_size if z < zones - 1 else len(seg)
            chunk = seg[zs:ze]
            chunk = chunk[np.isfinite(chunk)]
            zone_means.append(round(float(np.mean(chunk)), 4) if len(chunk) else None)
        results.append(zone_means)

    zones_data = []
    for z in range(zones):
        va, vb = results[0][z], results[1][z]
        diff = round(vb - va, 4) if (va is not None and vb is not None) else None
        zones_data.append({
            "zone": z + 1,
            "dist_pct": round(z / zones, 2),
            f"lap_{lap_a}": va,
            f"lap_{lap_b}": vb,
            "diff": diff,
        })
    return {"channel": channel, "lap_a": lap_a, "lap_b": lap_b, "zones": zones_data}


def _get_lap_times(data: TelemetryData) -> dict:
    laps = []
    for i, t in enumerate(getattr(data, 'lap_times', [])):
        laps.append({"lap": i, "time_s": round(float(t), 4), "formatted": format_laptime(t)})
    return {"num_laps": len(laps), "laps": laps}


# ── Tool registry ─────────────────────────────────────────────────────────────

_TOOL_SCHEMAS = [
    {
        "name": "list_channels",
        "description": "List all available telemetry channel names in the loaded session.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_lap_times",
        "description": "Return all lap times for the session with lap index, seconds, and formatted string.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_channel_stats",
        "description": (
            "Return statistical summary (min, max, mean, std) for a telemetry channel. "
            "Optionally scoped to a specific lap index."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name (e.g. 'Speed', 'Throttle', 'BrakeRaw')"},
                "lap": {"type": "integer", "description": "Lap index (0-based). Omit for whole session."},
            },
            "required": ["channel"],
        },
    },
    {
        "name": "get_channel_slice",
        "description": (
            "Return resampled channel values between start_pct and end_pct of a lap "
            "(0.0=lap start, 1.0=lap end). Returns dist_pct + values arrays."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "lap": {"type": "integer"},
                "start_pct": {"type": "number", "description": "0.0–1.0"},
                "end_pct": {"type": "number", "description": "0.0–1.0"},
                "points": {"type": "integer", "description": "Number of output points (default 50)"},
            },
            "required": ["channel"],
        },
    },
    {
        "name": "compare_laps",
        "description": (
            "Compare a channel between two laps split into equal zones. "
            "Returns per-zone values and difference."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "lap_a": {"type": "integer"},
                "lap_b": {"type": "integer"},
                "zones": {"type": "integer", "description": "Number of zones (default 10)"},
            },
            "required": ["channel", "lap_a", "lap_b"],
        },
    },
]


def _dispatch_tool(name: str, tool_input: dict, data: TelemetryData) -> str:
    try:
        if name == "list_channels":
            result = _list_channels(data)
        elif name == "get_lap_times":
            result = _get_lap_times(data)
        elif name == "get_channel_stats":
            result = _get_channel_stats(data, **tool_input)
        elif name == "get_channel_slice":
            result = _get_channel_slice(data, **tool_input)
        elif name == "compare_laps":
            result = _compare_laps(data, **tool_input)
        else:
            result = {"error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = {"error": str(exc)}
    return json.dumps(result)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """You are a telemetry analyst for an iRacing driver. You have access to tools \
that query the raw telemetry channels from the driver's session. Use them to answer \
questions precisely with actual data rather than generic advice.

Guidelines:
- Always call list_channels or get_lap_times first if you need orientation.
- Quote specific numbers (e.g. "your average throttle in zone 3 was 68%").
- When comparing laps, use compare_laps to get zone-by-zone breakdown.
- Keep answers concise and action-oriented — this is a real driver looking to improve.
- If a channel doesn't exist, suggest the closest likely alternative.
"""


# ── Main streaming agent ──────────────────────────────────────────────────────

def ask_telemetry_agent(
    question: str,
    data: TelemetryData,
    report: AnalysisReport,
    api_key: str,
    car_name: str = "",
    track_name: str = "",
    model: str = _AGENT_MODEL,
) -> Generator[str, None, None]:
    """
    Stream a natural-language answer to `question` grounded in telemetry data.
    Uses Claude's tool_use to call local telemetry query functions.

    Yields text chunks suitable for streaming into a CTkTextbox.
    """
    if not api_key or not api_key.strip():
        yield "Set your Anthropic API key in Settings (⚙) to use the telemetry agent."
        return

    try:
        import anthropic
    except ImportError:
        yield "Install the 'anthropic' package to use the telemetry agent."
        return

    client = anthropic.Anthropic(api_key=api_key, timeout=90.0)

    # Seed the conversation with session context
    context_msg = (
        f"Session: {car_name} at {track_name}\n"
        f"Laps: {data.num_laps}  |  Best: {format_laptime(report.best_lap)}  |  "
        f"Avg: {format_laptime(report.avg_lap)}\n\n"
        f"Driver question: {question}"
    )
    messages = [{"role": "user", "content": context_msg}]

    for _round in range(_MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=model,
            max_tokens=1200,
            system=_SYSTEM,
            tools=_TOOL_SCHEMAS,
            messages=messages,
        )

        # Collect text and tool_use blocks
        text_parts: list[str] = []
        tool_calls: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        # Stream any text the model emitted this round
        for text in text_parts:
            if text:
                yield text

        if response.stop_reason == "end_turn" or not tool_calls:
            break

        # Execute tool calls and append results
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            result_json = _dispatch_tool(tc.name, tc.input, data)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result_json,
            })

        messages.append({"role": "user", "content": tool_results})

    else:
        yield "\n\n⚠ Agent reached maximum tool-call rounds."
