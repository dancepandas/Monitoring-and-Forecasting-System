#!/usr/bin/env python3
"""把 DEM + OSM 水系烘焙成 3D 地形 GLB 模型。

流程: 读 DEM 4 瓦片 → 拼 mosaic → 裁 AOI → 降采样 →
      光栅化水系 → 顶点着色(高程渐变+河道蓝) → trimesh 导出 GLB + meta。
"""
import json
import numpy as np
from PIL import Image
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEM_DIR = ROOT / 'scripts' / 'data' / 'geospatial' / 'dem'
WATER_GEOJSON = ROOT / 'web' / 'public' / 'geo' / 'water_system.geojson'
OUT_DIR = ROOT / 'web' / 'public' / 'models'
OUT_GLB = OUT_DIR / 'terrain.glb'
OUT_META = OUT_DIR / 'terrain_meta.json'

AOI = {'west': 112.88, 'east': 113.19, 'south': 25.60, 'north': 25.92}
GRID_SIZE = 600
EXAGGERATION = 10.0

COLOR_LOW = np.array([0x0f, 0x2a, 0x38], dtype=np.float32)
COLOR_HIGH = np.array([0x2d, 0x5a, 0x6b], dtype=np.float32)
COLOR_WATER = np.array([0x3b, 0x82, 0xf6], dtype=np.float32)

# Copernicus 瓦片 → (lat, lon) 左下角
TILES = {
    'N25_00_E112_00': (25, 112), 'N25_00_E113_00': (25, 113),
    'N26_00_E112_00': (26, 112), 'N26_00_E113_00': (26, 113),
}


def load_dem_mosaic():
    """读 4 个 1°×1° 瓦片拼成 2°×2° mosaic。
    返回 (array[7200,7200] float32, {'west','east','south','north'})。
    mosaic 行0=北(lat27), 列0=西(lon112)。
    """
    tile_h = tile_w = 3600
    mosaic = np.zeros((tile_h * 2, tile_w * 2), dtype=np.float32)
    mosaic[:] = np.nan
    for fname, (lat, lon) in TILES.items():
        path = DEM_DIR / f'{fname}.tif'
        if not path.exists():
            raise FileNotFoundError(f'缺少 DEM 瓦片: {path}')
        arr = np.array(Image.open(path), dtype=np.float32)
        # lat=26 在上(行0), lat=25 在下(行1); lon=112 在左(列0), lon=113 在右(列1)
        row = 0 if lat == 26 else 1
        col = 0 if lon == 112 else 1
        mosaic[row*tile_h:(row+1)*tile_h, col*tile_w:(col+1)*tile_w] = arr
    bounds = {'west': 112.0, 'east': 114.0, 'south': 25.0, 'north': 27.0}
    return mosaic, bounds


def crop_aoi(mosaic, mosaic_bounds, aoi):
    """从 mosaic 裁出 AOI。mosaic 行0=北。
    返回 array[H,W] float32 (AOI 的高程, 行0=北)。"""
    mb = mosaic_bounds
    h, w = mosaic.shape
    # 经度 → 列
    x0 = int((aoi['west'] - mb['west']) / (mb['east'] - mb['west']) * w)
    x1 = int((aoi['east'] - mb['west']) / (mb['east'] - mb['west']) * w)
    # 纬度 → 行 (行0=北, 即 north)
    y0 = int((mb['north'] - aoi['north']) / (mb['north'] - mb['south']) * h)
    y1 = int((mb['north'] - aoi['south']) / (mb['north'] - mb['south']) * h)
    return mosaic[y0:y1, x0:x1]


def downsample(arr, size):
    """降采样到 size×size (PIL NEAREST 保持精度)。"""
    img = Image.fromarray(arr.astype(np.float32), mode='F')
    img = img.resize((size, size), Image.NEAREST)
    return np.array(img, dtype=np.float32)
