<script setup lang="ts">
import { ref, onMounted } from "vue";
import { store } from "../store";
import { updateMe } from "../api/client";

// ─── 个人信息编辑 ────────────────────────────────────
const email = ref("");
const editingInfo = ref(false);
const savingInfo = ref(false);
const infoMsg = ref("");
const infoMsgType = ref<"ok" | "err">("ok");

function syncFromStore() {
  email.value = store.currentUser?.email ?? "";
}
onMounted(syncFromStore);

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
    const updated = await updateMe(store.baseUrl, {
      email: email.value.trim(),
    });
    store.currentUser = updated;
    editingInfo.value = false;
    infoMsgType.value = "ok";
    infoMsg.value = "保存成功";
    store.addLog("个人信息已更新");
  } catch (e: any) {
    infoMsgType.value = "err";
    infoMsg.value = e?.message || "保存失败，请稍后重试";
  } finally {
    savingInfo.value = false;
  }
}

// ─── 修改用户名 ───────────────────────────────────────
const newUsername = ref("");
const editingUsername = ref(false);
const savingUsername = ref(false);
const usernameMsg = ref("");
const usernameMsgType = ref<"ok" | "err">("ok");

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
    const updated = await updateMe(store.baseUrl, {
      username: newUsername.value.trim(),
    } as any);
    store.currentUser = updated;
    editingUsername.value = false;
    usernameMsgType.value = "ok";
    usernameMsg.value = "用户名修改成功";
    store.addLog("用户名已更新");
  } catch (e: any) {
    usernameMsgType.value = "err";
    usernameMsg.value = e?.message || "修改失败，请稍后重试";
  } finally {
    savingUsername.value = false;
  }
}

// ─── 修改密码 ─────────────────────────────────────────
const oldPwd = ref("");
const newPwd = ref("");
const confirmPwd = ref("");
const editingPwd = ref(false);
const savingPwd = ref(false);
const pwdMsg = ref("");
const pwdMsgType = ref<"ok" | "err">("ok");

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
    await updateMe(store.baseUrl, {
      old_password: oldPwd.value,
      new_password: newPwd.value,
    } as any);
    editingPwd.value = false;
    pwdMsgType.value = "ok";
    pwdMsg.value = "密码修改成功";
    store.addLog("密码已更新");
  } catch (e: any) {
    pwdMsgType.value = "err";
    pwdMsg.value = e?.message || "修改失败，请检查原密码是否正确";
  } finally {
    savingPwd.value = false;
  }
}

