<template>
  <section class="account-center">
    <header class="account-center__hero">
      <div class="account-center__avatar">{{ initial }}</div>
      <div>
        <div class="account-center__eyebrow">Account Center</div>
        <h1>{{ profile.displayName || profile.username || "当前用户" }}</h1>
        <p>{{ profile.username || "" }} · {{ roleLabel }}</p>
      </div>
    </header>

    <div class="account-center__grid">
      <article class="account-center__card">
        <span class="account-center__label">账户概览</span>
        <strong>{{ profile.username || "-" }}</strong>
        <p>当前登录身份和本机工作台账户。</p>
      </article>
      <article class="account-center__card" :class="`is-${modelStatus.kind}`">
        <span class="account-center__label">模型配置</span>
        <strong>{{ modelStatus.label }}</strong>
        <p>{{ modelStatus.detail }}</p>
        <button type="button" @click="open('/llm/providers')">打开模型供应商</button>
      </article>
      <article class="account-center__card">
        <span class="account-center__label">安全与登录</span>
        <strong>会话安全</strong>
        <p>密码修改仍由现有用户设置页面负责。</p>
        <button type="button" @click="open('/account/settings')">打开设置</button>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { getStoredAuthProfile } from "@/utils/auth-storage.js";
import { readLocalMainModelSelection } from "@/services/local-main-model-runtime.js";
import { readLocalModelProviders } from "@/services/local-model-runtime.js";

const router = useRouter();
const profile = getStoredAuthProfile();
const initial = computed(() => String(profile.displayName || profile.username || "?").slice(0, 1).toUpperCase());
const roleLabel = computed(() => profile.role === "admin" ? "管理员" : "普通用户");
const modelStatus = computed(() => {
  const providers = readLocalModelProviders().filter((item) => item.enabled !== false);
  const selection = readLocalMainModelSelection();
  const selected = providers.find((item) => item.id === selection.providerId) || providers[0];
  if (!selected) return { kind: "unconfigured", label: "尚未配置", detail: "配置模型后才能开始 AI 对话。" };
  if (!selected.base_url || !(selection.modelName || selected.default_model)) return { kind: "unconfigured", label: "尚未配置", detail: "请补充 Base URL 和默认模型。" };
  return { kind: "ready", label: "已配置", detail: `${selected.name} · ${selection.modelName || selected.default_model}` };
});
function open(path) { void router.push(path); }
</script>

<style scoped>
.account-center { min-height: 100%; padding: 28px; color: #0f172a; background: linear-gradient(145deg, rgba(248,250,252,.9), rgba(226,232,240,.65)); }
.account-center__hero { display: flex; align-items: center; gap: 18px; padding: 24px; border: 1px solid rgba(255,255,255,.8); border-radius: 24px; background: rgba(255,255,255,.7); box-shadow: 0 20px 44px rgba(15,23,42,.08); }
.account-center__avatar { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 20px; color: white; background: linear-gradient(145deg,#8b5cf6,#2563eb); font-size: 26px; font-weight: 700; }
.account-center__eyebrow,.account-center__label { color: #64748b; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; font-weight: 700; }
h1 { margin: 7px 0 4px; font-size: 28px; } p { margin: 0; color: #64748b; line-height: 1.6; }
.account-center__grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; margin-top: 18px; }
.account-center__card { min-height: 142px; padding: 20px; border: 1px solid rgba(255,255,255,.8); border-radius: 20px; background: rgba(255,255,255,.64); }
.account-center__card strong { display: block; margin: 13px 0 5px; font-size: 20px; }
.account-center__card button { margin-top: 14px; border: 0; border-radius: 999px; padding: 8px 13px; color: white; background: #0f172a; cursor: pointer; }
.account-center__card.is-ready { border-color: rgba(16,185,129,.35); }
@media (max-width: 720px) { .account-center { padding: 16px; } .account-center__grid { grid-template-columns: 1fr; } }
</style>
