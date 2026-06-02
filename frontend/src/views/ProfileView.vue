<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { updateMe, setAuthToken } from "../api/client";
import { store } from "../store";

const router = useRouter();

const email = ref("");
const editingInfo = ref(false);
const savingInfo = ref(false);
const infoMsg = ref("");
const infoMsgType = ref<"ok" | "err">("ok");

const newUsername = ref("");
const editingUsername = ref(false);
const savingUsername = ref(false);
const usernameMsg = ref("");
const usernameMsgType = ref<"ok" | "err">("ok");

const oldPwd = ref("");
const newPwd = ref("");
const confirmPwd = ref("");
const editingPwd = ref(false);
const savingPwd = ref(false);
const pwdMsg = ref("");
const pwdMsgType = ref<"ok" | "err">("ok");

/** 成功消息 3s 后自动清空 */
function autoHide(msgRef: typeof infoMsg, delay = 3000) {
  setTimeout(() => {
    msgRef.value = "";
  }, delay);
}

function syncFromStore() {
  email.value = store.currentUser?.email ?? "";
}

onMounted(syncFromStore);

function goBack() {
  if (window.history.length > 1) {
    router.back();
  } else {
    router.push("/home");
  }
}

function applyUpdate(resp: Awaited<ReturnType<typeof updateMe>>) {
  store.currentUser = resp.user;
  if (resp.token) {
    store.setToken(resp.token);
    setAuthToken(resp.token);
  }
}

function startEditInfo() {
  syncFromStore();
  infoMsg.value = "";
  editingInfo.value = true;
}

function cancelEditInfo() {
  editingInfo.value = false;
  infoMsg.value = "";
}

async function saveInfo() {
  savingInfo.value = true;
  infoMsg.value = "";
  try {
    const resp = await updateMe(store.baseUrl, {
      email: email.value.trim(),
    });
    applyUpdate(resp);
    editingInfo.value = false;
    infoMsgType.value = "ok";
    infoMsg.value = "保存成功";
    autoHide(infoMsg);
    store.addLog("个人信息已更新");
  } catch (e: any) {
    infoMsgType.value = "err";
    infoMsg.value = e?.message || "保存失败，请稍后重试";
  } finally {
    savingInfo.value = false;
  }
}

function startEditUsername() {
  newUsername.value = store.currentUser?.username ?? "";
  usernameMsg.value = "";
  editingUsername.value = true;
}

function cancelEditUsername() {
  editingUsername.value = false;
  usernameMsg.value = "";
}

async function saveUsername() {
  if (!newUsername.value.trim()) {
    usernameMsgType.value = "err";
    usernameMsg.value = "用户名不能为空";
    return;
  }
  savingUsername.value = true;
  usernameMsg.value = "";
  try {
    const resp = await updateMe(store.baseUrl, {
      username: newUsername.value.trim(),
    });
    applyUpdate(resp);
    editingUsername.value = false;
    usernameMsgType.value = "ok";
    usernameMsg.value = "用户名修改成功";
    autoHide(usernameMsg);
    store.addLog("用户名已更新");
  } catch (e: any) {
    usernameMsgType.value = "err";
    usernameMsg.value = e?.message || "修改失败，请稍后重试";
  } finally {
    savingUsername.value = false;
  }
}

function startEditPwd() {
  oldPwd.value = "";
  newPwd.value = "";
  confirmPwd.value = "";
  pwdMsg.value = "";
  editingPwd.value = true;
}

function cancelEditPwd() {
  editingPwd.value = false;
  pwdMsg.value = "";
}

