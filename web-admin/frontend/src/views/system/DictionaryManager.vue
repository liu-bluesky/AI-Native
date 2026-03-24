<template>
  <div class="dictionary-page" v-loading="loading">
    <section class="dictionary-hero">
      <div>
        <p class="dictionary-hero__eyebrow">Dictionary Center</p>
        <h2>字典管理</h2>
        <p class="dictionary-hero__desc">
          在这里维护平台级字典。模型类型修改后，模型供应商和 AI 对话参数面板会自动读取最新字典。
        </p>
      </div>
      <div class="dictionary-hero__actions">
        <el-button type="primary" plain @click="openCreateDialog">新增字典</el-button>
        <el-button :loading="loading" @click="refreshAll">刷新</el-button>
        <el-button
          type="warning"
          plain
          :disabled="!selectedDictionaryKey || resetting"
          :loading="resetting"
          @click="resetDictionary"
        >
          {{ resetActionLabel }}
        </el-button>
        <el-button
          type="primary"
          :disabled="!selectedDictionaryKey || saving"
          :loading="saving"
          @click="saveDictionary"
        >
          保存字典
        </el-button>
      </div>
    </section>

    <div class="dictionary-layout">
      <aside class="dictionary-sidebar">
        <div class="dictionary-panel">
          <div class="dictionary-panel__header dictionary-panel__header--compact">
            <div class="dictionary-panel__title">字典列表</div>
            <el-tag size="small" type="info">{{ dictionaries.length }} 个</el-tag>
          </div>
          <div class="dictionary-list">
            <button
              v-for="item in dictionaries"
              :key="item.key"
              type="button"
              class="dictionary-list__item"
              :class="{ 'is-active': selectedDictionaryKey === item.key }"
              @click="selectDictionary(item.key)"
            >
              <div class="dictionary-list__row">
                <span class="dictionary-list__label">{{ item.label || item.key }}</span>
                <div class="dictionary-list__tags">
                  <el-tag size="small" :type="item.builtin ? 'info' : 'success'" effect="plain">
                    {{ item.builtin ? '内置' : '自定义' }}
                  </el-tag>
                  <el-tag size="small">{{ item.option_count || 0 }} 项</el-tag>
                </div>
              </div>
              <div class="dictionary-list__meta">{{ item.key }}</div>
              <div v-if="item.description" class="dictionary-list__desc">
                {{ item.description }}
              </div>
            </button>
          </div>
        </div>
      </aside>

      <section class="dictionary-main">
        <div class="dictionary-panel">
          <template v-if="selectedDictionaryKey">
            <div class="dictionary-panel__header">
              <div>
                <div class="dictionary-panel__title">
                  {{ form.label || selectedDictionaryKey }}
                </div>
                <div class="dictionary-panel__meta">{{ selectedDictionaryKey }}</div>
              </div>
              <el-tag :type="selectedDictionaryBuiltin ? 'info' : 'success'">
                {{ selectedDictionaryBuiltin ? '内置字典' : '自定义字典' }}
              </el-tag>
            </div>

            <div class="dictionary-usage">
              <div class="dictionary-usage__head">
                <div class="dictionary-panel__title">调用页面</div>
                <el-tag size="small" effect="plain">
                  {{ selectedDictionaryUsageRefs.length }} 处
                </el-tag>
              </div>
              <div v-if="selectedDictionaryUsageRefs.length" class="dictionary-usage__list">
                <button
                  v-for="usage in selectedDictionaryUsageRefs"
                  :key="usage.id || usage.route || usage.label"
                  type="button"
                  class="dictionary-usage__item"
                  @click="openUsageRef(usage)"
                >
                  <div class="dictionary-usage__title">
                    {{ usage.label || usage.route || '未命名页面' }}
                  </div>
                  <div class="dictionary-usage__route">{{ usage.route || '未登记路由' }}</div>
                  <div v-if="usage.description" class="dictionary-usage__desc">
                    {{ usage.description }}
                  </div>
                </button>
              </div>
              <el-empty
                v-else
                description="当前字典还没有登记页面调用关系"
                :image-size="48"
              />
            </div>

            <el-form label-position="top" class="dictionary-form">
              <div class="dictionary-form__grid">
                <el-form-item label="字典名称">
                  <el-input v-model="form.label" placeholder="例如：模型类型" />
                </el-form-item>
                <el-form-item label="默认值">
                  <el-select v-model="form.default_value" placeholder="选择默认值" style="width: 100%">
                    <el-option
                      v-for="option in normalizedFormOptions"
                      :key="option.id"
                      :label="option.label || option.id"
                      :value="option.id"
                    />
                  </el-select>
                </el-form-item>
              </div>

              <el-form-item label="描述">
                <el-input
                  v-model="form.description"
                  type="textarea"
                  :rows="3"
                  resize="vertical"
                  placeholder="说明这个字典的用途和影响范围。"
                />
              </el-form-item>

              <div class="dictionary-options__head">
                <div>
                  <div class="dictionary-panel__title">字典项</div>
                  <div class="dictionary-panel__desc">维护候选值、标签和扩展说明。</div>
                </div>
                <el-button @click="addOption">新增字典项</el-button>
              </div>

              <div class="dictionary-options">
                <div
                  v-for="(item, index) in form.options"
                  :key="item.key"
                  class="dictionary-option-card"
                >
                  <div class="dictionary-option-card__head">
                    <div class="dictionary-option-card__title">字典项 {{ index + 1 }}</div>
                    <el-button
                      text
                      type="danger"
                      :disabled="form.options.length <= 1"
                      @click="removeOption(index)"
                    >
                      删除
                    </el-button>
                  </div>

                  <div class="dictionary-form__grid">
                    <el-form-item label="值">
                      <el-input v-model="item.id" placeholder="例如：image_generation" />
                    </el-form-item>
                    <el-form-item label="显示名称">
                      <el-input v-model="item.label" placeholder="例如：图片生成" />
                    </el-form-item>
                  </div>

                  <el-form-item v-if="showChatParameterMode" label="参数模式">
                    <el-select v-model="item.chat_parameter_mode" style="width: 220px">
                      <el-option label="text" value="text" />
                      <el-option label="image" value="image" />
                      <el-option label="video" value="video" />
                    </el-select>
                  </el-form-item>

                  <el-form-item label="描述">
                    <el-input
                      v-model="item.description"
                      type="textarea"
                      :rows="2"
                      resize="vertical"
                      placeholder="说明这个字典项适合什么场景。"
                    />
                  </el-form-item>
                </div>
              </div>
            </el-form>
          </template>

          <el-empty v-else description="暂无可维护字典" :image-size="64" />
        </div>
      </section>
    </div>

    <el-dialog
      v-model="createDialogVisible"
      title="新增字典"
      width="520px"
      @closed="resetCreateForm"
    >
      <el-form label-position="top">
        <el-form-item label="字典 Key">
          <el-input
            v-model="createForm.key"
            placeholder="例如：image_styles"
            autocomplete="off"
          />
          <div class="dictionary-dialog__hint">仅支持字母、数字、点、下划线和中划线。</div>
        </el-form-item>
        <el-form-item label="字典名称">
          <el-input
            v-model="createForm.label"
            placeholder="例如：图片风格"
            autocomplete="off"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            resize="vertical"
            placeholder="说明这个字典要给哪些模块使用。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dictionary-dialog__footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="createDictionary">创建</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/utils/api.js'
