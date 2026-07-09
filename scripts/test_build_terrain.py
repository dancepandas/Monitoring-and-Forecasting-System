import numpy as np
from build_terrain_model import (
    load_dem_mosaic, crop_aoi, downsample, AOI,
    rasterize_waterways, compute_vertex_colors, GRID_SIZE,
)


def test_load_dem_mosaic():
    mosaic, bounds = load_dem_mosaic()
    assert mosaic.shape == (7200, 7200)
    assert bounds == {'west': 112.0, 'east': 114.0, 'south': 25.0, 'north': 27.0}
    assert np.nanmin(mosaic) > 0  # 郴州区域海拔 > 0
    assert np.nanmax(mosaic) < 9000


def test_crop_aoi_shape():
    mosaic, mb = load_dem_mosaic()
    aoi_arr = crop_aoi(mosaic, mb, AOI)
    # AOI 约 0.31°×0.32°, mosaic 2°=7200px → 约 1100×1150
    assert 900 < aoi_arr.shape[0] < 1300
    assert 900 < aoi_arr.shape[1] < 1300


def test_downsample():
    arr = np.random.rand(1100, 1150).astype(np.float32)
    out = downsample(arr, 600)
    assert out.shape == (600, 600)


def test_rasterize_waterways_has_hits():
    mask = rasterize_waterways(GRID_SIZE, AOI)
    assert mask.shape == (GRID_SIZE, GRID_SIZE)
    assert mask.dtype == bool
    # 郴州城区有郴江等河道, 必须命中一些顶点
    assert mask.sum() > 50, '河道未命中任何网格, 光栅化可能出错'


def test_compute_vertex_colors():
    heights = np.array([[100, 500], [1000, 1500]], dtype=np.float32)
    water = np.array([[True, False], [False, False]])
    colors = compute_vertex_colors(heights, water)
    assert colors.shape == (2, 2, 3)
    assert colors.dtype == np.uint8
    # 河道顶点 = 蓝色
    assert tuple(colors[0, 0]) == (0x3b, 0x82, 0xf6)
    # 低处比高处暗 (R 通道)
    assert colors[0, 1, 0] <= colors[1, 1, 0]
