<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { NormalizedRect } from "../types";
import { clampPlacementRect, heightForNormalizedWidth } from "../utils/pptInsert";

type DragMode = "move" | "resize-nw" | "resize-ne" | "resize-sw" | "resize-se";

const props = withDefaults(
  defineProps<{
    imageUrl: string;
    aspectRatio: string;
    slideAspect?: number;
    label?: string;
    saving?: boolean;
    /** false 时仅展示与删除，不可拖动/缩放 */
    movable?: boolean;
    /** false 时仅显示选框与删除，不叠浮动图（PNG 已烘焙时使用） */
    showImage?: boolean;
  }>(),
  { movable: true, showImage: true }
);

const emit = defineEmits<{
  remove: [];
  changeEnd: [];
}>();

const placement = defineModel<NormalizedRect>("placement", { required: true });

const overlayRef = ref<HTMLElement | null>(null);
const selected = ref(true);
const dragState = ref<{ mode: DragMode; startX: number; startY: number; origin: NormalizedRect } | null>(null);

const slideAspectValue = () => props.slideAspect || 16 / 9;

function clampRect(rect: NormalizedRect): NormalizedRect {
  return clampPlacementRect(rect, props.aspectRatio, slideAspectValue());
}

function heightForWidth(width: number) {
  return heightForNormalizedWidth(width, props.aspectRatio, slideAspectValue());
}

function resizeFromCorner(mode: DragMode, dx: number, _dy: number, origin: NormalizedRect): NormalizedRect {
  if (mode === "resize-se") {
    const width = Math.max(0.14, origin.width + dx);
    return clampRect({ x: origin.x, y: origin.y, width, height: heightForWidth(width) });
  }
  if (mode === "resize-sw") {
    const width = Math.max(0.14, origin.width - dx);
    const x = origin.x + origin.width - width;
    return clampRect({ x, y: origin.y, width, height: heightForWidth(width) });
  }
  if (mode === "resize-ne") {
    const width = Math.max(0.14, origin.width + dx);
    const height = heightForWidth(width);
    const y = origin.y + origin.height - height;
    return clampRect({ x: origin.x, y, width, height });
  }
  const width = Math.max(0.14, origin.width - dx);
  const height = heightForWidth(width);
  const x = origin.x + origin.width - width;
  const y = origin.y + origin.height - height;
  return clampRect({ x, y, width, height });
}

function onPointerDown(event: PointerEvent, mode: DragMode) {
  event.preventDefault();
  event.stopPropagation();
  selected.value = true;
  dragState.value = {
    mode,
    startX: event.clientX,
    startY: event.clientY,
    origin: { ...placement.value },
  };
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onWindowPointerUp);
}

function onPointerMove(event: PointerEvent) {
  const state = dragState.value;
  const shell = overlayRef.value;
  if (!state || !shell) return;
  const rect = shell.getBoundingClientRect();
  const dx = (event.clientX - state.startX) / rect.width;
  const dy = (event.clientY - state.startY) / rect.height;

  if (state.mode === "move") {
    placement.value = clampRect({
      ...state.origin,
      x: state.origin.x + dx,
      y: state.origin.y + dy,
    });
    return;
  }

  placement.value = resizeFromCorner(state.mode, dx, dy, state.origin);
}

function finishPointerUp(emitChangeEnd = true) {
  const wasDragging = dragState.value !== null;
  dragState.value = null;
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", onWindowPointerUp);
  if (wasDragging && emitChangeEnd) emit("changeEnd");
}

function onWindowPointerUp() {
  finishPointerUp(true);
}

function onShellPointerDown(event: PointerEvent) {
  if (event.target === overlayRef.value) {
    selected.value = false;
  }
}

function onBoxPointerDown(event: PointerEvent) {
  const target = event.target as HTMLElement | null;
  if (target?.closest(".ppt-insert-delete, .ppt-insert-handle, .ppt-insert-toolbar")) return;
  event.stopPropagation();
  selected.value = true;
  if (!props.movable) return;
  onPointerDown(event, "move");
}

function onRemoveClick(event: Event) {
  event.preventDefault();
  event.stopPropagation();
  finishPointerUp(false);
  emit("remove");
}

function onKeydown(event: KeyboardEvent) {
  if (!selected.value) return;
  if (event.key === "Delete" || event.key === "Backspace") {
    event.preventDefault();
    emit("remove");
  }
}

