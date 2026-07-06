"""站点注册表 —— 全局单一数据源。

对外展示用名称，内部存储/通信用编码。每个站点绑定各自的设备码与经纬度。
新增/更换站点只需修改本文件 STATIONS 字典。
"""

STATIONS = {
    "00125": {"name": "郴州", "device": "FD000848891909", "lon": 113.03915, "lat": 25.80385},
    "00230": {"name": "郴州-坳上", "device": "FD000696565714", "lon": 113.01888, "lat": 25.67971},
    "00231": {"name": "郴州-鸡嘴桥下游", "device": "FD000445060600", "lon": 113.01198, "lat": 25.81638},
    "00234": {"name": "郴州-燕泉河", "device": "FD000823998862", "lon": 113.02373, "lat": 25.78843},
}


def station_name(code: str) -> str:
    """测站编码 → 名称。未知编码返回原文。"""
    return STATIONS.get(code, {}).get("name", code)


def station_device(code: str) -> str:
    """测站编码 → 设备码。未知编码返回空串。"""
    return STATIONS.get(code, {}).get("device", "")


def station_geo(code: str) -> tuple:
    """测站编码 → (经度, 纬度)。未知编码返回 (None, None)。"""
    info = STATIONS.get(code)
    if not info:
        return (None, None)
    return (info.get("lon"), info.get("lat"))


def station_label(code: str) -> str:
    """返回 '名称(编码)' 格式，方便同时展示。"""
    name = station_name(code)
    return f"{name}" if name == code else f"{name}({code})"


def all_codes() -> list:
    """全部站点编码列表。"""
    return list(STATIONS.keys())


def codes_str() -> str:
    """逗号分隔的全部站点编码（供配置默认值）。"""
    return ",".join(STATIONS.keys())


# ── 模块级常量 ──
ALL_CODES = tuple(STATIONS.keys())  # 所有站点编码元组，不可变


def resolve_device_code(code: str) -> str:
    """解析设备码：先查站点专属设备，无则回退默认。"""
    from ..config import settings
    return station_device(code) or settings.default_device_code
