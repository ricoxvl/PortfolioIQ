"""Phase 11: account-scoped, downloadable financial reports.

Reports use current server-computed portfolio facts. No missing prices, periods,
benchmark values or investment performance are inferred. Source and methodology
warnings travel with the output. CSV protects text against spreadsheet formulas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
import csv
import math
import re
import unicodedata

from reportlab.lib.colors import HexColor, Color
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _safety(value: object) -> str:
    """Keep untrusted CSV text as text, never as formulas or control characters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return str(value) if math.isfinite(float(value)) else ""
        return str(value)
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    if clean.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + clean
    return clean


def _csv(columns: list[str], rows: list[list[object]]) -> bytes:
    out = StringIO(newline="")
    writer = csv.writer(out,lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_safety(value) for value in row])
    # UTF-8 BOM helps MS Excel detect this is a Unicode text export.
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def report_context(dashboard: dict, *, now: datetime | None = None) -> dict:
    generated = now or datetime.now(timezone.utc)
    portfolio = dashboard["portfolio"]
    summary = dashboard["summary"]
    hist = dashboard.get("history") or []
    valuation_date = summary.get("valuation_date") or (hist[-1]["date"] if hist else None)
    if portfolio.get("is_demo"):
        type_label = "FICTIONAL / SYNTHETIC DEMONSTRATION"
    elif portfolio.get("ledger_enabled"):
        type_label = "USER-IMPORTED DATED TRANSACTION LEDGER"
    else:
        type_label = "USER-IMPORTED HOLDINGS SNAPSHOT"
    return {
        "portfolio_id": portfolio["id"],
        "portfolio_name": portfolio["name"],
        "generated_at_utc": generated.astimezone(timezone.utc).isoformat(),
        "valuation_date": valuation_date,
        "data_classification": type_label,
        "summary": summary,
        "holdings": dashboard.get("holdings") or [],
        "history": hist,
        "source_notice": dashboard.get("data_notice") or "No source provided.",
        "methodology": dashboard.get("methodology") or {},
        "price_quality": dashboard.get("price_quality"),
        "attribution": dashboard.get("attribution"),
        "risk": dashboard.get("risk"),
    }


def holdings_csv(ctx: dict) -> bytes:
    rows = []
    for h in ctx["holdings"]:
        rows.append([
            h.get("symbol"), h.get("name"), h.get("asset_class"),
            h.get("sector"), h.get("quantity"), h.get("avg_cost"),
            h.get("current_price"), h.get("value"), h.get("weight"),
            h.get("unrealized_pl"), h.get("price_asof"),
            h.get("price_source"), ctx["data_classification"],ctx["valuation_date"],
        ])
    return _csv(
        ["symbol","name","asset_class","sector","quantity","average_cost_usd",
         "current_reference_price_usd","position_value_usd","weight_pct",
         "unrealized_pl_usd","price_date","price_source","data_classification","valuation_date"],
        rows,
    )


def performance_csv(ctx: dict) -> bytes | None:
    hist = ctx["history"]
    if not hist:
        return None
    rows = []
    for h in hist:
        rows.append([
            h.get("date"), h.get("value"), h.get("unit_nav"),
            h.get("external_flow"), h.get("benchmark"),
            ctx["data_classification"],
        ])
    return _csv(
        ["date","portfolio_value_usd","flow_adjusted_unit_nav","net_external_cash_flow_usd",
         "benchmark_reference_value","data_classification"],rows,
    )


def _printable(value: object, maxlen: int = 160) -> str:
    if value is None:
        return "Unavailable"
    text = unicodedata.normalize("NFKD",str(value))
    text = text.encode("ascii",errors="ignore").decode("ascii")
    text = re.sub(r"[\x00-\x1f\x7f]+"," ",text).strip()
    return text[:maxlen] or "Unavailable"


def _value(value: object, prefix: str = "", suffix: str = "") -> str:
    if value is None:
        return "Unavailable"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "Unavailable"
    if not math.isfinite(v):
        return "Unavailable"
    return f"{prefix}{v:,.2f}{suffix}"


def _lines(text: object, width: int = 90) -> list[str]:
    words = _printable(text,maxlen=600).split()
    out = []
    line = ""
    for word in words:
        test = (line+" "+word).strip()
        if len(test)>width and line:
            out.append(line)
            line=word
        else:
            line=test
    if line:
        out.append(line)
    return out or ["Unavailable"]