async function savePwd() {
  if (!oldPwd.value || !newPwd.value || !confirmPwd.value) {
    pwdMsgType.value = "err";
    pwdMsg.value = "请填写所有密码字段";
    return;
  }
  if (newPwd.value !== confirmPwd.value) {
    pwdMsgType.value = "err";
    pwdMsg.value = "两次输入的新密码不一致";
    return;
  }
  if (newPwd.value.length < 6) {
    pwdMsgType.value = "err";
    pwdMsg.value = "新密码长度至少 6 位";
    return;
  }
  savingPwd.value = true;
  pwdMsg.value = "";
  try {
    const resp = await updateMe(store.baseUrl, {
      old_password: oldPwd.value,
      new_password: newPwd.value,
    });
    applyUpdate(resp);
    editingPwd.value = false;
    pwdMsgType.value = "ok";
    pwdMsg.value = "密码修改成功";
    autoHide(pwdMsg);
    store.addLog("密码已更新");
  } catch (e: any) {
    pwdMsgType.value = "err";
    pwdMsg.value = e?.message || "修改失败，请检查当前密码是否正确";
  } finally {
    savingPwd.value = false;
  }
}

function formatDate(iso: string | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}
</script>

<template>
  <div class="profile-root">
    <section class="profile-panel surface-panel">
      <button class="back-btn" @click="goBack" aria-label="返回上一页">
        <span aria-hidden="true">‹</span>
        返回
      </button>
      <header class="profile-header">
        <div class="avatar">
          {{ (store.currentUser?.username || "?")[0].toUpperCase() }}
        </div>
        <div class="identity">
          <span class="eyebrow">个人中心</span>
          <h1>{{ store.currentUser?.username || "未登录用户" }}</h1>
          <div class="meta-row">
            <span :class="['role-badge', store.currentUser?.is_admin ? 'admin' : 'normal']">
              {{ store.currentUser?.is_admin ? "管理员" : "普通用户" }}
            </span>
            <span>注册于 {{ formatDate(store.currentUser?.created_at) }}</span>
          </div>
        </div>
      </header>

      <section class="profile-block">
        <div class="block-header">
          <div>
            <span class="section-label">Account</span>
            <h2>个人信息</h2>
          </div>
          <button v-if="!editingInfo" class="btn ghost" @click="startEditInfo">编辑</button>
        </div>

        <div v-if="!editingInfo" class="info-grid">
          <div class="info-item">
            <span>用户名</span>
            <strong>{{ store.currentUser?.username || "—" }}</strong>
          </div>
          <div class="info-item">
            <span>邮箱</span>
            <strong>{{ store.currentUser?.email || "—" }}</strong>
          </div>
        </div>

        <div v-else class="edit-stack">
          <label class="field">
            <span>邮箱</span>
            <input v-model="email" type="email" class="input" placeholder="请输入邮箱" />
          </label>
          <div class="action-row">
            <button class="btn solid" :disabled="savingInfo" @click="saveInfo">
              {{ savingInfo ? "保存中..." : "保存" }}
            </button>
            <button class="btn ghost" :disabled="savingInfo" @click="cancelEditInfo">取消</button>
          </div>
        </div>
        <p v-if="infoMsg" :class="['msg', infoMsgType]">{{ infoMsg }}</p>
      </section>

      <section class="profile-block">
        <div class="block-header">
          <div>
            <span class="section-label">Username</span>
            <h2>修改用户名</h2>
          </div>
          <button v-if="!editingUsername" class="btn ghost" @click="startEditUsername">修改</button>
        </div>

        <p v-if="!editingUsername" class="hint">用户名会用于登录和导航展示。</p>
        <div v-else class="edit-stack">
          <label class="field">
            <span>新用户名</span>
            <input v-model="newUsername" class="input" placeholder="请输入新用户名" />
          </label>
          <div class="action-row">
            <button class="btn solid" :disabled="savingUsername" @click="saveUsername">
              {{ savingUsername ? "保存中..." : "确认修改" }}
            </button>
            <button class="btn ghost" :disabled="savingUsername" @click="cancelEditUsername">
              取消
            </button>
          </div>
        </div>
        <p v-if="usernameMsg" :class="['msg', usernameMsgType]">{{ usernameMsg }}</p>
      </section>

      <section class="profile-block">
        <div class="block-header">
          <div>
            <span class="section-label">Security</span>
            <h2>修改密码</h2>
          </div>
          <button v-if="!editingPwd" class="btn ghost" @click="startEditPwd">修改</button>
        </div>

        <p v-if="!editingPwd" class="hint">修改后请使用新密码登录。</p>
        <div v-else class="edit-stack">
          <label class="field">
            <span>当前密码</span>
            <input v-model="oldPwd" type="password" class="input" placeholder="请输入当前密码" />
          </label>
          <label class="field">
            <span>新密码</span>
            <input v-model="newPwd" type="password" class="input" placeholder="至少 6 位" />
          </label>
          <label class="field">
            <span>确认新密码</span>
            <input v-model="confirmPwd" type="password" class="input" placeholder="再次输入新密码" />
          </label>
          <div class="action-row">
            <button class="btn solid" :disabled="savingPwd" @click="savePwd">
              {{ savingPwd ? "保存中..." : "确认修改" }}
            </button>
            <button class="btn ghost" :disabled="savingPwd" @click="cancelEditPwd">取消</button>
          </div>
        </div>
        <p v-if="pwdMsg" :class="['msg', pwdMsgType]">{{ pwdMsg }}</p>
      </section>
    </section>
  </div>
