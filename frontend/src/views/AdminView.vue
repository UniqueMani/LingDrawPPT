<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  adminClearLogs,
  adminDeleteFile,
  adminDownloadFile,
  adminExportLogs,
  adminListAuditLogs,
  adminListFiles,
  adminListLogs,
  adminListUsers,
  adminOverview,
  adminResetPassword,
  adminSetUserStatus,
  adminUpdateUser,
} from "../api/client";
import ChartPreview from "../components/ChartPreview.vue";
import { store } from "../store";
import type {
  AdminAuditLogDTO,
  AdminOverviewDTO,
  AdminUserDTO,
  UploadedFileDTO,
  UsageLogDTO,
} from "../types";

type Tab = "overview" | "users" | "files" | "logs";
const router = useRouter();
const route = useRoute();

function tabFromQuery(value: unknown): Tab {
  return value === "users" || value === "files" || value === "logs" ? value : "overview";
}

const activeTab = ref<Tab>(tabFromQuery(route.query.tab));
const busy = ref(false);
const message = ref("");
const error = ref("");
const headerCopy = computed(() => {
  const copy: Record<Tab, { eyebrow: string; title: string; description: string }> = {
    overview: {
      eyebrow: "管理后台",
      title: "系统维护中心",
      description: "查看用户、文件与系统使用情况。",
    },
    users: {
      eyebrow: "用户管理",
      title: "用户与权限管理",
      description: "维护用户资料、启用状态与登录密码。",
    },
    files: {
      eyebrow: "文件管理",
      title: "上传文件管理",
      description: "查询用户上传记录、解析状态与文件详情。",
    },
    logs: {
      eyebrow: "日志维护",
      title: "系统日志维护",
      description: "查询、导出和清理使用日志，检查管理员审计记录。",
    },
  };
  return copy[activeTab.value];
});

const overview = ref<AdminOverviewDTO | null>(null);
const users = ref<AdminUserDTO[]>([]);
const files = ref<UploadedFileDTO[]>([]);
const logs = ref<UsageLogDTO[]>([]);
const audits = ref<AdminAuditLogDTO[]>([]);
const userTotal = ref(0);
const fileTotal = ref(0);
const logTotal = ref(0);
const auditTotal = ref(0);

const userKeyword = ref("");
const userActive = ref("");
const fileKeyword = ref("");
const fileStatus = ref("");
const logEvent = ref("");
const logFrom = ref("");
const logTo = ref("");
const clearBefore = ref("");
const logMode = ref<"usage" | "audit">("usage");

const editUser = ref<AdminUserDTO | null>(null);
const editForm = ref({ full_name: "", email: "", organization: "" });
const resetUser = ref<AdminUserDTO | null>(null);
const resetPassword = ref("");

const eventLabels: Record<string, string> = {
  upload: "上传文件",
  analyze: "分析页面",
  generate: "生成内容",
  adopt: "采用结果",
};

const actionLabels: Record<string, string> = {
  update_user: "编辑用户",
  enable_user: "启用用户",
  disable_user: "禁用用户",
  reset_password: "重置密码",
  soft_delete_file: "软删除文件",
  clear_logs: "清理日志",
};

const statusLabels: Record<string, string> = {
  processing: "解析中",
  success: "成功",
  failed: "失败",
};

function showError(value: unknown) {
  error.value = value instanceof Error ? value.message : String(value);
  message.value = "";
}

function showMessage(value: string) {
  message.value = value;
  error.value = "";
}

