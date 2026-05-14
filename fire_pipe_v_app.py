"""
Fire Pipe Velocity Checker - Streamlit App
-------------------------------------------
Checks velocities in critical fire sprinkler pipes:
    1. Main ICV (feeder)
    2. Header pipe
    3. Ranger pipe

Flow basis:
    Q_per_head = density (mm/min) x area_per_head (m2)   [L/min]
    Q_ranger   = Q_per_head x N_ranger
    Q_header   = Q_per_head x N_header
    Q_ICV      = Q_per_head x N_total + Q_hydrant

Velocity limit flagged at 6 m/s.

Author: ViKO Consulting Engineers
"""

import io
import math
from datetime import datetime

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)


# =============================================================================
# CONSTANTS
# =============================================================================
VELOCITY_LIMIT = 6.0   # m/s
APP_TITLE = "Fire Pipe Velocity Checker"
COMPANY = "ViKO Consulting Engineers"


# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================
def velocity_m_s(q_lmin, bore_mm):
    """Convert L/min and bore in mm to velocity in m/s."""
    if bore_mm <= 0:
        return float("inf")
    q_m3s = q_lmin / 60000.0
    area_m2 = math.pi / 4.0 * (bore_mm / 1000.0) ** 2
    return q_m3s / area_m2


def min_bore_mm(q_lmin, v_limit=VELOCITY_LIMIT):
    """Minimum internal bore (mm) so that velocity does not exceed v_limit."""
    if q_lmin <= 0:
        return 0.0
    q_m3s = q_lmin / 60000.0
    area_required = q_m3s / v_limit
    d_m = math.sqrt(4.0 * area_required / math.pi)
    return d_m * 1000.0


def check_pipe(label, q_lmin, bore_mm):
    """Return a dict of results for a single pipe."""
    v = velocity_m_s(q_lmin, bore_mm)
    d_min = min_bore_mm(q_lmin)
    status = "PASS" if v <= VELOCITY_LIMIT else "FAIL"
    return {
        "label": label,
        "q": q_lmin,
        "bore": bore_mm,
        "velocity": v,
        "min_bore": d_min,
        "status": status,
    }


