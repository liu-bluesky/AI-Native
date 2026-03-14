<template>
  <div class="system-config-page" v-loading="loading">
    <section class="hero">
      <div>
        <p class="hero-eyebrow">System Control</p>
        <h2>系统配置、MCP 与本地连接器</h2>
        <p class="hero-desc">
          在这里维护系统级开关、默认 MCP 配置，以及当前远程 MCP 服务和本地连接器暴露出的能力状态。
        </p>
      </div>
      <div class="hero-actions">
        <el-button :loading="refreshingPanels" @click="refreshAllPanels"
          >刷新状态</el-button
        >
        <el-button type="primary" :loading="saving" @click="saveConfig"
          >保存配置</el-button
        >
      </div>
    </section>

    <section class="overview-grid">
      <article class="metric-card">
        <span class="metric-label">MCP 服务数</span>
        <strong class="metric-value">{{ mcpServers.length }}</strong>
        <span class="metric-foot">读取自系统级 `mcpServers`</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">已发现能力</span>
        <strong class="metric-value">{{ totalSkillCount }}</strong>
        <span class="metric-foot">tools + prompts + resources</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">探测异常</span>
        <strong class="metric-value">{{ totalErrorCount }}</strong>
        <span class="metric-foot">协议不兼容或服务不可达时出现</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">本地连接器</span>
        <strong class="metric-value">{{ connectorItems.length }}</strong>
        <span class="metric-foot">当前账号可管理的设备连接数</span>
      </article>
      <article class="metric-card">
        <span class="metric-label">在线连接器</span>
        <strong class="metric-value">{{ onlineConnectorCount }}</strong>
        <span class="metric-foot">90 秒内有心跳则视为在线</span>
      </article>
    </section>

    <div class="content-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h3>基础开关</h3>
            <p>控制系统默认行为。</p>
          </div>
        </div>

        <el-alert
          title="这些开关只影响系统级默认行为，不会修改既有业务数据。"
          type="info"
          :closable="false"
          show-icon
          class="inline-alert"
        />

        <el-form label-position="top" class="switch-form">
          <div class="switch-list">
            <div class="switch-card">
              <div>
                <div class="switch-title">允许生成项目使用手册</div>
                <div class="switch-desc">
                  控制项目页中的大模型生成使用手册入口。
                </div>
              </div>
              <el-switch v-model="form.enable_project_manual_generation" />
            </div>

            <div class="switch-card">
              <div>
                <div class="switch-title">允许生成员工手册</div>
                <div class="switch-desc">
                  控制员工页中的大模型生成使用手册入口。
                </div>
              </div>
              <el-switch v-model="form.enable_employee_manual_generation" />
            </div>
          </div>

          <div class="number-grid">
            <el-form-item label="单次对话最大上传文件数">
              <el-input-number
                v-model="form.chat_upload_max_limit"
                :min="1"
                :max="20"
              />
              <div class="field-desc">
                限制 AI 对话里一次最多上传的文件数量。
              </div>
            </el-form-item>

            <el-form-item label="模型默认 Max Tokens">
              <el-input-number
                v-model="form.chat_max_tokens"
                :min="128"
                :max="8192"
                :step="64"
              />
              <div class="field-desc">控制 AI 对话默认最大输出长度。</div>
            </el-form-item>
          </div>

          <el-form-item label="AI 对话中心默认系统提示词">
            <el-input
              v-model="form.default_chat_system_prompt"
              type="textarea"
              :rows="8"
              resize="vertical"
              placeholder="为空时使用系统内置默认提示词；填写后会作为项目聊天未单独配置 system prompt 时的默认值。"
            />
            <div class="field-desc">
              当项目聊天没有单独填写 `system_prompt` 时，会自动回退到这里。
            </div>
          </el-form-item>

          <div class="switch-card employee-rule-config-card">
            <div>
              <div class="switch-title">AI 员工规则自动生成</div>
              <div class="switch-desc">
                创建 AI 员工时，系统会基于系统级 MCP 规则源自动补全规则草稿，再落地为本地规则并绑定给员工；对话页不再展示规则来源选择。
              </div>
            </div>
            <el-switch
              v-model="form.employee_auto_rule_generation_enabled"
            />
          </div>

          <div class="number-grid">
            <el-form-item label="自动生成规则上限">
              <el-input-number
                v-model="form.employee_auto_rule_generation_max_count"
                :min="1"
                :max="6"
              />
              <div class="field-desc">
                每次创建员工最多补全多少条规则草稿。
              </div>
            </el-form-item>

            <el-form-item label="规则来源">
              <el-checkbox-group
                v-model="form.employee_auto_rule_generation_source_filters"
                class="employee-rule-source-group"
              >
                <el-checkbox
                  v-for="option in EMPLOYEE_AUTO_RULE_SOURCE_OPTIONS"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </el-checkbox>
              </el-checkbox-group>
              <div class="field-desc">
                当前先支持系统内置的 prompts.chat curated 规则源。
              </div>
            </el-form-item>
          </div>

          <el-form-item label="规则生成策略提示词">
            <el-input
              v-model="form.employee_auto_rule_generation_prompt"
              type="textarea"
              :rows="6"
              resize="vertical"
              placeholder="用于约束系统在员工创建时优先生成哪类规则。"
            />
            <div class="field-desc">
              这是后台自动生成规则时使用的内部策略提示词，不直接展示给终端用户。
            </div>
          </el-form-item>

          <div class="employee-skill-site-head">
            <div>
              <div class="switch-title">外部技能网站目录</div>
              <div class="switch-desc">
                创建 AI 员工时，这些站点会展示在“外部技能候选”区域，供用户点击跳转查看。
              </div>
            </div>
            <el-button @click="addEmployeeExternalSkillSite">新增站点</el-button>
          </div>

          <div class="employee-skill-site-list">
            <div
              v-for="(item, index) in form.employee_external_skill_sites"
              :key="item.id || `site-${index}`"
              class="employee-skill-site-card"
            >
              <div class="employee-skill-site-card__top">
                <div class="employee-skill-site-card__title">
                  站点 {{ index + 1 }}
                </div>
                <div class="employee-skill-site-card__actions">
                  <el-button
                    text
                    type="danger"
                    @click="removeEmployeeExternalSkillSite(index)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
              <div class="employee-skill-site-card__grid">
                <el-form-item label="名称">
                  <el-input v-model="item.title" placeholder="例如：Vue 深度应用" />
                </el-form-item>
              </div>
              <el-form-item label="跳转地址">
                <el-input
                  v-model="item.url"
                  placeholder="https://example.com/skills/vue"
                />
              </el-form-item>
              <el-form-item label="描述">
                <el-input
                  v-model="item.description"
                  type="textarea"
                  :rows="3"
                  resize="vertical"
                  placeholder="简短说明这个站点适合补哪些技能。"
                />
              </el-form-item>
            </div>
          </div>

          <div class="employee-skill-site-head registry-head">
            <div>
              <div class="switch-title">技能资源源</div>
              <div class="switch-desc">
                配置外部技能 registry。当前已接入 Vett，安装时会动态获取临时下载地址。
              </div>
            </div>
          </div>

          <div class="employee-skill-site-card">
            <div class="switch-card">
              <div>
                <div class="switch-title">启用 Vett Registry</div>
                <div class="switch-desc">
                  开启后，前端“技能资源”页面会通过该源搜索和安装技能。
                </div>
              </div>
              <el-switch v-model="form.skill_registry_sources.vett.enabled" />
            </div>

            <div class="employee-skill-site-card__grid registry-grid">
              <el-form-item label="Base URL">
                <el-input
                  v-model="form.skill_registry_sources.vett.base_url"
                  placeholder="https://vett.sh/api/v1"
                />
              </el-form-item>
              <el-form-item label="超时 (ms)">
                <el-input-number
                  v-model="form.skill_registry_sources.vett.timeout_ms"
                  :min="1000"
                  :max="60000"
                  :step="1000"
                />
              </el-form-item>
            </div>

            <div class="registry-risk-grid">
              <el-form-item label="允许安装风险">
                <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.allow">
                  <el-checkbox
                    v-for="item in RISK_LEVEL_OPTIONS"
                    :key="`allow-${item}`"
                    :value="item"
                  >
                    {{ item }}
                  </el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="需人工确认">
                <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.review">
                  <el-checkbox
                    v-for="item in RISK_LEVEL_OPTIONS"
                    :key="`review-${item}`"
                    :value="item"
                  >
                    {{ item }}
                  </el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="直接拦截">
                <el-checkbox-group v-model="form.skill_registry_sources.vett.risk_policy.deny">
                  <el-checkbox
                    v-for="item in RISK_LEVEL_OPTIONS"
                    :key="`deny-${item}`"
                    :value="item"
                  >
                    {{ item }}
                  </el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </div>
            <div class="field-desc">
              这里保存的是 registry API 地址，不是最终 artifact 下载地址。实际下载链接会在安装时实时换取。
            </div>
          </div>
        </el-form>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h3>系统 MCP 配置</h3>
            <p>保存为 JSON。默认会保留 `prompts.chat`。</p>
          </div>
          <div class="panel-actions">
            <el-button @click="formatMcpConfigText">格式化 JSON</el-button>
            <el-button @click="resetMcpConfig">恢复默认</el-button>
          </div>
        </div>

        <div class="server-switch-list">
          <div
            v-for="server in editableMcpServers"
            :key="`edit-${server.name}`"
            class="server-switch-item"
          >
            <div class="server-switch-meta">
              <div class="server-switch-name">{{ server.name }}</div>
              <div class="server-switch-url">{{ server.url || "未配置 URL" }}</div>
            </div>
            <div class="server-switch-actions">
              <el-tag size="small" :type="server.enabled ? 'success' : 'info'">
                {{ server.enabled ? "已启用" : "已停用" }}
              </el-tag>
              <el-switch
                :model-value="server.enabled"
                @change="(value) => toggleMcpServer(server.name, value)"
              />
            </div>
          </div>
        </div>

        <el-alert
          v-if="configParseError"
          class="inline-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="configParseError"
        />

        <div class="editor-shell">
          <div class="editor-toolbar">
            <span>mcpServers.json</span>
            <span class="editor-meta">{{ configLineCount }} 行</span>
          </div>
          <el-input
            v-model="form.mcp_config_text"
            type="textarea"
            :rows="16"
            spellcheck="false"
            resize="none"
            class="mcp-config-input"
          />
        </div>
        <p class="field-desc field-desc-block">
          当前页面会基于这里的 `url` 自动调用
          `tools/list`、`prompts/list`、`resources/list` 进行探测。
        </p>
      </section>
    </div>

    <section class="panel connector-panel">
      <div class="panel-head">
        <div>
          <h3>本地连接器</h3>
          <p>
            运行在用户自己的电脑上，用来桥接本地目录、本地命令和本地模型。
          </p>
        </div>
        <div class="panel-actions">
          <el-button :loading="connectorsLoading" @click="fetchLocalConnectors">
            刷新连接器
          </el-button>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="inline-alert"
        title="本地连接器适合远程用户。当前阶段已支持设备注册、心跳、目录探测、命令执行和本地模型桥接；Windows PTY 与反向连接仍在后续阶段完善。"
      />

      <div class="connector-metric-row">
        <div class="connector-metric">
          <span>桌面安装包</span>
          <strong>{{ desktopArtifactItems.length }}</strong>
        </div>
        <div class="connector-metric">
          <span>在线设备</span>
          <strong>{{ onlineConnectorCount }}</strong>
        </div>
        <div class="connector-metric">
          <span>总设备</span>
          <strong>{{ connectorItems.length }}</strong>
        </div>
      </div>

      <div class="connector-grid" v-loading="connectorsLoading">
        <div class="connector-column">
          <div class="connector-subhead">
            <h4>安装与接入</h4>
            <p>安装包保持通用分发，账号认证改为在 AI 对话中心里点击“匹配本地连接器”完成。</p>
          </div>

          <div class="pair-create-card desktop-artifact-card">
            <div class="desktop-artifact-card__head">
              <div class="desktop-artifact-card__title">桌面通用包</div>
              <div class="desktop-artifact-card__desc">
                这里展示当前服务器已经构建好的安装包。它们是通用程序包，不包含当前账号的自动配对信息。
              </div>
            </div>
            <div v-if="desktopArtifactItems.length" class="desktop-artifact-list">
              <button
                v-for="item in desktopArtifactItems"
                :key="item.filename"
                type="button"
                class="desktop-artifact-item"
                :disabled="downloadingDesktopArtifactKey === item.filename"
                @click="downloadDesktopArtifact(item)"
              >
                <div class="desktop-artifact-item__top">
                  <span class="desktop-artifact-item__label">{{ item.label }}</span>
                  <span class="desktop-artifact-item__size">{{ formatFileSize(item.size_bytes) }}</span>
                </div>
                <div class="desktop-artifact-item__desc">{{ item.description }}</div>
                <div class="desktop-artifact-item__meta">
                  {{ item.filename }} · {{ formatDateTime(item.updated_at) }}
                </div>
              </button>
            </div>
            <div v-else class="field-desc">
              当前还没有可分发的桌面安装包，请先在 `local-connector/desktop/dist`
              目录生成 `dmg / exe` 产物。
            </div>
          </div>

          <div class="pair-create-card">
            <div class="field-desc">
              当前推荐流程是：下载通用安装包，启动本机 Local Connector，然后回到“AI 对话中心 > 系统对话 > 设置”点击“匹配本地连接器”完成认证。
            </div>
          </div>
        </div>

        <div class="connector-column">
          <div class="connector-subhead">
            <h4>已连接设备</h4>
            <p>可查看在线状态、支持能力和最近一次心跳。</p>
          </div>

          <div v-if="connectorItems.length" class="connector-card-list">
            <article
              v-for="item in connectorItems"
              :key="item.id"
              class="connector-device-card"
            >
              <div class="connector-device-top">
                <div>
                  <div class="connector-device-title">
                    {{ item.connector_name || "Local Connector" }}
                  </div>
                  <div class="connector-device-subtitle">
                    {{ item.id }} · {{ item.owner_username || "unknown" }}
                  </div>
                </div>
                <div class="connector-device-tags">
                  <el-tag size="small" :type="item.online ? 'success' : 'info'">
                    {{ item.online ? "在线" : "离线" }}
                  </el-tag>
                  <el-tag
                    size="small"
                    :type="item.last_error ? 'danger' : 'success'"
                  >
                    {{ item.last_error ? "异常" : "正常" }}
                  </el-tag>
                </div>
              </div>

              <div class="connector-device-info">
                <span>平台：{{ formatPlatform(item.platform) }}</span>
                <span>版本：{{ item.app_version || "-" }}</span>
                <span>状态：{{ item.status || "-" }}</span>
                <span>最近心跳：{{ formatDateTime(item.last_seen_at) }}</span>
                <span v-if="item.advertised_url">
                  地址：{{ item.advertised_url }}
                </span>
              </div>

              <div class="connector-capability-row">
                <span
                  v-for="cap in connectorCapabilityLabels(item)"
                  :key="`${item.id}-${cap}`"
                  class="capsule capsule-tool"
                >
                  {{ cap }}
                </span>
                <span
                  v-if="item.health?.llm_bridge_enabled"
                  class="capsule capsule-prompt"
                >
                  本地模型已配置
                </span>
              </div>

              <el-alert
                v-if="item.last_error"
                class="connector-error"
                type="error"
                :closable="false"
                show-icon
                :title="item.last_error"
              />

              <div class="connector-device-actions">
                <el-button text type="primary" @click="copyText(item.id)">
                  复制 ID
                </el-button>
                <el-button
                  text
                  type="danger"
                  :loading="deletingConnectorId === item.id"
                  @click="deleteConnector(item)"
                >
                  删除
                </el-button>
              </div>
            </article>
          </div>
          <el-empty
            v-else
            description="当前还没有已连接设备"
            :image-size="56"
          />
        </div>
      </div>
    </section>

    <section class="panel skill-panel">
      <div class="panel-head">
        <div>
          <h3>当前 MCP 技能</h3>
          <p>
            下方展示每个系统级 MCP 服务返回的能力列表，以及每次探测的技术结果。
          </p>
        </div>
      </div>

      <div v-loading="skillsLoading" class="server-list">
        <el-empty
          v-if="!mcpServers.length && !skillsLoading"
          description="暂无可展示的 MCP 服务"
          :image-size="64"
        />

        <article
          v-for="server in mcpServers"
          :key="server.name"
          class="server-card"
        >
          <div class="server-head">
            <div>
              <div class="server-title-row">
                <h4>{{ server.name }}</h4>
                <el-tag
                  size="small"
                  :type="!server.enabled ? 'info' : server.errors?.length ? 'warning' : 'success'"
                >
                  {{ !server.enabled ? "已停用" : server.errors?.length ? "探测异常" : "正常" }}
                </el-tag>
              </div>
              <p class="server-url">{{ server.url || "未配置 URL" }}</p>
            </div>
            <div class="server-summary">{{ server.summary || "未探测" }}</div>
          </div>

          <div class="capsule-row">
            <span class="capsule capsule-tool"
              >Tools {{ server.tools?.length || 0 }}</span
            >
            <span class="capsule capsule-prompt"
              >Prompts {{ server.prompts?.length || 0 }}</span
            >
            <span class="capsule capsule-resource"
              >Resources {{ server.resources?.length || 0 }}</span
            >
            <span
              v-if="server.source === 'documentation_fallback'"
              class="capsule capsule-fallback"
              >文档兜底</span
            >
          </div>

          <el-alert
            v-if="server.notice"
            class="server-notice"
            type="info"
            :closable="false"
            show-icon
            :title="server.notice"
          />

          <div class="skill-section-grid">
            <div class="skill-box">
              <div class="skill-box-title">Tools</div>
              <div v-if="server.tools?.length" class="skill-list">
                <div
                  v-for="item in server.tools"
                  :key="`tool-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 tools</div>
            </div>

            <div class="skill-box">
              <div class="skill-box-title">Prompts</div>
              <div v-if="server.prompts?.length" class="skill-list">
                <div
                  v-for="item in server.prompts"
                  :key="`prompt-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 prompts</div>
            </div>

            <div class="skill-box">
              <div class="skill-box-title">Resources</div>
              <div v-if="server.resources?.length" class="skill-list">
                <div
                  v-for="item in server.resources"
                  :key="`resource-${server.name}-${item.name}`"
                  class="skill-item"
                >
                  <span class="skill-name">{{ item.name }}</span>
                  <span v-if="item.description" class="skill-desc">{{
                    item.description
                  }}</span>
                </div>
              </div>
              <div v-else class="skill-empty">暂无 resources</div>
            </div>
          </div>

          <div v-if="server.checks?.length" class="check-block">
            <div class="check-title">探测结果</div>
            <div class="check-list">
              <div
                v-for="check in server.checks"
                :key="`${server.name}-${check.method}`"
                class="check-item"
              >
                <div class="check-item-top">
                  <div class="check-method">{{ check.method }}</div>
                  <el-tag size="small" :type="check.ok ? 'success' : 'danger'">
                    {{ check.ok ? "成功" : "失败" }}
                  </el-tag>
                </div>
                <div class="check-message">
                  {{ check.message || "无返回信息" }}
                </div>
                <pre v-if="check.body_preview" class="check-preview">{{
                  check.body_preview
                }}</pre>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import api from "@/utils/api.js";

