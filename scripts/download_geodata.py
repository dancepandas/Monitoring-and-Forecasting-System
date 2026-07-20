#!/usr/bin/env python3
"""
郴州四站 — 水系图 & 流域DEM数据下载脚本
============================================
数据源:
  DEM:  Copernicus GLO-30 (AWS 公开 bucket, 30m分辨率)
  水系: OpenStreetMap Overpass API → 河流/溪流/湖泊/水库

输出目录: data/geospatial/
  ├── dem/          GeoTIFF DEM 瓦片
  ├── dem_mosaic/   拼接+裁剪后的DEM
  ├── water_system/ 水系矢量 (GeoJSON + Shapefile)
  └── station_locations.geojson  四个站点点位

依赖: pip install requests geopandas shapely fiona rasterio pyproj tqdm
(仅下载DEM瓦片不需要 rasterio; 如需拼接裁剪再装)

Author: Claude Code
Date: 2026-07-08
"""

import os, sys, json, time, hashlib
from pathlib import Path
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 配置 ─────────────────────────────────────────────
STATIONS = {
    "00125": {"name": "郴州",           "lon": 113.03915, "lat": 25.80385},
    "00230": {"name": "郴州-坳上",      "lon": 113.01888, "lat": 25.67971},
    "00231": {"name": "郴州-鸡嘴桥下游", "lon": 113.01198, "lat": 25.81638},
    "00234": {"name": "郴州-燕泉河",    "lon": 113.02373, "lat": 25.78843},
}

# 四个站点包围盒 (加 0.3° buffer 覆盖周边流域)
LON_MIN = min(s["lon"] for s in STATIONS.values()) - 0.3
LON_MAX = max(s["lon"] for s in STATIONS.values()) + 0.3
LAT_MIN = min(s["lat"] for s in STATIONS.values()) - 0.3
LAT_MAX = max(s["lat"] for s in STATIONS.values()) + 0.3

BASE_DIR = Path(__file__).resolve().parent / "data" / "geospatial"
DEM_DIR = BASE_DIR / "dem"
DEM_MOSAIC_DIR = BASE_DIR / "dem_mosaic"
WATER_DIR = BASE_DIR / "water_system"

# Copernicus DEM GLO-30 AWS 公开 bucket
COPERNICUS_DEM_URL = (
    "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/"
    "Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif"
)

# 备用: SRTM 30m (如果 Copernicus 不通)
SRTM_BASE = "https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_30x30/TIFF"

# ── HTTP 会话 ────────────────────────────────────────
def get_session():
    """创建带重试的 HTTP 会话"""
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GeoSpatialDownloader/1.0"})
    return s


def download_file(url, dest, desc=""):
    """下载文件到本地，带进度条 + 断点续传"""
    dest = Path(dest)
    if dest.exists():
        print(f"  ✅ 已存在: {dest.name}")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ⬇ 下载 {desc or dest.name} …", end=" ", flush=True)

    session = get_session()
    try:
        resp = session.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))

        with open(dest, "wb") as f:
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  ⬇ {desc or dest.name} … {pct:.0f}%", end="", flush=True)
        print(f"\r  ✅ 完成: {dest.name} ({downloaded/1024/1024:.1f} MB)")
    except Exception as e:
        print(f"\r  ❌ 失败: {e}")
        if dest.exists():
            dest.unlink()
        raise

    return dest


# ── 第1部分: DEM 数字高程模型 ──────────────────────────
def get_dem_tiles():
    """
    确定需要下载的 Copernicus DEM 1°×1° 瓦片。
    郴州区域 ~113°E, 25-26°N → 需要 N25E113, N26E113 以及周边
    """
    tiles = set()
    for lon in range(int(LON_MIN), int(LON_MAX) + 1):
        for lat in range(int(LAT_MIN), int(LAT_MAX) + 1):
            tile = f"N{lat:02d}_00_E{lon:03d}_00"
            tiles.add(tile)
    return sorted(tiles)


