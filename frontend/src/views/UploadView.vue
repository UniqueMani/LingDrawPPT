<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { store } from '../store';
import { extractText } from '../api/client';
import type { SlideRequest } from '../types';

const router = useRouter();
const fileInput = ref<HTMLInputElement | null>(null);
const loading = ref(false);
const message = ref("");

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function createInputFromPage(title: string, text: string): SlideRequest {
  return { topic: title || "未命名页面", body: text || "", data_description: "", slide_type: "content", mode: "auto" };
}

async function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  
  loading.value = true;
  message.value = "正在解析文档...";
  try {
    const resp = await extractText(store.baseUrl, file);
    store.docName = resp.filename;
    store.slides = [];
    
    const pages = resp.pages_detail.length > 0 ? resp.pages_detail : [{ page: 1, title: resp.title || "第1页", text: resp.text }];
    
    for (const p of pages) {
      store.slides.push({
        id: `${newId()}_${p.page}`,
        input: createInputFromPage(p.title || `第 ${p.page} 页`, p.text || ""),
        statusAnalyze: "idle",
        statusIllustration: "idle",
        history: [],
      });
    }
    store.currentIndex = 0;
    store.addLog(`成功上传并解析文件: ${resp.filename}，共 ${store.slides.length} 页`);
    router.push('/workspace');
  } catch (e: any) {
    message.value = e?.message || "上传失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="upload-container">
    <div class="upload-card">
      <h2>上传您的幻灯片文档</h2>
      <p>支持 .pptx 和 .pdf 格式，我们将自动提取每页文字并为您推荐可视化方案。</p>
      
      <div class="drop-zone" @click="fileInput?.click()">
        <div v-if="!loading" class="hint">
          <span class="icon">📁</span>
          <span>点击或拖拽文件到此处上传</span>
        </div>
        <div v-else class="loader">
          <div class="spinner"></div>
          <p>{{ message }}</p>
        </div>
      </div>
      
      <input ref="fileInput" type="file" accept=".pptx,.pdf" class="hidden" @change="onPickFile" />
      
      <div v-if="message && !loading" class="msg">{{ message }}</div>
    </div>
  </div>
</template>

<style scoped>
.upload-container { display: flex; justify-content: center; align-items: center; min-height: 60vh; }
.upload-card { background: white; padding: 40px; border-radius: 16px; border: 1px solid #dcefe5; width: 600px; text-align: center; }
.drop-zone { border: 2px dashed #1f9d60; border-radius: 12px; padding: 60px; margin: 30px 0; cursor: pointer; transition: background 0.2s; }
.drop-zone:hover { background: #f0fdf4; }
.icon { font-size: 48px; display: block; margin-bottom: 10px; }
.hidden { display: none; }
.loader { display: flex; flex-direction: column; align-items: center; }
.spinner { border: 4px solid #f3f3f3; border-top: 4px solid #1f9d60; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin-bottom: 10px; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
</style>