const DEFAULT_MCP_CONFIG = {
  mcpServers: {
    "prompts.chat": {
      url: "https://prompts.chat/api/mcp",
      enabled: true,
    },
  },
};
const DEFAULT_SKILL_REGISTRY_SOURCES = {
  vett: {
    enabled: true,
    base_url: "https://vett.sh/api/v1",
    timeout_ms: 10000,
    risk_policy: {
      allow: ["none", "low", "medium"],
      review: ["high"],
      deny: ["critical"],
    },
  },
};
const DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT =
  "基于员工职责、目标、技能建议和 prompts.chat MCP 相关能力，为员工自动补全 1 到 3 条可直接落地的执行规则。优先生成问题排查、输出规范、风险控制、技术选型相关规则；规则内容必须具体、可执行、可绑定。";
const EMPLOYEE_AUTO_RULE_SOURCE_OPTIONS = [
  {
    label: "prompts.chat curated 规则源",
    value: "prompts_chat_curated",
  },
];
const RISK_LEVEL_OPTIONS = ["none", "low", "medium", "high", "critical"];

function cloneConfig(value) {
  return JSON.parse(JSON.stringify(value));
}

const loading = ref(false);
const saving = ref(false);
const skillsLoading = ref(false);
const connectorsLoading = ref(false);
const downloadingDesktopArtifactKey = ref("");
const deletingConnectorId = ref("");
const refreshingPanels = ref(false);
const mcpServers = ref([]);
const connectorItems = ref([]);
const desktopArtifactItems = ref([]);
let connectorRefreshTimer = null;

