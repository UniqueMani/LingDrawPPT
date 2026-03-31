<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import type { IllustrationResponse, SlideRequest, SlideState, UserDTO } from "./types";
import { adminUsers, analyze, extractText, illustration, login, me, register, setAuthToken } from "./api/client";
import ResultPanel from "./components/ResultPanel.vue";
import ChartPreview from "./components/ChartPreview.vue";
import PPTXGenJS from "pptxgenjs";

type AppStep = "home" | "upload" | "workspace";
type MainTab = "workspace" | "admin";

const baseUrl = ref("http://127.0.0.1:8000");
const step = ref<AppStep>("home");
const tab = ref<MainTab>("workspace");
const token = ref(localStorage.getItem("token") || "");
const currentUser = ref<UserDTO | null>(null);
const authTab = ref<"login" | "register">("login");
const authName = ref("");
const authPwd = ref("");
const regFullName = ref("");
const regEmail = ref("");
const regOrg = ref("");
const regConfirmPwd = ref("");
const authLoading = ref(false);
const authMessage = ref("");
const adminList = ref<UserDTO[]>([]);
const uploadInputRef = ref<HTMLInputElement | null>(null);
const uploadLoading = ref(false);
const uploadMessage = ref("");
const docName = ref("");
const activityLogs = ref<string[]>(["欢迎使用 LingDraw PPT Studio"]);
const viewportWidth = ref(typeof window !== "undefined" ? window.innerWidth : 1280);
const handleResize = () => { viewportWidth.value = window.innerWidth; };
const showUserMenu = ref(false);
const toastMessage = ref("");
const showToast = ref(false);
const userMenuClickListener = (event: Event) => {
  const target = event.target as HTMLElement | null;
  if (!target) return;
  if (!target.closest(".userMenuWrap")) showUserMenu.value = false;
};
const slides = reactive<SlideState[]>([]);
const currentIndex = ref(0);
const adoptedChart = reactive<Record<string, boolean>>({});
const adoptedIllustration = reactive<Record<string, boolean>>({});
const chartCompRefs: Record<string, { exportPngDataUrl: () => Promise<string | null> }> = reactive({});

if (token.value) setAuthToken(token.value);
const currentSlide = computed(() => slides[currentIndex.value]);
const adoptedCount = computed(() => Object.keys(adoptedChart).length + Object.keys(adoptedIllustration).length);
const generatedCount = computed(() => slides.filter((s) => s.analyze || s.illustration).length);
const userInitial = computed(() => (currentUser.value?.username?.slice(0, 1) || "U").toUpperCase());
const userRoleText = computed(() => (currentUser.value?.is_admin ? "管理员" : "普通用户"));
const usageTrendOption = computed(() => ({
  tooltip: { trigger: "axis" },
  grid: { left: 24, right: 16, top: 24, bottom: 24 },
  xAxis: { type: "category", data: ["上传", "解析", "生成", "采用"], axisTick: { show: false } },
  yAxis: { type: "value", splitLine: { lineStyle: { color: "#e5f2ea" } } },
  series: [
    {
      type: "line",
      smooth: true,
      data: [slides.length > 0 ? 1 : 0, slides.length, generatedCount.value, adoptedCount.value],
      lineStyle: { color: "#1f9d60", width: 3 },
      areaStyle: { color: "rgba(31,157,96,0.18)" },
      symbolSize: 8,
      itemStyle: { color: "#1f9d60" },
    },
  ],
}));
const adoptionPieOption = computed(() => ({
  tooltip: { trigger: "item" },
  legend: { bottom: 0, textStyle: { color: "#4b5563" } },
  series: [
    {
      type: "pie",
      radius: ["45%", "72%"],
      avoidLabelOverlap: true,
      label: { show: false },
      data: [
        { value: adoptedCount.value, name: "已采用", itemStyle: { color: "#1f9d60" } },
        { value: Math.max(generatedCount.value - adoptedCount.value, 0), name: "待采用", itemStyle: { color: "#b7d8c5" } },
      ],
    },
  ],
}));
const overviewChartWidth = computed(() => {
  const w = viewportWidth.value;
  if (w <= 1100) return Math.max(260, w - 120);
  return Math.max(320, Math.floor((w - 180) / 2) - 40);
});

