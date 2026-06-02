<script setup lang="ts">
import type { SlideRequest } from "../types";

const slide = defineModel<SlideRequest>({ required: true });
</script>

<template>
  <div class="sif">
    <div class="f">
      <label>页面主题</label>
      <input v-model="slide.topic" type="text" class="inp" placeholder="本页标题" />
    </div>
    <div class="f">
      <label>正文</label>
      <textarea v-model="slide.body" class="ta" rows="4" placeholder="叙事、要点、自然语言描述…" />
    </div>
    <div class="f">
      <label>结构化数据（可选）</label>
      <textarea
        v-model="slide.data_description"
        class="ta dim"
        rows="3"
        placeholder="实体：指标 数值；多实体用分号分隔"
      />
    </div>
    <div class="row2">
      <div class="f tight">
        <label>幻灯片类型</label>
        <select v-model="slide.slide_type" class="sel">
          <option value="content">内容页</option>
          <option value="cover">封面</option>
          <option value="section-divider">分隔页</option>
        </select>
      </div>
      <div class="f tight">
        <label>推理模式</label>
        <select v-model="slide.mode" class="sel">
          <option value="auto">Auto</option>
          <option value="mock">规则 Mock</option>
          <option value="deepseek">DeepSeek</option>
        </select>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sif {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.f {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.f.tight {
  flex: 1;
}
label {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
.inp,
.ta,
.sel {
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
  font-family: inherit;
}
.ta.dim {
  background: #fcfdfc;
}
.sel {
  cursor: pointer;
  font-weight: 600;
}
.row2 {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
</style>