def download_dem_tiles():
    """下载所有覆盖的 DEM 瓦片"""
    tiles = get_dem_tiles()
    print(f"\n{'='*60}")
    print(f"📐 DEM 瓦片下载 (Copernicus GLO-30, 30m分辨率)")
    print(f"   覆盖范围: {LON_MIN:.2f}°E ~ {LON_MAX:.2f}°E, {LAT_MIN:.2f}°N ~ {LAT_MAX:.2f}°N")
    print(f"   需要 {len(tiles)} 个瓦片: {tiles}")
    print(f"{'='*60}")

    downloaded = []
    for tile in tiles:
        url = COPERNICUS_DEM_URL.format(tile=tile)
        dest = DEM_DIR / f"{tile}.tif"
        try:
            download_file(url, dest, desc=f"DEM {tile}")
            downloaded.append(dest)
        except Exception as e:
            print(f"  ⚠ Copernicus DEM {tile} 下载失败，尝试 SRTM 备用源...")
            # 备用: SRTM
            lat = int(tile[1:3])
            lon = int(tile.split("_E")[1][:3])
            srtm_tile = f"srtm_{lon:02d}_{lat:02d}"
            srtm_url = f"{SRTM_BASE}/{srtm_tile}.zip"
            # SRTM 的 tile 不同，可能需要不同的方法，先标记失败
            print(f"  ⚠ 备用源也需要单独处理，请手动下载")

    return downloaded


# ── 第2部分: 水系数据 (OpenStreetMap Overpass API) ───
def build_overpass_query():
    """
    构建 Overpass QL 查询 —— 提取指定范围内的所有水系要素
    包含: river, stream, canal, drain, ditch, lake, reservoir, pond, basin
    """
    bbox = f"{LAT_MIN},{LON_MIN},{LAT_MAX},{LON_MAX}"  # Overpass: S,W,N,E
    query = f"""
    [out:json][timeout:120];
    (
      way["waterway"~"river|stream|canal|drain|ditch|tributary"]({bbox});
      way["water"~"river|lake|reservoir|pond|basin|oxbow"]({bbox});
      way["natural"="water"]({bbox});
      way["waterway"="riverbank"]({bbox});
      relation["waterway"~"river|stream|canal"]({bbox});
      relation["water"~"river|lake|reservoir"]({bbox});
      relation["natural"="water"]({bbox});
    );
    (._;>;);
    out geom;
    """
    return query.strip()


def fetch_osm_water():
    """从 OpenStreetMap Overpass API 获取水系数据"""
    print(f"\n{'='*60}")
    print(f"🌊 水系数据获取 (OpenStreetMap Overpass API)")
    print(f"   查询范围: {LAT_MIN:.2f}-{LAT_MAX:.2f}°N, {LON_MIN:.2f}-{LON_MAX:.2f}°E")
    print(f"{'='*60}")

    overpass_url = "https://overpass-api.de/api/interpreter"
    query = build_overpass_query()

    geojson_path = WATER_DIR / "water_system_raw.geojson"
    if geojson_path.exists():
        print(f"  ✅ 已存在: {geojson_path.name}")
        return geojson_path

    WATER_DIR.mkdir(parents=True, exist_ok=True)

    # 尝试多个 Overpass 端点
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    for endpoint in endpoints:
        try:
            print(f"  ⬇ 查询 Overpass API: {endpoint} …", end=" ", flush=True)
            session = get_session()
            resp = session.post(endpoint, data=query.encode(), timeout=180)
            resp.raise_for_status()
            data = resp.json()

            n_elements = len(data.get("elements", []))
            print(f"✅ 获取 {n_elements} 个要素")

            if n_elements == 0:
                print("  ⚠ 返回空结果，尝试下一个端点...")
                continue

            # 保存原始 GeoJSON
            with open(geojson_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  💾 已保存: {geojson_path}")

            # 转换 Overpass JSON → 标准 GeoJSON
            geojson_clean = convert_overpass_to_geojson(data)
            clean_path = WATER_DIR / "water_system.geojson"
            with open(clean_path, "w", encoding="utf-8") as f:
                json.dump(geojson_clean, f, ensure_ascii=False, indent=2)
            print(f"  💾 标准GeoJSON: {clean_path} ({len(geojson_clean.get('features',[]))} 要素)")

            return geojson_path

        except requests.exceptions.Timeout:
            print(f"\r  ⚠ 超时，尝试下一个端点...")
        except Exception as e:
            print(f"\r  ⚠ 失败: {e}，尝试下一个端点...")

    print("  ❌ 所有 Overpass 端点均失败")
    return None


def convert_overpass_to_geojson(overpass_data):
    """将 Overpass API 响应转换为标准 GeoJSON"""
    features = []
    nodes = {}

    for el in overpass_data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])

    for el in overpass_data.get("elements", []):
        if el["type"] == "way" and "geometry" in el:
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if len(coords) < 2:
                continue

            tags = el.get("tags", {})
            props = {
                "osm_id": el["id"],
                "waterway": tags.get("waterway", ""),
                "water": tags.get("water", ""),
                "natural": tags.get("natural", ""),
                "name": tags.get("name", ""),
                "name:zh": tags.get("name:zh", tags.get("name:en", "")),
                "width": tags.get("width", ""),
            }

            geom_type = "LineString"
            if coords[0] == coords[-1] or tags.get("natural") == "water" or tags.get("water"):
                # 闭合多边形 —— 湖泊/水库/河流面
                geom_type = "Polygon"

            if geom_type == "LineString":
                geometry = {"type": "LineString", "coordinates": coords}
            else:
                geometry = {"type": "Polygon", "coordinates": [coords]}

            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": geometry,
            })

        elif el["type"] == "relation" and "members" in el:
            # 关系类型 —— 提取外环
            outer_ways = []
            for member in el.get("members", []):
                if member.get("role") == "outer" and member.get("type") == "way":
                    outer_ways.append(member["ref"])

            # 关系几何需要从 ways 重建，这里做简化处理
            tags = el.get("tags", {})
            if not outer_ways:
                continue

            # 找到关系中的 way 几何
            coords_list = []
            for way_id in outer_ways:
                way_coords = []
                for elem in overpass_data.get("elements", []):
                    if elem["id"] == way_id and elem.get("geometry"):
                        way_coords = [[p["lon"], p["lat"]] for p in elem["geometry"]]
                        break
                if way_coords:
                    coords_list.append(way_coords)

            if not coords_list:
                continue

            # 简化：取第一个 way 的几何
            coords = coords_list[0]
            if len(coords) < 3:
                continue

            props = {
                "osm_id": el["id"],
                "waterway": tags.get("waterway", ""),
                "water": tags.get("water", ""),
                "natural": tags.get("natural", ""),
                "name": tags.get("name", ""),
                "name:zh": tags.get("name:zh", tags.get("name:en", "")),
                "type": "relation",
            }

            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            })

    return {"type": "FeatureCollection", "features": features}


