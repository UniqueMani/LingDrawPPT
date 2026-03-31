<script setup lang="ts">
import type { SlideState } from "../types";

const props = defineProps<{
  slides: SlideState[];
  currentId: string;
  onSelect: (id: string) => void;
  onAdd: () => void;
  onDelete: (id: string) => void;
  onDuplicate: (id: string) => void;
}>();

function previewText(s: SlideState) {
  const t = s.input.topic?.trim();
  if (t) return t;
  const b = s.input.body?.trim();
  return b ? b.slice(0, 18) + (b.length > 18 ? "..." : "") : "(空)";
}

function analyzeBadge(s: SlideState) {
  if (s.statusAnalyze === "loading") return "分析中";
  if (s.statusAnalyze === "success") return "已出图";
  if (s.statusAnalyze === "error") return "分析失败";
  return "待分析";
}

function illusBadge(s: SlideState) {
  if (s.statusIllustration === "loading") return "生成中";
  if (s.statusIllustration === "success") return s.illustration?.illustration?.needIllus ? "插图建议" : "不强需插图";
  if (s.statusIllustration === "error") return "插图失败";
  return "待生成插图";
}
</script>

<template>
  <div class="slideList">
    <div class="toolbar">
      <div>
        <div class="title">页面导航</div>
        <div class="subtitle">{{ slides.length }} 页</div>
      </div>
      <button class="btn" @click="onAdd">+ 新建页面</button>
    </div>

    <div class="list">
      <div
        v-for="s in slides"
        :key="s.id"
        class="item"
        :class="{ active: s.id === currentId }"
        @click="onSelect(s.id)"
      >
        <div class="itemTitle">{{ previewText(s) }}</div>
        <div class="badges">
          <span class="pill">{{ analyzeBadge(s) }}</span>
          <span class="pill muted">{{ illusBadge(s) }}</span>
        </div>

        <div class="actions" @click.stop>
          <button class="mini" @click="onDuplicate(s.id)">复制</button>
          <button
            class="mini danger"
            @click="onDelete(s.id)"
            :disabled="slides.length <= 1"
            title="删除该页"
          >
            删除
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slideList {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 176px);
  min-height: 440px;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}
.subtitle {
  font-size: 12px;
  color: #6b7280;
}
.list {
  overflow: auto;
  padding-right: 4px;
}
.item {
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 12px;
  margin-bottom: 10px;
  cursor: pointer;
  background: linear-gradient(180deg, #ffffff 0%, #fcfdff 100%);
  transition: all 0.16s ease;
}
.item:hover {
  border-color: #c7d2fe;
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.05);
  transform: translateY(-1px);
}
.item.active {
  border-color: #1f9d60;
  box-shadow: 0 0 0 3px rgba(31, 157, 96, 0.14);
}
.itemTitle {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 6px;
  color: #111827;
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pill {
  display: inline-block;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
  background: #eaf9f0;
  color: #0f5132;
}
.pill.muted {
  background: #f3f4f6;
  color: #6b7280;
}
.actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.btn {
  border: 1px solid #1f9d60;
  background: #1f9d60;
  color: #fff;
  border-radius: 10px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.mini {
  border: 1px solid #e5e7eb;
  background: #fff;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  cursor: pointer;
}
.mini.danger {
  color: #b91c1c;
  border-color: #fca5a5;
}
.mini:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

