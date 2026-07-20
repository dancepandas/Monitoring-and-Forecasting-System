<template>
  <div class="voice-btns">
    <button
      class="vb mic"
      :class="[status]"
      :disabled="!canRecord && status === 'idle'"
      :title="micTitle"
      @click="$emit('toggle-mic')"
    >
      <span v-if="status === 'transcribing'" class="vb-spin">⟳</span>
      <span v-else-if="status === 'speaking'" class="vb-wave"><i></i><i></i><i></i></span>
      <span v-else class="vb-mic-ico">🎤</span>
    </button>
    <button
      class="vb mute"
      :class="{ on: muted }"
      :title="muted ? '已静音（点击开启语音播报）' : '点击静音语音播报'"
      @click="$emit('toggle-mute')"
    >
      {{ muted ? '🔇' : '🔊' }}
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  status: { type: String, default: 'idle' },
  muted: { type: Boolean, default: false },
  canRecord: { type: Boolean, default: true },
  error: { type: String, default: '' },
})
defineEmits(['toggle-mic', 'toggle-mute'])

const micTitle = computed(() => {
  if (props.error) return props.error
  if (props.status === 'recording') return '正在录音，点击结束'
  if (props.status === 'transcribing') return '识别中…'
  if (props.status === 'speaking') return '播报中（麦克风已禁用）'
  return '点按说话'
})
</script>

<style scoped>
.voice-btns { display: flex; align-items: flex-end; gap: 6px; flex-shrink: 0; }
.vb { min-height: 38px; width: 38px; border: 1px solid rgba(15,23,42,.12); border-radius: 18px; background: var(--bg-2); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 16px; transition: all .15s; }
.vb:hover { border-color: var(--primary); }
.vb:disabled { opacity: .45; cursor: not-allowed; }
.vb.mic.recording { border-color: var(--danger); background: rgba(220,38,38,.12); animation: vbPulse 1.2s ease-in-out infinite; }
.vb.mic.speaking { border-color: var(--water); background: rgba(14,165,233,.1); }
.vb.mute.on { border-color: var(--muted); opacity: .7; }
.vb-spin { display: inline-block; animation: vbRot 1s linear infinite; }
@keyframes vbRot { to { transform: rotate(360deg); } }
@keyframes vbPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(220,38,38,.25); } 50% { box-shadow: 0 0 0 6px transparent; } }
.vb-wave { display: inline-flex; align-items: flex-end; gap: 2px; height: 16px; }
.vb-wave i { width: 3px; background: var(--water); border-radius: 2px; animation: vbBar .9s ease-in-out infinite; }
.vb-wave i:nth-child(1) { height: 8px; animation-delay: 0s; }
.vb-wave i:nth-child(2) { height: 16px; animation-delay: .2s; }
.vb-wave i:nth-child(3) { height: 10px; animation-delay: .4s; }
@keyframes vbBar { 0%,100% { transform: scaleY(.4); } 50% { transform: scaleY(1); } }
</style>
