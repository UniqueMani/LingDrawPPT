<script setup lang="ts">
import * as echarts from "echarts";
import { nextTick, onBeforeUnmount, onMounted, watch } from "vue";
import { ref } from "vue";
import type { EChartsOption } from "../types";

const props = withDefaults(
  defineProps<{
    option?: EChartsOption | null;
    /** 容器固定高度（px）；不传则由外部 CSS 决定 */
    height?: number;
    backgroundColor?: string;
  }>(),
  {
    height: 320,
    backgroundColor: "#ffffff",
  }
);

const elRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let ro: ResizeObserver | null = null;

function ensureChart() {
  if (!elRef.value) return null;
  if (!chart) {
    chart = echarts.init(elRef.value, undefined, { renderer: "svg" });
  }
  return chart;
}

function render() {
  const c = ensureChart();
  if (!c) return;
  const opt = props.option;
  if (!opt || Object.keys(opt).length === 0) {
    c.clear();
    return;
  }
  c.setOption(opt, true);
}

function handleResize() {
  chart?.resize();
}

onMounted(() => {
  render();
  // ResizeObserver 精准监听容器大小变化，优于 window resize
  if (elRef.value && typeof ResizeObserver !== "undefined") {
    ro = new ResizeObserver(() => {
      chart?.resize();
    });
    ro.observe(elRef.value);
  }
  // 兜底：window resize（Safari 老版本等）
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  ro?.disconnect();
  ro = null;
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
  chart = null;
});

watch(
  () => props.option,
  async () => {
    await nextTick();
    render();
    // 数据变化后也 resize 一次，防止容器尺寸未同步
    chart?.resize();
  },
  { deep: true }
);

async function exportPngDataUrl() {
  await nextTick();
  await new Promise((r) => setTimeout(r, 150));
  const c = ensureChart();
  if (!c) return null;
  try {
    const dataUrl = c.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: props.backgroundColor,
    });
    return dataUrl || null;
  } catch {
    return null;
  }
}

defineExpose({ exportPngDataUrl });
</script>

<template>
  <div
    class="chart-wrap"
    :style="{ height: `${height}px`, backgroundColor: backgroundColor }"
  >
    <div ref="elRef" class="chart-inner" />
  </div>
</template>

<style scoped>
.chart-wrap {
  width: 100%;
  min-width: 0;
  overflow: hidden;
  border-radius: 6px;
}
.chart-inner {
  width: 100%;
  height: 100%;
}
</style>
