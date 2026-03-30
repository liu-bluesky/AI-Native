<template>
  <div class="creation-layout">
    <div
      class="creation-layout__ambient creation-layout__ambient--left"
      aria-hidden="true"
    />
    <div
      class="creation-layout__ambient creation-layout__ambient--right"
      aria-hidden="true"
    />
    <div class="creation-layout__mesh" aria-hidden="true" />

    <div class="creation-main">
      <div class="creation-workspace">
        <aside class="creation-workspace__sidebar">
          <div class="creation-sidebar-brand-panel">
            <div class="creation-sidebar-brand">
              <div class="creation-sidebar-brand__mark">AI</div>
              <div>
                <div class="creation-sidebar-brand__name">素材工作区</div>
                <div class="creation-sidebar-brand__meta">项目创作</div>
              </div>
            </div>
          </div>

          <div class="creation-workspace__project">
            <div class="creation-workspace__eyebrow">Project Context</div>
            <div class="creation-workspace__project-name">
              {{ project.name || "当前项目" }}
            </div>
            <div class="creation-workspace__project-meta">
              {{
                projectId
                  ? `${getProjectTypeLabel(project.type)} · ${projectId}`
                  : "缺少 project_id"
              }}
            </div>
          </div>

          <nav class="creation-workspace__nav">
            <button
              v-for="item in navItems"
              :key="item.key"
              type="button"
              class="creation-workspace__nav-item"
              :class="{ 'is-active': item.active }"
              @click="openNav(item)"
            >
              <span class="creation-workspace__nav-label">{{
                item.label
              }}</span>
              <span class="creation-workspace__nav-note">{{ item.note }}</span>
            </button>
          </nav>
        </aside>

        <section class="creation-workspace__content">
          <router-view />
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/utils/api.js";

const route = useRoute();
const router = useRouter();

const projectId = computed(() => String(route.query.project_id || "").trim());
const project = ref({});

const navItems = computed(() => [
  {
    key: "library",
    label: "素材库",
    note: "正式资产沉淀",
    path: "/materials",
    active: route.path === "/materials",
  },
  {
    key: "studio",
    label: "短片制作",
    note: "创作流程工作区",
    path: "/materials/studio",
    active: route.path === "/materials/studio",
  },
  {
    key: "voices",
    label: "音色模块",
    note: "创建自定义音色",
    path: "/materials/voices",
    active: route.path === "/materials/voices",
  },
  {
    key: "works",
    label: "我的作品",
    note: "结果回看与整理",
    path: "/materials/works",
    active: route.path === "/materials/works",
  },
]);

const projectTypeOptions = [
  { value: "image", label: "图片项目" },
  { value: "storyboard_video", label: "分镜视频项目" },
  { value: "mixed", label: "综合项目" },
];

function getProjectTypeLabel(value) {
  const normalized = String(value || "").trim();
  return (
    projectTypeOptions.find((item) => item.value === normalized)?.label ||
    "综合项目"
  );
}

async function fetchProject() {
  const currentProjectId = projectId.value;
  if (!currentProjectId) {
    project.value = {};
    return;
  }
  try {
    const data = await api.get(`/projects/${currentProjectId}`);
    project.value = data.project || {};
  } catch (err) {
    project.value = {};
    ElMessage.error(err?.detail || err?.message || "加载项目信息失败");
  }
}

function openNav(item) {
  void router.push({
    path: item.path,
    query: projectId.value ? { project_id: projectId.value } : {},
  });
}

watch(projectId, () => {
  void fetchProject();
});

onMounted(() => {
  void fetchProject();
});
</script>

