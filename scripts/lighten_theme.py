# -*- coding: utf-8 -*-
"""把暗色主题残留的硬编码颜色，语义化地转成亮色主题。
仅替换具体命中的 rgba/hex，保留 CSS 变量与状态色不动。"""
import re, sys, pathlib

FILES = [
    "web/src/styles/components.css",
    "web/src/styles/layout.css",
    "web/src/components/TabBar.vue",
    "web/src/components/SystemStatus.vue",
    "web/src/components/StationDrawer.vue",
    "web/src/components/ContextMenu.vue",
    "web/src/components/TrendChart.vue",
    "web/src/pages/OverviewPage.vue",
    "web/src/pages/AgentPage.vue",
    "web/src/pages/WarningsPage.vue",
    "web/src/pages/ReportsPage.vue",
    "web/src/pages/DevicesPage.vue",
    "web/src/pages/AdminSettingsPage.vue",
    "web/src/pages/AdminUsersPage.vue",
    "web/src/pages/LoginPage.vue",
    "web/src/components/Topbar.vue",
    "web/src/components/VoiceAssistant.vue",
    "web/src/components/TerrainPanel.vue",
]

ROOT = pathlib.Path(__file__).resolve().parent.parent

def repl_alpha(pat_from_rgb, mapper, text):
    """匹配 rgba(R, G, B, A) 并对 alpha 应用 mapper。"""
    r, g, b = pat_from_rgb
    rx = re.compile(rf"rgba\(\s*{r}\s*,\s*{g}\s*,\s*{b}\s*,\s*([0-9.]+)\s*\)", re.I)
    def sub(m):
        a = float(m.group(1))
        nr, ng, nb, na = mapper(a)
        return f"rgba({nr}, {ng}, {nb}, {na})"
    return rx.sub(sub, text)

def lighten_panel(a):
    # 深色面板背景 → 白色面板（轻微抬升 alpha 保证可读）
    return (255, 255, 255, round(min(a + 0.20, 0.96), 2))

def lighten_head(a):
    # 深色面板头/图表底 → 浅蓝灰
    return (241, 245, 249, round(min(a + 0.10, 0.95), 2))

def lighten_chart(a):
    # 极深图表底 → 浅灰
    return (241, 245, 249, round(max(a - 0.05, 0.5), 2))

total_changes = 0
for rel in FILES:
    p = ROOT / rel
    if not p.exists():
        print(f"skip (missing): {rel}")
        continue
    src = p.read_text(encoding="utf-8")
    orig = src
    # 1) 深色面板体（17,24,39 多用于面板/卡片背景）→ 白
    src = repl_alpha((17, 24, 39), lighten_panel, src)
    # 2) 极深底（6,10,20 用于图表/输入）→ 浅灰
    src = repl_alpha((6, 10, 20), lighten_chart, src)
    # 3) 近黑文字 #02040A（曾用作亮底按钮/徽章文字）→ 白
    src = src.replace("#02040A", "#FFFFFF")
    # 4) 模态遮罩（2,4,10）→ 中性深遮罩保留聚焦
    src = repl_alpha((2, 4, 10), lambda a: (15, 23, 42, round(a, 2)), src)
    # 5) 青色辉光（6,182,212）→ 新强调蓝（14,165,233），保留 alpha
    src = repl_alpha((6, 182, 212), lambda a: (14, 165, 233, round(a, 2)), src)
    if src != orig:
        p.write_text(src, encoding="utf-8")
        n = sum(1 for _ in re.finditer(r"rgba\(255, 255, 255", src))
        print(f"updated: {rel}")
        total_changes += 1
    else:
        print(f"no change: {rel}")

print(f"\n{total_changes} file(s) updated.")