watch(
  () => props.aspectRatio,
  () => {
    placement.value = clampRect(placement.value);
  }
);

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  finishPointerUp(false);
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div ref="overlayRef" class="ppt-insert-overlay" @pointerdown="onShellPointerDown">
    <div
      class="ppt-insert-box"
      :class="{
        'ppt-insert-box--selected': selected,
        'ppt-insert-box--saving': saving,
        'ppt-insert-box--readonly': !movable,
        'ppt-insert-box--chrome-only': !showImage,
      }"
      :style="{
        left: `${placement.x * 100}%`,
        top: `${placement.y * 100}%`,
        width: `${placement.width * 100}%`,
        height: `${placement.height * 100}%`,
      }"
      @pointerdown="onBoxPointerDown"
    >
      <img
        v-if="showImage && imageUrl"
        class="ppt-insert-image"
        :src="imageUrl"
        :alt="label || '待插入配图'"
        draggable="false"
      />
      <div v-if="saving" class="ppt-insert-saving-mask" aria-live="polite">正在写入 PPT...</div>
      <div class="ppt-insert-toolbar">
        <span class="ppt-insert-tag">{{ label || "待插入" }} · {{ aspectRatio }}</span>
      </div>
      <button
        type="button"
        class="ppt-insert-delete"
        title="删除"
        aria-label="删除配图"
        @pointerdown.stop
        @click.stop.prevent="onRemoveClick"
      >
        ×
      </button>
      <template v-if="selected && movable">
        <button
          type="button"
          class="ppt-insert-handle ppt-insert-handle--nw"
          aria-label="等比例缩放"
          @pointerdown.stop.prevent="onPointerDown($event, 'resize-nw')"
        />
        <button
          type="button"
          class="ppt-insert-handle ppt-insert-handle--sw"
          aria-label="等比例缩放"
          @pointerdown.stop.prevent="onPointerDown($event, 'resize-sw')"
        />
        <button
          type="button"
          class="ppt-insert-handle ppt-insert-handle--se"
          aria-label="等比例缩放"
          @pointerdown.stop.prevent="onPointerDown($event, 'resize-se')"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.ppt-insert-overlay {
  position: absolute;
  inset: 0;
  z-index: 8;
  pointer-events: none;
}

.ppt-insert-box {
  position: absolute;
  border: 2px solid rgba(74, 144, 255, 0.55);
  background: rgba(74, 144, 255, 0.08);
  cursor: move;
  overflow: visible;
  box-sizing: border-box;
  touch-action: none;
  pointer-events: auto;
}

.ppt-insert-box--selected {
  border-color: rgba(74, 144, 255, 0.98);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.85), 0 8px 24px rgba(74, 144, 255, 0.28);
}

.ppt-insert-box--readonly {
  cursor: default;
}

.ppt-insert-box--chrome-only {
  background: transparent;
}

.ppt-insert-box--saving {
  pointer-events: none;
}

.ppt-insert-saving-mask {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  color: var(--color-primary, #4a90ff);
  font-size: 13px;
  font-weight: 700;
  pointer-events: none;
}

.ppt-insert-image {
  width: 100%;
  height: 100%;
  object-fit: fill;
  pointer-events: none;
  display: block;
  background: #fff;
}

.ppt-insert-toolbar {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 6px;
  padding: 4px 8px;
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.72), rgba(15, 23, 42, 0));
  pointer-events: none;
}

.ppt-insert-tag {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: rgba(74, 144, 255, 0.92);
  pointer-events: none;
  white-space: nowrap;
}

.ppt-insert-delete {
  pointer-events: auto;
  position: absolute;
  right: -10px;
  top: -10px;
  z-index: 4;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.92);
  color: #fff;
  font-size: 18px;
  line-height: 1;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ppt-insert-delete:hover,
.ppt-insert-delete:focus-visible {
  background: rgba(185, 28, 28, 0.98);
}

.ppt-insert-handle {
  position: absolute;
  z-index: 2;
  width: 12px;
  height: 12px;
  padding: 0;
  border: 2px solid #fff;
  border-radius: 3px;
  background: rgba(74, 144, 255, 0.98);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.25);
  touch-action: none;
}

.ppt-insert-handle--nw {
  left: -6px;
  top: -6px;
  cursor: nwse-resize;
}

.ppt-insert-handle--sw {
  left: -6px;
  bottom: -6px;
  cursor: nesw-resize;
}

.ppt-insert-handle--se {
  right: -6px;
  bottom: -6px;
  cursor: nwse-resize;
}
</style>