const form = ref({
  enable_project_manual_generation: false,
  enable_employee_manual_generation: false,
  chat_upload_max_limit: 6,
  chat_max_tokens: 512,
  default_chat_system_prompt: "",
  employee_auto_rule_generation_enabled: true,
  employee_auto_rule_generation_source_filters: ["prompts_chat_curated"],
  employee_auto_rule_generation_max_count: 3,
  employee_auto_rule_generation_prompt:
    DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
  employee_external_skill_sites: [],
  skill_registry_sources: cloneConfig(DEFAULT_SKILL_REGISTRY_SOURCES),
  mcp_config_text: JSON.stringify(DEFAULT_MCP_CONFIG, null, 2),
});

const totalSkillCount = computed(() =>
  mcpServers.value.reduce(
    (sum, item) =>
      sum +
      Number(item?.tools?.length || 0) +
      Number(item?.prompts?.length || 0) +
      Number(item?.resources?.length || 0),
    0,
  ),
);

const totalErrorCount = computed(() =>
  mcpServers.value.reduce(
    (sum, item) => sum + Number(item?.errors?.length || 0),
    0,
  ),
);
const onlineConnectorCount = computed(
  () => connectorItems.value.filter((item) => item?.online).length,
);

const configLineCount = computed(
  () => String(form.value.mcp_config_text || "").split("\n").length,
);
const configParseError = computed(() => {
  try {
    parseMcpConfigText();
    return "";
  } catch (err) {
    return String(err?.message || "MCP 配置格式错误");
  }
});
const editableMcpServers = computed(() => {
  try {
    const parsed = parseMcpConfigText();
    const servers = parsed?.mcpServers;
    if (!servers || typeof servers !== "object" || Array.isArray(servers)) {
      return [];
    }
    return Object.entries(servers)
      .map(([name, value]) => ({
        name: String(name || "").trim(),
        url:
          value && typeof value === "object" && !Array.isArray(value)
            ? String(value.url || "").trim()
            : "",
        enabled:
          !(value && typeof value === "object" && !Array.isArray(value)) ||
          Boolean(value.enabled ?? true),
      }))
      .filter((item) => item.name);
  } catch {
    return [];
  }
});
function normalizeEmployeeExternalSkillSites(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    if (!rawItem || typeof rawItem !== "object" || Array.isArray(rawItem)) {
      continue;
    }
    const item = {
      id: String(rawItem.id || "").trim().slice(0, 80),
      title: String(rawItem.title || "").trim().slice(0, 120),
      description: String(rawItem.description || "").trim().slice(0, 280),
      url: String(rawItem.url || "").trim().slice(0, 500),
    };
    const dedupeKey = (
      item.id ||
      item.title ||
      item.url ||
      `site-${items.length + 1}`
    ).toLowerCase();
    if (!dedupeKey || seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    items.push(item);
    if (items.length >= 20) {
      break;
    }
  }
  return items;
}