function newId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function createInputFromPage(title: string, text: string): SlideRequest {
  return { topic: title || "未命名页面", body: text || "", data_description: "", slide_type: "content", mode: "auto" };
}

async function doAuth() {
  authLoading.value = true;
  authMessage.value = "";
  try {
    if (authTab.value === "register" && authPwd.value !== regConfirmPwd.value) {
      throw new Error("两次输入的密码不一致");
    }
    const resp = authTab.value === "login"
      ? await login(baseUrl.value, authName.value, authPwd.value)
      : await register(baseUrl.value, {
          username: authName.value,
          password: authPwd.value,
          full_name: regFullName.value,
          email: regEmail.value,
          organization: regOrg.value,
        });
    token.value = resp.token;
    currentUser.value = resp.user;
    setAuthToken(resp.token);
    localStorage.setItem("token", resp.token);
    step.value = "home";
    activityLogs.value.unshift(`用户 ${resp.user.username} 登录成功`);
  } catch (e: any) {
    authMessage.value = e?.message || String(e);
  } finally {
    authLoading.value = false;
  }
}

function logout() {
  token.value = "";
  currentUser.value = null;
  setAuthToken("");
  localStorage.removeItem("token");
  step.value = "home";
  activityLogs.value.unshift("用户已退出登录");
  showUserMenu.value = false;
}

function openUpload() {
  uploadInputRef.value?.click();
}

async function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  input.value = "";
  uploadLoading.value = true;
  uploadMessage.value = "";
  try {
    const resp = await extractText(baseUrl.value, file);
    docName.value = resp.filename;
    slides.splice(0, slides.length);
    const pages = resp.pages_detail.length > 0 ? resp.pages_detail : [{ page: 1, title: resp.title || "第1页", text: resp.text }];
    for (const p of pages) {
      slides.push({
        id: `${newId()}_${p.page}`,
        input: createInputFromPage(p.title || `第 ${p.page} 页`, p.text || ""),
        statusAnalyze: "idle",
        statusIllustration: "idle",
        history: [],
      });
    }
    currentIndex.value = 0;
    tab.value = "workspace";
    step.value = "workspace";
    uploadMessage.value = `解析完成，共 ${slides.length} 页。`;
    activityLogs.value.unshift(`上传并解析文件 ${resp.filename}，共 ${slides.length} 页`);
  } catch (e: any) {
    uploadMessage.value = e?.message || "文件解析失败";
  } finally {
    uploadLoading.value = false;
  }
}

async function generateChart() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.statusAnalyze = "loading";
  slide.errorAnalyze = undefined;
  try {
    slide.analyze = await analyze(baseUrl.value, slide.input);
    slide.statusAnalyze = "success";
    activityLogs.value.unshift(`第 ${currentIndex.value + 1} 页图表生成完成`);
  } catch (e: any) {
    slide.statusAnalyze = "error";
    slide.errorAnalyze = e?.message || String(e);
  }
}

async function generateIllustration() {
  const slide = currentSlide.value;
  if (!slide) return;
  slide.statusIllustration = "loading";
  slide.errorIllustration = undefined;
  try {
    slide.illustration = await illustration(baseUrl.value, slide.input);
    slide.statusIllustration = "success";
    activityLogs.value.unshift(`第 ${currentIndex.value + 1} 页配图策略生成完成`);
  } catch (e: any) {
    slide.statusIllustration = "error";
    slide.errorIllustration = e?.message || String(e);
  }
}

async function generateBoth() {
  await Promise.all([generateChart(), generateIllustration()]);
}

function adoptChart() {
  if (currentSlide.value) {
    adoptedChart[currentSlide.value.id] = true;
    activityLogs.value.unshift(`第 ${currentIndex.value + 1} 页图表已采用`);
  }
}

function adoptIllustrationAction() {
  if (currentSlide.value) {
    adoptedIllustration[currentSlide.value.id] = true;
    activityLogs.value.unshift(`第 ${currentIndex.value + 1} 页配图已采用`);
  }
}

