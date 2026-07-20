# -*- coding: utf-8 -*-
"""把大范围 water_system.geojson 裁剪到郴州四站周边并简化几何，
产出轻量级 chenzhou_hydro_simple.geojson 供前端水系地图渲染。

- 裁剪 bbox：覆盖四站 + 缓冲（lon 112.70-113.30, lat 25.45-26.05）
- 简化：Douglas-Peucker，容差 0.0015°（~150m），河流保留更多细节
- 河流(LineString)与水体(Polygon)分别保留，附带类型标签
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "public" / "geo" / "water_system.geojson"
OUT = ROOT / "web" / "public" / "geo" / "chenzhou_hydro_simple.geojson"

# 四站 bbox + 缓冲（站点 lon 113.01-113.04, lat 25.68-25.82）
BBOX = (112.70, 25.45, 113.30, 26.05)
SIMPLIFY_TOL = 0.0004   # ~45m，保留更多河道弯曲细节

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
            # 点到线段距离
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

def in_bbox(xy):
    return BBOX[0] <= xy[0] <= BBOX[2] and BBOX[1] <= xy[1] <= BBOX[3]

def walk_leaves(coords):
    """返回所有 [x,y] 叶子节点"""
    if not coords:
        return []
    if isinstance(coords[0], (int, float)):
        return [coords]
    out = []
    for c in coords:
        out.extend(walk_leaves(c))
    return out

def line_intersects_bbox(coords):
    # 若任一点在 bbox 内即视为相关（保守裁剪，保留跨越边界的河流）
    return any(in_bbox(p) for p in coords)

def simplify_geom(geom, tol):
    gtype = geom["type"]
    coords = geom["coordinates"]
    if gtype == "LineString":
        if not line_intersects_bbox(coords):
            return None
        return {"type": "LineString", "coordinates": dp_simplify(coords, tol)}
    if gtype == "MultiLineString":
        parts = [dp_simplify(l, tol) for l in coords if line_intersects_bbox(l)]
        parts = [p for p in parts if len(p) >= 2]
        if not parts:
            return None
        if len(parts) == 1:
            return {"type": "LineString", "coordinates": parts[0]}
        return {"type": "MultiLineString", "coordinates": parts}
    if gtype == "Polygon":
        rings = []
        ok = False
        for ring in coords:
            if any(in_bbox(p) for p in ring):
                ok = True
            r = dp_simplify(ring, tol)
            if len(r) >= 4:
                rings.append(r)
        if not ok or not rings:
            return None
        return {"type": "Polygon", "coordinates": rings}
    if gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = []
            ok = False
            for ring in poly:
                if any(in_bbox(p) for p in ring):
                    ok = True
                r = dp_simplify(ring, tol)
                if len(r) >= 4:
                    rings.append(r)
            if ok and rings:
                polys.append(rings)
        if not polys:
            return None
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}
        return {"type": "MultiPolygon", "coordinates": polys}
    return None

def main():
    print(f"reading {SRC.name} ...")
    data = json.loads(SRC.read_text(encoding="utf-8"))
    feats = data.get("features", [])
    print(f"source features: {len(feats)}")

    out_feats = []
    n_river = n_water = 0
    for f in feats:
        geom = f.get("geometry")
        if not geom:
            continue
        new_geom = simplify_geom(geom, SIMPLIFY_TOL)
        if not new_geom:
            continue
        props = dict(f.get("properties") or {})
        gt = new_geom["type"]
        # 分类：Polygon=水体块，LineString=河流线
        kind = "water" if "Polygon" in gt else "river"
        if kind == "water":
            n_water += 1
        else:
            n_river += 1
        props["_kind"] = kind
        out_feats.append({"type": "Feature", "properties": props, "geometry": new_geom})

    out = {"type": "FeatureCollection", "features": out_feats}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"out features: {len(out_feats)}  (rivers={n_river}, water={n_water})")
    print(f"wrote {OUT.name}  ({size_kb:.0f} KB)")

if __name__ == "__main__":
    main()