function normalizeRiskLevelList(value, fallback = []) {
  if (!Array.isArray(value)) {
    return [...fallback];
  }
  const items = [];
  const seen = new Set();
  for (const rawItem of value) {
    const item = String(rawItem || "").trim().toLowerCase();
    if (!item || seen.has(item)) {
      continue;
    }
    seen.add(item);
    items.push(item);
  }
  return items.length ? items : [...fallback];
}

function normalizeSkillRegistrySources(value) {
  const defaults = cloneConfig(DEFAULT_SKILL_REGISTRY_SOURCES);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return defaults;
  }
  const rawVett =
    value.vett && typeof value.vett === "object" && !Array.isArray(value.vett)
      ? value.vett
      : {};
  const rawPolicy =
    rawVett.risk_policy &&
    typeof rawVett.risk_policy === "object" &&
    !Array.isArray(rawVett.risk_policy)
      ? rawVett.risk_policy
      : {};
  return {
    vett: {
      enabled: rawVett.enabled !== false,
      base_url:
        String(rawVett.base_url || defaults.vett.base_url).trim() ||
        defaults.vett.base_url,
      timeout_ms: Math.min(
        60000,
        Math.max(1000, Number(rawVett.timeout_ms || defaults.vett.timeout_ms)),
      ),
      risk_policy: {
        allow: normalizeRiskLevelList(
          rawPolicy.allow,
          defaults.vett.risk_policy.allow,
        ),
        review: normalizeRiskLevelList(
          rawPolicy.review,
          defaults.vett.risk_policy.review,
        ),
        deny: normalizeRiskLevelList(
          rawPolicy.deny,
          defaults.vett.risk_policy.deny,
        ),
      },
    },
  };
}