<style scoped>
.creation-layout {
  position: relative;
  min-height: 100%;
  height: 100%;
  overflow: hidden;
  color: var(--page-text, #0f172a);
  background: var(
    --page-bg,
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 38%, #edf2f7 100%)
  );
}

.creation-layout__ambient,
.creation-layout__mesh {
  position: absolute;
  pointer-events: none;
}

.creation-layout__ambient {
  width: 32rem;
  height: 32rem;
  border-radius: 50%;
  filter: blur(72px);
  opacity: 0.72;
}

.creation-layout__ambient--left {
  top: -11rem;
  left: -14rem;
  background: rgba(125, 211, 252, 0.34);
}

.creation-layout__ambient--right {
  top: 2rem;
  right: -11rem;
  background: rgba(103, 232, 249, 0.22);
}

.creation-layout__mesh {
  inset: 0;
  opacity: 0.28;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.03) 1px, transparent 1px);
  background-size: 88px 88px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.68), transparent 78%);
}

.creation-main {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  min-height: 100%;
  padding: 0 20px 20px;
  box-sizing: border-box;
  overflow-x: hidden;
  overflow-y: auto;
}

.creation-workspace {
  display: grid;
  width: 100%;
  max-width: none;
  margin: 0 auto;
  height: 100%;
  min-height: 0;
  grid-template-columns: 332px minmax(0, 1fr);
  gap: 24px;
  padding: 18px 0 22px;
  align-items: stretch;
  box-sizing: border-box;
  overflow: hidden;
}

.creation-workspace__sidebar {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 28px;
  padding: 16px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.96),
    rgba(248, 250, 252, 0.92)
  );
  backdrop-filter: blur(14px);
  box-shadow:
    0 16px 36px rgba(15, 23, 42, 0.05),
    0 2px 8px rgba(15, 23, 42, 0.03);
  box-sizing: border-box;
  overflow: auto;
}

.creation-sidebar-brand-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.creation-sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.creation-sidebar-brand__mark {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #0f172a, #1e293b);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.08em;
  box-shadow: 0 16px 30px rgba(15, 23, 42, 0.14);
}

.creation-sidebar-brand__name {
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.3;
}

.creation-sidebar-brand__meta {
  margin-top: 2px;
  color: #7c8aa0;
  font-size: 12px;
  line-height: 1.5;
}

.creation-workspace__project {
  padding: 14px;
  border: 1px solid rgba(191, 219, 254, 0.72);
  border-radius: 22px;
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.12),
      transparent 32%
    ),
    linear-gradient(
      180deg,
      rgba(248, 250, 252, 0.98),
      rgba(255, 255, 255, 0.94)
    );
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.creation-workspace__eyebrow {
  color: #6b7a8e;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.creation-workspace__project-name {
  margin-top: 9px;
  color: #0f172a;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  word-break: break-word;
}

.creation-workspace__project-meta {
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.75;
  word-break: break-all;
}

.creation-workspace__nav {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  flex: 1;
}

.creation-workspace__nav-item {
  width: 100%;
  padding: 13px 14px;
  text-align: left;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.72);
  color: inherit;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease;
}

.creation-workspace__nav-item:hover,
.creation-workspace__nav-item.is-active {
  transform: translateY(-1px);
  border-color: rgba(191, 219, 254, 0.9);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.94)
  );
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.06);
}

.creation-workspace__nav-label {
  display: block;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.creation-workspace__nav-note {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.creation-workspace__content {
  min-width: 0;
  min-height: 0;
  padding: 0;
  height: 100%;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: auto;
  box-sizing: border-box;
}

@media (max-width: 1100px) {
  .creation-main {
    padding: 0 14px 18px;
  }

  .creation-workspace {
    grid-template-columns: 1fr;
    min-height: auto;
    height: auto;
    gap: 20px;
    padding: 14px 0 0;
  }

  .creation-workspace__sidebar {
    order: 2;
    overflow: hidden;
  }

  .creation-workspace__content {
    order: 1;
  }

  .creation-workspace__nav {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }
}

@media (max-width: 720px) {
  .creation-main {
    padding: 0 12px 16px;
  }

  .creation-workspace__nav {
    grid-template-columns: 1fr;
  }

  .creation-workspace__sidebar,
  .creation-workspace__content {
    border-radius: 24px;
  }

  .creation-workspace__project-name {
    font-size: 16px;
  }

  .creation-workspace__nav-item:hover,
  .creation-workspace__nav-item.is-active {
    transform: none;
  }
}
</style>