def portfolio_pdf(ctx: dict) -> bytes:
    """Create a clean bounded report. All facts come from the existing dashboard."""
    out = BytesIO()
    document=canvas.Canvas(out,pagesize=letter,pageCompression=1)
    document.setTitle("PortfolioIQ | Portfolio Research Report")
    document.setAuthor("PortfolioIQ | Research prototype")
    W,H=letter
    ink=HexColor("#142C35")
    teal=HexColor("#17685D")
    faded=HexColor("#657C84")
    green=HexColor("#D9ECE5")
    light=HexColor("#F2F7F5")
    y=H-112
    page=0

    def header():
        nonlocal y,page
        page+=1
        document.setFillColor(ink)
        document.rect(0,H-86,W,86,fill=1,stroke=0)
        document.setFillColor(HexColor("#DFF5E9"))
        document.setFont("Helvetica-Bold",18)
        document.drawString(40,H-45,"portfolioIQ")
        document.setFillColor(HexColor("#B3D4D1"))
        document.setFont("Helvetica",9)
        document.drawString(40,H-64,"ACCOUNT-SCOPED RESEARCH REPORT  |  EDUCATIONAL ONLY")
        document.setFillColor(faded)
        document.setFont("Helvetica",8)
        document.drawRightString(W-40,25,f"Page {page}  |  not investment advice")
        document.setStrokeColor(HexColor("#D5E3DF"))
        document.line(40,37,W-40,37)
        y=H-116

    def require(height: float):
        nonlocal y
        if y-height<62:
            document.showPage()
            header()

    def heading(title: str):
        nonlocal y
        require(30)
        document.setFillColor(teal)
        document.setFont("Helvetica-Bold",10)
        document.drawString(40,y,_printable(title,90).upper())
        y-=19

    def line(label: str, text: str):
        nonlocal y
        require(23)
        document.setFont("Helvetica",9)
        document.setFillColor(faded)
        document.drawString(40,y,_printable(label,36))
        document.setFont("Helvetica-Bold",9)
        document.setFillColor(ink)
        document.drawRightString(W-40,y,_printable(text,90))
        y-=21

    def note(text: str, *, label: str | None = None):
        nonlocal y
        if label:
            heading(label)
        wrapped=_lines(text,94)
        for l in wrapped[:10]:
            require(14)
            document.setFillColor(ink)
            document.setFont("Helvetica",8.4)
            document.drawString(40,y,l)
            y-=13
        y-=8

    header()
    heading("Portfolio snapshot")
    line("Name",ctx["portfolio_name"])
    line("Classification",ctx["data_classification"])
    line("Valuation date",ctx["valuation_date"] or "Unavailable / no history")
    line("Generated (UTC)",ctx["generated_at_utc"])
    document.setFillColor(light)
    document.roundRect(40,y-116,W-80,122,10,fill=1,stroke=0)
    document.setFillColor(ink)
    document.setFont("Helvetica-Bold",12)
    document.drawString(56,y-22,"Current computed summary")
    summary=ctx["summary"]
    metrics=[
        ("Portfolio value",_value(summary.get("total_value"),"$")),
        ("Reported period return",_value(summary.get("period_return"),suffix="%")),
        ("Unrealized gain/loss",_value(summary.get("unrealized_pl"),"$")),
        ("Top-three weight",_value(summary.get("top_3_concentration"),suffix="%")),
    ]
    for i,(label,value) in enumerate(metrics):
        x=56+(i%2)*255
        yy=y-45-(i//2)*44
        document.setFillColor(faded)
        document.setFont("Helvetica",8)
        document.drawString(x,yy,label)
        document.setFillColor(ink)
        document.setFont("Helvetica-Bold",13)
        document.drawString(x,yy-18,value)
    y-=148
    heading("Current holdings - shown values are not trade quotes")
    if not ctx["holdings"]:
        note("No current holdings on record. Cash-only positions may still have portfolio value.")
    else:
        headers=(40,115,255,345,427)
        def table_header():
            nonlocal y
            require(24)
            document.setFillColor(green)
            document.rect(40,y-6,W-80,22,fill=1,stroke=0)
            document.setFont("Helvetica-Bold",8)
            document.setFillColor(ink)
            for x,t in zip(headers,("Ticker","Security","Sector","Value","Weight")):
                document.drawString(x,y+2,t)
            y-=24
        table_header()
        for index,h in enumerate(ctx["holdings"]):
            if y<73:
                document.showPage();header();heading("Holdings (continued)");table_header()
            if index%2==0:
                document.setFillColor(light)
                document.rect(40,y-7,W-80,19,fill=1,stroke=0)
            vals=(
                _printable(h.get("symbol"),11),
                _printable(h.get("name"),22),
                _printable(h.get("sector"),14),
                _value(h.get("value"),"$"),
                _value(h.get("weight"),suffix="%"),
            )
            document.setFont("Helvetica",8)
            document.setFillColor(ink)
            for x,t in zip(headers,vals):
                document.drawString(x,y,t)
            y-=20
        y-=13
    note(ctx["source_notice"],label="Data provenance and quality")
    if ctx.get("price_quality"):
        q=ctx["price_quality"]
        note("Historical price coverage: "+("complete on observed valuation dates" if q.get("complete") else "incomplete; investment calculations may be unavailable")+". First incomplete date: "+str(q.get("first_incomplete_date") or "none identified")+".")
    method=ctx["methodology"]
    for key in ("return","risk","pricing"):
        if method.get(key):
            note(method[key],label=key+" methodology")
    note(
        "Generated from account-owned computed data at the time of export. "
        "The report does not certify source prices, completeness of corporate "
        "actions, benchmark licensing, performance forecasts, or investment suitability. "
        "Synthetic demo figures are fictional. No brokerage orders are placed.",
        label="Important limitations",
    )
    document.save()
    return out.getvalue()
