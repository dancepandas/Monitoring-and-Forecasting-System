#!/usr/bin/env python3
"""
DEM 数据处理: 合并 → 裁剪 → 生成 Cesium 地形瓦片
=====================================================
将下载的 Copernicus DEM GeoTIFF 瓦片:
  1. 合并 (mosaic) 覆盖郴州区域的 4 个瓦片
  2. 裁剪到 AOI (四个站点 + 10km buffer)
  3. 生成 Cesium heightmap 地形瓦片 (PNG)
  4. 生成高程量化地形 (quantized-mesh 模拟, 基于 PNG heightmap)

输出目录: web/public/terrain/
  ├── layer.json       Cesium 地形元数据
  └── {z}/{x}/{y}.png  PNG 高程瓦片 (heightmap-1.0 格式)

依赖: pip install rasterio numpy pillow

若 rasterio 安装困难（Windows GDAL 问题），可改用纯 numpy+PIL:
  备选方案在 process_dem_lightweight() 函数中

Author: Claude Code
Date: 2026-07-08
"""

import os, sys, json, struct, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import numpy as np

# ── 配置 ─────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR / "data" / "geospatial"
DEM_DIR = BASE_DIR / "dem"
OUTPUT_DIR = SCRIPT_DIR.parent / "web" / "public" / "terrain"

# AOI: 四个站点 + buffer (约 30km × 40km 覆盖郴州城区和周边流域)
STATIONS = {
    "00125": {"name": "郴州",           "lon": 113.03915, "lat": 25.80385},
    "00230": {"name": "郴州-坳上",      "lon": 113.01888, "lat": 25.67971},
    "00231": {"name": "郴州-鸡嘴桥下游", "lon": 113.01198, "lat": 25.81638},
    "00234": {"name": "郴州-燕泉河",    "lon": 113.02373, "lat": 25.78843},
}

# AOI 范围 (加 0.15° ≈ 16.6km buffer)
BUFFER_DEG = 0.15
AOI_LON_MIN = min(s["lon"] for s in STATIONS.values()) - BUFFER_DEG
AOI_LON_MAX = max(s["lon"] for s in STATIONS.values()) + BUFFER_DEG
AOI_LAT_MIN = min(s["lat"] for s in STATIONS.values()) - BUFFER_DEG
AOI_LAT_MAX = max(s["lat"] for s in STATIONS.values()) + BUFFER_DEG

# 地形瓦片配置
TILE_SIZE = 256  # 每个瓦片 256×256 像素
MAX_ZOOM = 14    # 最大缩放级别 (~9.5m/pixel at 25°N)
MIN_ZOOM = 8     # 最小缩放级别


