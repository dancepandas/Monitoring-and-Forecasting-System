import numpy as np
from build_terrain_model import load_dem_mosaic, crop_aoi, downsample, AOI


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