function addEmployeeExternalSkillSite() {
  form.value.employee_external_skill_sites = [
    ...normalizeEmployeeExternalSkillSites(form.value.employee_external_skill_sites),
    {
      id: `site-${Date.now()}`,
      title: "",
      description: "",
      url: "",
    },
  ];
}

function removeEmployeeExternalSkillSite(index) {
  form.value.employee_external_skill_sites = normalizeEmployeeExternalSkillSites(
    form.value.employee_external_skill_sites,
  ).filter((_, currentIndex) => currentIndex !== index);
}

function applyConfigToForm(config, options = {}) {
  const payload =
    config && typeof config === "object" && !Array.isArray(config) ? config : {};
  const preservePrompt = Boolean(options.preservePrompt);
  const preserveMcpConfig = Boolean(options.preserveMcpConfig);
  const hasPrompt = Object.prototype.hasOwnProperty.call(
    payload,
    "default_chat_system_prompt",
  );
  const hasEmployeeRulePrompt = Object.prototype.hasOwnProperty.call(
    payload,
    "employee_auto_rule_generation_prompt",
  );
  const hasMcpConfig = Object.prototype.hasOwnProperty.call(payload, "mcp_config");

  form.value = {
    ...form.value,
    enable_project_manual_generation:
      !!payload.enable_project_manual_generation,
    enable_employee_manual_generation:
      !!payload.enable_employee_manual_generation,
    chat_upload_max_limit: Number(payload.chat_upload_max_limit || 6),
    chat_max_tokens: Number(payload.chat_max_tokens || 512),
    default_chat_system_prompt:
      hasPrompt || !preservePrompt
        ? String(payload.default_chat_system_prompt || "")
        : String(form.value.default_chat_system_prompt || ""),
    employee_auto_rule_generation_enabled:
      !Object.prototype.hasOwnProperty.call(
        payload,
        "employee_auto_rule_generation_enabled",
      ) || !!payload.employee_auto_rule_generation_enabled,
    employee_auto_rule_generation_source_filters: Array.isArray(
      payload.employee_auto_rule_generation_source_filters,
    ) && payload.employee_auto_rule_generation_source_filters.length
      ? payload.employee_auto_rule_generation_source_filters
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : ["prompts_chat_curated"],
    employee_auto_rule_generation_max_count: Math.min(
      6,
      Math.max(1, Number(payload.employee_auto_rule_generation_max_count || 3)),
    ),
    employee_auto_rule_generation_prompt:
      hasEmployeeRulePrompt || !preservePrompt
        ? String(
            payload.employee_auto_rule_generation_prompt ||
              DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
          )
        : String(
            form.value.employee_auto_rule_generation_prompt ||
              DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
          ),
    employee_external_skill_sites: normalizeEmployeeExternalSkillSites(
      payload.employee_external_skill_sites,
    ),
    skill_registry_sources: normalizeSkillRegistrySources(
      payload.skill_registry_sources,
    ),
    mcp_config_text:
      hasMcpConfig || !preserveMcpConfig
        ? formatMcpConfig(payload.mcp_config)
        : String(form.value.mcp_config_text || formatMcpConfig(DEFAULT_MCP_CONFIG)),
  };
}

