# -*- coding: utf-8 -*-
"""把 DataV 郴州市行政边界 431000_full.json 简化为轻量
chenzhou_admin.geojson，供水系图作为「底层行政底图」渲染
（区县边界 + 名称，垫在水系之下）。"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "public" / "geo" / "431000_full.json"
OUT = ROOT / "web" / "public" / "geo" / "chenzhou_admin.geojson"

SIMPLIFY_TOL = 0.0008   # ~90m，行政区边界可略粗于河道


def dp_simplify(coords, tol):
    """Douglas-Peucker（保留首尾）。coords: [[x,y],...]"""
    if len(coords) < 3:
        return coords
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = coords[i]; bx, by = coords[j]
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) or 1.0
        maxd, idx = tol, -1
        for k in range(i + 1, j):
            px, py = coords[k]
            t = ((px - ax) * dx + (py - ay) * dy) / L
            t = max(0, min(1, t))
            cx, cy = ax + t * dx, ay + t * dy
            d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            if d > maxd:
                maxd, idx = d, k
        if idx > 0:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [coords[i] for i in range(len(coords)) if keep[i]]


def simplify_multipoly(coords, tol):
    out = []
    for poly in coords:
        rings = []
        for ring in poly:
            r = dp_simplify([c[:2] for c in ring], tol)
            if len(r) >= 4:
                rings.append(r)
        if rings:
            out.append(rings)
    return out


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    out_feats = []
    for f in data.get("features", []):
        g = f.get("geometry") or {}
        props = dict(f.get("properties") or {})
        if g.get("type") == "Polygon":
            polys = [g["coordinates"]]
        elif g.get("type") == "MultiPolygon":
            polys = g["coordinates"]
        else:
            continue
        polys = simplify_multipoly(polys, SIMPLIFY_TOL)
        if not polys:
            continue
        geom = ({"type": "Polygon", "coordinates": polys[0]}
                if len(polys) == 1
                else {"type": "MultiPolygon", "coordinates": polys})
        out_feats.append({
            "type": "Feature",
            "properties": {k: props.get(k) for k in ("name", "adcode", "center", "level")},
            "geometry": geom,
        })

    out = {"type": "FeatureCollection", "features": out_feats}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out_feats)} districts -> {OUT.name} ({OUT.stat().st_size / 1024:.0f} KB)")
    for fe in out_feats:
        print("  -", fe["properties"].get("name"), fe["properties"].get("adcode"),
              fe["properties"].get("center"), fe["geometry"]["type"])


if __name__ == "__main__":
    main()
