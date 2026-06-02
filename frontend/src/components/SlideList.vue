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
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}
.subtitle {
  font-size: 12px;
  color: var(--color-muted);
}
.list {
  overflow: auto;
  padding-right: 4px;
}
.item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
  cursor: pointer;
  background: var(--color-surface);
  transition: transform var(--motion-base) var(--motion-ease), box-shadow var(--motion-base) var(--motion-ease), border-color var(--motion-base) var(--motion-ease);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}
.item:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-card);
  transform: translateY(-1px);
}
.item.active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(139, 41, 66, 0.12);
}
.itemTitle {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 6px;
  color: var(--color-text);
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
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border: 1px solid var(--color-border);
}
.pill.muted {
  background: var(--color-bg-muted);
  color: var(--color-muted);
}
.actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.btn {
  border: 1px solid var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-control);
  min-height: var(--control-md);
  padding: 0 12px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.btn:hover {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  transform: translateY(-1px);
}
.mini {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: var(--radius-control);
  min-height: var(--control-sm);
  padding: 0 10px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-soft);
}
.mini:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.mini.danger {
  color: var(--color-danger);
  border-color: #fca5a5;
}
.mini:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>