# =============================================================================
# PDF GENERATION
# =============================================================================
def build_pdf(project, inputs, results, q_per_head, p_required):
    """Build a PDF report in memory and return the bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Fire Pipe Velocity Check",
        author=COMPANY,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Title"], fontSize=16, spaceAfter=4,
        textColor=colors.HexColor("#b00020"),
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10,
        spaceAfter=4, textColor=colors.HexColor("#333333"),
    )
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8,
                           textColor=colors.grey)

    story = []

    # ---- Header ----
    story.append(Paragraph("Fire Pipe Velocity Check", title_style))
    story.append(Paragraph(COMPANY, normal))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Velocity limit: {VELOCITY_LIMIT} m/s", small))
    story.append(Spacer(1, 6 * mm))

    # ---- Project info ----
    story.append(Paragraph("Project Information", h2))
    proj_data = [
        ["Project name", project["name"]],
        ["Project number", project["number"]],
        ["Designer", project["designer"]],
        ["Date", project["date"]],
    ]
    t = Table(proj_data, colWidths=[55 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(t)

    # ---- Design parameters ----
    story.append(Paragraph("Design Parameters", h2))
    param_data = [
        ["Sprinkler density",            f"{inputs['density']:.2f} mm/min"],
        ["Area per sprinkler",           f"{inputs['area']:.2f} m²"],
        ["K-factor (reference)",         f"{inputs['k']:.2f}"],
        ["Flow per sprinkler head",      f"{q_per_head:.2f} L/min"],
        ["Required head pressure (K)",   f"{p_required:.2f} bar"],
        ["Total operating sprinklers",   f"{inputs['n_total']}"],
        ["Max sprinklers per header",    f"{inputs['n_header']}"],
        ["Max sprinklers per ranger",    f"{inputs['n_ranger']}"],
        ["Hydrant allowance (ICV)",      f"{inputs['q_hydrant']:.2f} L/min"],
    ]
    t = Table(param_data, colWidths=[80 * mm, 85 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(t)

    # ---- Results table ----
    story.append(Paragraph("Results", h2))
    res_data = [["Pipe", "Q (L/min)", "Internal bore (mm)",
                 "Velocity (m/s)", "Min. bore (mm)", "Status"]]
    for r in results:
        res_data.append([
            r["label"],
            f"{r['q']:.2f}",
            f"{r['bore']:.2f}",
            f"{r['velocity']:.2f}",
            f"{r['min_bore']:.2f}",
            r["status"],
        ])

    t = Table(res_data, colWidths=[22 * mm, 28 * mm, 32 * mm,
                                   28 * mm, 30 * mm, 22 * mm])
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    # row colouring
    for i, r in enumerate(results, start=1):
        if r["status"] == "PASS":
            style.append(("BACKGROUND", (0, i), (-1, i),
                          colors.HexColor("#eaf7ea")))
        else:
            style.append(("BACKGROUND", (0, i), (-1, i),
                          colors.HexColor("#fdecea")))
    t.setStyle(TableStyle(style))
    story.append(t)

    # ---- Notes ----
    story.append(Spacer(1, 6 * mm))
    fails = [r for r in results if r["status"] == "FAIL"]
    if fails:
        story.append(Paragraph("Attention", h2))
        for r in fails:
            story.append(Paragraph(
                f"<b>{r['label']}</b> exceeds {VELOCITY_LIMIT} m/s. "
                f"Increase internal bore to at least "
                f"<b>{r['min_bore']:.2f} mm</b> "
                f"(select next standard NB up).", normal))
    else:
        story.append(Paragraph(
            f"<font color='#2a7a2a'><b>All checked pipes are within the "
            f"{VELOCITY_LIMIT} m/s limit.</b></font>", normal))

    # ---- Footer ----
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        f"{COMPANY} — Critical pipe check only (ICV / Header / Ranger). "
        f"Not a substitute for a full hydraulic calculation.", small))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# =============================================================================
# STREAMLIT UI
# =============================================================================
st.set_page_config(page_title=APP_TITLE, page_icon="🔥", layout="wide")

st.title("🔥 Fire Pipe Velocity Checker")
st.caption(f"{COMPANY} — Critical pipe check: ICV / Header / Ranger "
           f"(velocity limit {VELOCITY_LIMIT} m/s)")

# ---- Project info ----
st.subheader("Project Information")
c1, c2 = st.columns(2)
with c1:
    proj_name = st.text_input("Project name", value="")
    designer = st.text_input("Designer", value="")
with c2:
    proj_number = st.text_input("Project number", value="")
    proj_date = st.date_input("Date", value=datetime.now())

st.divider()

# ---- Inputs ----
st.subheader("Design Parameters")
c1, c2, c3 = st.columns(3)
with c1:
    density = st.number_input("Sprinkler density (mm/min)",
                              min_value=0.0, value=24.5, step=0.1, format="%.2f")
with c2:
    area_per_head = st.number_input("Area per sprinkler (m²)",
                                    min_value=0.0, value=8.57, step=0.1,
                                    format="%.2f")
with c3:
    k_factor = st.number_input("K-factor (reference)",
                               min_value=0.0, value=161.3, step=0.1,
                               format="%.2f")

st.subheader("Sprinkler Counts")
c1, c2, c3 = st.columns(3)
with c1:
    n_total = st.number_input("Total operating sprinklers (ICV)",
                              min_value=1, value=32, step=1)
with c2:
    n_header = st.number_input("Max sprinklers per header",
                               min_value=1, value=16, step=1)
with c3:
    n_ranger = st.number_input("Max sprinklers per ranger",
                               min_value=1, value=8, step=1)

st.subheader("Hydrant Allowance")
q_hydrant = st.number_input("Hydrant flow added to ICV (L/min, 0 if none)",
                            min_value=0.0, value=1900.0, step=50.0, format="%.2f")

st.subheader("Pipe Internal Bores")
c1, c2, c3 = st.columns(3)
with c1:
    bore_icv = st.number_input("ICV (main feeder) bore (mm)",
                               min_value=0.0, value=206.4, step=1.0, format="%.2f")
with c2:
    bore_header = st.number_input("Header pipe bore (mm)",
                                  min_value=0.0, value=155.32, step=1.0,
                                  format="%.2f")
with c3:
    bore_ranger = st.number_input("Ranger pipe bore (mm)",
                                  min_value=0.0, value=68.67, step=1.0,
                                  format="%.2f")

st.divider()

# ---- Calculations ----
q_per_head = density * area_per_head
q_ranger = q_per_head * n_ranger
q_header = q_per_head * n_header
q_icv = q_per_head * n_total + q_hydrant
p_required = (q_per_head / k_factor) ** 2 if k_factor > 0 else 0.0

results = [
    check_pipe("ICV",    q_icv,    bore_icv),
    check_pipe("Header", q_header, bore_header),
    check_pipe("Ranger", q_ranger, bore_ranger),
]

# ---- Display results ----
st.subheader("Results")

m1, m2, m3 = st.columns(3)
m1.metric("Flow per sprinkler head", f"{q_per_head:.2f} L/min")
m2.metric("Hydrant allowance", f"{q_hydrant:.0f} L/min")
m3.metric("Min head pressure (K-ref)", f"{p_required:.2f} bar")

# Build a simple results table
table_rows = []
for r in results:
    table_rows.append({
        "Pipe": r["label"],
        "Q (L/min)": f"{r['q']:.2f}",
        "Internal bore (mm)": f"{r['bore']:.2f}",
        "Velocity (m/s)": f"{r['velocity']:.2f}",
        "Min. bore (mm)": f"{r['min_bore']:.2f}",
        "Status": r["status"],
    })
st.dataframe(table_rows, use_container_width=True, hide_index=True)

# Pass / fail callouts
fails = [r for r in results if r["status"] == "FAIL"]
if fails:
    for r in fails:
        st.error(f"**{r['label']}** exceeds {VELOCITY_LIMIT} m/s. "
                 f"Increase internal bore to at least "
                 f"**{r['min_bore']:.2f} mm** (select next standard NB up).")
else:
    st.success(f"All checked pipes are within the {VELOCITY_LIMIT} m/s limit.")

st.divider()

# ---- PDF download ----
st.subheader("Export")

project = {
    "name":     proj_name or "—",
    "number":   proj_number or "—",
    "designer": designer or "—",
    "date":     proj_date.strftime("%Y-%m-%d"),
}
inputs = {
    "density":   density,
    "area":      area_per_head,
    "k":         k_factor,
    "n_total":   n_total,
    "n_header":  n_header,
    "n_ranger":  n_ranger,
    "q_hydrant": q_hydrant,
}

pdf_bytes = build_pdf(project, inputs, results, q_per_head, p_required)

filename = f"VelocityCheck_{proj_number or 'report'}_" \
           f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

st.download_button(
    label="📄 Download PDF Report",
    data=pdf_bytes,
    file_name=filename,
    mime="application/pdf",
)