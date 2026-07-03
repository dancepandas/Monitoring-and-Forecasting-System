"""warning_config.py 单元测试"""
import json
import tempfile
import os
from pathlib import Path


def _clean_config():
    """重置 warning_config 模块状态到初始默认值。"""
    from gateway.services import warning_config
    warning_config.invalidate_cache()
    # 确保测试不污染真实配置文件
    warning_config._CONFIG_PATH = Path(tempfile.mktemp(suffix='.json'))
    if warning_config._CONFIG_PATH.exists():
        warning_config._CONFIG_PATH.unlink()
    warning_config._cache = dict(warning_config.DEFAULT_STANDARDS)
    return warning_config


class TestWarningConfig:
    """预警配置核心逻辑测试"""

    def test_default_thresholds(self):
        wc = _clean_config()
        t = wc.get_station_thresholds('00125')
        assert t['level']['blue'] == 34.0
        assert t['level']['red'] == 36.0
        assert t['flow']['blue'] == 5000
        assert t['flow']['red'] == 18000
        assert t['is_custom'] is False

    def test_check_level_basic(self):
        wc = _clean_config()
        assert wc.check_level(34.0, '00125') == 'blue'
        assert wc.check_level(35.2, '00125') == 'yellow'
        assert wc.check_level(33.0, '00125') is None
        assert wc.check_level(36.0, '00125') == 'red'

    def test_check_flow_basic(self):
        wc = _clean_config()
        assert wc.check_flow(5000, '00125') == 'blue'
        assert wc.check_flow(9000, '00125') == 'yellow'
        assert wc.check_flow(4000, '00125') is None

    def test_custom_thresholds_merge_with_defaults(self):
        wc = _clean_config()
        # 只设置部分级别
        wc.update_station_threshold('00230', 'level', 'blue', 10.0)
        wc.update_station_threshold('00230', 'level', 'red', 20.0)
        t = wc.get_station_thresholds('00230')
        assert t['is_custom'] is True
        assert t['level']['blue'] == 10.0   # 自定义
        assert t['level']['red'] == 20.0    # 自定义
        assert t['level']['yellow'] == 35.0  # 继承默认
        assert t['level']['orange'] == 35.5  # 继承默认
        assert t['flow']['blue'] == 5000     # 未设流量，继承默认

    def test_custom_station_warning(self):
        wc = _clean_config()
        wc.update_station_threshold('00230', 'level', 'blue', 10.0)
        # 15 >= 10 blue → blue
        assert wc.check_level(15.0, '00230') == 'blue'
        # Other station unaffected
        assert wc.check_level(15.0, '00125') is None  # below 34.0

    def test_thresholds_optional_param(self):
        wc = _clean_config()
        t = wc.get_station_thresholds('00125')
        # 传入已有 thresholds dict 避免重复加载
        assert wc.check_level(35.2, '00125', t) == 'yellow'
        assert wc.check_flow(9000, '00125', t) == 'yellow'

    def test_atomic_save(self):
        wc = _clean_config()
        tmp = wc._CONFIG_PATH.with_suffix('.tmp')
        wc.save_standards(dict(wc.DEFAULT_STANDARDS))
        assert wc._CONFIG_PATH.exists()
        assert not tmp.exists()  # tmp 应该已被 replace 清理

    def test_migration_v1_to_v2(self):
        wc = _clean_config()
        # 写入 v1 格式
        v1 = {"level": {"blue": 100.0}, "flow": {"blue": 9999}, "admin_contact": "test"}
        wc._CONFIG_PATH.write_text(json.dumps(v1))
        wc.invalidate_cache()
        cfg = wc.load_standards()
        assert 'stations' in cfg
        assert cfg['_defaults']['level']['blue'] == 100.0
        assert cfg['_defaults']['flow']['blue'] == 9999
        assert cfg['admin_contact'] == 'test'

    def test_level_name(self):
        from gateway.services.warning_config import level_name
        assert level_name('blue') == '蓝色预警'
        assert level_name('red') == '红色预警'
        assert level_name('unknown') == 'unknown'

    def test_get_admin_contact(self):
        wc = _clean_config()
        contact = wc.get_admin_contact()
        assert isinstance(contact, str)
        assert len(contact) > 0


class TestStationNames:
    """站点注册表测试"""

    def test_all_codes(self):
        from gateway.services.station_names import all_codes, STATIONS
        codes = all_codes()
        assert '00125' in codes
        assert len(codes) == len(STATIONS)

    def test_station_lookup(self):
        from gateway.services.station_names import station_name, station_device
        assert station_name('00125') == '郴州'
        assert station_device('00125') == 'FD000848891909'

    def test_unknown_station(self):
        from gateway.services.station_names import station_name, station_device
        assert station_name('99999') == '99999'
        assert station_device('99999') == ''
