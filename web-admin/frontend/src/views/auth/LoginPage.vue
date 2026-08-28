<template>
  <div ref="motionRoot" class="login-motion-root">
    <AuthDesktopShell
      eyebrow="Desktop Access"
      title="进入你的 AI 桌面系统"
      description="登录后进入统一工作桌面，在同一套系统窗口里继续项目、素材、能力市场和 AI 工作台。"
      panel-title="Sign In"
      :features="loginFeatures"
      :dock-items="dockPreview"
    >
      <div class="login-panel__header">
        <div class="login-panel__eyebrow">账号登录</div>
        <div class="login-panel__title">欢迎回来</div>
        <div class="login-panel__text">输入账号和密码进入桌面工作区。</div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @focusin="handleFormFocusIn"
        @focusout="handleFormFocusOut"
      >
        <el-form-item label="账号" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入账号"
            autocomplete="username"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <div class="login-form__options">
          <el-checkbox v-model="form.rememberPassword">记住账号</el-checkbox>
        </div>

        <el-form-item class="login-form__submit">
          <el-button
            type="primary"
            :loading="loading"
            class="login-submit"
            @click="handleLogin"
          >
            登录并进入桌面
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-panel__footer">
        <span class="login-panel__footer-text">还没有账号？</span>
        <el-button text class="login-panel__link" @click="openRegistration">
          去注册
        </el-button>
      </div>
    </AuthDesktopShell>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { gsap } from "gsap";
import AuthDesktopShell from "@/components/auth/AuthDesktopShell.vue";
import { loginWithPassword, resolveSafeRedirectPath } from "@/utils/auth.js";
import { getRememberedLoginInfo, persistRememberedLoginInfo } from "@/utils/auth-storage.js";
import { openNativeExternalUrl } from "@/utils/native-desktop-bridge.js";

const EXTERNAL_REGISTRATION_URL = "https://token.ltllm.com/login";

const route = useRoute();
const router = useRouter();
const formRef = ref(null);
const motionRoot = ref(null);
const loading = ref(false);

const dockPreview = ["AI", "PR", "MT", "MK", "SE"];
const loginFeatures = [
  {
    title: "AI 工作台",
    text: "继续当前项目的对话、执行链路和工作上下文。",
  },
  {
    title: "项目应用",
    text: "把项目、素材和设置都收束成桌面里的独立小应用。",
  },
  {
    title: "连续状态",
    text: "登录后保留统一入口和桌面式系统感，不再跳散页。",
  },
];