function formatMcpConfig(value) {
  const config =
    value && typeof value === "object" ? value : DEFAULT_MCP_CONFIG;
  return JSON.stringify(config, null, 2);
}

function parseMcpConfigText() {
  let parsed;
  try {
    parsed = JSON.parse(
      String(form.value.mcp_config_text || "").trim() || "{}",
    );
  } catch (err) {
    throw new Error(`MCP 配置 JSON 解析失败：${err?.message || "格式错误"}`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP 配置必须是 JSON 对象");
  }
  return parsed;
}

function updateMcpConfig(mutator) {
  const parsed = parseMcpConfigText();
  mutator(parsed);
  form.value.mcp_config_text = formatMcpConfig(parsed);
}

function formatMcpConfigText() {
  try {
    form.value.mcp_config_text = formatMcpConfig(parseMcpConfigText());
    ElMessage.success("JSON 已格式化");
  } catch (err) {
    ElMessage.error(err?.message || "MCP 配置格式错误");
  }
}

function resetMcpConfig() {
  form.value.mcp_config_text = formatMcpConfig(DEFAULT_MCP_CONFIG);
}

function toggleMcpServer(serverName, enabled) {
  try {
    updateMcpConfig((config) => {
      config.mcpServers =
        config.mcpServers && typeof config.mcpServers === "object"
          ? config.mcpServers
          : {};
      const current =
        config.mcpServers[serverName] &&
        typeof config.mcpServers[serverName] === "object" &&
        !Array.isArray(config.mcpServers[serverName])
          ? { ...config.mcpServers[serverName] }
          : {};
      current.enabled = Boolean(enabled);
      config.mcpServers[serverName] = current;
    });
  } catch (err) {
    ElMessage.error(err?.message || "切换 MCP 服务状态失败");
  }
}

function parseDateTime(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value) {
  const date = parseDateTime(value);
  if (!date) {
    return "-";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatPlatform(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return "-";
  }
  if (raw === "macos" || raw === "darwin") {
    return "macOS";
  }
  if (raw === "windows" || raw === "win32" || raw === "nt") {
    return "Windows";
  }
  return raw;
}

function formatFileSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) {
    return "-";
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function connectorCapabilityLabels(item) {
  const capabilities =
    item?.capabilities && typeof item.capabilities === "object"
      ? item.capabilities
      : {};
  const labels = [];
  if (capabilities.workspace) {
    labels.push("本地目录");
  }
  if (capabilities.exec_stream) {
    labels.push("命令执行");
  }
  if (capabilities.pty) {
    labels.push("终端 PTY");
  }
  if (capabilities.local_llm_bridge) {
    labels.push("本地模型桥接");
  }
  return labels.length ? labels : ["已注册"];
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) {
    ElMessage.warning("没有可复制的内容");
    return;
  }
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败，请手动复制");
  }
}

async function fetchLocalConnectors(options = {}) {
  if (!options.silent) {
    connectorsLoading.value = true;
  }
  try {
    const [connectorData, desktopArtifactData] = await Promise.all([
      api.get("/local-connectors"),
      api.get("/local-connectors/desktop-artifacts").catch(() => ({ artifacts: [] })),
    ]);
    connectorItems.value = Array.isArray(connectorData?.connectors)
      ? connectorData.connectors
      : [];
    desktopArtifactItems.value = Array.isArray(desktopArtifactData?.artifacts)
      ? desktopArtifactData.artifacts
      : [];
  } catch (err) {
    if (!options.silent) {
      ElMessage.error(err?.detail || err?.message || "加载本地连接器失败");
    }
  } finally {
    if (!options.silent) {
      connectorsLoading.value = false;
    }
  }
}

async function downloadDesktopArtifact(item) {
  const filename = String(item?.filename || "").trim();
  if (!filename) {
    ElMessage.warning("缺少桌面包文件名");
    return;
  }
  downloadingDesktopArtifactKey.value = filename;
  try {
    const response = await api.get("/local-connectors/desktop-artifacts/download", {
      params: { name: filename },
      responseType: "blob",
    });
    const url = URL.createObjectURL(response);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    ElMessage.success("桌面安装包已下载");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "下载桌面安装包失败");
  } finally {
    downloadingDesktopArtifactKey.value = "";
  }
}

