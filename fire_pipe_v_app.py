"""
Fire Pipe Hydraulic Checker - Streamlit App (v2: full marching calc)
---------------------------------------------------------------------
Models a tree sprinkler system from the most remote sprinkler back to the ICV:

    [most remote sprinkler] -> ranger pipe (N sprinklers) -> header pipe (M rangers)
        -> static head (dz) -> ICV

Method (per supplied methodology):
    Q1 = density * area
    P1 = (Q1 / K_kPa)^2                        [K_kPa = K_bar / 10]
    For each segment i:
        d         = SANS 62 internal bore (mm) for the chosen NB
        dP_i      = 6.05e7 * (Q_i^1.85 * L) / (C^1.85 * d^4.87)   [kPa]
        P_next    = P_prev + dP_i
        q_next    = K_kPa * sqrt(P_next)
        Q_next    = Q_i + q_next
        v         = (Q_i / 60000) / (pi/4 * (d/1000)^2)
        Re        = v * (d/1000) / nu

Header pipe march: same equations, each "head" replaced by a ranger
take-off (q_next = total ranger discharge at that point's pressure).

Static head:  P_ICV = P_end_header + 9.81 * dz_m

Velocity limits flagged: ranger and header 7.6 m/s; ICV 7.2 m/s.

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
V_LIMIT_RANGER = 7.6       # m/s (ranger and header)
V_LIMIT_HEADER = 7.6       # m/s
V_LIMIT_ICV    = 7.2       # m/s
RE_MIN_TURBULENT = 4000    # below this, Hazen-Williams becomes invalid
G_KPA_PER_M = 9.81         # static head conversion (kPa per m of water)
NU_WATER = 1.0e-6          # m^2/s kinematic viscosity
HW_CONST = 6.05e7          # Hazen-Williams constant (kPa / L/min / m / mm form)

APP_TITLE = "Fire Pipe Hydraulic Checker"
COMPANY = "ViKO Consulting Engineers"

# SANS 62 nominal bore -> actual internal diameter (mm), medium-weight
SANS62 = {
    15: 16.5,
    20: 22.0,
    25: 27.8,
    32: 36.5,
    40: 42.4,
    50: 53.4,
    65: 69.0,
    80: 81.1,
    100: 105.5,
    125: 130.3,
    150: 155.7,
    200: 206.4,
    250: 260.4,
    300: 311.3,
}
NB_OPTIONS = list(SANS62.keys())


# =============================================================================
# CORE CALC FUNCTIONS
# =============================================================================
def hazen_williams_dp_kpa(q_lmin, length_m, c_hw, d_mm):
    """Friction loss along a pipe segment in kPa."""
    if d_mm <= 0 or q_lmin <= 0:
        return 0.0
    return HW_CONST * (q_lmin ** 1.85 * length_m) / (c_hw ** 1.85 * d_mm ** 4.87)


def velocity_m_s(q_lmin, d_mm):
    """Velocity (m/s) from Q in L/min and bore in mm."""
    if d_mm <= 0:
        return float("inf")
    q_m3s = q_lmin / 60000.0
    area_m2 = math.pi / 4.0 * (d_mm / 1000.0) ** 2
    return q_m3s / area_m2


def reynolds(v_ms, d_mm, nu=NU_WATER):
    return v_ms * (d_mm / 1000.0) / nu


def min_bore_mm(q_lmin, v_limit=V_LIMIT_HEADER):
    """Minimum internal bore (mm) so velocity stays below v_limit."""
    if q_lmin <= 0:
        return 0.0
    q_m3s = q_lmin / 60000.0
    area_required = q_m3s / v_limit
    return math.sqrt(4.0 * area_required / math.pi) * 1000.0


# =============================================================================
# RANGER MARCH
# =============================================================================
def march_ranger(n_heads, spacing_m, nb_mm, k_kpa, c_hw, density, area):
    """
    March from the most remote sprinkler along a single ranger.

    Returns:
        rows    : list of per-head dicts (Q, P, ΔP, v, Re)
        summary : dict with end-of-ranger totals (q_total, p_end, v_max, ...)
    """
    d = SANS62[nb_mm]
    q_design = density * area                    # L/min

    # Sprinkler 1 - most remote, must meet density-driven demand
    p1 = (q_design / k_kpa) ** 2                 # kPa
    q1 = q_design

    rows = [{
        "label": "Sprinkler 1 (remote)",
        "q_head": q1,
        "p_head": p1,
        "q_pipe": q1,
        "nb": nb_mm,
        "d_mm": d,
        "length_m": 0.0,
        "dp_kpa": 0.0,
        "v_ms": 0.0,
        "Re": 0.0,
    }]

    q_pipe_prev = q1
    p_prev = p1

    for i in range(1, n_heads):
        # friction in the segment carrying q_pipe_prev
        dp = hazen_williams_dp_kpa(q_pipe_prev, spacing_m, c_hw, d)
        p_next = p_prev + dp
        q_next_head = k_kpa * math.sqrt(p_next)
        q_pipe_next = q_pipe_prev + q_next_head
        v = velocity_m_s(q_pipe_prev, d)
        re = reynolds(v, d)

        rows.append({
            "label": f"Sprinkler {i + 1}",
            "q_head": q_next_head,
            "p_head": p_next,
            "q_pipe": q_pipe_next,
            "nb": nb_mm,
            "d_mm": d,
            "length_m": spacing_m,
            "dp_kpa": dp,
            "v_ms": v,
            "Re": re,
        })

        q_pipe_prev = q_pipe_next
        p_prev = p_next

    # exit segment: from last head toward the header take-off, carrying full ranger flow
    v_last = velocity_m_s(q_pipe_prev, d)
    re_last = reynolds(v_last, d)

    rows.append({
        "label": "Exit (to header)",
        "q_head": 0.0,
        "p_head": p_prev,
        "q_pipe": q_pipe_prev,
        "nb": nb_mm,
        "d_mm": d,
        "length_m": 0.0,
        "dp_kpa": 0.0,
        "v_ms": v_last,
        "Re": re_last,
    })

    summary = {
        "n_heads": n_heads,
        "nb_mm": nb_mm,
        "d_mm": d,
        "q_total": q_pipe_prev,         # flow leaving the ranger
        "p_end": p_prev,                # pressure at take-off into header
        "v_max": max(max((r["v_ms"] for r in rows), default=0.0), v_last),
        "re_min": min((r["Re"] for r in rows if r["Re"] > 0),
                      default=re_last),
        "v_exit": v_last,
        "re_exit": re_last,
    }
    return rows, summary


# =============================================================================
# HEADER MARCH
# =============================================================================
def march_header(n_rangers, spacing_m, nb_mm, k_kpa, c_hw,
                 density, area, ranger_n_heads, ranger_spacing, ranger_nb):
    """
    March along the header from the most remote ranger (take-off 1) toward
    the ICV. Each take-off injects a full ranger's discharge.

    For simplicity (per agreed scope: case 5(a) with case 4(a)), every
    ranger is assumed to be identical and computed once. The header march
    handles the pressure build-up between take-offs.
    """
    d_hdr = SANS62[nb_mm]

    # Compute the (identical) ranger once
    ranger_rows, ranger_summary = march_ranger(
        n_heads=ranger_n_heads, spacing_m=ranger_spacing, nb_mm=ranger_nb,
        k_kpa=k_kpa, c_hw=c_hw, density=density, area=area,
    )

    rangers = [{
        "index": 1,
        "rows": ranger_rows,
        "summary": ranger_summary,
        "p_inlet_kpa": ranger_summary["p_end"],
    }]

    header_rows = [{
        "label": "Take-off 1 (remote ranger)",
        "q_takeoff": ranger_summary["q_total"],
        "p_at_node": ranger_summary["p_end"],
        "q_pipe": ranger_summary["q_total"],
        "nb": nb_mm,
        "d_mm": d_hdr,
        "length_m": 0.0,
        "dp_kpa": 0.0,
        "v_ms": 0.0,
        "Re": 0.0,
    }]

    q_pipe_prev = ranger_summary["q_total"]
    p_prev = ranger_summary["p_end"]

    for i in range(1, n_rangers):
        dp = hazen_williams_dp_kpa(q_pipe_prev, spacing_m, c_hw, d_hdr)
        p_at_takeoff = p_prev + dp
        q_takeoff = ranger_summary["q_total"]    # identical ranger
        q_pipe_next = q_pipe_prev + q_takeoff
        v = velocity_m_s(q_pipe_prev, d_hdr)
        re = reynolds(v, d_hdr)

        header_rows.append({
            "label": f"Take-off {i + 1}",
            "q_takeoff": q_takeoff,
            "p_at_node": p_at_takeoff,
            "q_pipe": q_pipe_next,
            "nb": nb_mm,
            "d_mm": d_hdr,
            "length_m": spacing_m,
            "dp_kpa": dp,
            "v_ms": v,
            "Re": re,
        })

        rangers.append({
            "index": i + 1,
            "rows": ranger_rows,            # same layout (simplified)
            "summary": ranger_summary,
            "p_inlet_kpa": p_at_takeoff,
        })

        q_pipe_prev = q_pipe_next
        p_prev = p_at_takeoff

    # exit segment: from last take-off toward the ICV, carrying full header flow
    v_exit = velocity_m_s(q_pipe_prev, d_hdr)
    re_exit = reynolds(v_exit, d_hdr)

    header_rows.append({
        "label": "Exit (to ICV)",
        "q_takeoff": 0.0,
        "p_at_node": p_prev,
        "q_pipe": q_pipe_prev,
        "nb": nb_mm,
        "d_mm": d_hdr,
        "length_m": 0.0,
        "dp_kpa": 0.0,
        "v_ms": v_exit,
        "Re": re_exit,
    })

    summary = {
        "n_rangers": n_rangers,
        "nb_mm": nb_mm,
        "d_mm": d_hdr,
        "q_total": q_pipe_prev,
        "p_end": p_prev,
        "v_max": max(max((r["v_ms"] for r in header_rows), default=0.0),
                     v_exit),
        "v_exit": v_exit,
        "re_exit": re_exit,
    }
    return header_rows, summary, rangers


# =============================================================================
# ICV
# =============================================================================
def icv_calc(q_header, p_end_header, dz_m, nb_icv, q_hydrant_lmin,
             n_headers=1):
    """ICV summary. n_headers = number of symmetric headers feeding the ICV."""
    d = SANS62[nb_icv]
    static_kpa = G_KPA_PER_M * dz_m
    p_icv_kpa = p_end_header + static_kpa
    q_icv = q_header * n_headers + q_hydrant_lmin
    v = velocity_m_s(q_icv, d)
    re = reynolds(v, d)
    return {
        "nb_mm": nb_icv,
        "d_mm": d,
        "q_total": q_icv,
        "q_per_header": q_header,
        "n_headers": n_headers,
        "p_kpa": p_icv_kpa,
        "p_bar": p_icv_kpa / 100.0,
        "v_ms": v,
        "Re": re,
        "static_head_kpa": static_kpa,
        "dz_m": dz_m,
        "q_hydrant": q_hydrant_lmin,
    }


# =============================================================================
# PDF REPORT
# =============================================================================
def build_pdf(project, inputs, ranger_summary, header_data, header_summary,
              icv_data, rangers):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Fire Pipe Hydraulic Check", author=COMPANY,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Title"], fontSize=15, spaceAfter=4,
        textColor=colors.HexColor("#b00020"),
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=11, spaceBefore=8,
        spaceAfter=4, textColor=colors.HexColor("#333333"),
    )
    normal = styles["Normal"]
    small = ParagraphStyle("small", parent=normal, fontSize=8,
                           textColor=colors.grey)

    story = []
    story.append(Paragraph("Fire Pipe Hydraulic Check", title_style))
    story.append(Paragraph(COMPANY, normal))
    story.append(Paragraph(
        f"Generated: {datetime.now():%Y-%m-%d %H:%M} | "
        f"Velocity limits: ranger/header {V_LIMIT_RANGER} m/s, "
        f"ICV {V_LIMIT_ICV} m/s", small))
    story.append(Spacer(1, 4 * mm))

    # --- project info ---
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

    # --- inputs ---
    story.append(Paragraph("Design Inputs", h2))
    in_data = [
        ["Sprinkler density",              f"{inputs['density']:.2f} mm/min"],
        ["Area per sprinkler",             f"{inputs['area']:.2f} m²"],
        ["Sprinkler Area of Operation",    f"{inputs['area_of_operation']:.2f} m²"],
        ["K-factor (bar basis)",           f"{inputs['k_bar']:.2f}"],
        ["K-factor (kPa basis)",           f"{inputs['k_bar']/10:.3f}"],
        ["Hazen-Williams C",               f"{inputs['c_hw']}"],
        ["Sprinklers per ranger",          f"{inputs['ranger_heads']}"],
        ["Ranger spacing",                 f"{inputs['ranger_spacing']:.2f} m"],
        ["Ranger NB",                      f"{inputs['ranger_nb']} mm"
                                           f" (ID {SANS62[inputs['ranger_nb']]:.1f} mm)"],
        ["Rangers per header",             f"{inputs['header_rangers']}"],
        ["Header spacing",                 f"{inputs['header_spacing']:.2f} m"],
        ["Header NB",                      f"{inputs['header_nb']} mm"
                                           f" (ID {SANS62[inputs['header_nb']]:.1f} mm)"],
        ["Headers connected to ICV",       f"{inputs['n_headers']}"],
        ["ICV NB",                         f"{inputs['icv_nb']} mm"
                                           f" (ID {SANS62[inputs['icv_nb']]:.1f} mm)"],
        ["Static head (header → ICV)",     f"{inputs['dz']:.2f} m"],
        ["Hydrant allowance",              f"{inputs['q_hydrant']:.2f} L/min"],
    ]
    t = Table(in_data, colWidths=[80 * mm, 85 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(t)

    # --- ranger detail ---
    story.append(PageBreak())
    story.append(Paragraph("Ranger Pipe Calculation (per sprinkler)", h2))
    story.append(Paragraph(
        f"All rangers identical in this simplified model. "
        f"End-of-ranger Q: {ranger_summary['q_total']:.2f} L/min | "
        f"End-of-ranger P: {ranger_summary['p_end']:.2f} kPa | "
        f"v_max: {ranger_summary['v_max']:.2f} m/s", normal))
    story.append(Spacer(1, 2 * mm))

    data = [["Node", "Q sprinkler (L/min)", "P sprinkler (kPa)",
             "Q pipe (L/min)", "L (m)", "ΔP (kPa)", "v (m/s)", "Re"]]
    for row in rangers[0]["rows"]:
        data.append([
            row["label"],
            f"{row['q_head']:.2f}",
            f"{row['p_head']:.2f}",
            f"{row['q_pipe']:.2f}",
            f"{row['length_m']:.2f}",
            f"{row['dp_kpa']:.3f}",
            f"{row['v_ms']:.2f}" if row['v_ms'] > 0 else "—",
            f"{row['Re']:.0f}" if row['Re'] > 0 else "—",
        ])
    t = Table(data, colWidths=[28 * mm, 22 * mm, 22 * mm, 24 * mm,
                               16 * mm, 22 * mm, 18 * mm, 20 * mm])
    ts = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]
    for i, row in enumerate(rangers[0]["rows"], start=1):
        if row["v_ms"] > V_LIMIT_RANGER:
            ts.append(("BACKGROUND", (0, i), (-1, i),
                       colors.HexColor("#fdecea")))
    t.setStyle(TableStyle(ts))
    story.append(t)

    # --- header detail ---
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Header Pipe Calculation", h2))
    story.append(Paragraph(
        f"End-of-header Q: {header_summary['q_total']:.2f} L/min | "
        f"End-of-header P: {header_summary['p_end']:.2f} kPa | "
        f"v_max: {header_summary['v_max']:.2f} m/s", normal))
    story.append(Spacer(1, 2 * mm))

    data = [["Node", "Q take-off (L/min)", "P at node (kPa)",
             "Q pipe (L/min)", "L (m)", "ΔP (kPa)", "v (m/s)", "Re"]]
    for row in header_data:
        data.append([
            row["label"],
            f"{row['q_takeoff']:.2f}",
            f"{row['p_at_node']:.2f}",
            f"{row['q_pipe']:.2f}",
            f"{row['length_m']:.2f}",
            f"{row['dp_kpa']:.3f}",
            f"{row['v_ms']:.2f}" if row['v_ms'] > 0 else "—",
            f"{row['Re']:.0f}" if row['Re'] > 0 else "—",
        ])
    t = Table(data, colWidths=[34 * mm, 24 * mm, 24 * mm, 24 * mm,
                               14 * mm, 22 * mm, 16 * mm, 20 * mm])
    ts = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ]
    for i, row in enumerate(header_data, start=1):
        if row["v_ms"] > V_LIMIT_HEADER:
            ts.append(("BACKGROUND", (0, i), (-1, i),
                       colors.HexColor("#fdecea")))
    t.setStyle(TableStyle(ts))
    story.append(t)

    # --- ICV summary ---
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("ICV Summary", h2))
    icv_rows = [
        ["End-of-header pressure",
         f"{header_summary['p_end']:.2f} kPa "
         f"({header_summary['p_end']/100:.3f} bar)"],
        [f"Static head (Δz = {icv_data['dz_m']:.2f} m)",
         f"{icv_data['static_head_kpa']:.2f} kPa"],
        ["Hydrant allowance",
         f"{icv_data['q_hydrant']:.2f} L/min"],
        ["ICV pressure",
         f"{icv_data['p_kpa']:.2f} kPa "
         f"({icv_data['p_bar']:.3f} bar)"],
        ["Flow per header",
         f"{icv_data['q_per_header']:.2f} L/min"],
        ["Headers on ICV",
         f"{icv_data['n_headers']}"],
        ["ICV total flow",
         f"{icv_data['q_total']:.2f} L/min "
         f"({icv_data['n_headers']} × header + hydrant)"],
        ["ICV NB / ID",
         f"{icv_data['nb_mm']} mm  ({icv_data['d_mm']:.1f} mm)"],
        ["ICV velocity",
         f"{icv_data['v_ms']:.2f} m/s"],
        ["ICV Reynolds",
         f"{icv_data['Re']:.0f}"],
        [f"Min ICV bore @ {V_LIMIT_ICV} m/s",
         f"{min_bore_mm(icv_data['q_total'], v_limit=V_LIMIT_ICV):.2f} mm"],
    ]
    t = Table(icv_rows, colWidths=[80 * mm, 85 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story.append(t)

    # --- velocity flags ---
    story.append(Spacer(1, 5 * mm))
    flags = []
    if ranger_summary["v_max"] > V_LIMIT_RANGER:
        flags.append(f"Ranger velocity {ranger_summary['v_max']:.2f} m/s "
                     f"exceeds {V_LIMIT_RANGER} m/s.")
    if header_summary["v_max"] > V_LIMIT_HEADER:
        flags.append(f"Header velocity {header_summary['v_max']:.2f} m/s "
                     f"exceeds {V_LIMIT_HEADER} m/s.")
    if icv_data["v_ms"] > V_LIMIT_ICV:
        flags.append(f"ICV velocity {icv_data['v_ms']:.2f} m/s "
                     f"exceeds {V_LIMIT_ICV} m/s.")

    if flags:
        story.append(Paragraph("<b>Attention</b>", h2))
        for f in flags:
            story.append(Paragraph(f, normal))
    else:
        story.append(Paragraph(
            f"<font color='#2a7a2a'><b>All pipes within their velocity "
            f"limits ({V_LIMIT_RANGER} m/s ranger/header, "
            f"{V_LIMIT_ICV} m/s ICV).</b></font>", normal))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"{COMPANY} — Hydraulic check from most remote sprinkler to ICV. "
        f"Hazen-Williams (kPa form). Not a substitute for full system design.",
        small))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


# =============================================================================
# STREAMLIT UI
# =============================================================================
st.set_page_config(page_title=APP_TITLE, page_icon="🔥", layout="wide")
st.title("🔥 Fire Pipe Hydraulic Checker")
st.caption(f"{COMPANY} — Marching calculation from most remote sprinkler → ICV "
           f"| limits: ranger/header {V_LIMIT_RANGER} m/s, "
           f"ICV {V_LIMIT_ICV} m/s")

tab_proj, tab_design, tab_ranger, tab_header, tab_icv, tab_results = st.tabs(
    ["Project", "Design", "Ranger", "Header", "ICV", "Results"]
)

# ---- Project ----
with tab_proj:
    c1, c2 = st.columns(2)
    with c1:
        proj_name = st.text_input("Project name", value="")
        designer = st.text_input("Designer", value="")
    with c2:
        proj_number = st.text_input("Project number", value="")
        proj_date = st.date_input("Date", value=datetime.now())

# ---- Design ----
with tab_design:
    c1, c2, c3 = st.columns(3)
    with c1:
        density = st.number_input("Sprinkler density (mm/min)",
                                  min_value=0.0, value=24.5,
                                  step=0.1, format="%.2f")
    with c2:
        area_per_head = st.number_input("Area per sprinkler (m²)",
                                        min_value=0.0, value=12.3,
                                        step=0.1, format="%.2f")
    with c3:
        k_bar = st.number_input("K-factor (bar basis, e.g. 161.3)",
                                min_value=0.0, value=161.3,
                                step=0.1, format="%.2f")
    c1, c2 = st.columns(2)
    with c1:
        c_hw = st.number_input("Hazen-Williams C",
                               min_value=80, max_value=150,
                               value=120, step=1)
    with c2:
        q_hydrant = st.number_input("Hydrant flow added at ICV (L/min)",
                                    min_value=0.0, value=0.0,
                                    step=50.0, format="%.2f")
    area_of_operation = st.number_input(
        "Sprinkler Area of Operation (m²)",
        min_value=0.0, value=260.0, step=10.0, format="%.2f",
        help="Display only — recorded on the PDF for reference. "
             "Does not affect the hydraulic calculation at this stage.")

# ---- Ranger ----
with tab_ranger:
    c1, c2, c3 = st.columns(3)
    with c1:
        ranger_heads = st.number_input("Sprinklers per ranger",
                                       min_value=1, value=8, step=1)
    with c2:
        ranger_spacing = st.number_input("Spacing between heads (m)",
                                         min_value=0.1, value=3.0,
                                         step=0.1, format="%.2f")
    with c3:
        ranger_nb = st.selectbox("Ranger NB (mm)", NB_OPTIONS,
                                 index=NB_OPTIONS.index(50))
    st.caption(f"Internal diameter from SANS 62: "
               f"**{SANS62[ranger_nb]:.1f} mm**")

# ---- Header ----
with tab_header:
    n_headers = st.selectbox(
        "Number of headers connected to ICV",
        options=[1, 2],
        index=0,
        help="Choose 2 for a symmetric layout with two identical headers "
             "branching off the ICV. The ICV flow is then doubled.",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        header_rangers = st.number_input("Number of rangers per header",
                                         min_value=1, value=4, step=1)
    with c2:
        header_spacing = st.number_input("Spacing between rangers (m)",
                                         min_value=0.1, value=4.0,
                                         step=0.1, format="%.2f")
    with c3:
        header_nb = st.selectbox("Header NB (mm)", NB_OPTIONS,
                                 index=NB_OPTIONS.index(150))
    st.caption(f"Internal diameter from SANS 62: "
               f"**{SANS62[header_nb]:.1f} mm**")
    if n_headers == 2:
        st.info("Two symmetric headers assumed. Each header carries the "
                "same flow and pressure profile; ICV flow = 2 × header flow.")

# ---- ICV ----
with tab_icv:
    c1, c2 = st.columns(2)
    with c1:
        icv_nb = st.selectbox("ICV (main feeder) NB (mm)", NB_OPTIONS,
                              index=NB_OPTIONS.index(200))
        st.caption(f"Internal diameter from SANS 62: "
                   f"**{SANS62[icv_nb]:.1f} mm**")
    with c2:
        dz = st.number_input("Static head – header above ICV (m)",
                             min_value=0.0, value=5.0,
                             step=0.5, format="%.2f")
        st.caption(f"Adds {G_KPA_PER_M * dz:.2f} kPa to ICV pressure")

# =============================================================================
# CALCULATE
# =============================================================================
k_kpa = k_bar / 10.0

header_rows, header_summary, rangers = march_header(
    n_rangers=header_rangers,
    spacing_m=header_spacing,
    nb_mm=header_nb,
    k_kpa=k_kpa,
    c_hw=c_hw,
    density=density,
    area=area_per_head,
    ranger_n_heads=ranger_heads,
    ranger_spacing=ranger_spacing,
    ranger_nb=ranger_nb,
)
ranger_summary = rangers[0]["summary"]
icv_data = icv_calc(
    q_header=header_summary["q_total"],
    p_end_header=header_summary["p_end"],
    dz_m=dz,
    nb_icv=icv_nb,
    q_hydrant_lmin=q_hydrant,
    n_headers=n_headers,
)

# =============================================================================
# RESULTS TAB
# =============================================================================
with tab_results:
    st.subheader("Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Flow per remote sprinkler", f"{density * area_per_head:.1f} L/min")
    m2.metric("End-of-ranger Q",      f"{ranger_summary['q_total']:.1f} L/min")
    m3.metric("Q per header",         f"{header_summary['q_total']:.1f} L/min")
    m4.metric("ICV total Q",          f"{icv_data['q_total']:.1f} L/min")
    m5.metric("ICV pressure",         f"{icv_data['p_bar']:.2f} bar")

    st.markdown("##### Velocity check")
    vel_rows = [
        {"Pipe": "Ranger (max v)",
         "v (m/s)": f"{ranger_summary['v_max']:.2f}",
         "Limit": f"{V_LIMIT_RANGER}",
         "Status": "PASS" if ranger_summary['v_max'] <= V_LIMIT_RANGER
                   else "FAIL"},
        {"Pipe": "Header (max v)",
         "v (m/s)": f"{header_summary['v_max']:.2f}",
         "Limit": f"{V_LIMIT_HEADER}",
         "Status": "PASS" if header_summary['v_max'] <= V_LIMIT_HEADER
                   else "FAIL"},
        {"Pipe": "ICV",
         "v (m/s)": f"{icv_data['v_ms']:.2f}",
         "Limit": f"{V_LIMIT_ICV}",
         "Status": "PASS" if icv_data['v_ms'] <= V_LIMIT_ICV else "FAIL"},
    ]
    st.dataframe(vel_rows, use_container_width=True, hide_index=True)

    fails = [v for v in vel_rows if v["Status"] == "FAIL"]
    if fails:
        for f in fails:
            st.error(f"{f['Pipe']} — velocity {f['v (m/s)']} m/s exceeds "
                     f"{f['Limit']} m/s.")
    else:
        st.success(f"All pipes within their velocity limits "
                   f"(ranger/header {V_LIMIT_RANGER} m/s, "
                   f"ICV {V_LIMIT_ICV} m/s).")

    st.divider()
    st.subheader("Most remote ranger — per sprinkler")
    st.dataframe([{
        "Node": r["label"],
        "Q sprinkler (L/min)": round(r["q_head"], 2),
        "P sprinkler (kPa)": round(r["p_head"], 2),
        "Q pipe (L/min)": round(r["q_pipe"], 2),
        "L (m)": round(r["length_m"], 2),
        "ΔP (kPa)": round(r["dp_kpa"], 3),
        "v (m/s)": round(r["v_ms"], 2) if r["v_ms"] > 0 else "—",
        "Re": int(r["Re"]) if r["Re"] > 0 else "—",
    } for r in rangers[0]["rows"]],
        use_container_width=True, hide_index=True)

    st.subheader("Header pipe")
    st.dataframe([{
        "Node": r["label"],
        "Q take-off (L/min)": round(r["q_takeoff"], 2),
        "P at node (kPa)": round(r["p_at_node"], 2),
        "Q pipe (L/min)": round(r["q_pipe"], 2),
        "L (m)": round(r["length_m"], 2),
        "ΔP (kPa)": round(r["dp_kpa"], 3),
        "v (m/s)": round(r["v_ms"], 2) if r["v_ms"] > 0 else "—",
        "Re": int(r["Re"]) if r["Re"] > 0 else "—",
    } for r in header_rows],
        use_container_width=True, hide_index=True)

    st.subheader("ICV")
    st.dataframe([
        {"Quantity": "Flow per header",
         "Value": f"{icv_data['q_per_header']:.2f} L/min"},
        {"Quantity": "Headers on ICV",
         "Value": f"{icv_data['n_headers']}"},
        {"Quantity": "ICV total flow",
         "Value": f"{icv_data['q_total']:.2f} L/min"},
        {"Quantity": "ICV pressure",
         "Value": f"{icv_data['p_kpa']:.2f} kPa "
                  f"({icv_data['p_bar']:.3f} bar)"},
        {"Quantity": "ICV velocity",
         "Value": f"{icv_data['v_ms']:.2f} m/s"},
        {"Quantity": "Static head (Δz)",
         "Value": f"{icv_data['static_head_kpa']:.2f} kPa "
                  f"({icv_data['dz_m']:.2f} m)"},
        {"Quantity": f"Min bore for ≤ {V_LIMIT_ICV} m/s",
         "Value": f"{min_bore_mm(icv_data['q_total'], v_limit=V_LIMIT_ICV):.2f} mm"},
    ], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Export")
    project = {
        "name":     proj_name or "—",
        "number":   proj_number or "—",
        "designer": designer or "—",
        "date":     proj_date.strftime("%Y-%m-%d"),
    }
    inputs = {
        "density": density, "area": area_per_head, "k_bar": k_bar,
        "c_hw": c_hw, "q_hydrant": q_hydrant,
        "area_of_operation": area_of_operation,
        "ranger_heads": ranger_heads, "ranger_spacing": ranger_spacing,
        "ranger_nb": ranger_nb,
        "header_rangers": header_rangers, "header_spacing": header_spacing,
        "header_nb": header_nb, "n_headers": n_headers,
        "icv_nb": icv_nb, "dz": dz,
    }
    pdf_bytes = build_pdf(project, inputs, ranger_summary,
                          header_rows, header_summary, icv_data, rangers)
    filename = (f"HydraulicCheck_{proj_number or 'report'}_"
                f"{datetime.now():%Y%m%d_%H%M}.pdf")
    st.download_button(
        label="📄 Download PDF Report",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
    )