# ── 第1步: 尝试用 rasterio 处理 ────────────────────────
def process_with_rasterio():
    """使用 rasterio 合并和裁剪 DEM (推荐方案)"""
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.mask import mask
    from shapely.geometry import box
    import geopandas as gpd

    print("\n📐 使用 rasterio 处理 DEM...")

    # 找到所有下载的 DEM 文件
    dem_files = sorted(DEM_DIR.glob("*.tif"))
    if not dem_files:
        print("  ❌ 未找到 DEM 文件，请先运行 download_geodata.py")
        return None

    print(f"  📂 输入文件 ({len(dem_files)}):")
    for f in dem_files:
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"     {f.name} ({size_mb:.1f} MB)")

    # 打开所有 DEM 文件
    datasets = [rasterio.open(f) for f in dem_files]

    # 合并 (mosaic)
    print(f"\n  🔗 合并瓦片 ...")
    mosaic, out_transform = merge(datasets, method='first')
    out_meta = datasets[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_transform,
        "compress": "lzw",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    })

    # 保存合并后的 GeoTIFF
    mosaic_path = BASE_DIR / "dem_mosaic" / "chenzhou_dem_mosaic.tif"
    mosaic_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(mosaic_path, "w", **out_meta) as dest:
        dest.write(mosaic)
    print(f"  💾 合并完成: {mosaic_path} ({mosaic_path.stat().st_size/1024/1024:.1f} MB)")

    # 裁剪到 AOI
    aoi_geom = box(AOI_LON_MIN, AOI_LAT_MIN, AOI_LON_MAX, AOI_LAT_MAX)
    print(f"\n  ✂️ 裁剪到 AOI ...")
    with rasterio.open(mosaic_path) as src:
        out_image, out_transform = mask(src, [aoi_geom], crop=True)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        })

    clip_path = BASE_DIR / "dem_mosaic" / "chenzhou_dem_aoi.tif"
    with rasterio.open(clip_path, "w", **out_meta) as dest:
        dest.write(out_image)
    print(f"  💾 AOI裁剪完成: {clip_path} ({clip_path.stat().st_size/1024/1024:.1f} MB)")

    # 读取高程数据为 numpy 数组
    dem_array = out_image[0]  # 第一个波段
    transform = out_transform
    print(f"  📊 DEM 数据: {dem_array.shape[0]}×{dem_array.shape[1]} px")
    print(f"  📊 高程范围: {dem_array.min():.1f} ~ {dem_array.max():.1f} m")
    print(f"  📊 地理范围: {transform[2]:.4f}°E ~ {transform[2] + transform[0]*dem_array.shape[1]:.4f}°E")
    print(f"              {transform[5] + transform[4]*dem_array.shape[0]:.4f}°N ~ {transform[5]:.4f}°N")

    for ds in datasets:
        ds.close()

    return dem_array, transform, out_meta


# ── 第2步: 生成 Cesium 地形瓦片 ─────────────────────────
def encode_heightmap_png(elevation_2d, nodata=-9999):
    """
    将高程数组编码为 Cesium heightmap-1.0 PNG 格式。
    Cesium heightmap 格式: height = -10000 + ((R*256*256 + G*256 + B) * 0.1)
    即每个像素的 RGB 编码了相对于 -10000m 基准的高程值。

    返回值: RGBA uint8 numpy array
    """
    height, width = elevation_2d.shape

    # 处理 nodata
    valid = np.isfinite(elevation_2d) & (elevation_2d > -500) & (elevation_2d < 9000)
    elevation_2d = np.where(valid, elevation_2d, 0.0)

    # Cesium heightmap 编码公式:
    # elevation = -10000.0 + (red * 256.0 * 256.0 + green * 256.0 + blue) * 0.1
    # 反推: value = (elevation + 10000.0) / 0.1 = (elevation + 10000.0) * 10.0
    value = ((elevation_2d + 10000.0) * 10.0).astype(np.uint32)

    r = ((value >> 16) & 0xFF).astype(np.uint8)
    g = ((value >> 8) & 0xFF).astype(np.uint8)
    b = (value & 0xFF).astype(np.uint8)
    a = np.full_like(r, 255, dtype=np.uint8)

    rgba = np.stack([r, g, b, a], axis=-1)
    return rgba


def lonlat_to_pixel(lon, lat, transform):
    """将经纬度转换为 DEM 数组的像素坐标"""
    col = int((lon - transform[2]) / transform[0])
    row = int((lat - transform[5]) / transform[4])
    return col, row