const form = reactive({ username: "", password: "", rememberPassword: false });
const rules = {
  username: [{ required: true, message: "请输入账号", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};
let motionMedia = null;

onMounted(() => {
  const remembered = getRememberedLoginInfo();
  form.username = remembered.username;
  form.rememberPassword = remembered.enabled;
  void nextTick(playLoginMotion);
});

onBeforeUnmount(() => {
  motionMedia?.revert();
});

watch(loading, (busy) => {
  animateSubmitState(busy);
});

async function openRegistration() {
  try {
    if (await openNativeExternalUrl(EXTERNAL_REGISTRATION_URL)) return;
  } catch (_error) {
    // Use the browser fallback outside the desktop shell.
  }
  window.open(EXTERNAL_REGISTRATION_URL, "_blank", "noopener,noreferrer");
}

async function handleLogin() {
  animateSubmitPress();
  await formRef.value.validate();
  loading.value = true;
  try {
    await loginWithPassword({
      username: form.username.trim(),
      password: form.password,
    });
    persistRememberedLoginInfo({
      enabled: form.rememberPassword,
      username: form.username.trim(),
    });
    ElMessage.success("登录成功");
    await router.replace(resolveSafeRedirectPath(route.query.redirect, "/workbench"));
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "账号或密码错误");
  } finally {
    loading.value = false;
  }
}

function playLoginMotion() {
  const root = motionRoot.value;
  if (!root || motionMedia) return;

  motionMedia = gsap.matchMedia();
  motionMedia.add(
    {
      reduceMotion: "(prefers-reduced-motion: reduce)",
      fullMotion: "(prefers-reduced-motion: no-preference)",
    },
    (context) => {
      const reduceMotion = context.conditions.reduceMotion;
      const entranceTargets = [
        ".auth-desktop__wallpaper",
        ".auth-desktop__grid",
        ".auth-desktop__brand",
        ".auth-desktop__hero-copy",
        ".auth-desktop__feature",
        ".auth-desktop__dock",
      ];

      if (reduceMotion) {
        gsap.set(entranceTargets, {
          autoAlpha: 1,
          clearProps: "transform",
        });
        return;
      }

      gsap.set(
        [
          ".auth-desktop__wallpaper",
          ".auth-desktop__grid",
          ".auth-desktop__brand",
          ".auth-desktop__hero-copy",
          ".auth-desktop__feature",
          ".auth-desktop__dock",
        ],
        { autoAlpha: 0 },
      );
      gsap.set(
        [
          ".auth-desktop__brand",
          ".auth-desktop__hero-copy",
          ".auth-desktop__feature",
          ".auth-desktop__dock",
        ],
        { y: 14 },
      );

      gsap
        .timeline({ defaults: { duration: 0.62, ease: "power2.out" } })
        .to([".auth-desktop__wallpaper", ".auth-desktop__grid"], {
          autoAlpha: 1,
          duration: 0.36,
        })
        .to(".auth-desktop__brand", { autoAlpha: 1, y: 0 }, "-=0.12")
        .to(".auth-desktop__hero-copy", { autoAlpha: 1, y: 0 }, "-=0.38")
        .to(
          ".auth-desktop__feature",
          { autoAlpha: 1, y: 0, stagger: 0.07 },
          "-=0.32",
        )
        .to(".auth-desktop__dock", { autoAlpha: 1, y: 0 }, "-=0.34");

      gsap
        .timeline({ repeat: -1, yoyo: true, defaults: { ease: "sine.inOut" } })
        .to(".auth-desktop__ambient--left", { scale: 1.06, x: 12, y: 8, duration: 12 }, 0)
        .to(".auth-desktop__ambient--right", { scale: 1.05, x: -10, y: -6, duration: 14 }, 0)
        .to(".auth-desktop__grid", { autoAlpha: 0.58, duration: 10 }, 0);
    },
    root,
  );
}

function handleFormFocusIn(event) {
  const item = event.target?.closest?.(".el-form-item");
  if (!item || prefersReducedMotion()) return;
  gsap.to(item, {
    y: -2,
    duration: 0.2,
    ease: "power2.out",
    overwrite: "auto",
  });
}

function handleFormFocusOut(event) {
  const item = event.target?.closest?.(".el-form-item");
  if (!item || prefersReducedMotion()) return;
  gsap.to(item, {
    y: 0,
    duration: 0.22,
    ease: "power2.out",
    overwrite: "auto",
  });
}

function animateSubmitPress() {
  const button = motionRoot.value?.querySelector(".login-submit");
  if (!button || prefersReducedMotion()) return;
  gsap.fromTo(
    button,
    { scale: 0.985 },
    { scale: 1, duration: 0.24, ease: "power2.out", overwrite: "auto" },
  );
}

function animateSubmitState(busy) {
  const button = motionRoot.value?.querySelector(".login-submit");
  if (!button || prefersReducedMotion()) return;
  gsap.to(button, {
    scale: busy ? 0.992 : 1,
    duration: 0.24,
    ease: "power2.out",
    overwrite: "auto",
  });
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;
}
</script>

<style scoped>
.login-motion-root {
  min-height: 100dvh;
}

.login-panel__header {
  margin-bottom: 18px;
}

.login-panel__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #64748b;
}

.login-panel__title {
  margin-top: 8px;
  font-size: 28px;
  line-height: 1.1;
  font-weight: 700;
  color: #111827;
}

.login-panel__text {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #64748b;
}

.login-form :deep(.el-form-item__label) {
  color: #334155;
  font-weight: 600;
}

.login-form__submit {
  margin-top: 8px;
  margin-bottom: 0;
}

.login-form__options {
  display: flex;
  align-items: center;
  margin-top: -2px;
  margin-bottom: 12px;
}

.login-submit {
  position: relative;
  width: 100%;
  height: 44px;
  overflow: hidden;
  border-radius: 14px;
  border: 0;
  background: linear-gradient(180deg, #111827, #1f2937);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.16);
  transition:
    box-shadow 220ms ease,
    transform 220ms ease;
}

.login-submit::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-120%);
  background: linear-gradient(
    110deg,
    transparent 0%,
    rgba(255, 255, 255, 0.18) 42%,
    transparent 72%
  );
  pointer-events: none;
  transition: transform 680ms ease;
}

.login-submit:hover {
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.2);
  transform: translateY(-1px);
}

.login-submit:hover::after,
.login-submit.is-loading::after {
  transform: translateX(120%);
}

.login-panel__footer {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.login-panel__footer-text {
  color: #64748b;
}

.login-panel__link {
  font-weight: 600;
}

@media (prefers-reduced-motion: reduce) {
  .login-submit,
  .login-submit::after {
    transition: none;
  }

  .login-submit:hover {
    transform: none;
  }
}
</style>