function formatDate(iso: string | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
</script>

<template>
  <div class="profile-root">
    <div class="profile-card">

      <!-- 头像行 -->
      <div class="avatar-row">
        <div class="avatar">{{ (store.currentUser?.username || "?")[0].toUpperCase() }}</div>
        <div class="id-block">
          <div class="username-big">{{ store.currentUser?.username }}</div>
          <div class="meta-row">
            <span v-if="store.currentUser?.is_admin" class="badge admin">管理员</span>
            <span v-else class="badge normal">普通用户</span>
            <span class="joined">注册于 {{ formatDate(store.currentUser?.created_at) }}</span>
          </div>
        </div>
      </div>

      <!-- ① 个人信息 -->
      <section class="block">
        <div class="block-header">
          <span class="block-title">个人信息</span>
          <button v-if="!editingInfo" class="btn-link" @click="startEditInfo">编辑</button>
        </div>

        <div v-if="!editingInfo" class="info-grid">
          <div class="info-item">
            <span class="info-label">用户名</span>
            <span class="info-value">{{ store.currentUser?.username || '—' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">邮箱</span>
            <span class="info-value">{{ store.currentUser?.email || '—' }}</span>
          </div>
        </div>

        <div v-else class="edit-col">
          <label class="field">
            <span class="field-label">邮箱</span>
            <input v-model="email" type="email" class="input" placeholder="请输入邮箱" />
          </label>
          <div class="action-row">
            <button class="btn primary" :disabled="savingInfo" @click="saveInfo">
              <span v-if="savingInfo" class="spinner-small"></span>
              {{ savingInfo ? "保存中…" : "保存" }}
            </button>
            <button class="btn ghost" :disabled="savingInfo" @click="cancelEditInfo">取消</button>
          </div>
          <p v-if="infoMsg" :class="['msg', infoMsgType]">{{ infoMsg }}</p>
        </div>

        <p v-if="!editingInfo && infoMsg" :class="['msg', infoMsgType]">{{ infoMsg }}</p>
      </section>

      <div class="divider"></div>

      <!-- ② 修改用户名 -->
      <section class="block">
        <div class="block-header">
          <span class="block-title">修改用户名</span>
          <button v-if="!editingUsername" class="btn-link" @click="startEditUsername">修改</button>
        </div>

        <div v-if="!editingUsername" class="hint-text">点击右侧「修改」可更换登录用户名</div>

        <div v-else class="edit-col">
          <label class="field">
            <span class="field-label">新用户名</span>
            <input v-model="newUsername" class="input" placeholder="请输入新用户名" />
          </label>
          <div class="action-row">
            <button class="btn primary" :disabled="savingUsername" @click="saveUsername">
              <span v-if="savingUsername" class="spinner-small"></span>
              {{ savingUsername ? "保存中…" : "确认修改" }}
            </button>
            <button class="btn ghost" :disabled="savingUsername" @click="cancelEditUsername">取消</button>
          </div>
          <p v-if="usernameMsg" :class="['msg', usernameMsgType]">{{ usernameMsg }}</p>
        </div>

        <p v-if="!editingUsername && usernameMsg" :class="['msg', usernameMsgType]">{{ usernameMsg }}</p>
      </section>

      <div class="divider"></div>

      <!-- ③ 修改密码 -->
      <section class="block">
        <div class="block-header">
          <span class="block-title">修改密码</span>
          <button v-if="!editingPwd" class="btn-link" @click="startEditPwd">修改</button>
        </div>

        <div v-if="!editingPwd" class="hint-text">点击右侧「修改」可更换登录密码</div>

        <div v-else class="edit-col">
          <label class="field">
            <span class="field-label">当前密码</span>
            <input v-model="oldPwd" type="password" class="input" placeholder="请输入当前密码" />
          </label>
          <label class="field">
            <span class="field-label">新密码</span>
            <input v-model="newPwd" type="password" class="input" placeholder="至少 6 位" />
          </label>
          <label class="field">
            <span class="field-label">确认新密码</span>
            <input v-model="confirmPwd" type="password" class="input" placeholder="再次输入新密码" />
          </label>
          <div class="action-row">
            <button class="btn primary" :disabled="savingPwd" @click="savePwd">
              <span v-if="savingPwd" class="spinner-small"></span>
              {{ savingPwd ? "保存中…" : "确认修改" }}
            </button>
            <button class="btn ghost" :disabled="savingPwd" @click="cancelEditPwd">取消</button>
          </div>
          <p v-if="pwdMsg" :class="['msg', pwdMsgType]">{{ pwdMsg }}</p>
        </div>

        <p v-if="!editingPwd && pwdMsg" :class="['msg', pwdMsgType]">{{ pwdMsg }}</p>
      </section>

    </div>
  </div>
</template>

<style scoped>
.profile-root {
  padding: 40px 24px;
  display: flex;
  justify-content: center;
  background: #fafafa;
  min-height: calc(100vh - 70px);
}

.profile-card {
  background: #ffffff;
  border: 1px solid #e8e0e2;
  border-radius: 10px;
  padding: 36px 40px;
  width: min(580px, 100%);
  box-shadow: 0 4px 24px rgba(139, 41, 66, 0.06);
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* 头像行 */
.avatar-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 28px;
  padding-bottom: 28px;
  border-bottom: 1px solid #f0e8eb;
}
.avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #8b2942;
  color: #fff;
  font-size: 28px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.id-block { display: flex; flex-direction: column; gap: 8px; }
.username-big { font-size: 22px; font-weight: 700; color: #1a1a1a; }
.meta-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.badge { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 100px; letter-spacing: 0.03em; }
.badge.admin { background: #8b2942; color: #fff; }
.badge.normal { background: #f5eef1; color: #8b2942; border: 1px solid #e4d0d6; }
.joined { font-size: 12px; color: #8a8a8a; }

/* 区块 */
.block { padding: 22px 0; display: flex; flex-direction: column; gap: 14px; }
.divider { height: 1px; background: #f0e8eb; }

.block-header { display: flex; align-items: center; justify-content: space-between; }
.block-title { font-size: 15px; font-weight: 700; color: #1a1a1a; }
.btn-link {
  font-size: 13px; font-weight: 600; color: #8b2942;
  background: none; border: none; cursor: pointer; padding: 4px 8px;
  border-radius: 4px; transition: background 0.15s;
}
.btn-link:hover { background: #fdf5f7; }

.hint-text { font-size: 13px; color: #9a9a9a; }

/* 只读信息网格 */
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 32px; }
.info-item { display: flex; flex-direction: column; gap: 4px; }
.info-label { font-size: 11px; font-weight: 700; color: #8a8a8a; text-transform: uppercase; letter-spacing: 0.05em; }
.info-value { font-size: 15px; color: #1a1a1a; font-weight: 500; }

/* 编辑列 */
.edit-col { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 700; color: #5c5c5c; }

.input {
  padding: 10px 12px;
  border: 1px solid #d9cdd1;
  border-radius: 6px;
  font-size: 14px;
  color: #1a1a1a;
  background: #fff;
  transition: border-color 0.15s;
  outline: none;
  width: 100%;
  box-sizing: border-box;
}
.input:focus { border-color: #8b2942; box-shadow: 0 0 0 3px rgba(139,41,66,0.08); }

/* 按钮 */
.action-row { display: flex; gap: 10px; }
.btn {
  padding: 9px 20px; border-radius: 6px; font-size: 14px; font-weight: 600;
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  border: 1px solid transparent;
}
.btn.primary { background: #8b2942; color: #fff; border-color: #8b2942; }
.btn.primary:hover:not(:disabled) { background: #7a2439; border-color: #7a2439; }
.btn.ghost { background: #fff; color: #5c5c5c; border-color: #d9cdd1; }
.btn.ghost:hover:not(:disabled) { border-color: #8b2942; color: #8b2942; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.spinner-small {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 消息提示 */
.msg { margin: 0; font-size: 13px; padding: 9px 12px; border-radius: 6px; }
.msg.ok { background: #f0faf4; color: #15803d; border: 1px solid #bbf7d0; }
.msg.err { background: #fff5f7; color: #9f1239; border: 1px solid #fecdd3; }

@media (max-width: 520px) {
  .profile-card { padding: 24px 20px; }
  .info-grid { grid-template-columns: 1fr; }
}
</style>