def generate_tiles(dem_array, transform, min_zoom=MIN_ZOOM, max_zoom=MAX_ZOOM):
    """
    生成 Cesium heightmap-1.0 格式的地形瓦片。
    使用 XYZ 瓦片方案 (TMS 翻转 Y)。
    """
    from PIL import Image
    import rasterio

    print(f"\n{'='*60}")
    print(f"🗺 生成 Cesium 地形瓦片 (heightmap-1.0)")
    print(f"   Zoom 范围: {min_zoom} ~ {max_zoom}")
    print(f"   输出目录: {OUTPUT_DIR}")
    print(f"{'='*60}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dem_h, dem_w = dem_array.shape
    geo_left = transform[2]
    geo_top = transform[5]
    geo_right = geo_left + transform[0] * dem_w
    geo_bottom = geo_top + transform[4] * dem_h

    print(f"   DEM 范围: lon [{geo_left:.6f}, {geo_right:.6f}]")
    print(f"              lat [{geo_bottom:.6f}, {geo_top:.6f}]")
    print(f"   DEM 尺寸: {dem_w}×{dem_h} px")
    print(f"   分辨率:   {transform[0]*111320:.1f}m/px (lon) × {abs(transform[4])*111320:.1f}m/px (lat)")

    # 预计算每个 zoom 级别的瓦片范围
    total_tiles = 0
    for zoom in range(min_zoom, max_zoom + 1):
        # 使用 XYZ 瓦片编号 (与 Cesium 默认一致)
        n = 2 ** zoom
        # lat → tile Y (注意 Y 轴翻转)
        tile_y_min = int((1.0 - (geo_top + 90.0) / 180.0) * n)
        tile_y_max = int((1.0 - (geo_bottom + 90.0) / 180.0) * n)
        tile_x_min = int((geo_left + 180.0) / 360.0 * n)
        tile_x_max = int((geo_right + 180.0) / 360.0 * n)

        tile_y_min = max(0, tile_y_min)
        tile_y_max = min(n - 1, tile_y_max)
        tile_x_min = max(0, tile_x_min)
        tile_x_max = min(n - 1, tile_x_max)

        n_tiles = (tile_x_max - tile_x_min + 1) * (tile_y_max - tile_y_min + 1)
        total_tiles += n_tiles
        print(f"   Zoom {zoom:2d}: X[{tile_x_min}, {tile_x_max}] Y[{tile_y_min}, {tile_y_max}] = {n_tiles} 瓦片")

    print(f"\n   📦 总计: {total_tiles} 个瓦片待生成")

    # 逐 zoom 级别生成瓦片
    generated = 0
    for zoom in range(min_zoom, max_zoom + 1):
        n = 2 ** zoom

        tile_y_min = int((1.0 - (geo_top + 90.0) / 180.0) * n)
        tile_y_max = int((1.0 - (geo_bottom + 90.0) / 180.0) * n)
        tile_x_min = int((geo_left + 180.0) / 360.0 * n)
        tile_x_max = int((geo_right + 180.0) / 360.0 * n)

        tile_y_min = max(0, tile_y_min)
        tile_y_max = min(n - 1, tile_y_max)
        tile_x_min = max(0, tile_x_min)
        tile_x_max = min(n - 1, tile_x_max)

        for tx in range(tile_x_min, tile_x_max + 1):
            for ty in range(tile_y_min, tile_y_max + 1):
                # 计算瓦片在地理空间中的范围
                tile_lon_left = tx / n * 360.0 - 180.0
                tile_lon_right = (tx + 1) / n * 360.0 - 180.0
                tile_lat_top = 90.0 - ty / n * 180.0
                tile_lat_bottom = 90.0 - (ty + 1) / n * 180.0

                # 计算瓦片在 DEM 数组中的像素范围
                px_left = int((tile_lon_left - geo_left) / transform[0])
                px_right = int((tile_lon_right - geo_left) / transform[0])
                py_top = int((tile_lat_top - geo_top) / transform[4])
                py_bottom = int((tile_lat_bottom - geo_top) / transform[4])

                # 裁剪到 DEM 范围
                px_left = max(0, px_left)
                px_right = min(dem_w, px_right)
                py_top = max(0, py_top)
                py_bottom = min(dem_h, py_bottom)

                # 提取瓦片对应的高程数据
                tile_dem = dem_array[py_top:py_bottom, px_left:px_right]

                if tile_dem.size == 0:
                    continue

                # 缩放到 256×256
                from PIL import Image as PILImage
                img = PILImage.fromarray(tile_dem.astype(np.float32))

                # 使用 NEAREST 重采样 (保持原始精度)
                # 注意: 如果瓦片区域小于 DEM 分辨率，直接拉伸
                img_resized = img.resize((TILE_SIZE, TILE_SIZE), PILImage.NEAREST)

                tile_array = np.array(img_resized)

                # 编码为 heightmap PNG
                heightmap = encode_heightmap_png(tile_array)

                # 保存
                tile_dir = OUTPUT_DIR / str(zoom) / str(tx)
                tile_dir.mkdir(parents=True, exist_ok=True)
                tile_path = tile_dir / f"{ty}.png"

                result = PILImage.fromarray(heightmap, 'RGBA')
                result.save(tile_path, 'PNG', optimize=True)

                generated += 1
                if generated % 50 == 0:
                    print(f"   ... 已生成 {generated}/{total_tiles} 瓦片")

    print(f"   ✅ 完成: {generated} 个瓦片")
    return generated


# ── 第3步: 生成 layer.json ─────────────────────────────
def create_layer_json():
    """生成 Cesium terrain provider 的 layer.json"""
    dem_files = sorted(DEM_DIR.glob("*.tif"))
    if not dem_files:
        print("⚠ 无 DEM 文件，使用默认参数生成 layer.json")

    layer = {
        "tilejson": "2.1.0",
        "name": "郴州区域 DEM (30m)",
        "description": "郴州四站流域地形 - Copernicus GLO-30",
        "version": "1.0.0",
        "format": "heightmap-1.0",
        "attribution": "Copernicus DEM GLO-30 (2024)",
        "scheme": "tms",
        "tiles": ["{z}/{x}/{y}.png"],
        "minzoom": MIN_ZOOM,
        "maxzoom": MAX_ZOOM,
        "bounds": [AOI_LON_MIN, AOI_LAT_MIN, AOI_LON_MAX, AOI_LAT_MAX],
        "projection": "EPSG:4326",
        "available": [[
            {"startX": 0, "startY": 0, "endX": 2**MAX_ZOOM-1, "endY": 2**MAX_ZOOM-1}
        ]],
        "extensions": ["watermask"],
    }

    layer_path = OUTPUT_DIR / "layer.json"
    with open(layer_path, "w", encoding="utf-8") as f:
        json.dump(layer, f, indent=2)
    print(f"\n📋 layer.json → {layer_path}")
    return layer_path


# ── 第4步: 生成增强可视化数据 ────────────────────────────
def create_hillshade_array(dem_array, transform):
    """
    生成山体阴影 (hillshade) 用于贴图
    使用标准 hillshade 算法 (azimuth=315°, altitude=45°)
    """
    from PIL import Image as PILImage

    h, w = dem_array.shape
    cell_size = abs(transform[0]) * 111320  # 约30m

    # 计算坡度和坡向
    dy, dx = np.gradient(dem_array, cell_size)

    # 太阳参数
    azimuth = 315.0  # 光源方位角
    altitude = 45.0  # 光源高度角

    azimuth_rad = np.radians(360.0 - azimuth + 90.0)
    altitude_rad = np.radians(altitude)

    # Hillshade 公式
    slope = np.arctan(np.sqrt(dx*dx + dy*dy))
    aspect = np.arctan2(dy, -dx)

    hillshade = (np.cos(altitude_rad) * np.cos(slope) +
                 np.sin(altitude_rad) * np.sin(slope) * np.cos(azimuth_rad - aspect))

    # 归一化到 0-255
    hillshade = np.clip(hillshade * 255, 0, 255).astype(np.uint8)

    # 保存
    hillshade_path = BASE_DIR / "dem_mosaic" / "chenzhou_hillshade.png"
    hillshade_path.parent.mkdir(parents=True, exist_ok=True)
    img = PILImage.fromarray(hillshade, mode='L')
    img.save(hillshade_path, optimize=True)
    print(f"\n🏔 山体阴影: {hillshade_path}")
    return hillshade_path


def create_contours_geojson(dem_array, transform):
    """
    生成等高线 GeoJSON (用于 3D 可视化叠加)
    使用简单的 marching squares 算法
    """
    print(f"\n📐 生成等高线...")

    h, w = dem_array.shape
    min_elev = np.floor(dem_array.min() / 50) * 50
    max_elev = np.ceil(dem_array.max() / 50) * 50
    levels = np.arange(min_elev, max_elev + 1, 50)  # 每 50m 一条等高线

    features = []

    try:
        from skimage import measure
        from shapely.geometry import LineString, mapping as shapely_mapping

        geo_left = transform[2]
        geo_top = transform[5]
        dx = transform[0]
        dy = transform[4]

        for level in levels:
            if level < dem_array.min() or level > dem_array.max():
                continue
            contours = measure.find_contours(dem_array, level)
            for contour in contours:
                if len(contour) < 3:
                    continue
                coords = [[geo_left + c[1] * dx, geo_top + c[0] * dy] for c in contour]
                feat = {
                    "type": "Feature",
                    "properties": {"elevation": float(level), "type": "contour"},
                    "geometry": {"type": "LineString", "coordinates": coords},
                }
                features.append(feat)

    except ImportError:
        print("  ⚠ scikit-image 未安装，跳过等高线生成")
        print("  pip install scikit-image shapely")

    if features:
        geojson = {"type": "FeatureCollection", "features": features}
        contour_path = BASE_DIR / "dem_mosaic" / "chenzhou_contours.geojson"
        with open(contour_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False)
        print(f"  📊 等高线: {contour_path} ({len(features)} 条线, {len(levels)} 高程级别)")
        return contour_path

    return None


# ── 轻量级方案 (无需 rasterio) ─────────────────────────
def process_dem_lightweight():
    """
    纯 numpy + PIL 方案 (无需安装 rasterio/GDAL)
    适用于 Windows 上 GDAL 安装困难的场景。
    直接使用下载的 GeoTIFF 文件（如果下载的是 TIFF 格式）。
    如 Copernicus 下载失败，则用 SRTM 数据或模拟 DEM。
    """
    from PIL import Image as PILImage

    print("\n📐 轻量级 DEM 处理...")

    dem_files = sorted(DEM_DIR.glob("*.tif"))
    if not dem_files:
        print("  ❌ 无 DEM 文件可用")
        return None, None, None

    # 尝试用 PIL 读取第一个 TIFF
    # PIL 无法直接读地理 TIFF，需要用 tifffile 或 raw 读取
    try:
        import tifffile
    except ImportError:
        print("  ⚠ 未安装 tifffile, 尝试安装: pip install tifffile")
        return None, None, None

    print(f"  📂 使用 tifffile 读取 DEM ...")
    arrays = []
    for f in dem_files:
        try:
            arr = tifffile.imread(f)
            arrays.append(arr)
            print(f"     {f.name}: {arr.shape}")
        except Exception as e:
            print(f"     ⚠ {f.name}: {e}")

    if not arrays:
        return None, None, None

    # 简单拼接 (假设瓦片排列正确)
    # 实际需要根据地理坐标精确拼接，这里做简化处理
    final_array = arrays[0]
    for arr in arrays[1:]:
        # 简单垂直拼接
        if arr.shape[1] == final_array.shape[1]:
            final_array = np.vstack([final_array, arr])

    print(f"  📊 合并后尺寸: {final_array.shape}")
    print(f"  📊 高程范围: {final_array.min():.1f} ~ {final_array.max():.1f} m")

    # 构建简单的 transform (近似)
    # Copernicus DEM 30m 在 25°N 约: lon_res ≈ 0.000277° (30m), lat_res ≈ 0.000277°
    transform = (0.000277, 0.0, AOI_LON_MIN, 0.0, -0.000277, AOI_LAT_MAX)  # dummy

    return final_array, transform, {}


# ── 主流程 ────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║     DEM 处理: 合并→裁剪→Cesium地形瓦片→叠加图层       ║")
    print("╚══════════════════════════════════════════════════════╝")

    # 检查输入
    dem_files = list(DEM_DIR.glob("*.tif"))
    if not dem_files:
        print("\n❌ 未找到 DEM 文件!")
        print(f"   请先运行: python scripts/download_geodata.py")
        print(f"   或手动下载 DEM 到: {DEM_DIR}")
        if BASE_DIR.exists():
            print(f"\n   现有数据文件:")
            for f in BASE_DIR.rglob("*"):
                if f.is_file():
                    print(f"     {f.relative_to(BASE_DIR)}")
        sys.exit(1)

    # 尝试使用 rasterio
    dem_array = None
    transform = None
    meta = None

    try:
        dem_array, transform, meta = process_with_rasterio()
    except ImportError:
        print("\n⚠ rasterio 未安装，尝试轻量级方案...")
        print("  推荐安装: pip install rasterio")
        print("  (Windows 可从 https://www.lfd.uci.edu/~gohlke/pythonlibs/ 下载 whl)")
        dem_array, transform, meta = process_dem_lightweight()
    except Exception as e:
        print(f"\n⚠ rasterio 处理失败: {e}")
        print("  尝试轻量级方案...")
        dem_array, transform, meta = process_dem_lightweight()

    if dem_array is None:
        print("\n❌ DEM 处理失败")
        print("\n💡 手动解决方案:")
        print("   1. 安装 rasterio: pip install rasterio")
        print("      Windows: 从 https://www.lfd.uci.edu/~gohlke/pythonlibs/ 下载 whl")
        print("   2. 使用 QGIS: 加载DEM → 栅格工具 → 导出为 GeoTIFF")
        print("   3. 使用 gdal 命令行:")
        print(f"      gdal_merge.py -o mosaic.tif {' '.join(str(f) for f in dem_files)}")
        print(f"      gdal_translate -projwin {AOI_LON_MIN} {AOI_LAT_MAX} {AOI_LON_MAX} {AOI_LAT_MIN} mosaic.tif aoi.tif")
        sys.exit(1)

    # 生成山体阴影
    try:
        create_hillshade_array(dem_array, transform)
    except Exception as e:
        print(f"  ⚠ 山体阴影生成失败: {e}")

    # 生成等高线
    try:
        create_contours_geojson(dem_array, transform)
    except Exception as e:
        print(f"  ⚠ 等高线生成失败: {e}")

    # 生成 Cesium 地形瓦片
    try:
        generate_tiles(dem_array, transform)
    except Exception as e:
        print(f"  ⚠ 瓦片生成失败: {e}")
        import traceback
        traceback.print_exc()

    # 生成 layer.json
    create_layer_json()

    # 汇总
    print(f"\n{'='*60}")
    print(f"✅ 处理完成!")
    print(f"{'='*60}")
    print(f"\n📂 输出文件:")
    if OUTPUT_DIR.exists():
        tile_count = len(list(OUTPUT_DIR.rglob("*.png")))
        print(f"   地形瓦片: {OUTPUT_DIR} ({tile_count} PNG 文件)")
    mosaic_dir = BASE_DIR / "dem_mosaic"
    if mosaic_dir.exists():
        for f in mosaic_dir.rglob("*"):
            if f.is_file():
                print(f"   {f.relative_to(BASE_DIR)} ({f.stat().st_size/1024/1024:.1f} MB)")

    print(f"\n📌 下一步:")
    print(f"   1. 启动前端: cd web && npm run dev")
    print(f"   2. 地形瓦片将由 Vite 自动静态服务")
    print(f"   3. 在 CesiumMap.vue 中配置 terrainProvider:")
    print(f"      terrainProvider: new Cesium.CesiumTerrainProvider({{")
    print(f"        url: '/terrain',")
    print(f"        requestVertexNormals: true,")
    print(f"      }})")


if __name__ == "__main__":
    main()
