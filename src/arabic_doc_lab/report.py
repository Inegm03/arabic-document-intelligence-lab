"""Privacy-preserving summaries and self-contained HTML experiment reports."""

from __future__ import annotations

import html
import os
import statistics
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .experiment import ExperimentRecord
from .manifest import DatasetManifest


@dataclass(frozen=True)
class Aggregate:
    """Aggregate metrics for records sharing a domain, condition, and severity."""

    domain: str
    condition: str
    severity: int
    count: int
    mean_cer: float
    mean_wer: float
    p50_latency_ms: float
    p95_latency_ms: float


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sequence."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def aggregate_records(records: Iterable[ExperimentRecord]) -> list[Aggregate]:
    """Aggregate records without retaining predictions or sample identifiers."""
    groups: dict[tuple[str, str, int], list[ExperimentRecord]] = defaultdict(list)
    for record in records:
        groups[(record.domain, record.condition, record.severity)].append(record)

    summaries = []
    for (domain, condition, severity), group in sorted(groups.items()):
        latencies = [record.latency_ms for record in group]
        summaries.append(
            Aggregate(
                domain=domain,
                condition=condition,
                severity=severity,
                count=len(group),
                mean_cer=statistics.fmean(record.cer for record in group),
                mean_wer=statistics.fmean(record.wer for record in group),
                p50_latency_ms=_percentile(latencies, 0.50),
                p95_latency_ms=_percentile(latencies, 0.95),
            )
        )
    return summaries


def _curve_svg(records: Sequence[ExperimentRecord], metric: str, label: str) -> str:
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    for record in records:
        grouped[(record.condition, record.severity)].append(getattr(record, metric))

    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    clean_values = grouped.pop(("clean", 0), [])
    for (condition, severity), values in sorted(grouped.items()):
        series[condition].append((severity, statistics.fmean(values)))
    if clean_values:
        baseline = statistics.fmean(clean_values)
        if series:
            for points in series.values():
                points.append((0, baseline))
        else:
            series["clean"].append((0, baseline))
    for points in series.values():
        points.sort()

    width, height = 720, 300
    left, right, top, bottom = 58, 20, 20, 48
    plot_width, plot_height = width - left - right, height - top - bottom
    max_severity = max((severity for points in series.values() for severity, _ in points), default=1)
    max_value = max((value for points in series.values() for _, value in points), default=1.0)
    y_max = max(1.0, max_value)
    colors = ("#38bdf8", "#f97316", "#a78bfa", "#4ade80", "#f472b6")

    def x_position(severity: int) -> float:
        return left + (severity / max(1, max_severity)) * plot_width

    def y_position(value: float) -> float:
        return top + plot_height - (value / y_max) * plot_height

    elements = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(label)}">',
        '<g class="grid">',
    ]
    for index in range(5):
        value = y_max * index / 4
        y = y_position(value)
        elements.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}"/>')
        elements.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.0%}</text>')
    for severity in range(max_severity + 1):
        x = x_position(severity)
        elements.append(
            f'<text x="{x:.1f}" y="{top+plot_height+20}" text-anchor="middle">{severity}</text>'
        )
    elements.append("</g>")

    legend = []
    for index, (condition, points) in enumerate(sorted(series.items())):
        color = colors[index % len(colors)]
        coordinates = " ".join(
            f"{x_position(severity):.1f},{y_position(value):.1f}" for severity, value in points
        )
        elements.append(
            f'<polyline points="{coordinates}" fill="none" stroke="{color}" '
            'stroke-width="3" stroke-linejoin="round"/>'
        )
        for severity, value in points:
            elements.append(
                f'<circle cx="{x_position(severity):.1f}" cy="{y_position(value):.1f}" '
                f'r="4" fill="{color}"><title>{html.escape(condition)}, severity {severity}: '
                f'{value:.2%}</title></circle>'
            )
        legend.append(
            f'<span><i style="background:{color}"></i>{html.escape(condition.replace("_", " "))}</span>'
        )
    elements.extend(
        [
            (
                f'<line class="axis" x1="{left}" y1="{top+plot_height}" '
                f'x2="{width-right}" y2="{top+plot_height}"/>'
            ),
            f'<text x="{width/2}" y="{height-10}" text-anchor="middle">Severity</text>',
            "</svg>",
            f'<div class="legend">{"".join(legend)}</div>',
        ]
    )
    return "".join(elements)


