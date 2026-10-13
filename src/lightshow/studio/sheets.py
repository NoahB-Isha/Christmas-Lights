"""
sheets.py -- printable placement sheets: one PDF page per prop group, top-down,
showing where every prop goes (inches / feet), its silhouette, controller and
port, and the distances between neighbours. Page 1 is the whole course.

    placement_pdf(layout, project, "out/studio/placement.pdf")

Needs matplotlib (pip install matplotlib).
"""

import math, os, time
import numpy as np


def _ascii(s):
    return "".join(ch for ch in str(s) if ord(ch) < 0x2E80)      # drop CJK (号) so any PDF font renders


def placement_pdf(layout, project, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Rectangle

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    groups = layout.groups
    cards = project.d.get("cards", {})

    def gcolor(gid):
        return (groups.get(gid) or {}).get("color", "#888888")

    def draw_map(ax, props, title, show_ctrl=True, detail=True, xwin=None):
        if not props:
            ax.text(0.5, 0.5, "no props", ha="center", transform=ax.transAxes); return
        xs = [p.x for p in props]; ys = [p.y for p in props]
        half = max(p.shape()["w"] for p in props) / 2 + 24
        x0, x1 = min(xs) - half, max(xs) + half
        if xwin:
            x0, x1 = xwin
        y0, y1 = min(ys) - 70, max(ys) + 95
        for cid, c in layout.controllers.items():
            if show_ctrl and c.get("x") is not None and any(p.controller == cid for p in props):
                x0 = min(x0, c["x"] - 20); x1 = max(x1, c["x"] + 20); y0 = min(y0, c["y"] - 30); y1 = max(y1, c["y"] + 20)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
        # grid every 5 ft
        for gx in np.arange(math.floor(x0 / 60) * 60, x1 + 60, 60):
            ax.axvline(gx, color="#e6e6e6", lw=0.5, zorder=0)
        for gy in np.arange(math.floor(y0 / 60) * 60, y1 + 60, 60):
            ax.axhline(gy, color="#e6e6e6", lw=0.5, zorder=0)
        ax.set_xlabel("x (inches; grid = 5 ft)  →  car direction / right"); ax.set_ylabel("y (inches)")
        ax.set_title(title, fontsize=13, loc="left")
        # controllers + cables
        if show_ctrl:
            for cid, c in layout.controllers.items():
                mine = [p for p in props if p.controller == cid]
                if not mine or c.get("x") is None:
                    continue
                ax.add_patch(Rectangle((c["x"] - 9, c["y"] - 6), 18, 12, fc="#333", ec=gcolor(c.get("group", mine[0].group)), lw=1.5, zorder=3))
                ax.text(c["x"], c["y"] - 10, cards.get(cid, {}).get("sd_label", cid) if cards.get(cid, {}).get("sd_label", cid) != cid else cid,
                        ha="center", va="top", fontsize=7, color="#333", family="monospace")
                for p in mine:
                    ax.plot([c["x"], p.x], [c["y"], p.y], color="#bbb", lw=0.6, ls=":", zorder=1)
        # props: footprint line + silhouette + label
        for p in props:
            s = p.shape(); col = gcolor(p.group)
            a = math.radians(p.rot); hw = s["w"] / 2
            ax.plot([p.x - hw * math.cos(a), p.x + hw * math.cos(a)], [p.y - hw * math.sin(a), p.y + hw * math.sin(a)], color=col, lw=3, zorder=4, solid_capstyle="round")
            fx, fy = math.sin(a), -math.cos(a)                      # panel faces -y at rot 0
            ax.annotate("", xy=(p.x + fx * 14, p.y + fy * 14), xytext=(p.x, p.y), arrowprops=dict(arrowstyle="->", color=col, lw=1), zorder=4)
            if detail:
                # silhouette above the footprint (~26 in tall); names alternate high / low so neighbours don't collide
                loc = p.local(); sc = 26.0 / max(s["h"], 1e-3)
                ax.scatter(p.x + loc[:, 0] * sc * 0.8, p.y + 24 + loc[:, 1] * sc, s=1.2, color=col, zorder=5, linewidths=0)
                k = sorted(props, key=lambda q: q.x).index(p)
                lab = f"{p.id}  {_ascii(p.label)}".strip()
                ax.text(p.x, p.y + 24 + 26 + (6 if k % 2 == 0 else 20), lab, ha="center", va="bottom", fontsize=6.5, zorder=6)
                if p.controller:
                    ax.text(p.x, p.y - 8, f"{p.controller}:{p.port}", ha="center", va="top", fontsize=6.5, family="monospace", color="#333", zorder=6)
            else:
                ax.text(p.x, p.y + 8, p.id, ha="center", va="bottom", fontsize=5.5, zorder=6)
        # neighbour distances along x
        if detail:
            order = sorted(props, key=lambda p: p.x)
            for a_, b_ in zip(order[:-1], order[1:]):
                d = math.hypot(b_.x - a_.x, b_.y - a_.y)
                mx, my = (a_.x + b_.x) / 2, (a_.y + b_.y) / 2
                ax.plot([a_.x, b_.x], [a_.y, b_.y], color="#999", lw=0.5, zorder=2)
                ax.text(mx, my - 26, f"{d / 12:.1f} ft", ha="center", va="top", fontsize=6.5, color="#555", zorder=6,
                        bbox=dict(fc="white", ec="none", pad=0.5))

    with PdfPages(path) as pdf:
        # page 1: whole course
        fig = plt.figure(figsize=(11, 8.5))
        ax = fig.add_axes([0.05, 0.12, 0.92, 0.8])
        draw_map(ax, layout.props, f"Whole course — {len(layout.props)} props, {len(groups)} groups   ({stamp})", show_ctrl=False, detail=False)
        leg = "   ".join(f"■ {_ascii(g.get('label', gid))}" for gid, g in groups.items())
        fig.text(0.05, 0.04, leg, fontsize=9)
        for k, (gid, g) in enumerate(groups.items()):
            fig.text(0.05 + k * 0.0, 0.04, "", color=gcolor(gid))
        pdf.savefig(fig); plt.close(fig)
        # one page per group: map on top, table below
        for gid, g in groups.items():
            props = sorted(layout.in_group(gid), key=lambda p: p.x)
            fig = plt.figure(figsize=(11, 8.5))
            px = sum(p.n for p in props)
            title = f"{_ascii(g.get('label', gid))} — {len(props)} props, {px:,} px   ({stamp})"
            # a long row would squash to a line at equal aspect: wrap it into strips
            if props:
                xs = [p.x for p in props]; span = max(xs) - min(xs) + 120
                nstrips = int(np.clip(math.ceil(span / 420), 1, 4))
                edges = np.linspace(min(xs) - 60, max(xs) + 60, nstrips + 1)
                h = 0.52 / nstrips
                for k in range(nstrips):
                    ax = fig.add_axes([0.05, 0.44 + (nstrips - 1 - k) * h, 0.92, h - 0.02])
                    strip = [p for p in props if edges[k] - 1 <= p.x <= edges[k + 1] + 1]
                    draw_map(ax, strip or props[:1], title if k == 0 else "", xwin=(edges[k], edges[k + 1]))
                    if k < nstrips - 1:
                        ax.set_xlabel("")
            else:
                ax = fig.add_axes([0.05, 0.42, 0.92, 0.52]); draw_map(ax, props, title)
            axt = fig.add_axes([0.05, 0.03, 0.92, 0.31]); axt.axis("off")
            rows = [[p.id, _ascii(p.label)[:26], p.controller or "—", p.port or "", str(p.n), f"{p.x:.0f}", f"{p.y:.0f}", f"{p.z:.0f}", f"{p.rot:.0f}°",
                     "yes" if p.mirror else ""] for p in props]
            if rows:
                tbl = axt.table(cellText=rows, colLabels=["prop", "name", "controller", "port", "px", "x in", "y in", "z in", "rot", "mirror"],
                                loc="upper center", cellLoc="left", colLoc="left")
                tbl.auto_set_font_size(False); tbl.set_fontsize(6.5 if len(rows) > 14 else 7.5); tbl.scale(1, 1.05 if len(rows) > 14 else 1.25)
                for (r, c), cell in tbl.get_celld().items():
                    cell.set_edgecolor("#cccccc")
                    if r == 0:
                        cell.set_facecolor("#eeeeee"); cell.set_text_props(weight="bold")
            cids = sorted({p.controller for p in props if p.controller})
            fig.text(0.05, 0.352, "Cards: " + ", ".join(f"{c} (SD “{cards.get(c, {}).get('sd_label', c)}”)" for c in cids) if cids else "Cards: none assigned", fontsize=8, color="#333")
            pdf.savefig(fig); plt.close(fig)
    return path