function fmtTime(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function fmtSize(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

async function loadOverview() {
  overview.value = await adminOverview(store.baseUrl);
}

async function loadUsers() {
  const data = await adminListUsers(store.baseUrl, { keyword: userKeyword.value, active: userActive.value || undefined });
  users.value = data.items;
  userTotal.value = data.total;
}

async function loadFiles() {
  const data = await adminListFiles(store.baseUrl, { keyword: fileKeyword.value, status: fileStatus.value });
  files.value = data.items;
  fileTotal.value = data.total;
}

async function loadLogs() {
  if (logMode.value === "audit") {
    const data = await adminListAuditLogs(store.baseUrl);
    audits.value = data.items;
    auditTotal.value = data.total;
    return;
  }
  const data = await adminListLogs(store.baseUrl, {
    event_type: logEvent.value,
    date_from: logFrom.value,
    date_to: logTo.value,
  });
  logs.value = data.items;
  logTotal.value = data.total;
}

async function refresh() {
  busy.value = true;
  error.value = "";
  try {
    if (activeTab.value === "overview") await loadOverview();
    if (activeTab.value === "users") await loadUsers();
    if (activeTab.value === "files") await loadFiles();
    if (activeTab.value === "logs") await loadLogs();
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}

function openEdit(user: AdminUserDTO) {
  editUser.value = user;
  editForm.value = { full_name: user.full_name, email: user.email, organization: user.organization };
}

async function saveUser() {
  if (!editUser.value) return;
  try {
    await adminUpdateUser(store.baseUrl, editUser.value.id, editForm.value);
    editUser.value = null;
    showMessage("用户资料已更新");
    await loadUsers();
  } catch (e) {
    showError(e);
  }
}

async function toggleUser(user: AdminUserDTO) {
  const next = !user.is_active;
  if (!window.confirm(`确定要${next ? "启用" : "禁用"}用户“${user.username}”吗？`)) return;
  try {
    await adminSetUserStatus(store.baseUrl, user.id, next);
    showMessage(`用户已${next ? "启用" : "禁用"}`);
    await loadUsers();
  } catch (e) {
    showError(e);
  }
}

function openReset(user: AdminUserDTO) {
  resetUser.value = user;
  resetPassword.value = "";
}

async function saveResetPassword() {
  if (!resetUser.value) return;
  try {
    await adminResetPassword(store.baseUrl, resetUser.value.id, resetPassword.value);
    resetUser.value = null;
    showMessage("临时密码已设置");
  } catch (e) {
    showError(e);
  }
}

async function downloadFile(file: UploadedFileDTO) {
  try {
    await adminDownloadFile(store.baseUrl, file.id, file.original_filename);
  } catch (e) {
    showError(e);
  }
}

async function deleteFile(file: UploadedFileDTO) {
  if (!window.confirm(`确定软删除文件记录“${file.original_filename}”吗？原文件会保留。`)) return;
  try {
    await adminDeleteFile(store.baseUrl, file.id);
    showMessage("文件记录已软删除");
    await loadFiles();
  } catch (e) {
    showError(e);
  }
}

async function exportLogs() {
  try {
    await adminExportLogs(store.baseUrl, { event_type: logEvent.value, date_from: logFrom.value, date_to: logTo.value });
  } catch (e) {
    showError(e);
  }
}

async function clearLogs() {
  if (!clearBefore.value) return showError("请选择日志清理截止日期");
  if (!window.confirm(`确定清理 ${clearBefore.value} 之前的使用日志吗？此操作不可撤销。`)) return;
  try {
    const result = await adminClearLogs(store.baseUrl, `${clearBefore.value}T00:00:00`);
    showMessage(`已清理 ${result.deleted} 条使用日志`);
    await loadLogs();
  } catch (e) {
    showError(e);
  }
}

const trendOption = computed(() => {
  const keys = ["upload", "analyze", "generate", "adopt"];
  return {
    tooltip: { trigger: "axis" as const },
    grid: { left: 38, right: 16, top: 18, bottom: 28 },
    xAxis: { type: "category" as const, data: keys.map((key) => eventLabels[key]), axisLine: { lineStyle: { color: "#d9cdd1" } } },
    yAxis: { type: "value" as const, splitLine: { lineStyle: { color: "#f0e8eb" } } },
    color: ["#8b2942"],
    series: [{ type: "bar" as const, data: keys.map((key) => overview.value?.event_counts[key] || 0), barMaxWidth: 42 }],
  };
});

onMounted(async () => {
  if (store.currentUser && !store.currentUser.is_admin) {
    router.push("/home");
    return;
  }
  await refresh();
});

watch(
  () => route.query.tab,
  async (tab) => {
    activeTab.value = tabFromQuery(tab);
    await refresh();
  },
);
</script>

<template>
  <div class="admin-root">
    <header class="admin-head">
      <div>
        <span class="eyebrow">{{ headerCopy.eyebrow }}</span>
        <h1>{{ headerCopy.title }}</h1>
        <p>{{ headerCopy.description }}</p>
      </div>
      <button class="btn secondary" type="button" :disabled="busy" @click="refresh">刷新数据</button>
    </header>

    <p v-if="message" class="notice ok">{{ message }}</p>
    <p v-if="error" class="notice error">{{ error }}</p>

    <section v-if="activeTab === 'overview'" class="stack">
      <div class="metric-grid">
        <article class="metric"><span>用户总数</span><strong>{{ overview?.total_users || 0 }}</strong></article>
        <article class="metric"><span>启用用户</span><strong>{{ overview?.active_users || 0 }}</strong></article>
        <article class="metric"><span>文件记录</span><strong>{{ overview?.total_files || 0 }}</strong></article>
        <article class="metric"><span>解析失败</span><strong>{{ overview?.failed_files || 0 }}</strong></article>
        <article class="metric"><span>近 30 天事件</span><strong>{{ overview?.recent_events || 0 }}</strong></article>
      </div>
      <div class="two-col">
        <article class="panel chart-panel">
          <h2>近 30 天使用事件</h2>
          <ChartPreview :option="trendOption" :height="260" />
        </article>
        <article class="panel">
          <h2>最近管理员操作</h2>
          <div class="list-row" v-for="item in overview?.recent_audit_logs || []" :key="item.id">
            <strong>{{ actionLabels[item.action_type] || item.action_type }}</strong>
            <span>{{ item.admin_username }} · {{ fmtTime(item.created_at) }}</span>
          </div>
          <p v-if="!overview?.recent_audit_logs.length" class="empty">暂无操作记录</p>
        </article>
      </div>
      <article class="panel">
        <h2>最近解析失败文件</h2>
        <div class="list-row" v-for="item in overview?.recent_failed_files || []" :key="item.id">
          <strong>{{ item.original_filename }}</strong>
          <span>{{ item.username }} · {{ item.error_message || "解析失败" }}</span>
        </div>
        <p v-if="!overview?.recent_failed_files.length" class="empty">暂无失败文件</p>
      </article>
    </section>

    <section v-if="activeTab === 'users'" class="panel">
      <div class="toolbar">
        <input v-model="userKeyword" class="input" placeholder="搜索用户名、姓名、邮箱或组织" />
        <select v-model="userActive" class="input"><option value="">全部状态</option><option value="true">已启用</option><option value="false">已禁用</option></select>
        <button class="btn primary" @click="loadUsers">查询</button>
        <span class="count">共 {{ userTotal }} 位用户</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>用户</th><th>姓名</th><th>组织</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td><strong>{{ user.username }}</strong><small>{{ user.email || "-" }}</small></td>
              <td>{{ user.full_name || "-" }}</td><td>{{ user.organization || "-" }}</td>
              <td>{{ user.is_admin ? "管理员" : "普通用户" }}</td>
              <td><span :class="['status', user.is_active ? 'success' : 'failed']">{{ user.is_active ? "已启用" : "已禁用" }}</span></td>
              <td>{{ fmtTime(user.created_at) }}</td>
              <td class="actions">
                <button class="link-btn" @click="openEdit(user)">编辑</button>
                <button v-if="!user.is_admin" class="link-btn" @click="toggleUser(user)">{{ user.is_active ? "禁用" : "启用" }}</button>
                <button v-if="!user.is_admin" class="link-btn" @click="openReset(user)">重置密码</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="activeTab === 'files'" class="panel">
      <div class="toolbar">
        <input v-model="fileKeyword" class="input" placeholder="搜索文件名" />
        <select v-model="fileStatus" class="input"><option value="">全部状态</option><option value="success">成功</option><option value="failed">失败</option><option value="processing">解析中</option></select>
        <button class="btn primary" @click="loadFiles">查询</button>
        <span class="count">共 {{ fileTotal }} 条记录</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>文件名</th><th>用户</th><th>大小</th><th>页数</th><th>状态</th><th>上传时间</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="file in files" :key="file.id">
              <td><strong>{{ file.original_filename }}</strong><small v-if="file.error_message">{{ file.error_message }}</small></td>
              <td>{{ file.username }}</td><td>{{ fmtSize(file.file_size) }}</td><td>{{ file.pages }}</td>
              <td><span :class="['status', file.parse_status]">{{ statusLabels[file.parse_status] || file.parse_status }}</span></td>
              <td>{{ fmtTime(file.created_at) }}</td>
              <td class="actions"><button class="link-btn" @click="downloadFile(file)">下载</button><button class="link-btn danger" @click="deleteFile(file)">软删除</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="activeTab === 'logs'" class="panel">
      <div class="subtabs"><button :class="{ active: logMode === 'usage' }" @click="logMode = 'usage'; loadLogs()">使用日志</button><button :class="{ active: logMode === 'audit' }" @click="logMode = 'audit'; loadLogs()">管理员审计</button></div>
      <template v-if="logMode === 'usage'">
        <div class="toolbar">
          <select v-model="logEvent" class="input"><option value="">全部事件</option><option v-for="(label, key) in eventLabels" :key="key" :value="key">{{ label }}</option></select>
          <input v-model="logFrom" class="input" type="date" /><input v-model="logTo" class="input" type="date" />
          <button class="btn primary" @click="loadLogs">查询</button><button class="btn secondary" @click="exportLogs">导出 CSV</button>
          <span class="count">共 {{ logTotal }} 条日志</span>
        </div>
        <div class="maintenance"><span>清理指定日期以前的日志</span><input v-model="clearBefore" class="input" type="date" /><button class="btn danger-btn" @click="clearLogs">清理日志</button></div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>用户</th><th>事件</th><th>发生时间</th></tr></thead><tbody><tr v-for="item in logs" :key="item.id"><td>{{ item.id }}</td><td>{{ item.username }}</td><td>{{ eventLabels[item.event_type] || item.event_type }}</td><td>{{ fmtTime(item.created_at) }}</td></tr></tbody></table></div>
      </template>
      <template v-else>
        <p class="count">共 {{ auditTotal }} 条审计记录</p>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>管理员</th><th>操作</th><th>目标</th><th>详情</th><th>时间</th></tr></thead><tbody><tr v-for="item in audits" :key="item.id"><td>{{ item.id }}</td><td>{{ item.admin_username }}</td><td>{{ actionLabels[item.action_type] || item.action_type }}</td><td>{{ item.target_type }} #{{ item.target_id }}</td><td>{{ item.detail }}</td><td>{{ fmtTime(item.created_at) }}</td></tr></tbody></table></div>
      </template>
    </section>

    <div v-if="editUser" class="modal-backdrop" @click.self="editUser = null">
      <form class="modal" @submit.prevent="saveUser"><h2>编辑用户</h2><input v-model="editForm.full_name" class="input" placeholder="姓名" /><input v-model="editForm.email" class="input" placeholder="邮箱" /><input v-model="editForm.organization" class="input" placeholder="组织" /><div class="modal-actions"><button type="button" class="btn secondary" @click="editUser = null">取消</button><button class="btn primary">保存</button></div></form>
    </div>
    <div v-if="resetUser" class="modal-backdrop" @click.self="resetUser = null">
      <form class="modal" @submit.prevent="saveResetPassword"><h2>重置 {{ resetUser.username }} 的密码</h2><input v-model="resetPassword" class="input" type="password" placeholder="至少 6 位临时密码" /><div class="modal-actions"><button type="button" class="btn secondary" @click="resetUser = null">取消</button><button class="btn primary">确认重置</button></div></form>
    </div>
  </div>
</template>

<style scoped>
.admin-root { width: 100%; max-width: 1380px; margin: 0 auto; padding: var(--space-6); }
.admin-head, .toolbar, .maintenance, .modal-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.admin-head { justify-content: space-between; margin-bottom: 20px; }
h1 { margin: 10px 0 4px; color: var(--color-text); font-size: 28px; } h2 { margin: 0 0 14px; font-size: 16px; } p { color: var(--color-muted); }
.eyebrow { color: var(--color-primary); font-weight: 800; font-size: 12px; }
.subtabs { display: flex; gap: 6px; padding: 4px; margin-bottom: 18px; border: 1px solid var(--color-border); border-radius: var(--radius-card); background: var(--color-bg-muted); width: fit-content; }
.subtabs button { border: 0; border-radius: var(--radius-control); padding: 0 14px; background: transparent; color: var(--color-muted); font-weight: 800; cursor: pointer; }
.subtabs button.active { color: var(--color-primary); background: var(--color-surface); box-shadow: var(--shadow-card); }
.stack { display: flex; flex-direction: column; gap: 16px; }.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.metric, .panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-card); box-shadow: var(--shadow-card); }
.metric { min-height: 104px; padding: 18px; }.metric span, .count, small { display: block; color: var(--color-muted); font-size: 12px; }.metric strong { display: block; margin-top: 12px; color: var(--color-primary); font-size: 28px; }
.panel { padding: 18px; }.two-col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }.list-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--color-border); font-size: 13px; }.list-row span { color: var(--color-muted); text-align: right; }.empty { font-size: 13px; }
.toolbar { margin-bottom: 14px; }.input { min-height: var(--control-md); border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); padding: 0 11px; background: var(--color-surface); color: var(--color-text); }
.btn { min-height: var(--control-md); padding: 0 14px; border-radius: var(--radius-control); border: 1px solid transparent; cursor: pointer; font-weight: 800; }.primary { color: white; background: var(--color-primary); }.secondary { color: var(--color-primary); background: var(--color-surface); border-color: var(--color-primary-border); }.danger-btn { color: var(--color-danger); background: var(--color-danger-soft); border-color: #fee2e2; }
.table-wrap { overflow-x: auto; } table { width: 100%; min-width: 820px; border-collapse: collapse; font-size: 13px; } th, td { padding: 11px 10px; border-bottom: 1px solid var(--color-border); text-align: left; vertical-align: top; } th { color: var(--color-muted); background: var(--color-bg-muted); font-size: 12px; } td strong { display: block; }.actions { white-space: nowrap; }.link-btn { border: 0; min-height: 28px; padding: 0 6px; color: var(--color-primary); background: transparent; cursor: pointer; font-weight: 800; font-size: 12px; }.link-btn.danger { color: var(--color-danger); }
.status { display: inline-flex; padding: 3px 7px; border-radius: var(--radius-control); font-size: 12px; font-weight: 800; }.status.success { color: #166534; background: #f0fdf4; }.status.failed { color: var(--color-danger); background: var(--color-danger-soft); }.status.processing { color: var(--color-warning); background: #fffbeb; }
.notice { padding: 10px 12px; border-radius: var(--radius-control); font-size: 13px; }.notice.ok { color: #166534; background: #f0fdf4; }.notice.error { color: var(--color-danger); background: var(--color-danger-soft); }.maintenance { margin: 12px 0; padding: 12px; background: var(--color-bg-muted); border-radius: var(--radius-control); }
.modal-backdrop { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 16px; background: rgba(26, 26, 26, .32); }.modal { width: min(440px, 100%); display: flex; flex-direction: column; gap: 12px; padding: 20px; border-radius: var(--radius-card); background: var(--color-surface); box-shadow: var(--shadow-card-hover); }.modal-actions { justify-content: flex-end; margin-top: 4px; }
@media (max-width: 900px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.two-col { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .admin-root { padding: var(--space-4); }.metric-grid { grid-template-columns: 1fr; } }
</style>
