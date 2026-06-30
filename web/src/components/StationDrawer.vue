<template>
  <Teleport to="body">
    <transition name="drawer">
      <div v-if="visible" class="drawer-overlay" @click.self="close">
        <aside class="station-drawer">
          <header class="drawer-head">
            <div>
              <h2>{{ station.name || '站点详情' }}</h2>
              <span class="drawer-code">{{ station.code || '' }}</span>
            </div>
            <button class="drawer-close" @click="close">✕</button>
          </header>
          <div class="drawer-body">
            <div class="drawer-stat">
              <span>水位</span><b>{{ station.level ?? '—' }} <small>m</small></b>
            </div>
            <div class="drawer-stat">
              <span>流量</span><b>{{ station.flow ?? '—' }} <small>m³/s</small></b>
            </div>
            <div class="drawer-stat">
              <span>状态</span><b :class="station.badgeClass">{{ station.status || '—' }}</b>
            </div>
            <p class="drawer-detail">{{ station.detail || '暂无详情' }}</p>
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
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(4px);
  display: flex;
  justify-content: flex-end;
}
.station-drawer {
  width: 380px; max-width: 90vw;
  height: 100%;
  border-left: 1px solid var(--edge);
  background: var(--glass-deep);
  backdrop-filter: blur(18px);
  box-shadow: -16px 0 40px rgba(0, 0, 0, .4);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--line);
}
.drawer-head h2 { margin: 0; font-size: 16px; color: #fff; }
.drawer-code { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.drawer-close {
  border: 0; background: transparent; color: var(--muted);
  font-size: 16px; cursor: pointer; padding: 4px;
}
.drawer-close:hover { color: #fff; }
.drawer-body { padding: 16px 18px; display: grid; gap: 10px; }
.drawer-stat {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 8px 12px; border-radius: 6px; background: var(--chip);
}
.drawer-stat span { color: var(--muted); font-size: 12px; }
.drawer-stat b { font-family: var(--serif); font-size: 18px; color: #fff; }
.drawer-stat b small { font-size: 11px; color: var(--muted); }
.drawer-detail { margin: 0; color: var(--ink-2); font-size: 12px; line-height: 1.6; }
.drawer-enter-active, .drawer-leave-active { transition: all .25s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .station-drawer, .drawer-leave-to .station-drawer { transform: translateX(100%); }
</style>