function updateIllustration(next: { keywords: string[]; prompt: string }) {
  const slide = currentSlide.value;
  if (!slide?.illustration) return;
  slide.illustration.illustration.keywords = next.keywords;
  slide.illustration.illustration.prompt = next.prompt;
}

function setChartRef(id: string) {
  return (instance: any) => {
    if (instance) chartCompRefs[id] = instance;
  };
}

async function exportPptx() {
  const pptx = new (PPTXGenJS as any)();
  pptx.layout = "LAYOUT_WIDE";
  await nextTick();
  await new Promise((r) => setTimeout(r, 500));
  for (const s of slides) {
    const ps = pptx.addSlide();
    ps.addText(s.input.topic || "Slide", { x: 0.4, y: 0.2, w: 12.6, h: 0.5, fontSize: 18, bold: true, color: "000000" });
    const chartComp = chartCompRefs[s.id];
    const dataUrl = chartComp && s.analyze?.chart?.echartsOption ? await chartComp.exportPngDataUrl() : null;
    if (dataUrl && dataUrl.includes(",")) ps.addImage({ data: dataUrl.split(",")[1], x: 0.4, y: 0.8, w: 12.6, h: 4.6 });
    const ill: IllustrationResponse | undefined = s.illustration?.illustration;
    const textBlock = `插图策略：${ill?.needIllus ? "需要插图" : "不强需插图"}\nkeywords:\n${(ill?.keywords || []).slice(0, 8).map((k) => `- ${k}`).join("\n")}\nprompt:\n${(ill?.prompt || "").slice(0, 500)}`;
    ps.addText(textBlock, { x: 0.4, y: 5.55, w: 12.6, h: 1.8, fontSize: 10, color: "111111" });
  }
  pptx.writeFile({ fileName: `LingDrawPPT_demo_${Date.now()}.pptx` });
}

async function loadAdminUsers() {
  adminList.value = await adminUsers(baseUrl.value);
}

function showTopToast(message: string) {
  toastMessage.value = message;
  showToast.value = true;
  window.setTimeout(() => {
    showToast.value = false;
  }, 1800);
}

function gotoWorkspace() {
  if (slides.length === 0) {
    step.value = "upload";
    showTopToast("请先上传 PPTX / PDF 文件，再进入工作台");
    return;
  }
  step.value = "workspace";
}

onMounted(async () => {
  window.addEventListener("resize", handleResize);
  window.addEventListener("click", userMenuClickListener);
  if (!token.value) return;
  try {
    currentUser.value = await me(baseUrl.value);
    activityLogs.value.unshift(`欢迎回来，${currentUser.value.username}`);
  } catch {
    token.value = "";
    setAuthToken("");
    localStorage.removeItem("token");
  }
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  window.removeEventListener("click", userMenuClickListener);
});
</script>

