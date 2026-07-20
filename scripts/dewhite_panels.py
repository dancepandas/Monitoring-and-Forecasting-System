# -*- coding: utf-8 -*-
"""把面板类「半透明白底」rgba(255,255,255,a>=0.4) 统一换成 var(--bg-2)，
消除刺眼白；低透明度 hover 蒙层(<=0.1) 不动。"""
import re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent / "web" / "src"
FILES = [
    "styles/components.css",
    "components/StationDrawer.vue",
    "components/AgentChatPanel.vue",
    "components/SystemStatus.vue",
    "components/VoiceButton.vue",
    "pages/AgentPage.vue",
    "pages/OverviewPage.vue",
    "pages/WarningsPage.vue",
    "pages/ReportsPage.vue",
    "pages/DevicesPage.vue",
    "components/HydroMap.vue",
]

# 匹配 background: rgba(255,255,255, A) 或 background:rgba(255,255,255,A)
RX = re.compile(r"(background\s*:\s*)rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([0-9.]+)\s*\)", re.I)

changed = 0
for rel in FILES:
    p = ROOT / rel
    if not p.exists():
        continue
    src = p.read_text(encoding="utf-8")
    orig = src

    def sub(m):
        a = float(m.group(2))
        if a < 0.35:
            return m.group(0)  # 低透明 hover 蒙层保留
        return f"{m.group(1)}var(--bg-2)"

    src = RX.sub(sub, src)
    if src != orig:
        p.write_text(src, encoding="utf-8")
        changed += 1
        print("updated:", rel)

print(f"\n{changed} file(s) updated.")
