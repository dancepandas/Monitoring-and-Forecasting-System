<template>
  <Teleport to="body">
    <transition name="drawer">
      <div v-if="visible" class="drawer-overlay" @click.self="close">
        <aside class="station-drawer">
          <header class="drawer-head">
            <div class="drawer-title">
              <span class="drawer-code">站点详情</span>
              <h2>{{ station.name || '站点详情' }}</h2>
            </div>
            <button class="drawer-close" @click="close">✕</button>
          </header>
          <div class="drawer-body">
            <div class="drawer-stat">
              <span>水位</span>
              <b>{{ station.level ?? '—' }} <small>m</small></b>
            </div>
            <div class="drawer-stat">
              <span>流量</span>
              <b>{{ station.flow ?? '—' }} <small>m³/s</small></b>
            </div>
            <div class="drawer-stat">
              <span>状态</span>
              <b :class="station.badgeClass">{{ station.status || '—' }}</b>
            </div>
            <div v-if="station.anomaly && station.anomaly.flagged" class="drawer-stat">
              <span>数据质量</span>
              <b class="anomaly">⚠ 数据存疑</b>
            </div>
            <div class="drawer-detail-panel">
              <span class="detail-label">详情</span>
              <p class="drawer-detail">{{ station.detail || '暂无详情' }}</p>
            </div>
            <div v-if="station.anomaly && station.anomaly.flagged" class="drawer-detail-panel anomaly-panel">
              <span class="detail-label">异常说明</span>
              <p class="drawer-detail">{{ station.anomaly.reason || station.anomaly.message || '该站近期数据存在异常，请核查设备与上游计算。' }}</p>
            </div>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  visible: { type: Boolean, default: false },
  station: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close'])
function close() { emit('close') }
</script>

<style scoped>
.drawer-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  justify-content: flex-end;
}
.station-drawer {
  width: 420px; max-width: 90vw;
  height: 100%;
  border-left: 1px solid var(--line);
  background: var(--glass-strong);
  box-shadow: -12px 0 60px rgba(0, 0, 0, .55), 0 0 40px rgba(14, 165, 233, 0.06);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  position: relative;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}
.station-drawer::before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 2px;
  background: linear-gradient(180deg, var(--primary), transparent);
  box-shadow: 0 0 14px var(--primary-glow);
}

.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-2);
}
.drawer-title { display: grid; gap: 5px; }
.drawer-head h2 { margin: 0; font-family: var(--display); font-size: 20px; font-weight: 600; color: var(--ink); letter-spacing: .03em; }
.drawer-code { font-family: var(--mono); font-size: 11px; font-weight: 500; color: var(--primary); letter-spacing: .06em; }
.drawer-close {
  border: 1px solid var(--line); border-radius: var(--radius-sm);
  background: var(--bg-3); color: var(--ink-2);
  font-size: 14px; cursor: pointer; padding: 7px 13px;
  transition: all .18s ease;
}
.drawer-close:hover { color: #FFFFFF; background: var(--primary); border-color: var(--primary); box-shadow: 0 0 14px var(--primary-glow); }

.drawer-body { padding: 16px; display: grid; gap: 11px; }
.drawer-stat {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
  transition: all .18s ease;
}
.drawer-stat:hover { border-color: var(--edge); background: var(--bg-2); box-shadow: 0 0 14px var(--glow-weak); }
.drawer-stat span { font-family: var(--sans); font-size: 11px; font-weight: 500; color: var(--muted); letter-spacing: .04em; }
.drawer-stat b { font-family: var(--display); font-size: 22px; font-weight: 600; color: var(--ink); }
.drawer-stat b small { font-size: 12px; color: var(--muted); font-weight: 500; }
.drawer-stat b.danger { color: var(--danger); text-shadow: 0 0 10px var(--danger-glow); }
.drawer-stat b.warn { color: var(--orange); }
.drawer-stat b.ok { color: var(--ok); text-shadow: 0 0 10px var(--ok-glow); }
.drawer-stat b.anomaly { color: var(--anomaly); text-shadow: 0 0 10px var(--anomaly-glow); }

.drawer-detail-panel.anomaly-panel { border-left-color: var(--anomaly); background: var(--anomaly-soft); }
.drawer-detail-panel.anomaly-panel .detail-label { color: var(--anomaly); }

.drawer-detail-panel {
  margin-top: 2px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  padding: 12px;
  background: var(--bg-2);
}
.detail-label {
  display: block;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 8px;
}
.drawer-detail { margin: 0; color: var(--ink-2); font-size: 13px; line-height: 1.7; }

.drawer-enter-active, .drawer-leave-active { transition: all .28s cubic-bezier(.4, 0, .2, 1); }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .station-drawer, .drawer-leave-to .station-drawer { transform: translateX(100%); }
</style>
