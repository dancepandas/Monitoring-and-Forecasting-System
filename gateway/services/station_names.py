"""站点名称映射。全局统一：对外展示用名称，内部存储用编码。"""

STATION_NAMES = {
    "00106": "仙桃站",
    "00107": "城西站",
    "00108": "南桥站",
}


def station_name(code: str) -> str:
    """测站编码 → 名称。未知编码返回原文。"""
    return STATION_NAMES.get(code, code)


def station_label(code: str) -> str:
    """返回 '名称(编码)' 格式，方便同时展示。"""
    name = station_name(code)
    return f"{name}" if name == code else f"{name}({code})"