import { fetchDictionary } from '@/utils/dictionaries.js'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const creating = ref(false)
const createDialogVisible = ref(false)
const dictionaries = ref([])
const selectedDictionaryKey = ref('')

const form = reactive({
  label: '',
  description: '',
  default_value: '',
  options: [],
})
const dictionaryMeta = reactive({
  builtin: true,
  usage_refs: [],
})
const createForm = reactive({
  key: '',
  label: '',
  description: '',
})

let optionSeed = 0

function createOption(option = {}) {
  optionSeed += 1
  return {
    key: `dictionary-option-${optionSeed}`,
    id: String(option?.id || '').trim(),
    label: String(option?.label || '').trim(),
    description: String(option?.description || '').trim(),
    chat_parameter_mode: String(option?.chat_parameter_mode || 'text').trim() || 'text',
  }
}

const normalizedFormOptions = computed(() => {
  const values = []
  const seen = new Set()
  form.options.forEach((item) => {
    const id = String(item?.id || '').trim()
    if (!id || seen.has(id)) return
    seen.add(id)
    values.push({
      id,
      label: String(item?.label || id).trim() || id,
      description: String(item?.description || '').trim(),
      chat_parameter_mode: String(item?.chat_parameter_mode || 'text').trim() || 'text',
    })
  })
  return values
})