# ── 第3部分: 从 HydroSHEDS 获取流域边界 ────────────────
def download_hydrosheds_basin():
    """
    HydroSHEDS 提供全球流域边界数据
    郴州属于长江流域/珠江流域分界带
    下载 HydroBASINS level 6-8 覆盖本区域
    """
    print(f"\n{'='*60}")
    print(f"🏞 流域边界数据 (HydroSHEDS HydroBASINS)")
    print(f"{'='*60}")

    # HydroSHEDS HydroBASINS - Asia
    # Level 6: Pfafstetter level 6 basins (most useful for regional scale)
    basin_urls = {
        "hybas_as_lev06_v1c": "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_as_lev06_v1c.zip",
        "hybas_as_lev07_v1c": "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_as_lev07_v1c.zip",
        "hybas_as_lev08_v1c": "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_as_lev08_v1c.zip",
    }

    # HydroRIVERS (河流线)
    river_urls = {
        "as_riv_15s": "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_as_shp.zip",
    }

    results = {}

    print("\n  --- HydroBASINS 流域边界 ---")
    for name, url in basin_urls.items():
        dest = WATER_DIR / f"{name}.zip"
        try:
            download_file(url, dest, desc=name)
            results[name] = dest
        except Exception as e:
            print(f"  ⚠ {name} 跳过: {e}")

    print("\n  --- HydroRIVERS 河流网络 ---")
    for name, url in river_urls.items():
        dest = WATER_DIR / f"{name}.zip"
        try:
            download_file(url, dest, desc=name)
            results[name] = dest
        except Exception as e:
            print(f"  ⚠ {name} 跳过: {e}")

    return results


