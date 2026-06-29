<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-row">
        <div class="mark"></div>
        <div><b>水文监测指挥核心</b><span>River Command Core</span></div>
      </div>
    </div>
    <nav class="nav">
      <router-link to="/"><span>流域总览</span></router-link>
      <router-link to="/stations"><span>监测站点</span></router-link>
      <router-link to="/warnings"><span>预警处置</span></router-link>
      <router-link to="/alerts"><span>告警中心</span></router-link>
      <router-link to="/devices"><span>视频巡检</span></router-link>
      <router-link to="/reports"><span>日报归档</span></router-link>
      <router-link to="/agent"><span>智能体对话</span></router-link>
    </nav>
    <div class="sidebar-foot">
      <div class="agent-card">
        <b>FloodMind 在线</b>
        <p>可读取监测数据、运行预报模型、生成处置建议与日报草稿。</p>
      </div>
    </div>
  </aside>
</template>