</template>

<style scoped>
.profile-root {
  flex: 1;
  padding: var(--space-6);
  background: var(--color-bg);
}

.profile-panel {
  max-width: var(--panel-max-width);
  margin: 0 auto;
  padding: var(--space-8);
  animation: panel-in var(--motion-slow) var(--motion-ease) both;
}

.back-btn {
  min-height: var(--control-sm);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: var(--space-5);
  padding: 0 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.back-btn span {
  font-size: 20px;
  line-height: 1;
}

.back-btn:hover {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
  transform: translateY(-1px);
}

.profile-header {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  padding-bottom: var(--space-6);
  border-bottom: 1px solid var(--color-border);
}

.avatar {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-card);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: #fff;
  font-size: 30px;
  font-weight: 900;
  flex-shrink: 0;
}

.identity {
  min-width: 0;
}

.eyebrow,
.section-label {
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.identity h1 {
  margin: 6px 0 8px;
  color: var(--color-text);
  font-size: 28px;
  line-height: 1.2;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-muted);
  font-size: 13px;
}

.role-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
}

.role-badge.admin {
  background: var(--color-primary);
  color: #fff;
}

.role-badge.normal {
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
}

.profile-block {
  padding: var(--space-6) 0;
  border-bottom: 1px solid var(--color-border);
}

.profile-block:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.block-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.block-header h2 {
  margin: 4px 0 0;
  color: var(--color-text);
  font-size: 18px;
  line-height: 1.3;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.info-item {
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-card);
  background: var(--color-bg);
}

.info-item span,
.field span {
  display: block;
  margin-bottom: var(--space-2);
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 800;
}

.info-item strong {
  display: block;
  overflow-wrap: anywhere;
  color: var(--color-text);
  font-size: 15px;
}

.hint {
  margin: 0;
  color: var(--color-muted);
  font-size: 13px;
}

.edit-stack {
  display: grid;
  gap: var(--space-4);
  max-width: 520px;
}

.field {
  display: block;
}

.input {
  width: 100%;
  min-height: var(--control-lg);
  padding: 0 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
}

.input:focus {
  border-color: var(--color-primary);
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.btn {
  min-height: var(--control-md);
  padding: 0 14px;
  border-radius: var(--radius-control);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn.ghost {
  background: var(--color-surface);
  border-color: var(--color-primary-border);
  color: var(--color-primary);
}

.btn.ghost:hover:not(:disabled) {
  background: var(--color-primary-soft);
  border-color: var(--color-primary);
  transform: translateY(-1px);
}

.btn.solid {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.btn.solid:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  transform: translateY(-1px);
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.msg {
  margin: var(--space-4) 0 0;
  padding: 10px 12px;
  border-radius: var(--radius-control);
  font-size: 13px;
  font-weight: 600;
}

.msg.ok {
  background: #f0faf4;
  color: #15803d;
  border: 1px solid #bbf7d0;
}

.msg.err {
  background: var(--color-danger-soft);
  color: var(--color-danger);
  border: 1px solid #fecdd3;
}

@media (max-width: 640px) {
  .profile-root {
    padding: var(--space-4);
  }

  .profile-panel {
    padding: var(--space-5);
  }

  .profile-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