<template>
  <div class="shell">
    <transition name="toast-fade">
      <div v-if="showToast" class="topToast">{{ toastMessage }}</div>
    </transition>
    <header v-if="token" class="topbar">
      <div class="logo">LingDraw PPT Studio</div>
      <nav class="nav">
        <button class="navBtn" :class="{ active: step === 'home' }" @click="step = 'home'">首页</button>
        <button class="navBtn" :class="{ active: step === 'upload' }" @click="step = 'upload'" :disabled="!token">上传</button>
        <button class="navBtn" :class="{ active: step === 'workspace' }" @click="gotoWorkspace">工作台</button>
        <button v-if="currentUser?.is_admin" class="navBtn" :class="{ active: tab === 'admin' }" @click="tab = 'admin'; step = 'workspace'; loadAdminUsers()">管理员</button>
      </nav>
      <div class="topRight">
        <template v-if="token">
          <div class="userMenuWrap">
            <button class="userInfo" @click.stop="showUserMenu = !showUserMenu">
              <div class="avatar">{{ userInitial }}</div>
              <div class="userMeta">
                <div class="userName">{{ currentUser?.username || "用户" }}</div>
                <div class="userRole">{{ userRoleText }}</div>
              </div>
            </button>
            <div v-if="showUserMenu" class="userMenu">
              <div class="menuItem strong">{{ currentUser?.username || "用户" }}</div>
              <div class="menuItem muted">{{ userRoleText }}</div>
              <button class="menuBtn" @click="logout">退出登录</button>
            </div>
          </div>
        </template>
      </div>
    </header>

    <main class="main" :class="{ authMain: !token }">
      <section v-if="!token" class="authCard loginOnlyCard">
        <div class="authBrand">
          <div class="authEyebrow">WELCOME</div>
          <h1 class="authTitle">LingDraw PPT Studio</h1>
          <p class="authSlogan">上传你的文档，一键生成专业图表与配图策略</p>
        </div>
        <div class="authRight">
          <div class="authTabs">
            <button class="authTab" :class="{ active: authTab === 'login' }" @click="authTab = 'login'">登录</button>
            <button class="authTab" :class="{ active: authTab === 'register' }" @click="authTab = 'register'">注册</button>
          </div>
          <input v-model="authName" class="textInput" placeholder="请输入用户名" />
          <input v-model="authPwd" class="textInput" placeholder="请输入密码(至少6位)" type="password" />
          <template v-if="authTab === 'register'">
            <input v-model="regConfirmPwd" class="textInput" placeholder="请再次输入密码" type="password" />
            <input v-model="regFullName" class="textInput" placeholder="请输入姓名" />
            <input v-model="regEmail" class="textInput" placeholder="请输入邮箱" />
            <input v-model="regOrg" class="textInput" placeholder="请输入单位/组织" />
          </template>
          <button class="btn authSubmit" @click="doAuth" :disabled="authLoading">{{ authLoading ? "提交中..." : "提交" }}</button>
          <div v-if="authMessage" class="hint">{{ authMessage }}</div>
        </div>
      </section>

      <section v-else-if="step === 'home'" class="heroCard">
        <h2>工作台总览</h2>
        <div class="dashboardGrid">
          <div class="statCard"><div class="k">当前文件</div><div class="v">{{ docName || "未上传" }}</div></div>
          <div class="statCard"><div class="k">页面数量</div><div class="v">{{ slides.length }}</div></div>
          <div class="statCard"><div class="k">已生成页面</div><div class="v">{{ generatedCount }}</div></div>
          <div class="statCard"><div class="k">已采用结果</div><div class="v">{{ adoptedCount }}</div></div>
        </div>
        <div class="dashboardGrid">
          <div class="panel">
            <div class="panelTitle">最近消息记录</div>
            <div class="logList">
              <div v-for="(log, i) in activityLogs.slice(0, 8)" :key="i" class="logItem">{{ log }}</div>
            </div>
          </div>
          <div class="panel">
            <div class="panelTitle">快速教程</div>
            <ol class="guideList">
              <li>点击顶部“上传”并选择 `PPTX/PDF`。</li>
              <li>系统自动解析每页文字，进入工作台。</li>
              <li>左侧选中某一页，右侧点击“生成图表/配图”。</li>
              <li>确认效果后点击“采用图表/采用配图”。</li>
              <li>最后导出 `PPTX`。</li>
            </ol>
          </div>
        </div>
        <div class="dashboardGrid chartRow">
          <div class="panel">
            <div class="panelTitle">使用流程趋势</div>
            <ChartPreview :option="usageTrendOption" :width="overviewChartWidth" :height="280" />
          </div>
          <div class="panel">
            <div class="panelTitle">生成采用占比</div>
            <ChartPreview :option="adoptionPieOption" :width="overviewChartWidth" :height="280" />
          </div>
        </div>
        <div class="actionRow">
          <button class="btn" @click="step = 'upload'">开始上传</button>
          <button class="btn secondary" @click="gotoWorkspace">进入工作台</button>
        </div>
      </section>

      <section v-else-if="step === 'upload'" class="uploadCard">
        <h2>上传 PPTX / PDF</h2>
        <button class="btn" @click="openUpload" :disabled="uploadLoading">{{ uploadLoading ? "解析中..." : "选择文件" }}</button>
        <input ref="uploadInputRef" class="hiddenFile" type="file" accept=".pptx,.pdf" @change="onPickFile" />
        <div v-if="uploadMessage" class="hint">{{ uploadMessage }}</div>
      </section>

      <section v-else class="workspace">
        <div v-if="tab === 'workspace'" class="workspaceBody">
          <aside class="leftPane">
            <div class="paneTitle">文件页预览 {{ docName ? `· ${docName}` : "" }}</div>
            <div class="pageList">
              <button v-for="(s, i) in slides" :key="s.id" class="pageItem" :class="{ active: i === currentIndex }" @click="currentIndex = i">
                <div class="pageIdx">第 {{ i + 1 }} 页</div>
                <div class="pageTitle">{{ s.input.topic }}</div>
                <div class="pageSnippet">{{ (s.input.body || "").slice(0, 60) }}</div>
              </button>
            </div>
          </aside>

          <section class="centerPane" v-if="currentSlide">
            <div class="paneTitle">当前页内容</div>
            <textarea v-model="currentSlide.input.body" class="contentEditor"></textarea>
            <div class="actionRow">
              <button class="btn secondary" @click="generateChart">生成图表</button>
              <button class="btn secondary" @click="generateIllustration">生成配图</button>
              <button class="btn" @click="generateBoth">一起生成</button>
              <button class="btn ghost" @click="adoptChart" :disabled="!currentSlide.analyze">采用图表</button>
              <button class="btn ghost" @click="adoptIllustrationAction" :disabled="!currentSlide.illustration">采用配图</button>
            </div>
            <div class="statusRow">
              <span>图表采用: {{ adoptedChart[currentSlide.id] ? "已采用" : "未采用" }}</span>
              <span>配图采用: {{ adoptedIllustration[currentSlide.id] ? "已采用" : "未采用" }}</span>
              <button class="btn secondary" @click="exportPptx">导出 PPTX</button>
            </div>
            <ResultPanel :slide="currentSlide" :onRerunChart="generateChart" :onRerunIllustration="generateIllustration" :onRerunBoth="generateBoth" :onChangeIllustration="updateIllustration" />
          </section>
        </div>

        <div v-else-if="currentUser?.is_admin" class="adminPane">
          <div class="paneTitle">管理员界面</div>
          <button class="btn secondary" @click="loadAdminUsers">刷新用户列表</button>
          <div class="table">
            <div class="tr head"><div>ID</div><div>用户名</div><div>角色</div><div>创建时间</div></div>
            <div class="tr" v-for="u in adminList" :key="u.id">
              <div>{{ u.id }}</div><div>{{ u.username }}</div><div>{{ u.is_admin ? "管理员" : "普通用户" }}</div><div>{{ u.created_at }}</div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer v-if="token" class="footer">
      <span>LingDraw PPT Studio</span>
      <span>上传解析 · 按页生成 · 人工确认采用</span>
    </footer>

    <div class="hiddenExport">
      <ChartPreview v-for="s in slides" :key="s.id" :ref="setChartRef(s.id)" :option="s.analyze?.chart?.echartsOption" :width="1200" :height="560" />
    </div>
  </div>
