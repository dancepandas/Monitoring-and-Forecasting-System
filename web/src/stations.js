// 郴州四站单一数据源（前端）—— 轮播 store 与 CesiumMap 共用
// 与后端 gateway/services/station_names.py 的 STATIONS 保持一致
export const STATIONS = [
  { code: '00125', name: '郴州',           lon: 113.03915, lat: 25.80385, device: 'FD000848891909' },
  { code: '00230', name: '郴州-坳上',       lon: 113.01888, lat: 25.67971, device: 'FD000696565714' },
  { code: '00231', name: '郴州-鸡嘴桥下游', lon: 113.01198, lat: 25.81638, device: 'FD000445060600' },
  { code: '00234', name: '郴州-燕泉河',     lon: 113.02373, lat: 25.78843, device: 'FD000823998862' },
]

// 全部站点编码（汇总查询用）
export const ALL_STATION_CODES = STATIONS.map(s => s.code).join(',')
