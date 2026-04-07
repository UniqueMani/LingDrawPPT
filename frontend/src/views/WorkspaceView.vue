<script setup lang="ts">
import { computed } from 'vue';
import { store } from '../store';
import { analyze, illustration } from '../api/client';
import ResultPanel from '../components/ResultPanel.vue';

const currentSlide = computed(() => store.slides[store.currentIndex]);

async function generateBoth() {
  const slide = currentSlide.value;
  if (!slide) return;
  
  slide.statusAnalyze = "loading";
  slide.statusIllustration = "loading";
  
  try {
    const [analyzeResp, illusResp] = await Promise.all([
      analyze(store.baseUrl, slide.input),
      illustration(store.baseUrl, slide.input)
    ]);
    slide.analyze = analyzeResp;
    slide.illustration = illusResp;
    slide.statusAnalyze = "success";
    slide.statusIllustration = "success";
    store.addLog(`第 ${store.currentIndex + 1} 页生成成功`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.statusIllustration = "error";
    store.addLog(`生成失败: ${e?.message}`);
  }
}

function updateIllustration(next: { keywords: string[]; prompt: string }) {
  const slide = currentSlide.value;
  if (!slide?.illustration) return;
  slide.illustration.illustration.keywords = next.keywords;
  slide.illustration.illustration.prompt = next.prompt;
}
</script>

<template>
  <div class="workspace-layout">
    <!-- 左侧幻灯片列表骨架 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>页面列表</h3>
        <p>{{ store.docName }}</p>
      </div>
      <div class="slide-list">
        <div 
          v-for="(slide, index) in store.slides" 
          :key="slide.id" 
          class="slide-item" 
          :class="{ active: index === store.currentIndex }"
          @click="store.currentIndex = index"
        >
          <div class="slide-num">{{ index + 1 }}</div>
          <div class="slide-info">
            <div class="slide-title">{{ slide.input.topic }}</div>
            <div class="slide-status">{{ slide.statusAnalyze === 'success' ? '✅ 已生成' : '🕒 待处理' }}</div>
          </div>
        </div>
      </div>
    </aside>

    <!-- 中间核心操作区 -->
    <main class="content">
      <div v-if="currentSlide" class="editor-panel">
        <div class="editor-header">
          <input v-model="currentSlide.input.topic" class="title-input" placeholder="输入页面主题..." />
          <div class="header-actions">
            <select v-model="currentSlide.input.mode" class="select-input">
              <option value="auto">自动模式 (Auto)</option>
              <option value="mock">规则模式 (Mock)</option>
              <option value="deepseek">DeepSeek 模式</option>
            </select>
            <button class="btn primary" @click="generateBoth" :disabled="currentSlide.statusAnalyze === 'loading'">
              <span v-if="currentSlide.statusAnalyze === 'loading'" class="btn-spinner"></span>
              {{ currentSlide.statusAnalyze === 'loading' ? '正在分析...' : '一键生成' }}
            </button>
          </div>
        </div>
        
        <div class="form-grid">
          <div class="form-item full">
            <label>📝 正文内容 (Body)</label>
            <textarea v-model="currentSlide.input.body" class="body-editor" placeholder="输入页面文字内容..."></textarea>
          </div>
          <div class="form-item">
            <label>📊 数据描述 (Data Description - 可选)</label>
            <textarea v-model="currentSlide.input.data_description" class="data-editor" placeholder="例如: 2021年销量100, 2022年销量150..."></textarea>
          </div>
          <div class="form-item">
            <label>📑 幻灯片类型</label>
            <select v-model="currentSlide.input.slide_type" class="select-input block">
              <option value="content">内容页 (Content)</option>
              <option value="cover">封面页 (Cover)</option>
              <option value="section-divider">分隔页 (Section Divider)</option>
            </select>
          </div>
        </div>
      </div>

      <!-- 结果展示区域 -->
      <div class="results-container">
        <div class="section-title">
          <span class="title-icon">✨</span>
          生成结果预览
        </div>
        
        <div v-if="!currentSlide?.analyze && !currentSlide?.illustration" class="empty-state">
          <div class="empty-icon">💡</div>
          <p>请在上方编辑内容并点击“一键生成”</p>
          <span>我们将为您自动生成 ECharts 图表和插图建议</span>
        </div>

        <div v-else class="preview-grid">
          <div class="preview-card chart-area">
            <div class="card-header">📊 智能图表推荐</div>
            <div class="card-body">
              <ResultPanel 
                :slide="currentSlide" 
                :onRerunChart="generateBoth" 
                :onRerunIllustration="generateBoth" 
                :onRerunBoth="generateBoth" 
                :onChangeIllustration="updateIllustration"
              />
            </div>
          </div>

          <div class="preview-card illustration-area">
            <div class="card-header">🎨 视觉插图建议</div>
            <div class="card-body">
              <div v-if="currentSlide.illustration" class="illus-info">
                <div class="info-group">
                  <label>关键词</label>
                  <div class="tag-cloud">
                    <span v-for="kw in currentSlide.illustration.illustration.keywords" :key="kw" class="tag">{{ kw }}</span>
                  </div>
                </div>
                <div class="info-group">
                  <label>生成提示词 (Prompt)</label>
                  <div class="prompt-text">{{ currentSlide.illustration.illustration.prompt }}</div>
                </div>
                <div class="image-placeholder">
                  <span class="placeholder-icon">🖼️</span>
                  <span>AI 图片生成预留位</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.workspace-layout { display: flex; height: calc(100vh - 70px); background: #f1f5f9; }
.sidebar { width: 320px; background: white; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; box-shadow: 4px 0 10px rgba(0,0,0,0.02); }
.sidebar-header { padding: 24px; border-bottom: 1px solid #f1f5f9; }
.sidebar-header h3 { margin: 0; color: #0f172a; font-size: 16px; font-weight: 800; }
.sidebar-header p { margin: 8px 0 0; font-size: 12px; color: #64748b; font-weight: 500; }

.slide-list { flex: 1; overflow-y: auto; padding: 12px; }
.slide-item { display: flex; align-items: center; padding: 14px; border-radius: 12px; cursor: pointer; margin-bottom: 8px; border: 1px solid transparent; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-item:hover { background: #f8fafc; transform: translateX(4px); }
.slide-item.active { background: #f0fdf4; border-color: #1f9d60; box-shadow: 0 4px 12px rgba(31, 157, 96, 0.08); }
.slide-num { width: 28px; height: 28px; background: #f1f5f9; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 800; margin-right: 14px; color: #64748b; }
.slide-item.active .slide-num { background: #1f9d60; color: white; }
.slide-info { flex: 1; overflow: hidden; }
.slide-title { font-size: 13px; font-weight: 700; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slide-status { font-size: 11px; color: #94a3b8; margin-top: 4px; font-weight: 600; }

.content { flex: 1; padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 24px; max-width: 1400px; margin: 0 auto; width: 100%; }

.editor-panel { 
  background: white; 
  padding: 24px; 
  border-radius: 16px; 
  border: 1px solid #e2e8f0; 
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.04); 
}

.editor-header { 
  display: flex; 
  justify-content: space-between; 
  align-items: center; 
  margin-bottom: 24px; 
  padding-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
  gap: 20px; 
}

.title-input { 
  font-size: 22px; 
  font-weight: 800; 
  border: none; 
  outline: none; 
  flex: 1; 
  color: #0f172a; 
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s;
  background: transparent;
}
.title-input:hover { background: #f8fafc; }
.title-input:focus { background: #f8fafc; box-shadow: inset 0 0 0 2px #1f9d60; }

.header-actions { display: flex; gap: 12px; align-items: center; }

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.form-item { display: flex; flex-direction: column; gap: 8px; }
.form-item.full { grid-column: span 2; }
.form-item label { font-size: 13px; font-weight: 700; color: #475569; padding-left: 4px; }

.body-editor, .data-editor, .select-input { 
  width: 100%; 
  border: 1px solid #cbd5e1; 
  border-radius: 10px; 
  padding: 12px 16px; 
  font-family: inherit; 
  font-size: 14px; 
  color: #1e293b;
  background: #ffffff;
  transition: all 0.2s;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.body-editor:focus, .data-editor:focus, .select-input:focus { 
  outline: none; 
  border-color: #1f9d60; 
  box-shadow: 0 0 0 4px rgba(31, 157, 96, 0.1);
}

.body-editor { height: 120px; resize: vertical; line-height: 1.6; }
.data-editor { height: 100px; resize: vertical; background: #fcfdfc; }

.select-input { 
  appearance: none; 
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2364748b'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 16px;
  padding-right: 40px;
  cursor: pointer;
  font-weight: 600;
}
.select-input:hover { border-color: #94a3b8; }

.results-container { flex: 1; }
.section-title { font-size: 18px; font-weight: 800; color: #0f172a; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
.title-icon { background: #fffbeb; border-radius: 8px; padding: 4px; font-size: 20px; }
.empty-state { 
  background: white; 
  padding: 80px 40px; 
  border-radius: 16px; 
  border: 2px dashed #e2e8f0; 
  text-align: center; 
  color: #64748b;
}
.empty-icon { font-size: 40px; margin-bottom: 16px; }
.empty-state p { font-size: 16px; font-weight: 700; color: #1e293b; margin: 0 0 8px 0; }
.empty-state span { font-size: 14px; color: #94a3b8; }

.preview-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; min-height: 500px; }
.preview-card { background: white; border-radius: 16px; border: 1px solid #e2e8f0; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
.card-header { padding: 16px 20px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; font-weight: 800; font-size: 14px; color: #1e293b; }
.card-body { flex: 1; padding: 20px; position: relative; }

.illus-info { display: flex; flex-direction: column; gap: 20px; }
.info-group label { display: block; font-size: 12px; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.05em; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
.tag { background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; border: 1px solid #e2e8f0; }
.prompt-text { background: #f8fafc; padding: 12px; border-radius: 10px; font-size: 13px; line-height: 1.5; color: #334155; border: 1px solid #f1f5f9; }

.image-placeholder { 
  margin-top: 10px; 
  height: 180px; 
  background: #f8fafc; 
  border-radius: 12px; 
  display: flex; 
  flex-direction: column;
  align-items: center; 
  justify-content: center; 
  color: #94a3b8; 
  border: 2px dashed #e2e8f0;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}
.placeholder-icon { font-size: 24px; }

.btn { 
  padding: 10px 24px; 
  border-radius: 10px; 
  border: none; 
  cursor: pointer; 
  font-weight: 700; 
  font-size: 14px;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.primary { 
  background: #1f9d60; 
  color: white; 
  box-shadow: 0 4px 12px rgba(31, 157, 96, 0.2);
}
.primary:hover:not(:disabled) { 
  background: #167e4d; 
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(31, 157, 96, 0.3);
}
.primary:disabled { background: #94a3b8; cursor: not-allowed; transform: none; box-shadow: none; }

.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
