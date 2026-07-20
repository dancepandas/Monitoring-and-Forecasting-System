<template>
  <header class="topbar">
    <div class="page-title">
      <span v-if="sectionCode" class="section-code">{{ sectionCode }}</span>
      <h1>{{ title }}</h1>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>
    <div class="top-actions" v-if="actionLabel">
      <button class="btn primary" @click="$emit('primary-action')">{{ actionLabel }}</button>
    </div>
  </header>
</template>

<script setup>
defineProps({
  title: String,
  subtitle: String,
  actionLabel: String,
  sectionCode: String
})
defineEmits(['primary-action'])
</script>
