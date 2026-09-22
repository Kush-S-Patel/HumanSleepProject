"""Minimal clinical report export helpers (JSON / BIDS TSV / printable PDF)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional


def study_export_json(
    *,
    meta: dict,
    metrics: dict,
    summary: dict,
    hypnogram: Optional[dict],
    events: Optional[dict],
    provenance: Optional[dict] = None,
    comparison: Optional[dict] = None,
) -> dict:
    return {
        "schema": "hsp-lab.study.v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "metrics": metrics,
        "summary": summary,
        "hypnogram": hypnogram,
        "events": (events or {}).get("events", events),
        "provenance": provenance or (meta or {}).get("provenance"),
        "comparison": comparison,
    }


def events_to_bids_tsv(events: list[dict], hypnogram: Optional[dict] = None) -> str:
    """BIDS-Events-like TSV: onset, duration, trial_type, value, spo2_nadir."""
    lines = ["onset\tduration\ttrial_type\tvalue\tspo2_nadir"]
    for e in events:
        nadir = e.get("nadir_spo2")
        nadir_s = "" if nadir is None else str(nadir)
        lines.append(
            f"{e.get('onset_sec', 0):.3f}\t"
            f"{e.get('duration_sec', 0):.3f}\t"
            f"{e.get('category', '')}\t"
            f"{e.get('subtype', '')}\t"
            f"{nadir_s}"
        )
    if hypnogram and hypnogram.get("stages"):
        epoch = float(hypnogram.get("epoch_length_sec") or 30.0)
        for i, st in enumerate(hypnogram["stages"]):
            if st in (None, "", "?"):
                continue
            lines.append(f"{i * epoch:.3f}\t{epoch:.3f}\tsleep_stage\t{st}\t")
    return "\n".join(lines) + "\n"


def clinician_report_html(
    *,
    meta: dict,
    metrics: dict,
    summary: dict,
    comparison: Optional[dict] = None,
) -> str:
    """Printable HTML clinical summary (browser → Save as PDF)."""
    name = meta.get("display_name") or meta.get("uid") or "Study"
    findings = "".join(
        f"<li><strong>{f.get('title','')}</strong> — {f.get('detail','')}</li>"
        for f in (summary.get("findings") or [])
    )
    caveats = "".join(f"<li>{c}</li>" for c in (summary.get("caveats") or []))
    cmp_block = ""
    if comparison:
        rows = "".join(
            f"<tr><td>{k}</td><td>{_cell(comparison.get('human', {}).get(k))}</td>"
            f"<td>{_cell(comparison.get('ai', {}).get(k))}</td></tr>"
            for k in ("ahi", "rdi", "arousal_index", "spo2_nadir", "odi", "total_sleep_time_min")
            if comparison.get("human", {}).get(k) is not None
            or comparison.get("ai", {}).get(k) is not None
        )
        cmp_block = f"""
        <h2>AI vs human</h2>
        <table><thead><tr><th>Metric</th><th>Human</th><th>AI (CAISR)</th></tr></thead>
        <tbody>{rows}</tbody></table>
        """
    prov = meta.get("provenance") or {}
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>HSP Lab report — {name}</title>
<style>
  body {{ font-family: Georgia, serif; color: #0f1720; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
  .meta {{ color: #5a6b7c; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #d7dde5; }}
  .sev {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }}
  @media print {{ body {{ margin: 0; }} }}
</style></head><body>
  <h1>{name}</h1>
  <div class="meta">{meta.get("uid")} · {meta.get("cohort")} · {meta.get("annotation_source")}
  · exported {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</div>
  <p class="sev">{summary.get("overall_severity", "unknown")} overall · OSA {summary.get("osa_severity", "unknown")}</p>
  <p>{summary.get("headline", "")}</p>
  <h2>Key metrics</h2>
  <table>
    <tr><th>AHI</th><td>{_cell(metrics.get("ahi"))} /h</td></tr>
    <tr><th>RDI</th><td>{_cell(metrics.get("rdi"))} /h</td></tr>
    <tr><th>Arousal index</th><td>{_cell(metrics.get("arousal_index"))} /h</td></tr>
    <tr><th>SpO₂ nadir</th><td>{_cell(metrics.get("spo2_nadir"))} %</td></tr>
    <tr><th>ODI</th><td>{_cell(metrics.get("odi"))} /h</td></tr>
    <tr><th>Total sleep</th><td>{_cell(metrics.get("total_sleep_time_min"))} min</td></tr>
    <tr><th>Efficiency</th><td>{_cell(metrics.get("sleep_efficiency_pct"))} %</td></tr>
  </table>
  <h2>Findings</h2>
  <ul>{findings or "<li>None recorded</li>"}</ul>
  {cmp_block}
  <h2>Caveats</h2>
  <ul>{caveats or "<li>Research / decision-support only — not a clinical diagnosis.</li>"}</ul>
  <h2>Provenance</h2>
  <pre style="font-size:0.75rem;white-space:pre-wrap;background:#f4f6f8;padding:0.75rem;">{json.dumps(prov, indent=2)}</pre>
  <p style="font-size:0.75rem;color:#7a8b9a">{summary.get("disclaimer", "")}</p>
</body></html>"""


def _cell(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def clinician_report_pdf(
    *,
    meta: dict,
    metrics: dict,
    summary: dict,
) -> bytes:
    """Tiny single-page PDF (Helvetica) for download without extra deps."""
    name = str(meta.get("display_name") or meta.get("uid") or "Study")[:60]
    lines = [
        "HSP Lab — Clinical summary (research)",
        name,
        f"UID: {meta.get('uid')}  |  Source: {meta.get('annotation_source')}",
        f"Severity: {summary.get('overall_severity')}  OSA: {summary.get('osa_severity')}",
        "",
        str(summary.get("headline") or "")[:90],
        "",
        f"AHI {_cell(metrics.get('ahi'))}/h   RDI {_cell(metrics.get('rdi'))}/h   ArI {_cell(metrics.get('arousal_index'))}/h",
        f"SpO2 nadir {_cell(metrics.get('spo2_nadir'))}%   ODI {_cell(metrics.get('odi'))}/h",
        f"TST {_cell(metrics.get('total_sleep_time_min'))} min   Eff {_cell(metrics.get('sleep_efficiency_pct'))}%",
        "",
        "Not a clinical diagnosis. Review against the raw PSG before use.",
    ]
    # Escape PDF string specials
    safe = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in lines]
    content_lines = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    first = True
    for ln in safe:
        if first:
            content_lines.append(f"({ln}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({ln}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "replace")

    objs: list[bytes] = []
    objs.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objs.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objs.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objs.append(b"4 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream\nendobj\n")
    objs.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(out))
        out += obj
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