const showChatParameterMode = computed(
  () => String(selectedDictionaryKey.value || '').trim() === 'llm_model_types',
)
const selectedDictionary = computed(
  () => dictionaries.value.find((item) => item.key === selectedDictionaryKey.value) || null,
)
const selectedDictionaryBuiltin = computed(
  () => selectedDictionary.value?.builtin ?? dictionaryMeta.builtin,
)
const selectedDictionaryUsageRefs = computed(() => {
  if (Array.isArray(dictionaryMeta.usage_refs) && dictionaryMeta.usage_refs.length) {
    return dictionaryMeta.usage_refs
  }
  return Array.isArray(selectedDictionary.value?.usage_refs)
    ? selectedDictionary.value.usage_refs
    : []
})
const resetActionLabel = computed(() => (
  selectedDictionaryBuiltin.value ? '恢复默认' : '删除字典'
))

function resetForm() {
  form.label = ''
  form.description = ''
  form.default_value = ''
  form.options = [createOption()]
  dictionaryMeta.builtin = true
  dictionaryMeta.usage_refs = []
}

function applyDictionary(definition) {
  form.label = String(definition?.label || '').trim()
  form.description = String(definition?.description || '').trim()
  form.options = Array.isArray(definition?.options) && definition.options.length
    ? definition.options.map((item) => createOption(item))
    : [createOption()]
  const preferredDefault = String(definition?.default_value || '').trim()
  form.default_value = normalizedFormOptions.value.some((item) => item.id === preferredDefault)
    ? preferredDefault
    : normalizedFormOptions.value[0]?.id || ''
  dictionaryMeta.builtin = definition?.builtin !== false
  dictionaryMeta.usage_refs = Array.isArray(definition?.usage_refs)
    ? definition.usage_refs.map((item) => ({
      id: String(item?.id || '').trim(),
      label: String(item?.label || '').trim(),
      route: String(item?.route || '').trim(),
      description: String(item?.description || '').trim(),
    }))
    : []
}

function resetCreateForm() {
  createForm.key = ''
  createForm.label = ''
  createForm.description = ''
}

function openCreateDialog() {
  resetCreateForm()
  createDialogVisible.value = true
}

async function fetchDictionaryList() {
  const data = await api.get('/dictionaries')
  dictionaries.value = Array.isArray(data?.items) ? data.items : []
  const availableKeys = new Set(
    dictionaries.value.map((item) => String(item?.key || '').trim()).filter(Boolean),
  )
  if (!dictionaries.value.length) {
    selectedDictionaryKey.value = ''
    return
  }
  if (!availableKeys.has(selectedDictionaryKey.value)) {
    selectedDictionaryKey.value = String(dictionaries.value[0]?.key || '').trim()
  }
}

async function fetchSelectedDictionary() {
  if (!selectedDictionaryKey.value) {
    resetForm()
    return
  }
  const data = await fetchDictionary(selectedDictionaryKey.value)
  applyDictionary(data)
}

async function refreshAll() {
  loading.value = true
  try {
    await fetchDictionaryList()
    await fetchSelectedDictionary()
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '加载字典失败')
  } finally {
    loading.value = false
  }
}

async function selectDictionary(dictionaryKey) {
  const normalizedKey = String(dictionaryKey || '').trim()
  if (!normalizedKey || normalizedKey === selectedDictionaryKey.value) return
  selectedDictionaryKey.value = normalizedKey
  loading.value = true
  try {
    await fetchSelectedDictionary()
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '加载字典详情失败')
  } finally {
    loading.value = false
  }
}

function openUsageRef(usage) {
  const route = String(usage?.route || '').trim()
  if (!route) return
  router.push(route)
}

function addOption() {
  form.options.push(createOption())
}

function removeOption(index) {
  form.options.splice(index, 1)
  if (!form.options.length) {
    form.options.push(createOption())
  }
  if (!normalizedFormOptions.value.some((item) => item.id === form.default_value)) {
    form.default_value = normalizedFormOptions.value[0]?.id || ''
  }
}

async function createDictionary() {
  const normalizedKey = String(createForm.key || '').trim()
  if (!normalizedKey) {
    ElMessage.warning('请先填写字典 Key')
    return
  }

  creating.value = true
  try {
    const response = await api.post('/dictionaries', {
      key: normalizedKey,
      label: String(createForm.label || '').trim() || normalizedKey,
      description: String(createForm.description || '').trim(),
      default_value: 'default',
      options: [
        {
          id: 'default',
          label: '默认选项',
          description: '',
        },
      ],
    })
    selectedDictionaryKey.value = String(response?.dictionary?.key || normalizedKey).trim()
    createDialogVisible.value = false
    await refreshAll()
    ElMessage.success('字典已创建')
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '创建字典失败')
  } finally {
    creating.value = false
  }
}