def render_html_report(
    manifest: DatasetManifest, records: Iterable[ExperimentRecord]
) -> str:
    """Render a self-contained aggregate report with no OCR text or source images."""
    record_list = list(records)
    if not record_list:
        raise ValueError("cannot render an HTML report without experiment records")
    aggregates = aggregate_records(record_list)
    sample_count = len({record.sample_id for record in record_list})
    engine_names = ", ".join(sorted({record.engine for record in record_list}))
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.domain)}</td>"
        f"<td>{html.escape(item.condition.replace('_', ' '))}</td>"
        f"<td>{item.severity}</td><td>{item.count}</td>"
        f"<td>{item.mean_cer:.2%}</td><td>{item.mean_wer:.2%}</td>"
        f"<td>{item.p50_latency_ms:.1f}</td><td>{item.p95_latency_ms:.1f}</td>"
        "</tr>"
        for item in aggregates
    )
    title = html.escape(manifest.name)
    source_url = html.escape(manifest.source_url, quote=True)
    license_url = html.escape(manifest.license_url, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — OCR robustness report</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin:0; background:#08111f; color:#e5edf7; }}
main {{ width:min(1120px, calc(100% - 32px)); margin:48px auto; }}
h1 {{ max-width:800px; font-size:clamp(2rem,5vw,4rem); line-height:1; }}
h2 {{ margin-top:40px; }} a {{ color:#7dd3fc; }}
.muted, .note {{ color:#9fb0c5; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
.card, .panel {{ background:#101c2d; border:1px solid #25334a; border-radius:14px; padding:20px; }}
.card strong {{ display:block; font-size:1.7rem; margin-top:6px; }}
.charts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr)); gap:16px; }}
svg {{ width:100%; height:auto; overflow:visible; }}
.grid line {{ stroke:#25334a; }} .grid text, svg text {{ fill:#9fb0c5; font-size:12px; }}
.axis {{ stroke:#607089; }} .legend {{ display:flex; gap:14px; flex-wrap:wrap; font-size:.85rem; }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }}
.table-wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; }}
th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #25334a; white-space:nowrap; }}
th {{ color:#9fb0c5; font-size:.8rem; text-transform:uppercase; }}
</style>
</head>
<body><main>
<p class="muted">Arabic Document Intelligence Robustness Lab</p>
<h1>{title}</h1>
<p>Aggregate OCR robustness results produced by <strong>{html.escape(engine_names)}</strong>.</p>
<div class="cards">
<div class="card">Source samples<strong>{sample_count}</strong></div>
<div class="card">Evaluations<strong>{len(record_list)}</strong></div>
<div class="card">Domains<strong>{len({record.domain for record in record_list})}</strong></div>
<div class="card">Conditions<strong>{len({record.condition for record in record_list})}</strong></div>
</div>
<h2>Severity curves</h2>
<p class="note">Lower is better. Values are arithmetic means across all evaluated samples.</p>
<div class="charts">
<section class="panel"><h3>Character error rate</h3>{_curve_svg(record_list, 'cer', 'Mean character error rate by corruption severity')}</section>
<section class="panel"><h3>Word error rate</h3>{_curve_svg(record_list, 'wer', 'Mean word error rate by corruption severity')}</section>
</div>
<h2>Detailed aggregates</h2>
<div class="panel table-wrap"><table>
<thead><tr><th>Domain</th><th>Condition</th><th>Severity</th><th>N</th><th>Mean CER</th><th>Mean WER</th><th>p50 ms</th><th>p95 ms</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<h2>Provenance and privacy</h2>
<p class="note">Dataset: <a href="{source_url}">{title}</a>. License: <a href="{license_url}">{html.escape(manifest.license_name)}</a>. This report contains aggregate metrics only—no OCR predictions, reference text, sample identifiers, or source images.</p>
</main></body></html>
"""


def write_html_report(
    output: str | Path, manifest: DatasetManifest, records: Iterable[ExperimentRecord]
) -> None:
    """Atomically write a self-contained HTML report."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_html_report(manifest, records)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
