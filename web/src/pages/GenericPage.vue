<template>
  <Topbar :title="page.title" :subtitle="page.sub" />
  <section class="page-content">
    <div class="command-grid">
      <article class="panel" v-for="p in page.panels" :key="p.head">
        <div class="panel-head"><h2>{{ p.head }}</h2><span>{{ p.span }}</span></div>
        <div class="panel-body">
          <p style="color:var(--muted);font-size:13px;line-height:1.7;">{{ p.desc }}</p>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import Topbar from '../components/Topbar.vue'

defineProps({
  page: { type: Object, required: true }
})
</script>