</template>

<style scoped>
.shell{min-height:100vh;display:flex;flex-direction:column;background:linear-gradient(180deg,#f6fffb 0%,#edfbf3 100%);}
.topToast{position:fixed;top:84px;left:50%;transform:translateX(-50%);z-index:50;background:#0f5132;color:#fff;padding:10px 14px;border-radius:10px;font-size:13px;font-weight:700;box-shadow:0 10px 20px rgba(15,81,50,.25);}
.topbar{min-height:70px;padding:10px 18px;display:flex;align-items:center;justify-content:flex-start;background:#fff;border-bottom:1px solid #d7efe1;gap:20px;flex-wrap:wrap;}
.logo{font-size:18px;font-weight:800;color:#0f5132;}
.nav{display:flex;gap:8px;margin-left:8px;}
.navBtn{border:none;background:transparent;color:#3c4b43;border-radius:10px;padding:8px 10px;font-weight:700;cursor:pointer;position:relative;transition:color .18s ease;}
.navBtn::after{content:"";position:absolute;left:10px;right:10px;bottom:2px;height:3px;border-radius:999px;background:transparent;transition:all .18s ease;}
.navBtn:hover{color:#0f5132;background:rgba(31,157,96,.07);}
.navBtn.active{color:#0f5132;background:rgba(31,157,96,.1);}
.navBtn.active::after{background:#1f9d60;}
.topRight{display:flex;gap:8px;align-items:center;margin-left:auto;}
.userMenuWrap{position:relative;}
.userInfo{display:flex;align-items:center;gap:8px;padding:6px 10px;border:1px solid #dcefe5;border-radius:999px;background:#f7fcf9;cursor:pointer;}
.avatar{width:28px;height:28px;border-radius:50%;background:#1f9d60;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;}
.userMeta{display:flex;flex-direction:column;align-items:flex-start;line-height:1.1;}
.userName{font-size:13px;font-weight:700;color:#0f5132;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.userRole{font-size:11px;color:#6b7280;}
.userMenu{position:absolute;right:0;top:44px;min-width:170px;background:#fff;border:1px solid #dcefe5;border-radius:12px;box-shadow:0 8px 20px rgba(15,81,50,.12);padding:8px;z-index:20;}
.menuItem{padding:6px 8px;font-size:12px;}
.menuItem.strong{font-weight:700;color:#0f5132;}
.menuItem.muted{color:#6b7280;}
.menuBtn{width:100%;margin-top:6px;border:1px solid #f0c2c2;background:#fff8f8;color:#b91c1c;border-radius:8px;padding:7px 8px;font-size:12px;font-weight:700;cursor:pointer;}
.main{flex:1;padding:clamp(12px,2vw,24px);display:flex;flex-direction:column;align-items:center;}
.main.authMain{justify-content:center;align-items:center;padding:32px 20px;background:
  radial-gradient(circle at 15% 20%, rgba(31,157,96,.12), transparent 42%),
  radial-gradient(circle at 85% 78%, rgba(89,126,255,.10), transparent 36%),
  linear-gradient(180deg,#f8fffb 0%,#eefaf3 100%);}
.main>section{width:100%;max-width:1400px;margin-inline:auto;box-sizing:border-box;}
.main.authMain>section{width:min(800px, calc(100vw - 40px));max-width:none;margin-inline:0;}
.authCard,.heroCard,.uploadCard,.workspace{background:#fff;border:1px solid #d7efe1;border-radius:16px;padding:clamp(12px,1.6vw,22px);box-shadow:0 10px 26px rgba(15,81,50,.08);}
.authCard,.uploadCard{max-width:840px;display:flex;flex-direction:column;gap:12px;}
.heroCard{display:flex;flex-direction:column;gap:10px;}
.authCard{
  max-width:800px;
  width:100%;
  display:flex;
  flex-direction:column;
  gap:14px;
  background: linear-gradient(145deg, #ffffff 0%, #f7fcf9 100%);
}
.loginOnlyCard{
  width:100%;
  border-radius:22px;
  border:1px solid #d2e8dc;
  box-shadow:
    0 20px 40px rgba(15,81,50,.12),
    0 2px 0 rgba(255,255,255,.65) inset;
}
.authBrand{padding:4px 4px 2px 4px;text-align:left;}
.authRight{border:1px solid #dbeee2;border-radius:14px;padding:14px;background:#fff;display:flex;flex-direction:column;gap:8px;}
.authEyebrow{
  display:inline-block;
  font-size:11px;
  letter-spacing:.08em;
  font-weight:800;
  color:#0f5132;
  background:#eaf7ef;
  border-radius:999px;
  padding:4px 10px;
  margin-bottom:8px;
}
.authTitle{margin:0;font-size:30px;line-height:1.15;color:#0f5132;letter-spacing:-0.02em;}
.authSlogan{margin:10px 0 0 0;color:#4b5563;font-size:14px;line-height:1.5;}
.authTabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;}
.authTab{
  border:1px solid #cfe8d9;
  background:#f7fcf9;
  color:#1f3a2e;
  border-radius:10px;
  padding:8px 10px;
  font-weight:700;
  cursor:pointer;
}
.authTab.active{
  background:#e8f8ef;
  border-color:#9fd5b8;
  color:#0f5132;
}
.textInput{
  border:1px solid #cce9da;
  border-radius:10px;
  padding:11px 12px;
  width:100%;
  box-sizing:border-box;
  transition:border-color .18s ease, box-shadow .18s ease;
}
.textInput:focus{
  outline:none;
  border-color:#7fc7a2;
  box-shadow:0 0 0 3px rgba(31,157,96,.12);
}
.authSubmit{margin-top:8px;width:100%;}
.btn{border:1px solid #1f9d60;background:linear-gradient(135deg,#3fbc75 0%,#1f9d60 100%);color:#fff;border-radius:10px;padding:9px 12px;font-weight:700;cursor:pointer;}
.btn.secondary,.btn.ghost{background:#fff;color:#0f5132;border-color:#8bcda9;}
.hint{font-size:13px;color:#4b5563;}
.dashboardGrid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:12px;margin:10px 0;}
.chartRow .panel{min-height:330px;}
.statCard{border:1px solid #dcefe5;border-radius:12px;padding:10px;background:#f8fffb;}
.statCard .k{font-size:12px;color:#6b7280;}
.statCard .v{font-size:18px;font-weight:800;color:#0f5132;margin-top:4px;}
.panel{border:1px solid #dcefe5;border-radius:12px;padding:10px;background:#fff;}
.panelTitle{font-size:14px;font-weight:700;color:#0f5132;margin-bottom:8px;}
.logList{display:flex;flex-direction:column;gap:6px;max-height:160px;overflow:auto;}
.logItem{font-size:12px;color:#374151;background:#f7faf9;border-radius:8px;padding:6px 8px;}
.guideList{margin:0;padding-left:18px;color:#374151;font-size:13px;display:flex;flex-direction:column;gap:6px;}
.workspaceBody{display:grid;grid-template-columns:minmax(240px,320px) minmax(0,1fr);gap:12px;}
.leftPane,.centerPane{border:1px solid #e2f3ea;border-radius:14px;padding:12px;background:#fcfffd;}
.paneTitle{font-size:14px;font-weight:800;color:#0f5132;margin-bottom:10px;}
.pageList{display:flex;flex-direction:column;gap:8px;max-height:72vh;overflow:auto;}
.pageItem{text-align:left;border:1px solid #dcefe5;background:#fff;border-radius:12px;padding:10px;cursor:pointer;}
.pageItem.active{border-color:#58b980;box-shadow:0 0 0 2px rgba(88,185,128,.2);}
.pageIdx{font-size:12px;color:#0f5132;font-weight:700;}
.pageTitle{font-size:13px;font-weight:700;color:#1f2937;margin-top:4px;}
.pageSnippet{font-size:12px;color:#6b7280;margin-top:4px;}
.contentEditor{width:100%;min-height:130px;border:1px solid #d9eee3;border-radius:10px;padding:10px;resize:vertical;}
.actionRow{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;}
.statusRow{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:13px;color:#334155;margin-bottom:10px;}
.footer{min-height:54px;border-top:1px solid #d7efe1;background:#fff;display:flex;justify-content:space-between;align-items:center;padding:8px 18px;color:#475569;font-size:12px;gap:8px;flex-wrap:wrap;}
.table{margin-top:10px;border:1px solid #d8efdf;border-radius:12px;overflow:hidden;}
.tr{display:grid;grid-template-columns:80px 1fr 120px 1.5fr;gap:8px;padding:8px 10px;border-top:1px solid #eef8f2;font-size:13px;}
.tr.head{background:#f1fcf6;font-weight:800;color:#0f5132;border-top:none;}
.hiddenFile,.hiddenExport{display:none;}
.toast-fade-enter-active,.toast-fade-leave-active{transition:all .18s ease;}
.toast-fade-enter-from,.toast-fade-leave-to{opacity:0;transform:translateX(-50%) translateY(-8px);}
@media (max-width:1100px){.workspaceBody,.dashboardGrid,.authCard{grid-template-columns:1fr;} .chartRow .panel{min-height:300px;} .main>section{max-width:100%;} .main.authMain>section{width:min(900px, calc(100vw - 20px));} .userName{max-width:92px;} .nav{overflow-x:auto;max-width:100%;} .authTitle{font-size:26px;}}
</style>