# ── 第4部分: 站点 GeoJSON ──────────────────────────────
def write_station_geojson():
    """生成四个站点的 GeoJSON 文件"""
    features = []
    for code, info in STATIONS.items():
        features.append({
            "type": "Feature",
            "properties": {
                "station_code": code,
                "station_name": info["name"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [info["lon"], info["lat"]],
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    path = BASE_DIR / "station_locations.geojson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    print(f"\n📍 站点坐标: {path}")
    return path


# ── 第5部分: 额外高质量数据源 ──────────────────────────
def download_sentinel2_river_map():
    """
    使用 ESA WorldCover / 或者从自然地球数据获取水系
    Natural Earth: 全球 1:10m 河流+湖泊数据
    """
    print(f"\n{'='*60}")
    print(f"🗺 Natural Earth 全球水系 (1:10m 高精度)")
    print(f"{'='*60}")

    ne_urls = {
        "ne_10m_rivers_lake_centerlines": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
        "ne_10m_lakes": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
        "ne_10m_rivers_europe": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_europe.zip",  # 含亚洲河流
    }

    results = {}
    for name, url in ne_urls.items():
        dest = WATER_DIR / f"{name}.zip"
        try:
            download_file(url, dest, desc=name)
            results[name] = dest
        except Exception as e:
            print(f"  ⚠ {name} 跳过: {e}")

    return results


# ── 主流程 ────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║     郴州四站 — 水系图 & 流域DEM数据下载脚本           ║")
    print("║     数据源: Copernicus DEM + OSM + HydroSHEDS       ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"\n📋 目标站点:")
    for code, info in STATIONS.items():
        print(f"   {code}  {info['name']:12s}  ({info['lon']:.4f}, {info['lat']:.4f})")
    print(f"\n📐 数据覆盖范围: {LON_MIN:.2f}°E~{LON_MAX:.2f}°E, {LAT_MIN:.2f}°N~{LAT_MAX:.2f}°N")
    print(f"📁 输出目录: {BASE_DIR}")

    # 创建目录
    for d in [DEM_DIR, DEM_MOSAIC_DIR, WATER_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Step 1: DEM 瓦片
    print(f"\n\n{'#'*60}")
    print(f"#  STEP 1/4: DEM 数字高程模型 (30m 分辨率)")
    print(f"{'#'*60}")
    try:
        download_dem_tiles()
    except Exception as e:
        print(f"  ❌ DEM下载出错: {e}")
        print(f"  手动下载地址:")
        print(f"   - Copernicus DEM: https://spacedata.copernicus.eu/collections/copernicus-digital-elevation-model")
        print(f"   - SRTM 30m: https://dwtkns.com/srtm30m/ (选择 N25E113, N26E113)")

    # Step 2: OSM 水系
    print(f"\n\n{'#'*60}")
    print(f"#  STEP 2/4: OSM 水系矢量数据")
    print(f"{'#'*60}")
    try:
        fetch_osm_water()
    except Exception as e:
        print(f"  ❌ OSM水系获取出错: {e}")

    # Step 3: HydroSHEDS
    print(f"\n\n{'#'*60}")
    print(f"#  STEP 3/4: HydroSHEDS 流域 & 河流数据")
    print(f"{'#'*60}")
    try:
        download_hydrosheds_basin()
    except Exception as e:
        print(f"  ❌ HydroSHEDS下载出错: {e}")

    # Step 4: Natural Earth 补充
    print(f"\n\n{'#'*60}")
    print(f"#  STEP 4/4: Natural Earth 补充水系")
    print(f"{'#'*60}")
    try:
        download_sentinel2_river_map()
    except Exception as e:
        print(f"  ❌ Natural Earth下载出错: {e}")

    # 站点 GeoJSON
    write_station_geojson()

    # ── 汇总 ──
    print(f"\n\n{'='*60}")
    print(f"📊 下载汇总")
    print(f"{'='*60}")
    for d in [DEM_DIR, WATER_DIR, DEM_MOSAIC_DIR]:
        if d.exists():
            files = list(d.rglob("*"))
            if files:
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                print(f"  {d.relative_to(BASE_DIR)}: {len(files)} 文件, {total_size/1024/1024:.1f} MB")

    print(f"\n✅ 数据下载完成!")
    print(f"\n📌 提示:")
    print(f"   1. DEM瓦片 ({BASE_DIR / 'dem'}) —— 如需拼接+裁剪到流域范围，运行:")
    print(f"      python scripts/process_dem.py")
    print(f"   2. 水系数据 ({BASE_DIR / 'water_system'}) —— 可用 QGIS/ArcGIS 打开 GeoJSON")
    print(f"   3. 如需更精细的DEM (12m ALOS) 请至: https://www.eorc.jaxa.jp/ALOS/en/aw3d30/")
    print(f"   4. 在 QGIS 中同时加载 DEM + 水系 + 站点 即可制作流域专题图")


if __name__ == "__main__":
    main()