async function deleteConnector(item) {
  const connectorId = String(item?.id || "").trim();
  if (!connectorId) {
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确定删除本地连接器「${item?.connector_name || connectorId}」？`,
      "删除连接器",
      {
        type: "warning",
      },
    );
  } catch {
    return;
  }
  deletingConnectorId.value = connectorId;
  try {
    await api.delete(`/local-connectors/${connectorId}`);
    connectorItems.value = connectorItems.value.filter((entry) => entry.id !== connectorId);
    ElMessage.success("连接器已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除连接器失败");
  } finally {
    deletingConnectorId.value = "";
  }
}

async function refreshMcpSkills() {
  skillsLoading.value = true;
  try {
    const data = await api.get("/system-config/mcp-skills");
    mcpServers.value = Array.isArray(data?.servers) ? data.servers : [];
  } catch (err) {
    mcpServers.value = [];
    ElMessage.error(err?.detail || err?.message || "加载 MCP 技能失败");
  } finally {
    skillsLoading.value = false;
  }
}

async function refreshAllPanels() {
  refreshingPanels.value = true;
  try {
    await Promise.all([refreshMcpSkills(), fetchLocalConnectors()]);
  } finally {
    refreshingPanels.value = false;
  }
}

async function fetchConfig() {
  loading.value = true;
  try {
    const data = await api.get("/system-config");
    applyConfigToForm(data?.config);
    await Promise.all([refreshMcpSkills(), fetchLocalConnectors()]);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载系统配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  let mcpConfig;
  try {
    mcpConfig = parseMcpConfigText();
  } catch (err) {
    ElMessage.error(err?.message || "MCP 配置格式错误");
    return;
  }

  saving.value = true;
  try {
    const data = await api.patch("/system-config", {
      enable_project_manual_generation:
        !!form.value.enable_project_manual_generation,
      enable_employee_manual_generation:
        !!form.value.enable_employee_manual_generation,
      chat_upload_max_limit: Number(form.value.chat_upload_max_limit || 6),
      chat_max_tokens: Number(form.value.chat_max_tokens || 512),
      default_chat_system_prompt: String(
        form.value.default_chat_system_prompt || "",
      ),
      employee_auto_rule_generation_enabled: Boolean(
        form.value.employee_auto_rule_generation_enabled,
      ),
      employee_auto_rule_generation_source_filters: Array.isArray(
        form.value.employee_auto_rule_generation_source_filters,
      )
        ? form.value.employee_auto_rule_generation_source_filters
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : ["prompts_chat_curated"],
      employee_auto_rule_generation_max_count: Number(
        form.value.employee_auto_rule_generation_max_count || 3,
      ),
      employee_auto_rule_generation_prompt: String(
        form.value.employee_auto_rule_generation_prompt ||
          DEFAULT_EMPLOYEE_RULE_GENERATION_PROMPT,
      ),
      employee_external_skill_sites: normalizeEmployeeExternalSkillSites(
        form.value.employee_external_skill_sites,
      ),
      skill_registry_sources: normalizeSkillRegistrySources(
        form.value.skill_registry_sources,
      ),
      mcp_config: mcpConfig,
    });
    applyConfigToForm(data?.config, {
      preservePrompt: true,
      preserveMcpConfig: true,
    });
    await refreshMcpSkills();
    ElMessage.success("系统配置已保存");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存系统配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  fetchConfig();
  connectorRefreshTimer = window.setInterval(() => {
    fetchLocalConnectors({ silent: true });
  }, 30000);
});

onBeforeUnmount(() => {
  if (connectorRefreshTimer) {
    window.clearInterval(connectorRefreshTimer);
    connectorRefreshTimer = null;
  }
});
</script>

<style scoped>
.system-config-page {
  --page-bg: linear-gradient(180deg, #f5f7fb 0%, #eef2f7 100%);
  --panel-bg: rgba(255, 255, 255, 0.92);
  --panel-border: rgba(112, 128, 144, 0.14);
  --panel-shadow: 0 18px 48px rgba(32, 56, 85, 0.08);
  --text-main: #1f2a37;
  --text-muted: #637083;
  --accent: #1e6aa8;
  --accent-soft: rgba(30, 106, 168, 0.1);
  --green-soft: rgba(55, 146, 98, 0.12);
  --amber-soft: rgba(191, 130, 44, 0.14);
  min-height: 100%;
  padding: 24px;
  background: var(--page-bg);
}

.hero,
.panel,
.metric-card {
  border: 1px solid var(--panel-border);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(12px);
}

.hero {
  display: flex;
  position: sticky;
  top: 12px;
  z-index: 30;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  padding: 24px 28px;
  border-radius: 24px;
  background:
    radial-gradient(
      circle at top right,
      rgba(30, 106, 168, 0.14),
      transparent 32%
    ),
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.98),
      rgba(246, 249, 252, 0.94)
    );
}

.hero-eyebrow {
  margin: 0 0 10px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hero h2 {
  margin: 0;
  color: var(--text-main);
  font-size: 28px;
  line-height: 1.2;
}

.hero-desc {
  margin: 12px 0 0;
  max-width: 720px;
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 18px;
  background: var(--panel-bg);
}

.metric-label {
  color: var(--text-muted);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.metric-value {
  color: var(--text-main);
  font-size: 32px;
  line-height: 1;
}

.metric-foot {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
  gap: 16px;
  margin-top: 16px;
}

.panel {
  padding: 20px;
  border-radius: 24px;
  background: var(--panel-bg);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.panel-head h3 {
  margin: 0;
  color: var(--text-main);
  font-size: 18px;
}

.panel-head p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.inline-alert {
  margin-bottom: 16px;
}

.switch-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.switch-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.switch-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(245, 248, 251, 0.9);
  border: 1px solid rgba(112, 128, 144, 0.12);
}

.switch-title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.switch-desc {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.number-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.field-desc {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.field-desc-block {
  margin-bottom: 0;
}

.employee-rule-config-card {
  margin-top: 12px;
}

.employee-rule-source-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.employee-skill-site-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.registry-head {
  margin-top: 8px;
}

.employee-skill-site-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
  padding-right: 4px;
}

.employee-skill-site-card {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.employee-skill-site-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.employee-skill-site-card__title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.employee-skill-site-card__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.employee-skill-site-card__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.registry-grid {
  margin-top: 14px;
}

.registry-risk-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.server-switch-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.server-switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(245, 248, 251, 0.9);
}

.server-switch-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.server-switch-name {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.server-switch-url {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.server-switch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.editor-shell {
  overflow: hidden;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.16);
  background: #0f1720;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  color: rgba(234, 239, 245, 0.86);
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.editor-meta {
  color: rgba(234, 239, 245, 0.58);
}

:deep(.mcp-config-input .el-textarea__inner) {
  min-height: 380px !important;
  padding: 18px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: #edf2f7;
  font-size: 13px;
  line-height: 1.7;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  box-shadow: none;
}

.skill-panel {
  margin-top: 16px;
}

.connector-panel {
  margin-top: 16px;
}

.connector-metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.connector-metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.connector-metric span {
  color: var(--text-muted);
  font-size: 12px;
}

.connector-metric strong {
  color: var(--text-main);
  font-size: 28px;
  line-height: 1;
}

.connector-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 16px;
}

.connector-column {
  min-width: 0;
}

.connector-subhead {
  margin-bottom: 14px;
}

.connector-subhead h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 15px;
}

.connector-subhead p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.pair-create-card,
.pair-code-card,
.connector-device-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.pair-create-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 14px;
}

.pair-create-row {
  display: flex;
  gap: 10px;
}

.pair-ttl-select {
  flex: 1;
}

.pair-custom-ttl-input {
  width: 160px;
  flex-shrink: 0;
}

.pair-code-list,
.connector-card-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pair-code-top,
.connector-device-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.pair-code-value,
.connector-device-title {
  color: var(--text-main);
  font-size: 15px;
  font-weight: 700;
}

.pair-code-meta,
.connector-device-subtitle {
  margin-top: 6px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.pair-code-info,
.connector-device-info {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  margin-top: 14px;
}

.pair-code-info span,
.connector-device-info span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.pair-code-actions,
.connector-device-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.connector-device-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.connector-capability-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.connector-error {
  margin-top: 14px;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.server-card {
  padding: 18px;
  border-radius: 20px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.98),
    rgba(248, 250, 252, 0.92)
  );
}

.server-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.server-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.server-title-row h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 17px;
}

.server-url {
  margin: 8px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
}

.server-summary {
  padding: 9px 12px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
}

.capsule-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.capsule {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.capsule-tool {
  background: var(--accent-soft);
  color: var(--accent);
}

.capsule-prompt {
  background: var(--green-soft);
  color: #2f7c57;
}

.capsule-resource {
  background: var(--amber-soft);
  color: #9a6518;
}

.capsule-fallback {
  background: rgba(90, 95, 160, 0.12);
  color: #4852a3;
}

.server-notice {
  margin-top: 14px;
}

.skill-section-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.skill-box {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(112, 128, 144, 0.14);
  background: rgba(248, 250, 252, 0.9);
}

.skill-box-title {
  margin-bottom: 10px;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-name {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 600;
  word-break: break-word;
}

.skill-desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.skill-empty {
  color: var(--text-muted);
  font-size: 12px;
}

.check-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed rgba(112, 128, 144, 0.2);
}

.check-title {
  margin-bottom: 10px;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.check-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.check-item {
  padding: 12px;
  border-radius: 14px;
  background: #f7f9fb;
  border: 1px solid rgba(112, 128, 144, 0.14);
}

.desktop-artifact-card {
  margin-bottom: 16px;
}

.desktop-artifact-card__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.desktop-artifact-card__title {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 700;
}

.desktop-artifact-card__desc {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.desktop-artifact-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.desktop-artifact-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  text-align: left;
  border: 1px solid rgba(112, 128, 144, 0.14);
  border-radius: 14px;
  background: #f7f9fb;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease;
}

.desktop-artifact-item:hover {
  border-color: rgba(40, 94, 255, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(28, 55, 90, 0.08);
}

.desktop-artifact-item:disabled {
  cursor: not-allowed;
  opacity: 0.65;
  transform: none;
  box-shadow: none;
}

.desktop-artifact-item__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.desktop-artifact-item__label {
  color: var(--text-main);
  font-size: 13px;
  font-weight: 700;
}

.desktop-artifact-item__size,
.desktop-artifact-item__meta {
  color: var(--text-muted);
  font-size: 12px;
}

.desktop-artifact-item__desc {
  color: var(--text-main);
  font-size: 12px;
  line-height: 1.5;
}

.check-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.check-method {
  color: var(--text-main);
  font-size: 12px;
  font-weight: 700;
}

.check-message {
  margin-top: 8px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.check-preview {
  margin: 10px 0 0;
  padding: 10px;
  border-radius: 12px;
  background: #101922;
  color: #dbe6ef;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

@media (max-width: 1100px) {
  .content-grid,
  .connector-grid,
  .connector-metric-row,
  .employee-skill-site-card__grid,
  .skill-section-grid,
  .check-list,
  .overview-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .system-config-page {
    padding: 16px;
  }

  .hero,
  .panel {
    padding: 18px;
    border-radius: 18px;
  }

  .hero,
  .panel-head,
  .server-head,
  .switch-card,
  .employee-skill-site-head,
  .employee-skill-site-card__top,
  .server-switch-item,
  .pair-code-top,
  .connector-device-top {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-actions,
  .panel-actions {
    width: 100%;
  }

  .number-grid,
  .pair-code-info,
  .connector-device-info,
  .desktop-artifact-list {
    grid-template-columns: 1fr;
  }

  .server-switch-actions,
  .pair-create-row {
    justify-content: space-between;
  }

  .server-summary {
    white-space: normal;
  }
}
</style>