async function saveDictionary() {
  const options = normalizedFormOptions.value
  if (!selectedDictionaryKey.value) {
    ElMessage.warning('请先选择字典')
    return
  }
  if (!options.length) {
    ElMessage.warning('请至少保留一个字典项')
    return
  }
  if (!options.some((item) => item.id === form.default_value)) {
    form.default_value = options[0].id
  }

  saving.value = true
  try {
    await api.put(`/dictionaries/${encodeURIComponent(selectedDictionaryKey.value)}`, {
      label: String(form.label || '').trim(),
      description: String(form.description || '').trim(),
      default_value: String(form.default_value || '').trim(),
      options: options,
    })
    await refreshAll()
    ElMessage.success('字典已保存')
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || '保存字典失败')
  } finally {
    saving.value = false
  }
}

async function resetDictionary() {
  if (!selectedDictionaryKey.value) return
  const isBuiltin = selectedDictionaryBuiltin.value
  try {
    await ElMessageBox.confirm(
      isBuiltin
        ? '恢复默认后，会清空当前字典的自定义配置，继续吗？'
        : '删除后，这个自定义字典会从系统设置中移除，继续吗？',
      isBuiltin ? '恢复默认' : '删除字典',
      { type: 'warning' },
    )
  } catch {
    return
  }

  resetting.value = true
  try {
    await api.delete(`/dictionaries/${encodeURIComponent(selectedDictionaryKey.value)}`)
    await refreshAll()
    ElMessage.success(isBuiltin ? '已恢复默认字典' : '已删除自定义字典')
  } catch (e) {
    ElMessage.error(e?.detail || e?.message || (isBuiltin ? '恢复默认失败' : '删除字典失败'))
  } finally {
    resetting.value = false
  }
}

onMounted(() => {
  resetForm()
  void refreshAll()
})
</script>

<style scoped>
.dictionary-page {
  display: grid;
  gap: 20px;
}

.dictionary-hero,
.dictionary-panel {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
}

.dictionary-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 26px;
}

.dictionary-hero__eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7c8aa0;
}

.dictionary-hero h2 {
  margin: 0;
  font-size: 28px;
  color: #0f172a;
}

.dictionary-hero__desc {
  margin: 10px 0 0;
  max-width: 760px;
  color: #526071;
  line-height: 1.7;
}

.dictionary-hero__actions {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.dictionary-layout {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 20px;
  min-height: 0;
}

.dictionary-sidebar,
.dictionary-main {
  min-width: 0;
}

.dictionary-panel {
  padding: 22px;
}

.dictionary-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.dictionary-panel__header--compact {
  align-items: center;
  margin-bottom: 14px;
}

.dictionary-panel__title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.dictionary-panel__meta {
  margin-top: 6px;
  font-size: 12px;
  color: #7c8aa0;
}

.dictionary-panel__desc {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.dictionary-list {
  display: grid;
  gap: 12px;
}

.dictionary-list__item {
  width: 100%;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: #fff;
  padding: 14px;
  text-align: left;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.dictionary-list__item:hover {
  transform: translateY(-1px);
  border-color: rgba(56, 189, 248, 0.32);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
}

.dictionary-list__item.is-active {
  border-color: rgba(15, 23, 42, 0.16);
  background: #f8fbff;
}

.dictionary-list__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dictionary-list__tags {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.dictionary-list__label {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.dictionary-list__meta {
  margin-top: 8px;
  font-size: 12px;
  color: #7c8aa0;
}

.dictionary-list__desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #526071;
}

.dictionary-form {
  display: grid;
  gap: 4px;
}

.dictionary-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.dictionary-usage {
  margin-bottom: 20px;
  padding: 16px 18px;
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.dictionary-usage__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.dictionary-usage__list {
  display: grid;
  gap: 12px;
}

.dictionary-usage__item {
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  background: #fff;
  padding: 14px 16px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}

.dictionary-usage__item:hover {
  border-color: rgba(37, 99, 235, 0.35);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.dictionary-usage__title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.dictionary-usage__route {
  margin-top: 4px;
  font-size: 12px;
  color: #2563eb;
}

.dictionary-usage__desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #526071;
}

.dictionary-options__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0 4px;
}

.dictionary-options {
  display: grid;
  gap: 16px;
}

.dictionary-dialog__hint {
  margin-top: 8px;
  font-size: 12px;
  color: #7c8aa0;
}

.dictionary-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.dictionary-option-card {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 18px;
  background: #fbfdff;
  padding: 18px;
}

.dictionary-option-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.dictionary-option-card__title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

@media (max-width: 960px) {
  .dictionary-layout {
    grid-template-columns: 1fr;
  }

  .dictionary-form__grid {
    grid-template-columns: 1fr;
  }

  .dictionary-hero {
    flex-direction: column;
  }
}
</style>
