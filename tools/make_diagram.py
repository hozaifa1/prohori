"""Generate a publication-grade, visual architecture and CV metrology diagram for PROHORI.
Features:
- Visual illustrations of every CV transformation (Perspective ChArUco -> Rectified Patch ->
  Distance Transform Heatmap & Skeleton -> Bias Removal -> LightGlue Cross-Visit Matching).
- Concrete AWS architecture mapping (Graviton4 COOL c8g, Graviton2 t4g, Bedrock Agent, DynamoDB/S3, SNS).
- Distinct closed-loop agentic feedback path (Amber) vs certified measurement path (Blue/Teal).
- 100% solid black typography, high-contrast badges, and zero text/line collisions.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (FancyBboxPatch, FancyArrowPatch, Rectangle,
                                Polygon, Circle)
import numpy as np

# ─────────────────────────────────────────────────────────────
# PALETTE & CONFIG
# ─────────────────────────────────────────────────────────────
BG = "#FFFFFF"
SOLID_BLACK = "#000000"
TEXT_MUTED = "#1E293B"

C_EDGE = "#4338CA"      # Indigo (Edge Mobile & Human Actuator)
BG_EDGE = "#EEF2FF"
BD_EDGE = "#6366F1"

C_GATEWAY = "#059669"   # Emerald (Graviton2 Gateway - Free Tier)
BG_GATEWAY = "#ECFDF5"
BD_GATEWAY = "#10B981"

C_COMPUTE = "#1D4ED8"   # Royal Blue (Graviton4 + COOL 3.1)
BG_COMPUTE = "#EFF6FF"
BD_COMPUTE = "#3B82F6"

C_AGENT = "#C2410C"     # Burnt Orange (Bedrock Agentic Loop)
BG_AGENT = "#FFF7ED"
BD_AGENT = "#F97316"

C_STORAGE = "#0D9488"   # Teal (DynamoDB + S3 Ledger)
BG_STORAGE = "#F0FDFA"
BD_STORAGE = "#14B8A6"

C_ALERT = "#BE123C"     # Crimson (SNS Engineer Alert)
BG_ALERT = "#FFF1F2"
BD_ALERT = "#F43F5E"

fig, ax = plt.subplots(figsize=(18.0, 10.6), dpi=240)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 180)
ax.set_ylim(0, 106)
ax.axis("off")


# ─────────────────────────────────────────────────────────────
# DRAWING HELPERS
# ─────────────────────────────────────────────────────────────
def draw_container(x, y, w, h, title, subtitle="", bg="#FFFFFF", border="#000000", lw=2.0, tag=None):
    """Draw a structural tier container with safe padding."""
    patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=2.0",
                           facecolor=bg, edgecolor=border, linewidth=lw, zorder=2)
    ax.add_patch(patch)
    
    # Title
    t_y = y + h - 2.6
    ax.text(x + 2.2, t_y, title, ha="left", va="center",
            fontsize=9.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
    if subtitle:
        ax.text(x + 2.2, t_y - 2.4, subtitle, ha="left", va="center",
                fontsize=7.8, fontweight="bold", color=border, zorder=4)
    if tag:
        ax.text(x + w - 2.0, t_y, tag, ha="right", va="center",
                fontsize=7.4, fontweight="bold", color=border,
                bbox=dict(boxstyle="round,pad=0.20", facecolor="#FFFFFF", edgecolor=border, lw=1.0),
                zorder=4)


def draw_arrow(p1, p2, label=None, color="#000000", lw=2.2, style="-|>",
               rad=0.0, label_bg="#FFFFFF", label_pos=None, dashed=False,
               label_fontsize=7.6):
    """Draw an arrow with an isolated background badge."""
    ls = "--" if dashed else "-"
    arrow = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=12,
                            color=color, linewidth=lw, linestyle=ls, zorder=3,
                            connectionstyle=f"arc3,rad={rad}",
                            shrinkA=3, shrinkB=3)
    ax.add_patch(arrow)
    
    if label:
        if label_pos is not None:
            lx, ly = label_pos
        else:
            lx = (p1[0] + p2[0]) / 2
            ly = (p1[1] + p2[1]) / 2 + 2.2
            
        ax.text(lx, ly, label, ha="center", va="center",
                fontsize=label_fontsize, fontweight="bold", color=SOLID_BLACK, zorder=6,
                bbox=dict(boxstyle="round,pad=0.20,rounding_size=0.8",
                          facecolor=label_bg, edgecolor=color, linewidth=1.1, zorder=5))


# ─────────────────────────────────────────────────────────────
# 1. HEADER & SYSTEM TITLE
# ─────────────────────────────────────────────────────────────
ax.text(3.5, 102.0, "PROHORI: Closed-Loop Vision Metrology & AWS Graviton Architecture",
        fontsize=17.5, fontweight="bold", color=SOLID_BLACK, va="top")
ax.text(3.5, 98.2, "Phone PWA Guided Capture  →  AWS Graviton4 + COOL 3.1 Metrology Pipeline  →  Amazon Bedrock Closed-Loop Agent",
        fontsize=10.0, fontweight="bold", color=C_COMPUTE, va="top")

# Top-Right Semantic Legend
leg_x = 123.0
leg_y = 100.0
ax.add_patch(FancyBboxPatch((leg_x, leg_y - 2.4), 53, 4.4, boxstyle="round,pad=0.25",
                           facecolor="#F8FAFC", edgecolor=SOLID_BLACK, lw=1.2, zorder=2))

ax.add_patch(Rectangle((leg_x + 2, leg_y - 0.9), 2.4, 1.6, facecolor=C_COMPUTE, edgecolor=SOLID_BLACK, lw=0.6, zorder=3))
ax.text(leg_x + 5.2, leg_y - 0.1, "COOL / Graviton4", fontsize=7.8, fontweight="bold", color=SOLID_BLACK, va="center")

ax.add_patch(Rectangle((leg_x + 20, leg_y - 0.9), 2.4, 1.6, facecolor=C_AGENT, edgecolor=SOLID_BLACK, lw=0.6, zorder=3))
ax.text(leg_x + 23.2, leg_y - 0.1, "Bedrock Agent Loop", fontsize=7.8, fontweight="bold", color=SOLID_BLACK, va="center")

ax.add_patch(Rectangle((leg_x + 39, leg_y - 0.9), 2.4, 1.6, facecolor=C_GATEWAY, edgecolor=SOLID_BLACK, lw=0.6, zorder=3))
ax.text(leg_x + 42.2, leg_y - 0.1, "AWS Free Tier", fontsize=7.8, fontweight="bold", color=SOLID_BLACK, va="center")


# ─────────────────────────────────────────────────────────────
# 2. LEFT PANEL: TIER 1 - FIELD CAPTURE & OPERATOR HUD
# ─────────────────────────────────────────────────────────────
draw_container(x=3.5, y=19.0, w=35.0, h=76.0,
               title="TIER 1: Edge PWA Capture",
               subtitle="BROWSER PWA • CLIENT-SIDE PRIVACY",
               bg=BG_EDGE, border=BD_EDGE, lw=2.2, tag="MOBILE EDGE")

# Visual Sub-Block 1A: Concrete Target + ChArUco Marker
ax.add_patch(FancyBboxPatch((5.5, 62.0), 31.0, 24.5, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_EDGE, lw=1.4, zorder=3))
ax.text(7.0, 84.0, "Physical Target & ChArUco Scale", fontsize=8.8, fontweight="bold", color=SOLID_BLACK, zorder=4)

# Draw concrete wall + crack + ChArUco board
ax.add_patch(Rectangle((7.0, 64.5), 28.0, 16.5, facecolor="#E2E8F0", edgecolor="#94A3B8", lw=1.0, zorder=4))
# ChArUco Board
ax.add_patch(Rectangle((8.5, 71.5), 8.5, 8.0, facecolor="#0F172A", edgecolor="#000000", lw=1.0, zorder=5))
for r in range(3):
    for c in range(3):
        if (r + c) % 2 == 0:
            ax.add_patch(Rectangle((8.5 + c*2.83, 71.5 + r*2.66), 2.83, 2.66, facecolor="#FFFFFF", zorder=6))
ax.text(12.7, 70.1, "200mm Scale Board", fontsize=6.8, fontweight="bold", color=SOLID_BLACK, ha="center", zorder=7)

# Crack drawing
crack_pts = [(19.0, 80.0), (20.5, 77.0), (19.8, 73.5), (21.2, 69.0), (22.5, 65.0)]
cx, cy = zip(*crack_pts)
ax.plot(cx, cy, color="#1E293B", lw=3.0, zorder=6)
ax.text(23.5, 74.0, "Concrete\nCrack", fontsize=7.4, fontweight="bold", color=SOLID_BLACK, va="center", zorder=7)

ax.text(7.0, 63.0, "• FaceDetectorYN (Client Blur)  • 60 FPS WebRTC",
        fontsize=7.4, fontweight="bold", color=SOLID_BLACK, zorder=4)

# Visual Sub-Block 1B: Smartphone PWA HUD & Feedback Actuator
ax.add_patch(FancyBboxPatch((5.5, 21.0), 31.0, 37.0, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_EDGE, lw=1.4, zorder=3))
ax.text(7.0, 55.5, "Smartphone PWA HUD (Operator Loop)", fontsize=8.8, fontweight="bold", color=SOLID_BLACK, zorder=4)

# Phone frame
ax.add_patch(FancyBboxPatch((8.5, 24.5), 25.0, 28.5, boxstyle="round,pad=0.3,rounding_size=1.5",
                           facecolor="#0F172A", edgecolor="#334155", lw=1.5, zorder=5))
# Phone Screen
ax.add_patch(Rectangle((10.0, 26.5), 22.0, 24.5, facecolor="#1E293B", edgecolor="none", zorder=6))
# Camera reticle
ax.add_patch(Rectangle((13.0, 33.0), 16.0, 13.0, facecolor="none", edgecolor="#38BDF8", lw=1.2, ls="--", zorder=7))
# HUD Prompt banner
ax.add_patch(FancyBboxPatch((11.0, 28.0), 20.0, 5.5, boxstyle="round,pad=0.2",
                           facecolor="#FEF3C7", edgecolor="#F59E0B", lw=1.2, zorder=8))
ax.text(21.0, 31.5, "AGENT DIRECTIVE:", fontsize=6.6, fontweight="heavy", color="#B45309", ha="center", zorder=9)
ax.text(21.0, 29.2, "\"Move 15cm Closer & Relight\"", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, ha="center", zorder=9)

ax.text(7.0, 22.2, "• Human Actuator Closes Perception-Action Loop",
        fontsize=7.4, fontweight="bold", color=C_AGENT, zorder=4)


# ─────────────────────────────────────────────────────────────
# 3. CENTER-TOP PANEL: TIER 3 - CV & COOL METROLOGY PIPELINE
# ─────────────────────────────────────────────────────────────
draw_container(x=43.5, y=51.0, w=84.0, h=44.0,
               title="TIER 3: Computer Vision Metrology Pipeline",
               subtitle="AWS GRAVITON4 (EC2 c8g) • OPENCV 5.0.0 + COOL 3.1 (KleidiCV VECTOR INTRINSICS)",
               bg=BG_COMPUTE, border=BD_COMPUTE, lw=2.4, tag="CORE WORKLOAD")

# 5 Visual Transformation Micro-Cards
tw = 15.0
th = 31.5
y_box = 53.5

# --- STEP 1: POSE & SCALE ---
x1 = 45.2
ax.add_patch(FancyBboxPatch((x1, y_box), tw, th, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_COMPUTE, lw=1.2, zorder=3))
ax.text(x1 + tw/2, y_box + th - 2.2, "1. Pose & Scale", ha="center", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x1 + tw/2, y_box + th - 4.2, "cv2.solvePnP", ha="center", fontsize=7.2, fontweight="bold", color=C_COMPUTE, zorder=4)

# Skewed perspective quad with 3D axes
quad = Polygon([[x1+2.5, y_box+17.5], [x1+12.5, y_box+19.5], [x1+13.5, y_box+7.0], [x1+1.5, y_box+9.0]],
               closed=True, facecolor="#F1F5F9", edgecolor="#64748B", lw=1.2, zorder=5)
ax.add_patch(quad)
ax.arrow(x1+4.0, y_box+11.0, 4.0, 1.0, head_width=0.8, color="#DC2626", zorder=6) # X
ax.arrow(x1+4.0, y_box+11.0, 1.0, 4.0, head_width=0.8, color="#16A34A", zorder=6) # Y
ax.arrow(x1+4.0, y_box+11.0, -1.5, -2.0, head_width=0.8, color="#2563EB", zorder=6) # Z

ax.text(x1 + tw/2, y_box + 4.8, "ChArUco Pose [R|t]\nHomography Matrix H",
        ha="center", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x1 + tw/2, y_box + 1.8, "Conditioned mm Scale",
        ha="center", fontsize=6.8, fontweight="bold", color=C_COMPUTE, zorder=4)


# --- STEP 2: METRIC RECTIFICATION ---
x2 = 61.7
ax.add_patch(FancyBboxPatch((x2, y_box), tw, th, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_COMPUTE, lw=1.2, zorder=3))
ax.text(x2 + tw/2, y_box + th - 2.2, "2. Rectification", ha="center", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x2 + tw/2, y_box + th - 4.2, "warpPerspective", ha="center", fontsize=7.2, fontweight="bold", color=C_COMPUTE, zorder=4)

ax.add_patch(Rectangle((x2+2.0, y_box+8.0), 11.0, 13.5, facecolor="#F8FAFC", edgecolor="#3B82F6", lw=1.2, zorder=5))
for i in range(1, 4):
    ax.plot([x2+2.0 + i*2.75, x2+2.0 + i*2.75], [y_box+8.0, y_box+21.5], color="#BFDBFE", lw=0.8, zorder=6)
for i in range(1, 5):
    ax.plot([x2+2.0, x2+13.0], [y_box+8.0 + i*2.7, y_box+8.0 + i*2.7], color="#BFDBFE", lw=0.8, zorder=6)
ax.plot([x2+7.5, x2+7.2, x2+7.8, x2+7.4], [y_box+19.5, y_box+15.5, y_box+11.5, y_box+9.0], color="#0F172A", lw=2.4, zorder=7)

ax.text(x2 + tw/2, y_box + 4.8, "Fronto-Parallel View\n17.4 px / mm Scale",
        ha="center", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x2 + tw/2, y_box + 1.8, "Zero Monocular Drift",
        ha="center", fontsize=6.8, fontweight="bold", color=C_COMPUTE, zorder=4)


# --- STEP 3: SEGMENTATION & SKELETON ---
x3 = 78.2
ax.add_patch(FancyBboxPatch((x3, y_box), tw, th, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_COMPUTE, lw=1.2, zorder=3))
ax.text(x3 + tw/2, y_box + th - 2.2, "3. Segmentation", ha="center", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x3 + tw/2, y_box + th - 4.2, "CLAHE + Thinning", ha="center", fontsize=7.2, fontweight="bold", color=C_COMPUTE, zorder=4)

ax.add_patch(Rectangle((x3+2.0, y_box+8.0), 11.0, 13.5, facecolor="#F1F5F9", edgecolor="#64748B", lw=1.2, zorder=5))
c_poly = Polygon([[x3+6.0, y_box+20.5], [x3+8.5, y_box+20.5], [x3+9.0, y_box+14.5], [x3+8.5, y_box+9.0],
                  [x3+6.0, y_box+9.0], [x3+6.5, y_box+14.5]], closed=True, facecolor="#334155", zorder=6)
ax.add_patch(c_poly)
ax.plot([x3+7.2, x3+7.7, x3+7.2], [y_box+19.5, y_box+14.5, y_box+10.0], color="#EF4444", lw=1.4, zorder=7)

ax.text(x3 + tw/2, y_box + 4.8, "Adaptive Threshold\nximgproc.thinning",
        ha="center", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x3 + tw/2, y_box + 1.8, "Medial Axis Skeleton S",
        ha="center", fontsize=6.8, fontweight="bold", color=C_COMPUTE, zorder=4)


# --- STEP 4: DISTANCE TRANSFORM METROLOGY ---
x4 = 94.7
ax.add_patch(FancyBboxPatch((x4, y_box), tw, th, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_COMPUTE, lw=1.2, zorder=3))
ax.text(x4 + tw/2, y_box + th - 2.2, "4. Distance Field", ha="center", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x4 + tw/2, y_box + th - 4.2, "distanceTransform", ha="center", fontsize=7.2, fontweight="bold", color=C_COMPUTE, zorder=4)

ax.add_patch(Rectangle((x4+2.0, y_box+8.0), 11.0, 13.5, facecolor="#0F172A", edgecolor="#38BDF8", lw=1.2, zorder=5))
ax.add_patch(Polygon([[x4+5.5, y_box+20.5], [x4+9.0, y_box+20.5], [x4+9.5, y_box+14.5], [x4+9.0, y_box+9.0],
                      [x4+5.5, y_box+9.0], [x4+6.0, y_box+14.5]], closed=True, facecolor="#0284C7", zorder=6))
ax.add_patch(Polygon([[x4+6.5, y_box+19.5], [x4+8.0, y_box+19.5], [x4+8.5, y_box+14.5], [x4+8.0, y_box+10.0],
                      [x4+6.5, y_box+10.0], [x4+7.0, y_box+14.5]], closed=True, facecolor="#FACC15", zorder=7))
ax.add_patch(Circle((x4+7.5, y_box+14.5), 1.5, facecolor="none", edgecolor="#EF4444", lw=1.2, ls="--", zorder=8))

ax.text(x4 + tw/2, y_box + 4.8, "Euclidean Distance L2\nRaw: w = 2 · DT(S)",
        ha="center", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x4 + tw/2, y_box + 1.8, "Normal Aperture Vector",
        ha="center", fontsize=6.8, fontweight="bold", color=C_COMPUTE, zorder=4)


# --- STEP 5: BIAS COMPENSATION & CERTIFIED MM ---
x5 = 111.2
ax.add_patch(FancyBboxPatch((x5, y_box), tw, th, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_COMPUTE, lw=1.2, zorder=3))
ax.text(x5 + tw/2, y_box + th - 2.2, "5. Bias Corrected", ha="center", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x5 + tw/2, y_box + th - 4.2, "-1.00 px Analytical", ha="center", fontsize=7.2, fontweight="bold", color=C_COMPUTE, zorder=4)

ax.add_patch(FancyBboxPatch((x5+1.5, y_box+9.0), 12.0, 11.5, boxstyle="round,pad=0.2",
                           facecolor="#ECFDF5", edgecolor="#10B981", lw=1.4, zorder=5))
ax.text(x5+tw/2, y_box+17.0, "CERTIFIED MM", fontsize=6.8, fontweight="heavy", color="#047857", ha="center", zorder=6)
ax.text(x5+tw/2, y_box+13.6, "0.34 mm", fontsize=11.0, fontweight="heavy", color=SOLID_BLACK, ha="center", zorder=6)
ax.text(x5+tw/2, y_box+10.8, "± 0.04 mm", fontsize=8.0, fontweight="bold", color="#059669", ha="center", zorder=6)

ax.text(x5 + tw/2, y_box + 4.8, "w = (w_raw - 1.00px) / s\nUncertainty Budget ±σ",
        ha="center", fontsize=7.0, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(x5 + tw/2, y_box + 1.8, "Quality Gate Certified",
        ha="center", fontsize=6.8, fontweight="bold", color="#059669", zorder=4)


# ─────────────────────────────────────────────────────────────
# 4. CENTER-BOTTOM PANEL: TIER 4 - BEDROCK AGENTIC TRIAGE
# ─────────────────────────────────────────────────────────────
draw_container(x=43.5, y=18.0, w=84.0, h=29.5,
               title="TIER 4: Bedrock Agentic Quality Gate & Triage Loop",
               subtitle="EVALUATES OBSERVATION VECTOR Ot  •  6-ACTION DISCRETE RE-SHOOT POLICY",
               bg=BG_AGENT, border=BD_AGENT, lw=2.2, tag="REASONING LOOP")

# Sub-Box 4A: Observation Vector
ax.add_patch(FancyBboxPatch((47.0, 19.5), 37.0, 20.0, boxstyle="round,pad=0.25",
                           facecolor="#FFFFFF", edgecolor=BD_AGENT, lw=1.2, zorder=3))
ax.text(48.5, 37.0, "Structured Observation Vector Ot", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)

ax.text(48.5, 34.0, "• Ncorners (ChArUco Marker Count)", fontsize=7.5, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(48.5, 31.5, "• Var_Lap (Laplacian Blur Variance)", fontsize=7.5, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(48.5, 29.0, "• px/mm (Effective Spatial Resolution)", fontsize=7.5, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(48.5, 26.5, "• θoblique (Surface Obliquity Angle)", fontsize=7.5, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(48.5, 24.0, "• fglare (Specular Glare Fraction)", fontsize=7.5, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(48.5, 21.0, "• Evaluates Quality Gate (px/mm ≥ 15)", fontsize=7.5, fontweight="bold", color=C_AGENT, zorder=4)

# Sub-Box 4B: 6-Action Space & Decision Logic
ax.add_patch(FancyBboxPatch((86.0, 19.5), 39.5, 20.0, boxstyle="round,pad=0.25",
                           facecolor="#FFFFFF", edgecolor=BD_AGENT, lw=1.2, zorder=3))
ax.text(87.5, 37.0, "Discrete 6-Action Space & Directives", fontsize=8.4, fontweight="bold", color=SOLID_BLACK, zorder=4)

ax.text(87.5, 34.0, "1. reshoot_steadier   (Motion blur detected)", fontsize=7.3, fontweight="bold", color="#B45309", zorder=4)
ax.text(87.5, 31.5, "2. move_closer        (px/mm below gate 15.0)", fontsize=7.3, fontweight="bold", color="#B45309", zorder=4)
ax.text(87.5, 29.0, "3. relight             (Severe specular glare / shadow)", fontsize=7.3, fontweight="bold", color="#B45309", zorder=4)
ax.text(87.5, 26.5, "4. reposition_marker  (Marker occlusion / high θ)", fontsize=7.3, fontweight="bold", color="#B45309", zorder=4)
ax.text(87.5, 24.0, "5. accept_with_widened_uncertainty", fontsize=7.3, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(87.5, 21.2, "6. abandon_and_log    (Unrecoverable geometry)", fontsize=7.3, fontweight="bold", color=SOLID_BLACK, zorder=4)


# ─────────────────────────────────────────────────────────────
# 5. RIGHT PANEL: TIER 5 - TEMPORAL RE-ID, STORAGE & ESCALATION
# ─────────────────────────────────────────────────────────────
draw_container(x=131.0, y=18.0, w=45.5, h=77.0,
               title="TIER 5: Re-ID, Audit & Alert",
               subtitle="OPENCV 5 LightGlue  •  DynamoDB  •  SNS EMAIL",
               bg=BG_STORAGE, border=BD_STORAGE, lw=2.2, tag="PERSISTENCE")

# Sub-Box 5A: Temporal Re-ID with LightGlue
ax.add_patch(FancyBboxPatch((134.0, 66.0), 40.5, 21.0, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_STORAGE, lw=1.2, zorder=3))
ax.text(135.5, 84.5, "Cross-Visit Joint Re-ID", fontsize=8.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 82.0, "ALIKED / DISK + LightGlueMatcher", fontsize=7.2, fontweight="bold", color=C_STORAGE, zorder=4)

# Dual patch matching graphic
ax.add_patch(Rectangle((136.5, 70.0), 15.0, 10.5, facecolor="#F1F5F9", edgecolor="#94A3B8", lw=0.8, zorder=5))
ax.text(144.0, 78.5, "Visit T0 (Archive)", fontsize=6.0, fontweight="bold", color=SOLID_BLACK, ha="center", zorder=6)
ax.plot([144.0, 144.0], [71.0, 77.0], color="#0F172A", lw=1.5, zorder=6)

ax.add_patch(Rectangle((158.0, 70.0), 15.0, 10.5, facecolor="#F1F5F9", edgecolor="#94A3B8", lw=0.8, zorder=5))
ax.text(165.5, 78.5, "Visit T1 (Current)", fontsize=6.0, fontweight="bold", color=SOLID_BLACK, ha="center", zorder=6)
ax.plot([165.5, 165.5], [71.0, 77.0], color="#0F172A", lw=1.5, zorder=6)

# LightGlue match lines
ax.plot([144.0, 165.5], [74.5, 74.5], color="#10B981", lw=1.2, ls=":", zorder=7)
ax.plot([144.0, 165.5], [72.5, 72.5], color="#10B981", lw=1.2, ls=":", zorder=7)

ax.text(135.5, 67.5, "• 42 Inliers (Conf > 0.88) -> Verified Same Joint",
        fontsize=7.2, fontweight="bold", color="#047857", zorder=4)


# Sub-Box 5B: DynamoDB + S3 Storage Ledger
ax.add_patch(FancyBboxPatch((134.0, 44.5), 40.5, 19.5, boxstyle="round,pad=0.3",
                           facecolor="#FFFFFF", edgecolor=BD_STORAGE, lw=1.2, zorder=3))
ax.text(135.5, 61.5, "DynamoDB Ledger & S3 Evidence", fontsize=8.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 58.7, "• Per-Joint Time-Series History Table", fontsize=7.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 56.2, "• Visit T0 (61d ago): 0.21 mm ± 0.03 mm", fontsize=7.4, fontweight="bold", color="#475569", zorder=4)
ax.text(135.5, 53.7, "• Visit T1 (Today):   0.34 mm (+62% Growth)", fontsize=7.4, fontweight="bold", color="#B91C1C", zorder=4)
ax.text(135.5, 51.2, "• Encrypted Redacted S3 Scans + Traces", fontsize=7.4, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 47.5, "• 25 GB Storage Always-Free Tier", fontsize=7.2, fontweight="bold", color=C_GATEWAY, zorder=4)


# Sub-Box 5C: Structural Engineer SNS Alert
ax.add_patch(FancyBboxPatch((134.0, 20.0), 40.5, 22.5, boxstyle="round,pad=0.3",
                           facecolor=BG_ALERT, edgecolor=BD_ALERT, lw=1.4, zorder=3))
ax.text(135.5, 39.8, "Structural Engineer Alert (SNS)", fontsize=8.6, fontweight="bold", color=C_ALERT, zorder=4)
ax.text(135.5, 37.1, "• Exceeds ACI 224R-01 Durability Limit", fontsize=7.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 34.6, "  (0.30 mm Threshold for Moist Air/Humidity)", fontsize=7.2, fontweight="bold", color="#991B1B", zorder=4)
ax.text(135.5, 31.8, "• Dispatches Automated SNS Email Package", fontsize=7.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 29.3, "• Prompts Formal On-Site Structural Audit", fontsize=7.6, fontweight="bold", color=SOLID_BLACK, zorder=4)
ax.text(135.5, 26.3, "• Strict Rule: Never Emits Safety Verdict", fontsize=7.6, fontweight="heavy", color=C_ALERT, zorder=4)
ax.text(135.5, 23.3, "  (Provides Durability Reference, Not Capacity)", fontsize=6.8, fontweight="bold", color=TEXT_MUTED, zorder=4)


# ─────────────────────────────────────────────────────────────
# 6. INTER-TIER DATAFLOW ARROWS & CONNECTORS
# ─────────────────────────────────────────────────────────────

# --- FLOW A: TIER 1 -> TIER 3 (Raw Stream Ingestion via Gateway) ---
draw_arrow((38.5, 73.0), (43.5, 73.0),
           label="TIER 2: HTTPS Gateway (t4g)", color=C_COMPUTE, lw=2.4,
           label_pos=(41.0, 76.0))

# --- FLOW B: TIER 3 -> TIER 4 (Observation Vector to Bedrock Agent) ---
draw_arrow((85.5, 51.0), (85.5, 47.5),
           label="Observation Ot [Blur, Res, Obliquity]", color=C_AGENT, lw=2.2,
           label_pos=(85.5, 49.25))

# --- FLOW C: TIER 4 -> TIER 1 (Closed-Loop Directive Feedback to HUD) ---
draw_arrow((43.5, 31.0), (38.5, 31.0),
           label="Agent Directive (WSS)", color=C_AGENT, lw=2.4,
           label_pos=(41.0, 33.8))

# --- FLOW D: TIER 1B -> TIER 1A (Human Operator Action) ---
draw_arrow((21.0, 58.0), (21.0, 62.0),
           label="Operator Adjusts Frame", color=C_EDGE, lw=2.2,
           label_pos=(21.0, 60.0))

# --- FLOW E: TIER 3 -> TIER 5 (Certified Measurement to Storage & Re-ID) ---
draw_arrow((127.5, 73.0), (134.0, 73.0),
           label="Certified mm", color=C_STORAGE, lw=2.4,
           label_pos=(129.25, 75.8))

# --- FLOW F: TIER 5B -> TIER 5C (Limit Exceedance to Engineer Alert) ---
draw_arrow((154.25, 44.5), (154.25, 42.5),
           label="Limit Exceeded (w > 0.30mm)", color=C_ALERT, lw=2.2,
           label_pos=(154.25, 43.5))


# ─────────────────────────────────────────────────────────────
# 7. BOTTOM BENCHMARK & REPRODUCIBILITY BANNER
# ─────────────────────────────────────────────────────────────
bot_y = 2.0
bot_h = 14.5
ax.add_patch(FancyBboxPatch((3.5, bot_y), 173.0, bot_h,
                           boxstyle="round,pad=0.4,rounding_size=1.8",
                           facecolor="#F8FAFC", edgecolor=SOLID_BLACK, lw=1.8, zorder=2))

ax.text(6.0, bot_y + bot_h - 2.8, "EVALUATION, BENCHMARKING & REPRODUCIBILITY SUITE (OpenCV 5 & COOL)",
        fontsize=10.8, fontweight="bold", color=SOLID_BLACK, zorder=4)

ax.text(6.0, bot_y + bot_h - 6.2,
        "•  [Workload Validation]  Stock OpenCV vs COOL KleidiCV on Graviton4 (c8g)  |  Accuracy Invariance Proof (Identical Numerics)  |  Latency, Throughput & Cost / 1k Frames",
        fontsize=9.0, fontweight="bold", color=SOLID_BLACK, zorder=4)

ax.text(6.0, bot_y + bot_h - 9.4,
        "•  [Metrology Corpora]  CrackForest (118) / Crack500 (3.3k) / DeepCrack (537)  |  Machined Slots & Calibrated Feeler Gauges  |  Agent Policy Ablation (P0 / P1 / P2)",
        fontsize=9.0, fontweight="bold", color=SOLID_BLACK, zorder=4)

ax.text(6.0, bot_y + bot_h - 12.6,
        "•  [Open Artifacts]  Full AMI IDs, COOL Build Flags, Raw Performance CSVs, and Agent Lab Decision Traces Shipped in Repository",
        fontsize=8.8, fontweight="bold", color=SOLID_BLACK, zorder=4)

# ─────────────────────────────────────────────────────────────
# SAVE & EXPORT
# ─────────────────────────────────────────────────────────────
plt.tight_layout(pad=0.3)
out_path = "f:/Projects/Prohori/grant/architecture.png"
plt.savefig(out_path, facecolor=BG, bbox_inches="tight", dpi=240)
plt.close()
print("Successfully generated publication-grade visual architecture diagram at:", out_path)
