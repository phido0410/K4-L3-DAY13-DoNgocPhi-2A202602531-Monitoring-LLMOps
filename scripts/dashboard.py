"""Dashboard 6 panel dựng từ data/logs.jsonl theo contract config/dashboard.yaml.

Chạy: streamlit run scripts/dashboard.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.metrics import percentile

CONFIG = yaml.safe_load((REPO_ROOT / "config" / "dashboard.yaml").read_text(encoding="utf-8"))["dashboard"]
PANELS = {panel["id"]: panel for panel in CONFIG["panels"]}
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"

# Categorical slots theo thứ tự cố định (blue, orange, aqua, yellow); threshold dùng màu trung tính
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
THRESHOLD_COLOR = "#8a8984"


def load_logs(window_start: datetime) -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame()
    rows = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df[df["ts"] >= window_start].copy()
    df["minute"] = df["ts"].dt.floor("1min")
    return df


def threshold_ok(panel: dict, value: float) -> bool:
    threshold = panel["threshold"]
    return value <= threshold["value"] if threshold["operator"] == "lte" else value >= threshold["value"]


def threshold_tile(panel: dict, label: str, value: float, fmt: str) -> None:
    threshold = panel["threshold"]
    op = "≤" if threshold["operator"] == "lte" else "≥"
    status = "✅ Đạt" if threshold_ok(panel, value) else "🔴 Vi phạm"
    st.metric(label, fmt.format(value))
    st.caption(f"{status} · threshold {threshold['aggregation']} {op} {threshold['value']}")


def line_chart(data: pd.DataFrame, panel: dict, y_title: str, x_domain: list, mark: str = "line") -> alt.Chart:
    series = list(dict.fromkeys(data["series"]))
    color = alt.Color(
        "series:N",
        scale=alt.Scale(domain=series, range=SERIES_COLORS[: len(series)]),
        legend=alt.Legend(title=None, orient="top"),
    )
    x = alt.X(
        "minute:T",
        title="Thời gian (bucket 1 phút, giờ địa phương)",
        scale=alt.Scale(domain=x_domain),
        axis=alt.Axis(format="%H:%M"),
    )
    tooltip = [
        alt.Tooltip("minute:T", title="Phút", format="%H:%M"),
        alt.Tooltip("series:N", title="Series"),
        alt.Tooltip("value:Q", title=y_title, format=",.4~f"),
    ]
    base = alt.Chart(data)
    if mark == "bar":
        chart = base.mark_bar(size=10, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
    else:
        chart = base.mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=64, filled=True))
    # detail=segment: không nối line qua các phút không có dữ liệu
    chart = chart.encode(
        x=x, y=alt.Y("value:Q", title=y_title), color=color, detail="segment:N", tooltip=tooltip
    )

    threshold = panel["threshold"]
    op = "≤" if threshold["operator"] == "lte" else "≥"
    rule_df = pd.DataFrame(
        {"value": [threshold["value"]], "label": [f"threshold {threshold['aggregation']} {op} {threshold['value']}"]}
    )
    rule = alt.Chart(rule_df).mark_rule(color=THRESHOLD_COLOR, strokeDash=[6, 4], strokeWidth=2).encode(y="value:Q")
    rule_label = alt.Chart(rule_df).mark_text(align="left", dx=4, dy=-8).encode(y="value:Q", x=alt.value(0), text="label:N")
    return (chart + rule + rule_label).properties(height=260)


def per_minute(df: pd.DataFrame, columns: dict[str, pd.Series]) -> pd.DataFrame:
    frames = []
    for name, s in columns.items():
        frame = pd.DataFrame({"minute": s.index, "series": name, "value": s.values}).sort_values("minute")
        frame["segment"] = name + (frame["minute"].diff() > pd.Timedelta(minutes=1)).cumsum().astype(str)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def render() -> None:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=CONFIG["time_range_minutes"])
    x_domain = [window_start.isoformat(), now.isoformat()]
    df = load_logs(window_start)

    st.caption(
        f"Nguồn: `data/logs.jsonl` · Time range: {CONFIG['time_range_minutes']} phút gần nhất "
        f"({window_start.astimezone():%H:%M}–{now.astimezone():%H:%M} giờ địa phương) · "
        f"Auto refresh {CONFIG['refresh_seconds']}s"
    )
    if df.empty:
        st.info("Chưa có log trong time range. Chạy API và `python scripts/load_test.py`.")
        return

    received = df[df["event"] == "request_received"]
    sent = df[df["event"] == "response_sent"]
    failed = df[df["event"] == "request_failed"]
    by_min = sent.groupby("minute")

    col1, col2 = st.columns(2)
    with col1:
        panel = PANELS["latency"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        latencies = sent["latency_ms"].dropna().astype(int).tolist()
        ttfts = sent["ttft_ms"].dropna().astype(int).tolist()
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("P50", f"{percentile(latencies, 50):.0f} ms")
        with t2:
            threshold_tile(panel, "P95", percentile(latencies, 95), "{:.0f} ms")
        t3.metric("P99", f"{percentile(latencies, 99):.0f} ms")
        t4.metric("TTFT P95", f"{percentile(ttfts, 95):.0f} ms")
        data = per_minute(sent, {
            "latency P50": by_min["latency_ms"].apply(lambda s: percentile(s.tolist(), 50)),
            "latency P95": by_min["latency_ms"].apply(lambda s: percentile(s.tolist(), 95)),
            "latency P99": by_min["latency_ms"].apply(lambda s: percentile(s.tolist(), 99)),
            "TTFT P95": by_min["ttft_ms"].apply(lambda s: percentile(s.tolist(), 95)),
        })
        st.altair_chart(line_chart(data, panel, "ms", x_domain), width="stretch")

    with col2:
        panel = PANELS["traffic"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        counts = received.groupby("minute").size()
        t1, t2 = st.columns(2)
        t1.metric("Tổng request", f"{len(received)}")
        with t2:
            threshold_tile(panel, "Request/phút (phút gần nhất)", float(counts.iloc[-1]) if len(counts) else 0.0, "{:.0f}")
        data = per_minute(received, {"requests": counts})
        st.altair_chart(line_chart(data, panel, "requests/phút", x_domain, mark="bar"), width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        panel = PANELS["errors"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        error_rate = len(failed) / len(received) * 100 if len(received) else 0.0
        tool = df[df["tool_success"].notna()] if "tool_success" in df else df.iloc[0:0]
        retrieval_success = tool["tool_success"].astype(bool).mean() * 100 if len(tool) else 100.0
        t1, t2, t3 = st.columns(3)
        with t1:
            threshold_tile(panel, "Error rate", error_rate, "{:.1f} %")
        t2.metric("Retrieval success", f"{retrieval_success:.1f} %")
        breakdown = failed["error_type"].value_counts().to_dict() if len(failed) else {}
        t3.metric("Request lỗi", f"{len(failed)}")
        t3.caption("Theo loại: " + (", ".join(f"{k} × {v}" for k, v in breakdown.items()) or "không có"))
        rec_min = received.groupby("minute").size()
        fail_min = failed.groupby("minute").size().reindex(rec_min.index, fill_value=0)
        tool_min = tool.groupby("minute")["tool_success"].apply(lambda s: s.astype(bool).mean() * 100)
        data = per_minute(df, {"error rate %": fail_min / rec_min * 100, "retrieval success %": tool_min})
        st.altair_chart(line_chart(data, panel, "%", x_domain), width="stretch")

    with col2:
        panel = PANELS["cost"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        cost_min = by_min["cost_usd"].sum()
        t1, t2 = st.columns(2)
        with t1:
            threshold_tile(panel, "Tổng cost (time range)", float(sent["cost_usd"].sum()), "${:.4f}")
        t2.metric("Cost TB / request", f"${sent['cost_usd'].mean():.5f}")
        data = per_minute(sent, {"cost / phút": cost_min, "cost lũy kế": cost_min.cumsum()})
        st.altair_chart(line_chart(data, panel, "USD", x_domain), width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        panel = PANELS["tokens"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        t1, t2 = st.columns(2)
        with t1:
            threshold_tile(panel, "Tổng input tokens", float(sent["tokens_in"].sum()), "{:,.0f}")
        with t2:
            threshold_tile(panel, "Tổng output tokens", float(sent["tokens_out"].sum()), "{:,.0f}")
        data = per_minute(sent, {
            "input tokens (lũy kế)": by_min["tokens_in"].sum().cumsum(),
            "output tokens (lũy kế)": by_min["tokens_out"].sum().cumsum(),
        })
        st.altair_chart(line_chart(data, panel, "tokens", x_domain), width="stretch")

    with col2:
        panel = PANELS["quality"]
        st.subheader(f"{panel['title']} ({panel['unit']})")
        threshold_tile(panel, "Quality score trung bình", float(sent["quality_score"].mean()), "{:.2f}")
        data = per_minute(sent, {"quality mean": by_min["quality_score"].mean()})
        st.altair_chart(line_chart(data, panel, "score 0–1", x_domain), width="stretch")


st.set_page_config(page_title=CONFIG["title"], layout="wide")
st.title(CONFIG["title"])
st.fragment(run_every=CONFIG["refresh_seconds"])(render)()
