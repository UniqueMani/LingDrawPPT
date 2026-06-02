<script setup lang="ts">
import * as echarts from "echarts";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { EChartsOption } from "../types";

const props = withDefaults(
  defineProps<{
    option?: EChartsOption | null;
    width?: number | string;
    height?: number | string;
    backgroundColor?: string;
  }>(),
  {
    width: "100%",
    height: 420,
    backgroundColor: "#ffffff",
  }
);

const elRef = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

const styleWidth = computed(() => (typeof props.width === "number" ? `${props.width}px` : props.width));
const styleHeight = computed(() => (typeof props.height === "number" ? `${props.height}px` : props.height));

function ensureChart() {
  if (!elRef.value) return null;
  if (!chart) {
    // 用 svg 渲染，便于 getDataURL 导出图片
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

  c.resize();
  c.setOption(opt, true);
}

function resizeChart() {
  if (!chart) return;
  chart.resize();
}

onMounted(() => {
  render();
  if (elRef.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        resizeChart();
        render();
      });
    });
    resizeObserver.observe(elRef.value);
  }
  window.addEventListener("resize", resizeChart);
});

onBeforeUnmount(() => {
  try {
    window.removeEventListener("resize", resizeChart);
  } catch {
    // ignore
  }
  resizeObserver?.disconnect();
  resizeObserver = null;
  if (chart) {
    chart.dispose();
    chart = null;
  }
});

watch(
  () => props.option,
  () => {
    render();
  },
  { deep: true }
);

async function exportPngDataUrl() {
  await nextTick();
  // 等一下让 ECharts 完成布局
  await new Promise((r) => setTimeout(r, 150));
  const c = ensureChart();
  if (!c) return null;

  // getDataURL 返回：data:image/png;base64,XXXX
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
    ref="elRef"
    :style="{
      width: styleWidth,
      height: styleHeight,
      backgroundColor: backgroundColor,
    }"
  />
</template>

