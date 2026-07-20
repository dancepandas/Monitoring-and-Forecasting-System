/**
 * localTerrainProvider.js — 自定义 Cesium TerrainProvider (plain object)
 * =======================================================
 * Cesium 1.108+ 的 TerrainProvider 是纯接口 (不能继承, super() 会抛
 * "defines an interface" 错误)。正确方式: 返回实现接口的 plain object,
 * 用 new Cesium.Terrain(provider) 包装后赋给 viewer.terrain。
 *
 * 数据: heightmap PNG, elevation = -10000 + (R*65536 + G*256 + B) * 0.1 (米)
 * 瓦片: EPSG:4326, GeographicTilingScheme(1×1 根), y=0 北
 */

import * as Cesium from 'cesium'

export function createLocalTerrainProvider(url, options = {}) {
  const _url = url.replace(/\/$/, '')
  const minZoom = options.minZoom ?? 10
  const maxZoom = options.maxZoom ?? 15
  const bounds = options.bounds ?? [112.0, 25.0, 114.0, 27.0]

  const tilingScheme = new Cesium.GeographicTilingScheme({
    numberOfLevelZeroTilesX: 1,
    numberOfLevelZeroTilesY: 1,
  })

  let reqCount = 0

  function heightsFromImage(image) {
    const canvas = document.createElement('canvas')
    canvas.width = image.width
    canvas.height = image.height
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    ctx.drawImage(image, 0, 0)
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data
    const w = canvas.width, h = canvas.height
    const buffer = new Float32Array(w * h)
    for (let i = 0; i < w * h; i++) {
      const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2]
      buffer[i] = -10000.0 + (r * 65536 + g * 256 + b) * 0.1
    }
    if (image.close) { try { image.close() } catch (e) {} }
    return new Cesium.HeightmapTerrainData({ buffer, width: w, height: h })
  }

  function fetchTile(x, y, level, request) {
    reqCount++
    if (reqCount <= 8 || reqCount % 50 === 0) {
      console.log(`[Terrain] 请求瓦片 #${reqCount}: z=${level} x=${x} y=${y}`)
    }
    // 范围检查
    if (level < minZoom || level > maxZoom) return undefined
    const n = 1 << level
    const [wst, sth, est, nth] = bounds
    const xMin = Math.floor(((wst + 180) / 360) * n)
    const xMax = Math.ceil(((est + 180) / 360) * n)
    const yMin = Math.floor((1 - (nth + 90) / 180) * n)
    const yMax = Math.ceil((1 - (sth + 90) / 180) * n)
    if (x < xMin || x >= xMax || y < yMin || y >= yMax) return undefined

    const resource = new Cesium.Resource({
      url: `${_url}/${level}/${x}/${y}.png`,
      request,
    })
    const promise = resource.fetchImage({ preferImageBitmap: true })
    if (!promise) return undefined
    return promise
      .then((img) => heightsFromImage(img))
      .catch(() => undefined)
  }

  // plain object 实现 TerrainProvider 接口
  const provider = {
    tilingScheme,
    errorEvent: new Cesium.Event(),
    credit: new Cesium.Credit('© Copernicus DEM GLO-30 (30m)'),
    availability: undefined,
    hasWaterMask: false,
    hasVertexNormals: false,
    ready: true,
    readyPromise: Promise.resolve(true),
    getLevelMaximumGeometricError(level) {
      return 20000.0 / (1 << level)
    },
    getTileDataAvailable(x, y, level) {
      if (level < minZoom || level > maxZoom) return false
      const n = 1 << level
      const [wst, sth, est, nth] = bounds
      const xMin = Math.floor(((wst + 180) / 360) * n)
      const xMax = Math.ceil(((est + 180) / 360) * n)
      const yMin = Math.floor((1 - (nth + 90) / 180) * n)
      const yMax = Math.ceil((1 - (sth + 90) / 180) * n)
      return x >= xMin && x < xMax && y >= yMin && y < yMax
    },
    loadTileDataAvailability() { return Promise.resolve() },
    requestTileGeometry: fetchTile,   // 旧接口
    getTileGeometry: fetchTile,        // ★ 新接口 (1.108+)
  }

  // ★ 关键: 让 plain object 通过 instanceof Cesium.TerrainProvider 检查
  // (TerrainProvider 构造函数会抛 "interface" 错, 不能 new/继承;
  //  但 Cesium.Terrain 包装 / globe 集成都用 instanceof 判定)
  Object.setPrototypeOf(provider, Cesium.TerrainProvider.prototype)

  return provider
}
