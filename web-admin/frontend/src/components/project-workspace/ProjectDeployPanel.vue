<template>
  <div class="project-deploy-panel">
    <ProjectWorkspaceBlock eyebrow="Deploy" :title="deployPanelTitle">
      <template #actions>
        <div v-if="activeDeployTab === 'settings'" class="project-deploy-panel__actions">
          <el-button size="small" :loading="deployValidating" @click="validateDeploySettings">
            校验配置
          </el-button>
          <el-button
            type="primary"
            size="small"
            :disabled="!canManageProject"
            :loading="deploySaving"
            @click="saveDeploySettings"
          >
            保存配置
          </el-button>
        </div>
        <div v-else-if="activeDeployTab === 'artifacts'" class="project-deploy-panel__actions">
          <el-button
            type="primary"
            size="small"
            :disabled="!canManageProject"
            @click="openArtifactUploadDialog"
          >
            上传产物
          </el-button>
          <el-button
            size="small"
            :loading="deployArtifactsLoading || deployRunsLoading"
            @click="refreshDeployStatus"
          >
            刷新状态
          </el-button>
        </div>
        <div v-else class="project-deploy-panel__actions">
          <el-button
            size="small"
            :loading="deployArtifactsLoading || deployRunsLoading"
            @click="refreshDeployStatus"
          >
            刷新状态
          </el-button>
        </div>
      </template>

      <div class="deploy-tabs-shell">
        <el-tabs v-model="activeDeployTab" class="deploy-tabs">
          <el-tab-pane name="settings">
            <template #label>
              <span class="deploy-tab-label">
                <span class="deploy-tab-label__title">部署配置</span>
                <span class="deploy-tab-label__meta">{{ settingsTabMeta }}</span>
              </span>
            </template>
          <div class="deploy-topbar">
            <el-switch v-model="deploySettingsForm.enabled" active-text="启用部署" />
            <el-select v-model="deploySettingsForm.default_profile" class="deploy-topbar__select">
              <el-option
                v-for="profile in deploySettingsForm.profiles"
                :key="profile.id"
                :label="profile.name || profile.id"
                :value="profile.id"
              />
            </el-select>
          </div>

          <div class="deploy-layout">
            <aside class="deploy-list">
              <div class="deploy-list__head">
                <span>环境档位</span>
                <el-button size="small" text @click="addDeployProfile">新增</el-button>
              </div>
              <button
                v-for="profile in deploySettingsForm.profiles"
                :key="profile.id"
                type="button"
                class="deploy-list__item"
                :class="{ 'is-active': profile.id === activeProfileId }"
                @click="selectDeployProfile(profile.id)"
              >
                <strong>{{ profile.name || profile.id }}</strong>
                <span>{{ profile.environment || profile.id }}</span>
              </button>
            </aside>

            <section v-if="activeProfile" class="deploy-editor">
              <div class="deploy-editor__header">
                <div>
                  <strong>{{ activeProfile.name || activeProfile.id }}</strong>
                  <span>{{ activeProfile.components.length }} 个部署单元</span>
                </div>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="deploySettingsForm.profiles.length <= 1"
                  @click="removeDeployProfile(activeProfile.id)"
                >
                  删除环境
                </el-button>
              </div>

              <el-form label-position="top" class="deploy-form">
                <div class="deploy-form__grid">
                  <el-form-item label="档位 ID">
                    <el-input v-model="activeProfile.id" @change="normalizeActiveProfileId" />
                  </el-form-item>
                  <el-form-item label="档位名称">
                    <el-input v-model="activeProfile.name" />
                  </el-form-item>
                  <el-form-item label="运行环境">
                    <el-input v-model="activeProfile.environment" />
                  </el-form-item>
                </div>
              </el-form>

              <div class="deploy-subgrid">
                <aside class="deploy-list deploy-list--nested">
                  <div class="deploy-list__head">
                    <span>部署单元</span>
                    <el-button size="small" text @click="addDeployComponent">新增</el-button>
                  </div>
                  <button
                    v-for="component in activeProfile.components"
                    :key="component.id"
                    type="button"
                    class="deploy-list__item"
                    :class="{ 'is-active': component.id === activeComponentId }"
                    @click="selectDeployComponent(component.id)"
                  >
                    <strong>{{ component.name || component.id }}</strong>
                    <span>{{ component.targets.length }} 台服务器</span>
                  </button>
                </aside>

                <section v-if="activeComponent" class="deploy-component">
                  <div class="deploy-editor__header">
                    <div>
                      <strong>{{ activeComponent.name || activeComponent.id }}</strong>
                      <span>{{ activeComponent.targets.length }} 台服务器</span>
                    </div>
                    <el-button
                      size="small"
                      type="danger"
                      plain
                      :disabled="activeProfile.components.length <= 1"
                      @click="removeDeployComponent(activeComponent.id)"
                    >
                      删除单元
                    </el-button>
                  </div>

                  <el-form label-position="top" class="deploy-form">
                    <div class="deploy-form__grid">
                      <el-form-item label="单元 ID">
                        <el-input v-model="activeComponent.id" @change="normalizeActiveComponentId" />
                      </el-form-item>
                      <el-form-item label="单元名称">
                        <el-input v-model="activeComponent.name" />
                      </el-form-item>
                      <el-form-item label="自动执行部署命令">
                        <el-switch
                          v-model="activeComponent.safety.auto_deploy_on_artifact_update"
                          active-text="上传产物后执行"
                        />
                      </el-form-item>
                      <el-form-item label="通知">
                        <el-switch v-model="activeComponent.notify.enabled" />
                      </el-form-item>
                      <el-form-item label="通知平台">
                        <el-select
                          v-model="notifyTargetForm.platform"
                          style="width: 100%"
                          @change="onNotifyPlatformChange"
                        >
                          <el-option label="飞书" value="feishu" />
                          <el-option label="微信" value="wechat" />
                          <el-option label="QQ" value="qq" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="通知机器人">
                        <el-select
                          v-model="notifyTargetForm.connector_id"
                          :loading="deployNotifyOptionsLoading"
                          filterable
                          clearable
                          placeholder="选择机器人"
                          style="width: 100%"
                          @change="onNotifyConnectorChange"
                        >
                          <el-option
                            v-for="item in notifyConnectorOptions"
                            :key="item.id"
                            :label="item.label"
                            :value="item.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="通知群">
                        <el-select
                          v-model="notifyTargetForm.chat_id"
                          :loading="deployNotifyOptionsLoading"
                          filterable
                          clearable
                          placeholder="选择已识别群"
                          style="width: 100%"
                          @change="onNotifyChatChange"
                        >
                          <el-option
                            v-for="item in notifyChatOptions"
                            :key="item.chat_id"
                            :label="item.label"
                            :value="item.chat_id"
                          />
                        </el-select>
                      </el-form-item>
                    </div>
                    <div v-if="notifyTargetForm.platform === 'feishu'" class="deploy-notify-resolver">
                      <el-input
                        v-model="notifyChatName"
                        placeholder="输入飞书群名称"
                        clearable
                        @keyup.enter="resolveNotifyChatByName"
                      />
                      <el-button
                        :loading="deployNotifyResolving"
                        :disabled="!notifyTargetForm.connector_id || !notifyChatName.trim()"
                        @click="resolveNotifyChatByName"
                      >
                        解析群
                      </el-button>
                    </div>
                  </el-form>

                  <div class="deploy-targets">
                    <div class="deploy-targets__head">
                      <strong>服务器目标</strong>
                      <el-button size="small" @click="addDeployTarget">新增服务器</el-button>
                    </div>
                    <div class="deploy-table-wrap">
                      <el-table :data="activeComponent.targets" stripe class="section-table deploy-targets-table">
                        <el-table-column label="启用" width="78">
                          <template #default="{ row }">
                            <el-switch v-model="row.enabled" />
                          </template>
                        </el-table-column>
                        <el-table-column label="名称" min-width="140">
                          <template #default="{ row }">
                            <el-input v-model="row.name" size="small" />
                          </template>
                        </el-table-column>
                        <el-table-column label="方式" width="90">
                          <template #default>
                            <el-tag size="small" effect="plain">FTP</el-tag>
                          </template>
                        </el-table-column>
                        <el-table-column label="FTP 连接" min-width="260">
                          <template #default="{ row }">
                            <el-select
                              v-model="row.ftp_credential_id"
                              size="small"
                              filterable
                              placeholder="选择全局 FTP 连接"
                              class="deploy-targets__credential-select"
                            >
                              <el-option
                                v-for="credential in ftpCredentialOptions"
                                :key="credential.id"
                                :label="credential.label"
                                :value="credential.id"
                                :disabled="credential.enabled === false"
                              />
                            </el-select>
                          </template>
                        </el-table-column>
                        <el-table-column label="远端目录" min-width="180">
                          <template #default="{ row }">
                            <el-input v-model="row.remote_path" size="small" placeholder="/opt/app/releases" />
                          </template>
                        </el-table-column>
                        <el-table-column label="部署命令" min-width="220">
                          <template #default="{ row, $index }">
                            <div class="deploy-targets__command-cell">
                              <el-input v-model="row.deploy_command" size="small" placeholder="./deploy.sh up" />
                              <el-button
                                size="small"
                                :loading="deployCommandGeneratingKey === deployTargetRowKey(row, $index)"
                                :disabled="!canManageProject"
                                @click="generateDeployCommand(row, $index)"
                              >
                                AI 生成
                              </el-button>
                            </div>
                          </template>
                        </el-table-column>
                        <el-table-column label="操作" width="82" fixed="right">
                          <template #default="{ $index }">
                            <el-button
                              size="small"
                              type="danger"
                              text
                              :disabled="activeComponent.targets.length <= 1"
                              @click="removeDeployTarget($index)"
                            >
                              删除
                            </el-button>
                          </template>
                        </el-table-column>
                      </el-table>
                    </div>
                  </div>
                </section>
              </div>
            </section>
          </div>

          <div v-if="deployValidation" class="project-deploy-panel__validation">
            <el-alert
              :title="deployValidation.valid ? '部署配置校验通过' : '部署配置仍需补充'"
              :type="deployValidation.valid ? 'success' : 'warning'"
              :closable="false"
              show-icon
            />
            <ul v-if="deployValidation.issues?.length">
              <li v-for="issue in deployValidation.issues" :key="`${issue.path}-${issue.message}`">
                <span>{{ issue.message }}</span>
              </li>
            </ul>
          </div>
        </el-tab-pane>

          <el-tab-pane name="artifacts">
            <template #label>
              <span class="deploy-tab-label">
                <span class="deploy-tab-label__title">部署产物</span>
                <span class="deploy-tab-label__meta">{{ artifactsTabMeta }}</span>
              </span>
            </template>
          <div class="deploy-table-wrap">
            <el-table
              v-loading="deployArtifactsLoading"
              :data="deployArtifacts"
              stripe
              class="section-table deploy-artifacts-table"
            >
              <el-table-column type="expand" width="42">
                <template #default="{ row }">
                  <div v-if="row.file_tree?.length" class="deploy-artifact-tree">
                    <div class="deploy-artifact-tree__head">
                      <strong>目录结构</strong>
                      <span>{{ row.file_count }} 个文件 · {{ formatFileSize(row.size) }}</span>
                    </div>
                    <el-tree
                      :data="row.file_tree"
                      node-key="path"
                      :props="{ label: 'name', children: 'children' }"
                      default-expand-all
                    >
                      <template #default="{ data }">
                        <span class="deploy-artifact-tree__node">
                          <span>{{ data.name }}</span>
                          <em v-if="data.type === 'file'">{{ formatFileSize(data.size) }}</em>
                        </span>
                      </template>
                    </el-tree>
                  </div>
                  <el-empty v-else description="该产物没有目录结构" :image-size="46" />
                </template>
              </el-table-column>
              <el-table-column label="产物" min-width="240">
                <template #default="{ row }">
                  <div class="project-deploy-panel__table-main">
                    <strong>{{ row.artifact_name || row.id }}</strong>
                    <span>{{ getDeployArtifactSubtitle(row) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="环境" width="120">
                <template #default="{ row }">
                  <el-tag effect="plain" type="info">{{ row.profile || "-" }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="部署单元" width="130">
                <template #default="{ row }">{{ row.component || "-" }}</template>
              </el-table-column>
              <el-table-column label="状态" width="140">
                <template #default="{ row }">
                  <el-tag :type="getDeployStatusTagType(getDeployArtifactStatus(row))">
                    {{ getDeployStatusLabel(getDeployArtifactStatus(row)) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="大小" width="120">
                <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
              </el-table-column>
              <el-table-column label="上传时间" min-width="150">
                <template #default="{ row }">{{ formatRelativeTime(row.uploaded_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="232" fixed="right" class-name="project-deploy-panel__fixed-actions">
                <template #default="{ row }">
                  <div class="project-deploy-panel__row-actions">
                    <el-button
                      v-if="hasDeployFailureLog(row)"
                      text
                      type="warning"
                      :loading="deployLogLoading && deployLogArtifactId === row.id"
                      :disabled="deletingArtifactId === row.id"
                      @click="openDeployLogDialog(row)"
                    >
                      日志
                    </el-button>
                    <el-button
                      text
                      type="primary"
                      :loading="deployingArtifactId === row.id"
                      :disabled="!canManageProject || deletingArtifactId === row.id"
                      @click="openAiDeployArtifact(row)"
                    >
                      AI 部署
                    </el-button>
                    <el-popconfirm
                      title="确定删除这个打包产物文件吗？"
                      confirm-button-text="删除"
                      cancel-button-text="取消"
                      @confirm="deleteDeployArtifact(row)"
                    >
                      <template #reference>
                        <el-button
                          text
                          type="danger"
                          :loading="deletingArtifactId === row.id"
                          :disabled="!canManageProject || deployingArtifactId === row.id"
                        >
                          删除
                        </el-button>
                      </template>
                    </el-popconfirm>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty
            v-if="!deployArtifactsLoading && !deployArtifacts.length"
            description="暂无部署产物"
            :image-size="60"
          />
        </el-tab-pane>

          <el-tab-pane name="runs">
            <template #label>
              <span class="deploy-tab-label">
                <span class="deploy-tab-label__title">部署运行</span>
                <span class="deploy-tab-label__meta">{{ runsTabMeta }}</span>
              </span>
            </template>
          <div class="deploy-table-wrap">
            <el-table v-loading="deployRunsLoading" :data="deployRuns" stripe class="section-table deploy-runs-table">
              <el-table-column label="运行 ID" min-width="180">
                <template #default="{ row }">
                  <code>{{ row.id }}</code>
                </template>
              </el-table-column>
              <el-table-column label="环境" width="110">
                <template #default="{ row }">{{ row.profile || "-" }}</template>
              </el-table-column>
              <el-table-column label="部署单元" width="130">
                <template #default="{ row }">{{ row.component || "-" }}</template>
              </el-table-column>
              <el-table-column label="阶段" min-width="180">
                <template #default="{ row }">
                  <div class="project-deploy-panel__table-main">
                    <strong>{{ getDeployStatusLabel(row.status) }}</strong>
                    <span>{{ row.stage || "-" }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="通知" min-width="170">
                <template #default="{ row }">
                  <div class="project-deploy-panel__notify-tags">
                    <el-tag
                      v-for="item in row.notify_result || []"
                      :key="`${item.platform}-${item.chat_id}`"
                      size="small"
                      effect="plain"
                      :type="item.status === 'preview' ? 'success' : 'info'"
                    >
                      {{ getDeployNotifyLabel(item) }}
                    </el-tag>
                    <span v-if="!row.notify_result?.length">-</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="日志摘要" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ row.log_excerpt || "-" }}</template>
              </el-table-column>
              <el-table-column label="更新时间" min-width="150">
                <template #default="{ row }">{{ formatRelativeTime(row.updated_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="96" fixed="right">
                <template #default="{ row }">
                  <el-popconfirm
                    title="确定删除这条部署运行记录吗？"
                    confirm-button-text="删除"
                    cancel-button-text="取消"
                    @confirm="deleteDeployRun(row)"
                  >
                    <template #reference>
                      <el-button
                        text
                        type="danger"
                        :loading="deletingRunId === row.id"
                        :disabled="!canManageProject"
                      >
                        删除
                      </el-button>
                    </template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-if="!deployRunsLoading && !deployRuns.length" description="暂无部署运行记录" :image-size="60" />
        </el-tab-pane>
        </el-tabs>
      </div>
    </ProjectWorkspaceBlock>

    <el-dialog
      v-model="artifactUploadDialogVisible"
      title="上传部署产物"
      width="560px"
      :close-on-click-modal="!artifactUploadSubmitting"
      :close-on-press-escape="!artifactUploadSubmitting"
      @closed="resetArtifactUploadDialog"
    >
      <el-form label-position="top" class="deploy-upload-form">
        <div class="deploy-form__grid deploy-upload-form__grid">
          <el-form-item label="环境档位">
            <el-select
              v-model="artifactUploadForm.profile"
              class="deploy-upload-form__control"
              @change="handleArtifactUploadProfileChange"
            >
              <el-option
                v-for="profile in artifactUploadProfileOptions"
                :key="profile.id"
                :label="profile.label"
                :value="profile.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="部署单元">
            <el-select
              v-model="artifactUploadForm.component"
              class="deploy-upload-form__control"
              @change="handleArtifactUploadComponentChange"
            >
              <el-option
                v-for="component in artifactUploadComponentOptions"
                :key="component.id"
                :label="component.label"
                :value="component.id"
              />
            </el-select>
          </el-form-item>
        </div>
        <div class="deploy-form__grid deploy-upload-form__grid">
          <el-form-item label="产物类型">
            <el-input v-model="artifactUploadForm.artifact_kind" />
          </el-form-item>
          <el-form-item label="版本号">
            <el-input v-model="artifactUploadForm.version" placeholder="可选" />
          </el-form-item>
        </div>
        <el-form-item label="上传内容">
          <input
            ref="artifactUploadInputRef"
            type="file"
            class="project-deploy-panel__file-input"
            @change="handleArtifactUploadFileChange"
          />
          <input
            ref="artifactUploadDirectoryInputRef"
            type="file"
            class="project-deploy-panel__file-input"
            multiple
            webkitdirectory
            directory
            @change="handleArtifactUploadDirectoryChange"
          />
          <div class="deploy-upload-file">
            <div class="deploy-upload-file__meta">
              <strong>{{ artifactUploadSelectionTitle }}</strong>
              <span>{{ artifactUploadFileMeta }}</span>
            </div>
            <div class="deploy-upload-file__actions">
              <el-button size="small" @click="selectArtifactUploadFile">
                选择文件
              </el-button>
              <el-button size="small" @click="selectArtifactUploadDirectory">
                选择目录
              </el-button>
            </div>
          </div>
          <div v-if="artifactUploadPreviewTree.length" class="deploy-artifact-tree deploy-artifact-tree--preview">
            <div class="deploy-artifact-tree__head">
              <strong>待上传目录</strong>
              <span>{{ selectedArtifactUploadDirectoryItems.length }}/{{ artifactUploadFiles.length }} 个文件</span>
              <div class="deploy-artifact-tree__actions">
                <el-button size="small" text @click="selectAllArtifactUploadFiles">全选</el-button>
                <el-button size="small" text @click="clearArtifactUploadFiles">清空</el-button>
              </div>
            </div>
            <el-tree
              ref="artifactUploadTreeRef"
              :data="artifactUploadPreviewTree"
              node-key="path"
              :props="{ label: 'name', children: 'children' }"
              :default-checked-keys="artifactUploadSelectedPaths"
              default-expand-all
              show-checkbox
              @check="handleArtifactUploadTreeCheck"
            >
              <template #default="{ data }">
                <span class="deploy-artifact-tree__node">
                  <span>{{ data.name }}</span>
                  <em v-if="data.type === 'file'">{{ formatFileSize(data.size) }}</em>
                </span>
              </template>
            </el-tree>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="deploy-upload-footer">
          <el-button :disabled="artifactUploadSubmitting" @click="artifactUploadDialogVisible = false">
            取消
          </el-button>
          <el-button
            type="primary"
            :loading="artifactUploadSubmitting"
            @click="submitArtifactUpload"
          >
            上传
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="aiDeployDialogVisible"
      title="AI 部署"
      width="960px"
      class="ai-deploy-dialog"
      append-to-body
      :z-index="3000"
      :close-on-click-modal="!aiDeployBusy"
      :close-on-press-escape="!aiDeployBusy"
      @closed="resetAiDeployDialog"
    >
      <div v-if="aiDeployArtifact" class="ai-deploy">
        <section class="ai-deploy__hero">
          <div class="ai-deploy__artifact">
            <div class="project-deploy-panel__table-main ai-deploy__artifact-title">
              <strong>{{ aiDeployArtifact.artifact_name || aiDeployArtifact.id }}</strong>
              <span>{{ getDeployArtifactSubtitle(aiDeployArtifact) }}</span>
            </div>
            <el-tag :type="getDeployStatusTagType(getDeployArtifactStatus(aiDeployArtifact))">
              {{ getDeployStatusLabel(getDeployArtifactStatus(aiDeployArtifact)) }}
            </el-tag>
          </div>
          <div class="ai-deploy__meta">
            <div v-for="item in aiDeploySummaryItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section class="ai-deploy__targets">
          <div class="ai-deploy__section-head">
            <strong>部署目标</strong>
            <span>{{ aiDeployTargets.length ? `${aiDeployTargets.length} 个目标` : "未启用" }}</span>
          </div>
          <div v-if="aiDeployTargets.length" class="ai-deploy__target-list">
            <div v-for="target in aiDeployTargets" :key="target.id || target.name || target.remote_path">
              <span>{{ target.name || target.id || "未命名目标" }}</span>
              <strong>{{ target.remote_path || "缺少远端目录" }}</strong>
              <em>{{ getAiDeployTargetActionLabel(target) }}</em>
            </div>
          </div>
          <el-empty v-else description="当前部署单元没有启用目标" :image-size="44" />
        </section>

        <section class="ai-deploy__requirement">
          <el-form label-position="top">
            <el-form-item label="部署要求">
              <el-input
                v-model="aiDeployRequirement"
                type="textarea"
                :rows="3"
                maxlength="1000"
                show-word-limit
                placeholder="例如：解压后部署，备份后覆盖远端目录，完成后重启服务并通知群里"
              />
            </el-form-item>
          </el-form>
        </section>

        <section class="ai-deploy__plan">
          <div class="ai-deploy__plan-head">
            <strong>执行流程</strong>
            <span v-if="aiDeployPlanMeta">{{ aiDeployPlanMeta }}</span>
          </div>
          <pre v-if="aiDeployPlan">{{ aiDeployPlan }}</pre>
          <el-empty
            v-else
            description="填写要求后点击生成流程"
            :image-size="52"
          />
        </section>
      </div>
      <template #footer>
        <div class="ai-deploy__footer">
          <el-button :disabled="aiDeployBusy" @click="aiDeployDialogVisible = false">
            取消
          </el-button>
          <el-button
            :loading="aiDeployPlanLoading"
            :disabled="!aiDeployArtifact || aiDeployExecuting"
            @click="generateAiDeployArtifactPlan"
          >
            生成流程
          </el-button>
          <el-button
            type="primary"
            :loading="aiDeployExecuting || deployingArtifactId === aiDeployArtifact?.id"
            :disabled="!aiDeployArtifact || !aiDeployPlan || aiDeployPlanLoading"
            @click="executeAiDeployArtifact"
          >
            执行部署
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deployLogDialogVisible"
      title="部署失败日志"
      width="680px"
      class="deploy-log-dialog"
      append-to-body
      :z-index="3200"
    >
      <div v-loading="deployLogLoading" class="deploy-log-detail">
        <template v-if="deployLogArtifact">
          <div class="deploy-log-detail__head">
            <div class="project-deploy-panel__table-main">
              <strong>{{ deployLogArtifact.artifact_name || deployLogArtifact.id }}</strong>
              <span>{{ deployLogArtifact.version || "未标记版本" }}</span>
            </div>
            <el-tag :type="getDeployStatusTagType(getDeployArtifactStatus(deployLogArtifact))">
              {{ getDeployStatusLabel(getDeployArtifactStatus(deployLogArtifact)) }}
            </el-tag>
          </div>

          <div class="deploy-log-detail__meta">
            <div>
              <span>环境</span>
              <strong>{{ deployLogArtifact.profile || "-" }}</strong>
            </div>
            <div>
              <span>部署单元</span>
              <strong>{{ deployLogArtifact.component || "-" }}</strong>
            </div>
            <div>
              <span>运行 ID</span>
              <strong>{{ deployLogRun?.id || deployLogArtifact.deployment_id || "-" }}</strong>
            </div>
            <div>
              <span>阶段</span>
              <strong>{{ deployLogRun?.stage || "-" }}</strong>
            </div>
          </div>

          <section v-if="deployLogArtifact.error" class="deploy-log-detail__section">
            <strong>错误信息</strong>
            <pre>{{ deployLogArtifact.error }}</pre>
          </section>

          <section v-if="deployLogRun?.log_excerpt" class="deploy-log-detail__section">
            <strong>日志摘要</strong>
            <pre>{{ deployLogRun.log_excerpt }}</pre>
          </section>

          <section v-if="deployLogToolResults.length" class="deploy-log-detail__section">
            <strong>Agent 工具结果</strong>
            <pre>{{ formatDeployLogJson(deployLogToolResults) }}</pre>
          </section>

          <section v-if="deployLogAgentTranscript.length" class="deploy-log-detail__section">
            <strong>Agent 执行轨迹</strong>
            <pre>{{ formatDeployLogJson(deployLogAgentTranscript) }}</pre>
          </section>

          <section v-if="deployLogMissingTargets.length" class="deploy-log-detail__section">
            <strong>缺失配置</strong>
            <div class="deploy-log-detail__missing">
              <el-tag
                v-for="target in deployLogMissingTargets"
                :key="formatDeployMissingTarget(target)"
                type="danger"
                effect="plain"
              >
                {{ formatDeployMissingTarget(target) }}
              </el-tag>
            </div>
          </section>

          <el-empty
            v-if="!hasDeployLogContent"
            description="暂无失败日志，刷新状态后再查看"
            :image-size="52"
          />
        </template>
      </div>
      <template #footer>
        <div class="deploy-log-dialog__footer">
          <el-button @click="deployLogDialogVisible = false">关闭</el-button>
          <el-button
            type="primary"
            :disabled="!deployLogText"
            @click="copyDeployLog"
          >
            复制日志
          </el-button>
        </div>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import ProjectWorkspaceBlock from "@/components/project-workspace/ProjectWorkspaceBlock.vue";
import api from "@/utils/api.js";
import {
  hasNativeDesktopBridge,
  runNativeExternalAgentOnce,
} from "@/utils/native-desktop-bridge.js";

const props = defineProps({
  projectId: {
    type: String,
    required: true,
  },
  project: {
    type: Object,
    default: () => ({}),
  },
  canManageProject: {
    type: Boolean,
    default: false,
  },
  manageBlockedMessage: {
    type: String,
    default: "仅项目创建者可编辑",
  },
});

const emit = defineEmits(["project-updated"]);

const deploySaving = ref(false);
const deployValidating = ref(false);
const deployArtifactsLoading = ref(false);
const deployRunsLoading = ref(false);
const ftpCredentialsLoading = ref(false);
const deployNotifyOptionsLoading = ref(false);
const deployNotifyResolving = ref(false);
const deployCommandGeneratingKey = ref("");
const deletingArtifactId = ref("");
const deployingArtifactId = ref("");
const deployLogArtifactId = ref("");
const deployLogDialogVisible = ref(false);
const deployLogLoading = ref(false);
const deployLogDetail = ref(null);
const aiDeployDialogVisible = ref(false);
const aiDeployArtifact = ref(null);
const aiDeployRequirement = ref("");
const aiDeployPlan = ref("");
const aiDeployPlanMeta = ref("");
const aiDeployPlanLoading = ref(false);
const aiDeployExecuting = ref(false);
const artifactUploadDialogVisible = ref(false);
const artifactUploadSubmitting = ref(false);
const artifactUploadInputRef = ref(null);
const artifactUploadDirectoryInputRef = ref(null);
const artifactUploadTreeRef = ref(null);
const artifactUploadFile = ref(null);
const artifactUploadFiles = ref([]);
const artifactUploadSelectedPaths = ref([]);
const artifactUploadSourceType = ref("file");
const artifactUploadForm = ref(createDefaultArtifactUploadForm());
const deployArtifacts = ref([]);
const deployRuns = ref([]);
const deletingRunId = ref("");
const ftpCredentials = ref([]);
const deployNotifyConnectors = ref([]);
const deployNotifyChats = ref([]);
const deployValidation = ref(null);
const deploySettingsForm = ref(createDefaultDeploySettings());
const activeDeployTab = ref("settings");
const activeProfileId = ref("prod");
const activeComponentId = ref("app");
const activeProfileObject = ref(null);
const activeComponentObject = ref(null);
const notifyTargetForm = ref(createDefaultDeployNotifyTarget());
const notifyChatName = ref("");

const deployPanelTitle = computed(() => {
  if (activeDeployTab.value === "artifacts") return "部署产物";
  if (activeDeployTab.value === "runs") return "部署运行";
  return "部署配置";
});

const settingsTabMeta = computed(() => {
  const profiles = Array.isArray(deploySettingsForm.value.profiles) ? deploySettingsForm.value.profiles : [];
  const componentCount = profiles.reduce((total, profile) => total + (profile?.components?.length || 0), 0);
  return `${profiles.length} 个档位 · ${componentCount} 个单元`;
});

const artifactsTabMeta = computed(() => {
  const total = deployArtifacts.value.length;
  const blockedCount = deployArtifacts.value.filter((row) => {
    const status = String(getDeployArtifactStatus(row) || "").trim().toLowerCase();
    return ["failed", "blocked"].includes(status);
  }).length;
  return total ? `${total} 个产物 · ${blockedCount} 个异常` : "暂无产物";
});

const runsTabMeta = computed(() => {
  const total = deployRuns.value.length;
  const blockedCount = deployRuns.value.filter((row) => {
    const status = String(row?.status || "").trim().toLowerCase();
    return ["blocked", "failed", "blocked_missing_target_config", "blocked_missing_remote_executor"].includes(status);
  }).length;
  return total ? `${total} 条运行 · ${blockedCount} 条阻塞` : "暂无记录";
});

const activeProfile = computed(() => {
  const profiles = deploySettingsForm.value.profiles || [];
  return profiles.find((profile) => profile.id === activeProfileId.value)
    || (profiles.includes(activeProfileObject.value) ? activeProfileObject.value : null);
});

const activeComponent = computed(() => {
  const components = activeProfile.value?.components || [];
  return components.find((component) => component.id === activeComponentId.value)
    || (components.includes(activeComponentObject.value) ? activeComponentObject.value : null);
});

const artifactUploadProfileOptions = computed(() =>
  (deploySettingsForm.value.profiles || [])
    .filter((profile) => profile && profile.enabled !== false)
    .map((profile) => ({
      id: String(profile.id || "").trim(),
      label: [String(profile.name || "").trim(), String(profile.id || "").trim()]
        .filter(Boolean)
        .join(" · "),
    }))
    .filter((profile) => profile.id),
);

const artifactUploadComponentOptions = computed(() => {
  const profile = getDeployProfileById(artifactUploadForm.value.profile);
  const components = Array.isArray(profile?.components) ? profile.components : [];
  return components
    .filter((component) => component && component.enabled !== false)
    .map((component) => ({
      id: String(component.id || "").trim(),
      label: [String(component.name || "").trim(), String(component.id || "").trim()]
        .filter(Boolean)
        .join(" · "),
      artifact_kind: String(component.artifact_kind || "").trim(),
    }))
    .filter((component) => component.id);
});

const aiDeployBusy = computed(() => aiDeployPlanLoading.value || aiDeployExecuting.value);

const aiDeployContext = computed(() =>
  aiDeployArtifact.value ? buildAiDeployArtifactContext(aiDeployArtifact.value) : null,
);

const aiDeployTargets = computed(() =>
  Array.isArray(aiDeployContext.value?.deploy_targets) ? aiDeployContext.value.deploy_targets : [],
);

const aiDeploySummaryItems = computed(() => {
  const context = aiDeployContext.value;
  if (!context) return [];
  return [
    {
      label: "环境",
      value: [context.deploy_profile.name, context.deploy_profile.id].filter(Boolean).join(" · ") || "-",
    },
    {
      label: "部署单元",
      value: [context.deploy_component.name, context.deploy_component.id].filter(Boolean).join(" · ") || "-",
    },
    {
      label: "应用类型",
      value: getAiDeployApplicationTypeLabel(context.deploy_component.application_type),
    },
    {
      label: "产物形态",
      value: getAiDeployStorageKindLabel(context.artifact.storage_kind, context.artifact.is_archive),
    },
    {
      label: "文件数",
      value: context.artifact.file_count ? `${context.artifact.file_count} 个` : "-",
    },
    {
      label: "大小",
      value: formatFileSize(context.artifact.size),
    },
  ];
});

const artifactUploadFileMeta = computed(() => {
  if (artifactUploadFiles.value.length) {
    return `已选 ${selectedArtifactUploadDirectoryItems.value.length}/${artifactUploadFiles.value.length} 个文件 · ${formatFileSize(totalArtifactUploadSize.value)}`;
  }
  const file = artifactUploadFile.value;
  if (!file) return "支持单文件或目录，最大 200 MB";
  return formatFileSize(file.size);
});

const totalArtifactUploadSize = computed(() =>
  selectedArtifactUploadDirectoryItems.value.reduce((sum, item) => sum + Number(item?.file?.size || 0), 0)
  + Number(artifactUploadFile.value?.size || 0),
);

const artifactUploadSelectionTitle = computed(() => {
  if (artifactUploadFiles.value.length) {
    return artifactUploadDirectoryName.value || "已选择目录";
  }
  return artifactUploadFile.value?.name || "未选择内容";
});

const artifactUploadDirectoryName = computed(() => {
  const firstPath = getArtifactUploadRelativePath(artifactUploadFiles.value[0]);
  return firstPath.split("/").filter(Boolean)[0] || "";
});

const artifactUploadDirectoryItems = computed(() =>
  artifactUploadFiles.value
    .map((file) => ({
      file,
      path: getArtifactUploadPathInsideDirectory(file),
      originalPath: getArtifactUploadRelativePath(file),
      name: file.name,
      size: file.size,
    }))
    .filter((item) => item.path),
);

const selectedArtifactUploadDirectoryItems = computed(() => {
  if (!artifactUploadDirectoryItems.value.length) return [];
  const selectedPaths = new Set(artifactUploadSelectedPaths.value);
  return artifactUploadDirectoryItems.value.filter((item) => selectedPaths.has(item.path));
});

const artifactUploadPreviewTree = computed(() =>
  buildDeployFileTree(
    artifactUploadDirectoryItems.value.map((item) => ({
      path: item.path,
      name: item.name,
      size: item.size,
    })),
  ),
);

const ftpCredentialOptions = computed(() =>
  ftpCredentials.value
    .map((item) => ({
      id: String(item?.id || "").trim(),
      label: [
        String(item?.name || item?.id || "").trim(),
        String(item?.host || "").trim()
          ? `${String(item.host).trim()}${item?.port ? `:${String(item.port).trim()}` : ""}`
          : "",
        item?.username ? `账号 ${item.username}` : "",
      ].filter(Boolean).join(" · "),
      enabled: item?.enabled !== false,
    }))
    .filter((item) => item.id && item.label),
);

const deployLogArtifact = computed(() =>
  deployLogDetail.value?.artifact ? normalizeDeployArtifact(deployLogDetail.value.artifact) : null,
);

const deployLogRun = computed(() =>
  deployLogDetail.value?.deployment ? normalizeDeployRun(deployLogDetail.value.deployment) : null,
);

const deployLogMissingTargets = computed(() => {
  const missingTargets = deployLogRun.value?.artifact_summary?.missing_targets;
  return Array.isArray(missingTargets) ? missingTargets : [];
});

const deployLogToolResults = computed(() => {
  const results = deployLogRun.value?.artifact_summary?.tool_results;
  return Array.isArray(results) ? results : [];
});

const deployLogAgentTranscript = computed(() => {
  const transcript = deployLogRun.value?.artifact_summary?.agent_transcript;
  return Array.isArray(transcript) ? transcript : [];
});

const deployLogText = computed(() => {
  const chunks = [];
  if (deployLogArtifact.value?.error) {
    chunks.push(`错误信息\n${deployLogArtifact.value.error}`);
  }
  if (deployLogRun.value?.log_excerpt) {
    chunks.push(`日志摘要\n${deployLogRun.value.log_excerpt}`);
  }
  if (deployLogToolResults.value.length) {
    chunks.push(`Agent 工具结果\n${formatDeployLogJson(deployLogToolResults.value)}`);
  }
  if (deployLogAgentTranscript.value.length) {
    chunks.push(`Agent 执行轨迹\n${formatDeployLogJson(deployLogAgentTranscript.value)}`);
  }
  if (deployLogMissingTargets.value.length) {
    chunks.push(`缺失配置\n${deployLogMissingTargets.value.map((target) => formatDeployMissingTarget(target)).join("\n")}`);
  }
  return chunks.join("\n\n").trim();
});

const hasDeployLogContent = computed(() => Boolean(deployLogText.value));

const notifyConnectorOptions = computed(() =>
  deployNotifyConnectors.value
    .filter((item) => item.platform === notifyTargetForm.value.platform)
    .map((item) => ({
      ...item,
      label: [
        String(item.name || item.id || "").trim(),
        String(item.agent_name || "").trim(),
      ].filter(Boolean).join(" · "),
    }))
    .filter((item) => item.id && item.label),
);

const notifyChatOptions = computed(() =>
  deployNotifyChats.value
    .filter((item) =>
      item.platform === notifyTargetForm.value.platform
      && item.connector_id === notifyTargetForm.value.connector_id
    )
    .map((item) => ({
      ...item,
      label: [
        String(item.chat_name || "").trim(),
        String(item.chat_id || "").trim(),
      ].filter(Boolean).join(" · "),
    }))
    .filter((item) => item.chat_id && item.label),
);

const selectedNotifyConnector = computed(() =>
  deployNotifyConnectors.value.find((item) =>
    item.platform === notifyTargetForm.value.platform
    && item.id === notifyTargetForm.value.connector_id
  ) || null,
);

function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatFileSize(value) {
  const size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let current = size;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  const precision = unitIndex === 0 || current >= 10 ? 0 : 1;
  return `${current.toFixed(precision)} ${units[unitIndex]}`;
}

function getDeployProfileById(profileId) {
  const id = String(profileId || "").trim();
  if (!id) return null;
  return (deploySettingsForm.value.profiles || []).find((profile) => String(profile.id || "").trim() === id) || null;
}

function getDeployComponentById(profileId, componentId) {
  const profile = getDeployProfileById(profileId);
  const id = String(componentId || "").trim();
  if (!profile || !id) return null;
  return (profile.components || []).find((component) => String(component.id || "").trim() === id) || null;
}

function syncArtifactUploadDefaults() {
  const profiles = deploySettingsForm.value.profiles || [];
  const preferredProfileId = getDeployProfileById(artifactUploadForm.value.profile)
    ? artifactUploadForm.value.profile
    : activeProfileId.value || profiles[0]?.id || "prod";
  artifactUploadForm.value.profile = String(preferredProfileId || "prod").trim();
  const profile = getDeployProfileById(artifactUploadForm.value.profile);
  const components = profile?.components || [];
  const activeComponentInProfile = getDeployComponentById(artifactUploadForm.value.profile, activeComponentId.value);
  const preferredComponentId = getDeployComponentById(artifactUploadForm.value.profile, artifactUploadForm.value.component)
    ? artifactUploadForm.value.component
    : activeComponentInProfile?.id || components[0]?.id || "";
  artifactUploadForm.value.component = String(preferredComponentId || "").trim();
  const component = getDeployComponentById(artifactUploadForm.value.profile, artifactUploadForm.value.component);
  artifactUploadForm.value.artifact_kind = String(
    component?.artifact_kind || profile?.artifact_kind || "source-bundle",
  ).trim() || "source-bundle";
}

function openArtifactUploadDialog() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  syncArtifactUploadDefaults();
  artifactUploadDialogVisible.value = true;
}

function resetArtifactUploadDialog() {
  artifactUploadFile.value = null;
  artifactUploadFiles.value = [];
  artifactUploadSelectedPaths.value = [];
  artifactUploadSourceType.value = "file";
  artifactUploadForm.value = createDefaultArtifactUploadForm();
  if (artifactUploadInputRef.value) {
    artifactUploadInputRef.value.value = "";
  }
  if (artifactUploadDirectoryInputRef.value) {
    artifactUploadDirectoryInputRef.value.value = "";
  }
}

function selectArtifactUploadFile() {
  artifactUploadInputRef.value?.click?.();
}

function selectArtifactUploadDirectory() {
  artifactUploadDirectoryInputRef.value?.click?.();
}

function handleArtifactUploadFileChange(event) {
  const file = event?.target?.files?.[0] || null;
  if (!file) {
    artifactUploadFile.value = null;
    return;
  }
  if (file.size > 200 * 1024 * 1024) {
    artifactUploadFile.value = null;
    if (artifactUploadInputRef.value) {
      artifactUploadInputRef.value.value = "";
    }
    ElMessage.error("文件超过 200 MB，当前上传入口不支持");
    return;
  }
  artifactUploadFile.value = file;
  artifactUploadFiles.value = [];
  artifactUploadSelectedPaths.value = [];
  artifactUploadSourceType.value = "file";
  if (artifactUploadDirectoryInputRef.value) {
    artifactUploadDirectoryInputRef.value.value = "";
  }
}

function handleArtifactUploadDirectoryChange(event) {
  const files = Array.from(event?.target?.files || []);
  if (!files.length) {
    artifactUploadFiles.value = [];
    artifactUploadSelectedPaths.value = [];
    return;
  }
  const totalSize = files.reduce((sum, file) => sum + Number(file?.size || 0), 0);
  artifactUploadFile.value = null;
  artifactUploadFiles.value = files;
  artifactUploadSelectedPaths.value = files
    .map((file) => stripArtifactUploadRootDirectory(getArtifactUploadRelativePath(file)))
    .filter(Boolean);
  artifactUploadSourceType.value = "directory";
  if (artifactUploadInputRef.value) {
    artifactUploadInputRef.value.value = "";
  }
  nextTick(() => {
    artifactUploadTreeRef.value?.setCheckedKeys?.(artifactUploadSelectedPaths.value);
  });
  if (totalSize > 200 * 1024 * 1024) {
    ElMessage.warning("目录总大小超过 200 MB，请取消部分文件后再上传");
  }
}

function handleArtifactUploadTreeCheck(_node, state) {
  const checkedKeys = Array.isArray(state?.checkedKeys) ? state.checkedKeys : [];
  const filePaths = new Set(artifactUploadDirectoryItems.value.map((item) => item.path));
  artifactUploadSelectedPaths.value = checkedKeys.filter((key) => filePaths.has(String(key || "")));
}

function selectAllArtifactUploadFiles() {
  artifactUploadSelectedPaths.value = artifactUploadDirectoryItems.value.map((item) => item.path);
  artifactUploadTreeRef.value?.setCheckedKeys?.(artifactUploadSelectedPaths.value);
}

function clearArtifactUploadFiles() {
  artifactUploadSelectedPaths.value = [];
  artifactUploadTreeRef.value?.setCheckedKeys?.([]);
}

function handleArtifactUploadProfileChange() {
  const profile = getDeployProfileById(artifactUploadForm.value.profile);
  const components = profile?.components || [];
  artifactUploadForm.value.component = String(components[0]?.id || "").trim();
  const component = getDeployComponentById(artifactUploadForm.value.profile, artifactUploadForm.value.component);
  artifactUploadForm.value.artifact_kind = String(
    component?.artifact_kind || profile?.artifact_kind || "source-bundle",
  ).trim() || "source-bundle";
}

function handleArtifactUploadComponentChange() {
  const component = getDeployComponentById(artifactUploadForm.value.profile, artifactUploadForm.value.component);
  const profile = getDeployProfileById(artifactUploadForm.value.profile);
  artifactUploadForm.value.artifact_kind = String(
    component?.artifact_kind || profile?.artifact_kind || "source-bundle",
  ).trim() || "source-bundle";
}

function encodeTarHeaderText(view, offset, length, value) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(String(value || ""));
  view.set(bytes.slice(0, Math.max(0, length)), offset);
}

function encodeTarHeaderOctal(view, offset, length, value) {
  const text = Math.max(0, Number(value || 0))
    .toString(8)
    .padStart(Math.max(0, length - 1), "0")
    .slice(-Math.max(0, length - 1));
  encodeTarHeaderText(view, offset, length, `${text}\0`);
}

function splitTarPath(path) {
  const cleanPath = String(path || "").replace(/\\/g, "/").replace(/^\/+/, "").trim();
  if (cleanPath.length <= 100) {
    return { name: cleanPath, prefix: "" };
  }
  const parts = cleanPath.split("/");
  const name = parts.pop() || "";
  const prefix = parts.join("/");
  if (name.length <= 100 && prefix.length <= 155) {
    return { name, prefix };
  }
  throw new Error(`文件路径过长，无法打包：${cleanPath}`);
}

function createTarHeader({ path, size, mtime }) {
  const header = new Uint8Array(512);
  const { name, prefix } = splitTarPath(path);
  encodeTarHeaderText(header, 0, 100, name);
  encodeTarHeaderOctal(header, 100, 8, 0o644);
  encodeTarHeaderOctal(header, 108, 8, 0);
  encodeTarHeaderOctal(header, 116, 8, 0);
  encodeTarHeaderOctal(header, 124, 12, size);
  encodeTarHeaderOctal(header, 136, 12, Math.floor(Number(mtime || Date.now()) / 1000));
  header.fill(32, 148, 156);
  header[156] = "0".charCodeAt(0);
  encodeTarHeaderText(header, 257, 6, "ustar");
  encodeTarHeaderText(header, 263, 2, "00");
  encodeTarHeaderText(header, 345, 155, prefix);
  const checksum = header.reduce((sum, byte) => sum + byte, 0);
  const checksumText = checksum.toString(8).padStart(6, "0").slice(-6);
  encodeTarHeaderText(header, 148, 8, `${checksumText}\0 `);
  return header;
}

async function buildArtifactUploadDirectoryTar(selectedDirectoryItems) {
  const chunks = [];
  selectedDirectoryItems.forEach((item) => {
    const path = String(item?.path || item?.name || "").replace(/\\/g, "/").replace(/^\/+/, "").trim();
    if (!path) return;
    chunks.push(createTarHeader({
      path,
      size: Number(item?.file?.size || 0),
      mtime: Number(item?.file?.lastModified || Date.now()),
    }));
    chunks.push(item.file);
    const paddingSize = (512 - (Number(item?.file?.size || 0) % 512)) % 512;
    if (paddingSize > 0) {
      chunks.push(new Uint8Array(paddingSize));
    }
  });
  chunks.push(new Uint8Array(1024));
  return new Blob(chunks, { type: "application/x-tar" });
}

async function submitArtifactUpload() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!props.projectId) return;
  const isDirectoryUpload = artifactUploadSourceType.value === "directory" && artifactUploadFiles.value.length > 0;
  const selectedDirectoryItems = isDirectoryUpload ? selectedArtifactUploadDirectoryItems.value : [];
  const selectedFiles = isDirectoryUpload
    ? selectedDirectoryItems.map((item) => item.file)
    : [artifactUploadFile.value].filter(Boolean);
  if (!selectedFiles.length) {
    ElMessage.warning(isDirectoryUpload ? "请选择要上传的目录内容" : "请选择要上传的文件或目录");
    return;
  }
  const selectedSize = selectedFiles.reduce((sum, item) => sum + Number(item?.size || 0), 0);
  if (selectedSize > 200 * 1024 * 1024) {
    ElMessage.error("已选内容超过 200 MB，请取消部分文件后再上传");
    return;
  }
  const profile = getDeployProfileById(artifactUploadForm.value.profile);
  const component = getDeployComponentById(artifactUploadForm.value.profile, artifactUploadForm.value.component);
  if (!profile) {
    ElMessage.warning("请选择部署环境");
    return;
  }
  if (!component) {
    ElMessage.warning("请选择部署单元");
    return;
  }
  artifactUploadSubmitting.value = true;
  try {
    const formData = new FormData();
    const manifest = isDirectoryUpload
      ? {
          source_type: "directory-tar",
          file_count: selectedFiles.length,
          root_directory: artifactUploadDirectoryName.value,
          file_entries: selectedDirectoryItems.map((item) => ({
            path: item.path,
            original_path: item.originalPath,
            name: item.name,
            size: item.size,
          })),
        }
      : {};
    if (isDirectoryUpload) {
      const archive = await buildArtifactUploadDirectoryTar(selectedDirectoryItems);
      formData.append("file", archive, `${artifactUploadDirectoryName.value || "directory-upload"}.tar`);
    } else {
      formData.append("file", selectedFiles[0], selectedFiles[0].name);
    }
    formData.append("profile", artifactUploadForm.value.profile);
    formData.append("component", artifactUploadForm.value.component);
    formData.append("artifact_name", isDirectoryUpload ? artifactUploadDirectoryName.value || "directory-upload" : selectedFiles[0].name);
    formData.append("artifact_kind", artifactUploadForm.value.artifact_kind || "source-bundle");
    formData.append("version", artifactUploadForm.value.version || "");
    formData.append("size", String(selectedSize));
    formData.append("manifest_json", JSON.stringify(manifest));
    const data = await api.post(`/projects/${props.projectId}/deploy-artifacts/upload`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    const status = String(data?.status || "").trim();
    if (status === "blocked") {
      ElMessage.warning("部署产物已上传，但状态异常");
    } else {
      ElMessage.success("部署产物已上传");
    }
    artifactUploadDialogVisible.value = false;
    await Promise.all([fetchDeployArtifacts(), fetchDeployRuns()]);
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "上传部署产物失败");
  } finally {
    artifactUploadSubmitting.value = false;
  }
}

function safeId(value, fallback) {
  return String(value || "").trim().replace(/\s+/g, "-") || fallback;
}

function createDefaultDeployNotifyTarget() {
  return {
    platform: "feishu",
    connector_id: "",
    chat_id: "",
    chat_name: "",
    resolve_identity: "bot",
  };
}

function createDefaultArtifactUploadForm() {
  return {
    profile: "prod",
    component: "",
    artifact_kind: "source-bundle",
    version: "",
  };
}

function createDefaultDeployTarget(index = 1) {
  return {
    id: `target-${index}`,
    name: `服务器 ${index}`,
    enabled: true,
    transport_mode: "ftp",
    ftp_credential_id: "",
    remote_path: "",
    deploy_command: "",
    health_check: {},
  };
}

function createDefaultDeployComponent() {
  return {
    id: "app",
    name: "默认服务",
    enabled: true,
    artifact_kind: "source-bundle",
    package: {},
    safety: {
      auto_deploy_on_artifact_update: false,
      dry_run_default: false,
    },
    notify: {
      enabled: false,
      targets: [],
    },
    targets: [createDefaultDeployTarget()],
  };
}

function createDefaultDeployProfile() {
  return {
    id: "prod",
    name: "生产环境",
    environment: "prod",
    artifact_kind: "source-bundle",
    enabled: true,
    package: {},
    transport: {},
    remote_executor: {},
    notify: { enabled: false, targets: [] },
    safety: { auto_deploy_on_artifact_update: false, dry_run_default: false },
    components: [createDefaultDeployComponent()],
  };
}

function createDefaultDeploySettings() {
  return {
    version: "2",
    enabled: false,
    default_profile: "prod",
    profiles: [createDefaultDeployProfile()],
  };
}

function normalizeDeployNotifyTarget(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    ...createDefaultDeployNotifyTarget(),
    ...source,
    platform: String(source.platform || "feishu").trim(),
    connector_id: String(source.connector_id || "").trim(),
    chat_id: String(source.chat_id || "").trim(),
    chat_name: String(source.chat_name || "").trim(),
    resolve_identity: String(source.resolve_identity || "bot").trim(),
  };
}

function normalizeDeployTarget(item, index = 0) {
  const source = item && typeof item === "object" ? item : {};
  const transport = source.transport && typeof source.transport === "object" ? source.transport : {};
  const remoteExecutor = source.remote_executor && typeof source.remote_executor === "object" ? source.remote_executor : {};
  return {
    ...createDefaultDeployTarget(index + 1),
    ...source,
    id: safeId(source.id, `target-${index + 1}`),
    name: String(source.name || source.id || `服务器 ${index + 1}`).trim(),
    enabled: true,
    transport_mode: "ftp",
    ftp_credential_id: String(source.ftp_credential_id || source.ftpCredentialId || transport.ftp_credential_id || "").trim(),
    remote_path: String(source.remote_path || transport.remote_path || "").trim(),
    deploy_command: String(source.deploy_command || remoteExecutor.deploy_command || "").trim(),
    health_check: source.health_check && typeof source.health_check === "object" ? { ...source.health_check } : {},
  };
}

function normalizeDeployComponent(item, index = 0, legacyProfile = null) {
  const source = item && typeof item === "object" ? item : {};
  const legacy = legacyProfile && typeof legacyProfile === "object" ? legacyProfile : {};
  const rawTargets = Array.isArray(source.targets) ? source.targets : [];
  const targets = rawTargets.length
    ? rawTargets.map((target, targetIndex) => normalizeDeployTarget(target, targetIndex))
    : [normalizeDeployTarget({
        id: "primary",
        name: "主服务器",
        transport: legacy.transport,
        remote_executor: legacy.remote_executor,
      })];
  const notify = source.notify && typeof source.notify === "object" ? source.notify : legacy.notify || {};
  const safety = source.safety && typeof source.safety === "object" ? source.safety : legacy.safety || {};
  return {
    ...createDefaultDeployComponent(),
    ...source,
    id: safeId(source.id, index === 0 ? "app" : `component-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "默认服务" : `部署单元 ${index + 1}`)).trim(),
    enabled: true,
    artifact_kind: String(source.artifact_kind || legacy.artifact_kind || "source-bundle").trim(),
    package: source.package && typeof source.package === "object" ? { ...source.package } : {},
    safety: {
      ...createDefaultDeployComponent().safety,
      ...safety,
      auto_deploy_on_artifact_update: Boolean(safety.auto_deploy_on_artifact_update),
      dry_run_default: Boolean(safety.dry_run_default),
    },
    notify: {
      enabled: Boolean(notify.enabled),
      targets: Array.isArray(notify.targets)
        ? notify.targets.map((target) => normalizeDeployNotifyTarget(target))
        : [],
    },
    targets,
  };
}

function normalizeDeployProfile(item, index = 0) {
  const source = item && typeof item === "object" ? item : {};
  const rawComponents = Array.isArray(source.components) ? source.components : [];
  const components = rawComponents.length
    ? rawComponents.map((component, componentIndex) => normalizeDeployComponent(component, componentIndex))
    : [normalizeDeployComponent({}, 0, source)];
  return {
    ...createDefaultDeployProfile(),
    ...source,
    id: safeId(source.id, index === 0 ? "prod" : `profile-${index + 1}`),
    name: String(source.name || source.id || (index === 0 ? "生产环境" : `环境 ${index + 1}`)).trim(),
    environment: String(source.environment || source.id || (index === 0 ? "prod" : `env-${index + 1}`)).trim(),
    enabled: source.enabled !== false,
    components,
  };
}

function normalizeDeploySettings(item) {
  const fallback = createDefaultDeploySettings();
  const source = item && typeof item === "object" ? item : {};
  const profiles = Array.isArray(source.profiles)
    ? source.profiles.map((profile, index) => normalizeDeployProfile(profile, index))
    : [];
  const nextProfiles = profiles.length ? profiles : [createDefaultDeployProfile()];
  const defaultProfile = String(source.default_profile || "").trim() || nextProfiles[0].id || "prod";
  return {
    ...fallback,
    ...source,
    version: "2",
    enabled: Boolean(source.enabled),
    default_profile: defaultProfile,
    profiles: nextProfiles,
  };
}

function syncDeployFormsFromSettings(rawSettings) {
  const settings = normalizeDeploySettings(rawSettings);
  deploySettingsForm.value = settings;
  activeProfileId.value = settings.profiles.some((profile) => profile.id === activeProfileId.value)
    ? activeProfileId.value
    : settings.default_profile || settings.profiles[0].id;
  const profile = activeProfile.value || settings.profiles[0];
  activeProfileObject.value = profile;
  activeComponentId.value = profile.components.some((component) => component.id === activeComponentId.value)
    ? activeComponentId.value
    : profile.components[0]?.id || "app";
  activeComponentObject.value = profile.components.find((component) => component.id === activeComponentId.value)
    || profile.components[0]
    || null;
  syncNotifyTargetForm();
}

function syncNotifyTargetForm() {
  notifyTargetForm.value = normalizeDeployNotifyTarget(activeComponent.value?.notify?.targets?.[0]);
  notifyChatName.value = notifyTargetForm.value.chat_name || getNotifyChatName(notifyTargetForm.value.chat_id);
}

function applyNotifyTargetToActiveComponent() {
  if (!activeComponent.value) return;
  const target = normalizeDeployNotifyTarget(notifyTargetForm.value);
  activeComponent.value.notify.targets =
    activeComponent.value.notify.enabled && target.platform && (target.connector_id || target.chat_id)
      ? [target]
      : [];
}

function normalizeDeployNotifyConnector(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    id: String(source.id || "").trim(),
    platform: String(source.platform || "").trim(),
    name: String(source.name || source.id || "").trim(),
    agent_name: String(source.agent_name || "").trim(),
    description: String(source.description || "").trim(),
    reply_identity: String(source.reply_identity || "bot").trim(),
    project_id: String(source.project_id || "").trim(),
  };
}

function normalizeDeployNotifyChat(item) {
  const source = item && typeof item === "object" ? item : {};
  return {
    platform: String(source.platform || "").trim(),
    connector_id: String(source.connector_id || "").trim(),
    chat_id: String(source.chat_id || "").trim(),
    chat_name: String(source.chat_name || "").trim(),
    session_id: String(source.session_id || "").trim(),
    source_type: String(source.source_type || "").trim(),
    chat_type: String(source.chat_type || "").trim(),
    scanned_at: String(source.scanned_at || "").trim(),
  };
}

function getNotifyChatName(chatId) {
  const normalized = String(chatId || "").trim();
  if (!normalized) return "";
  const match = deployNotifyChats.value.find((item) =>
    item.platform === notifyTargetForm.value.platform
    && item.connector_id === notifyTargetForm.value.connector_id
    && item.chat_id === normalized
  );
  return match?.chat_name || "";
}

function upsertNotifyChat(chat) {
  const item = normalizeDeployNotifyChat(chat);
  if (!item.platform || !item.connector_id || !item.chat_id) return;
  const index = deployNotifyChats.value.findIndex((current) =>
    current.platform === item.platform
    && current.connector_id === item.connector_id
    && current.chat_id === item.chat_id
  );
  if (index >= 0) {
    deployNotifyChats.value[index] = { ...deployNotifyChats.value[index], ...item };
  } else {
    deployNotifyChats.value.unshift(item);
  }
}

function onNotifyPlatformChange() {
  notifyTargetForm.value.connector_id = "";
  notifyTargetForm.value.chat_id = "";
  notifyTargetForm.value.chat_name = "";
  notifyTargetForm.value.resolve_identity = "bot";
  notifyChatName.value = "";
  applyNotifyTargetToActiveComponent();
}

function onNotifyConnectorChange() {
  const connector = selectedNotifyConnector.value;
  notifyTargetForm.value.chat_id = "";
  notifyTargetForm.value.chat_name = "";
  notifyTargetForm.value.resolve_identity = connector?.reply_identity || "bot";
  notifyChatName.value = "";
  applyNotifyTargetToActiveComponent();
}

function onNotifyChatChange(value) {
  const chatName = getNotifyChatName(value);
  notifyTargetForm.value.chat_name = chatName;
  notifyChatName.value = chatName;
  applyNotifyTargetToActiveComponent();
}

function buildDeploySettingsPayload() {
  applyNotifyTargetToActiveComponent();
  return normalizeDeploySettings(deploySettingsForm.value);
}

function firstDeployValidationMessage() {
  const issue = Array.isArray(deployValidation.value?.issues) ? deployValidation.value.issues[0] : null;
  return issue?.message || "部署配置未通过校验，请补齐标出的字段";
}

function selectDeployProfile(profileId) {
  applyNotifyTargetToActiveComponent();
  const profile = deploySettingsForm.value.profiles.find((item) => item.id === profileId);
  if (!profile) return;
  activeProfileId.value = profile.id;
  activeProfileObject.value = profile;
  activeComponentObject.value = profile.components?.[0] || null;
  activeComponentId.value = activeComponentObject.value?.id || "app";
  syncNotifyTargetForm();
}

function selectDeployComponent(componentId) {
  applyNotifyTargetToActiveComponent();
  const component = activeProfile.value?.components?.find((item) => item.id === componentId);
  if (!component) return;
  activeComponentId.value = component.id;
  activeComponentObject.value = component;
  syncNotifyTargetForm();
}

function addDeployProfile() {
  const index = deploySettingsForm.value.profiles.length + 1;
  const profile = normalizeDeployProfile({ id: `env-${index}`, name: `环境 ${index}`, environment: `env-${index}` }, index);
  deploySettingsForm.value.profiles.push(profile);
  selectDeployProfile(profile.id);
}

function removeDeployProfile(profileId) {
  if (deploySettingsForm.value.profiles.length <= 1) return;
  deploySettingsForm.value.profiles = deploySettingsForm.value.profiles.filter((profile) => profile.id !== profileId);
  if (deploySettingsForm.value.default_profile === profileId) {
    deploySettingsForm.value.default_profile = deploySettingsForm.value.profiles[0]?.id || "prod";
  }
  selectDeployProfile(deploySettingsForm.value.default_profile);
}

function addDeployComponent() {
  if (!activeProfile.value) return;
  const index = activeProfile.value.components.length + 1;
  const component = normalizeDeployComponent({ id: `component-${index}`, name: `部署单元 ${index}` }, index);
  activeProfile.value.components.push(component);
  selectDeployComponent(component.id);
}

function removeDeployComponent(componentId) {
  if (!activeProfile.value || activeProfile.value.components.length <= 1) return;
  activeProfile.value.components = activeProfile.value.components.filter((component) => component.id !== componentId);
  selectDeployComponent(activeProfile.value.components[0]?.id || "app");
}

function addDeployTarget() {
  if (!activeComponent.value) return;
  activeComponent.value.targets.push(createDefaultDeployTarget(activeComponent.value.targets.length + 1));
}

function removeDeployTarget(index) {
  if (!activeComponent.value || activeComponent.value.targets.length <= 1) return;
  activeComponent.value.targets.splice(index, 1);
}

function deployTargetRowKey(row, index = 0) {
  return [
    String(activeProfileId.value || "").trim(),
    String(activeComponentId.value || "").trim(),
    String(row?.id || index).trim(),
  ].join(":");
}

function cleanGeneratedDeployCommand(content) {
  let text = String(content || "").trim();
  if (!text) return "";
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object") {
      text = String(parsed.deploy_command || parsed.command || "").trim();
    }
  } catch {
    // Continue with plain text output.
  }
  if (text.includes("```")) {
    const match = text.match(/```(?:bash|sh|shell|json)?\s*([\s\S]*?)```/i);
    if (match) text = String(match[1] || "").trim();
    if (text.startsWith("{")) {
      try {
        const parsed = JSON.parse(text);
        text = String(parsed?.deploy_command || parsed?.command || text).trim();
      } catch {
        // Continue with fenced shell output.
      }
    }
  }
  return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim().slice(0, 1000).trim();
}

function buildDeployCommandGenerationPrompt({ profile, component, target, artifactKind, artifactPath }) {
  const payload = {
    project: {
      id: props.projectId,
      name: String(props.project?.name || "").trim(),
      description: String(props.project?.description || "").trim(),
    },
    deploy_profile: {
      id: String(profile?.id || "").trim(),
      name: String(profile?.name || "").trim(),
      environment: String(profile?.environment || "").trim(),
    },
    deploy_component: {
      id: String(component?.id || "").trim(),
      name: String(component?.name || "").trim(),
      artifact_kind: String(component?.artifact_kind || "").trim(),
      package: component?.package && typeof component.package === "object" ? component.package : {},
      auto_deploy_on_artifact_update: Boolean(component?.safety?.auto_deploy_on_artifact_update),
    },
    deploy_target: {
      id: String(target?.id || "").trim(),
      name: String(target?.name || "").trim(),
      transport_mode: "ftp",
      remote_path: String(target?.remote_path || "").trim(),
      existing_deploy_command: String(target?.deploy_command || "").trim(),
    },
    artifact: {
      artifact_path: String(artifactPath || "").trim(),
      artifact_kind: String(artifactKind || "source-bundle").trim() || "source-bundle",
    },
  };
  return [
    "你是谨慎的部署工程师。请基于输入信息生成一段适合保存到部署配置的 Linux shell 部署命令。",
    "命令将在系统把产物上传到目标 remote_path 后执行。只生成幂等、可重复执行、失败即停止的命令。",
    "约束：",
    "- 当前只支持 FTP 上传，服务器连接和密码已由系统全局 FTP 账户管理，命令里不要包含账号、密码、token、密钥。",
    "- 只能依据本次输入里的部署配置、目标路径和产物信息生成命令；不要扫描、读取或引用历史发布配置。",
    "- 如果无法确定具体重启命令，生成保守命令：校验目录、解压/同步产物、输出下一步提示，不要编造 systemctl 服务名。",
    "- 最终 deploy_command 不超过 1000 字符。",
    "",
    "只返回 JSON，不要输出 Markdown 或解释：{\"deploy_command\":\"...\"}",
    "",
    `输入：\n${JSON.stringify(payload, null, 2)}`,
  ].join("\n");
}

async function generateDeployCommandViaExternalAgent(row) {
  const chatSettings = props.project?.chat_settings && typeof props.project.chat_settings === "object"
    ? props.project.chat_settings
    : {};
  if (!hasNativeDesktopBridge()) {
    throw new Error("外部 Agent 需要在桌面端 Runner 中生成部署命令");
  }
  const workspacePath = String(
    chatSettings.connector_workspace_path
      || props.project?.workspace_path
      || "",
  ).trim();
  if (!workspacePath) {
    throw new Error("外部 Agent 缺少项目工作区路径，请先在项目聊天设置中配置本机工作区");
  }
  const artifactKind = activeComponent.value?.artifact_kind || activeProfile.value?.artifact_kind || "source-bundle";
  const artifactPath = String(
    activeComponent.value?.package?.artifact_path || activeComponent.value?.package?.output_path || "",
  ).trim();
  const result = await runNativeExternalAgentOnce({
    agentType: String(chatSettings.external_agent_type || "codex_cli").trim() || "codex_cli",
    workspacePath,
    prompt: buildDeployCommandGenerationPrompt({
      profile: activeProfile.value,
      component: activeComponent.value,
      target: row,
      artifactKind,
      artifactPath,
    }),
    timeoutMs: 120000,
  });
  const command = cleanGeneratedDeployCommand(
    result?.finalOutput || result?.final_output || result?.stdout || result?.output || "",
  );
  if (!command) {
    throw new Error("外部 Agent 没有返回可用部署命令");
  }
  return command;
}

async function generateDeployCommand(row, index = 0) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!props.projectId || !activeProfile.value || !activeComponent.value || !row) return;
  const rowKey = deployTargetRowKey(row, index);
  deployCommandGeneratingKey.value = rowKey;
  try {
    const chatMode = String(props.project?.chat_settings?.chat_mode || "system").trim().toLowerCase();
    if (chatMode === "external_agent") {
      row.deploy_command = await generateDeployCommandViaExternalAgent(row);
      ElMessage.success("部署命令已由外部 Agent 生成，保存配置后后续部署会直接复用");
      return;
    }
    const data = await api.post(`/projects/${props.projectId}/deploy-command/generate`, {
      profile: {
        id: activeProfile.value.id,
        name: activeProfile.value.name,
        environment: activeProfile.value.environment,
      },
      component: {
        id: activeComponent.value.id,
        name: activeComponent.value.name,
        artifact_kind: activeComponent.value.artifact_kind,
        package: activeComponent.value.package || {},
        safety: activeComponent.value.safety || {},
      },
      target: {
        id: row.id,
        name: row.name,
        remote_path: row.remote_path,
        deploy_command: row.deploy_command,
      },
      artifact_kind: activeComponent.value.artifact_kind || activeProfile.value.artifact_kind || "source-bundle",
      artifact_path: String(
        activeComponent.value.package?.artifact_path || activeComponent.value.package?.output_path || "",
      ).trim(),
    });
    row.deploy_command = String(data?.deploy_command || "").trim();
    ElMessage.success("部署命令已生成，保存配置后后续部署会直接复用");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "AI 生成部署命令失败");
  } finally {
    deployCommandGeneratingKey.value = "";
  }
}

function normalizeActiveProfileId() {
  const profile = activeProfile.value;
  if (!profile) return;
  const wasDefault = deploySettingsForm.value.default_profile === activeProfileId.value;
  profile.id = safeId(profile.id, "prod");
  activeProfileId.value = profile.id;
  activeProfileObject.value = profile;
  if (wasDefault || !deploySettingsForm.value.default_profile) {
    deploySettingsForm.value.default_profile = profile.id;
  }
}

function normalizeActiveComponentId() {
  const component = activeComponent.value;
  if (!component) return;
  component.id = safeId(component.id, "app");
  activeComponentId.value = component.id;
  activeComponentObject.value = component;
}

function getArtifactUploadRelativePath(file) {
  return String(file?.webkitRelativePath || file?.relativePath || file?.name || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .trim();
}

function stripArtifactUploadRootDirectory(path) {
  const parts = String(path || "").split("/").map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1) {
    return parts[0] || "";
  }
  const rootName = artifactUploadDirectoryName.value;
  if (rootName && parts[0] === rootName) {
    return parts.slice(1).join("/");
  }
  return parts.join("/");
}

function getArtifactUploadPathInsideDirectory(file) {
  return stripArtifactUploadRootDirectory(getArtifactUploadRelativePath(file));
}

function buildDeployFileTree(entries) {
  const root = [];
  const rootMap = new Map();
  entries.forEach((entry) => {
    const path = String(entry?.path || entry?.name || "").replace(/\\/g, "/").replace(/^\/+/, "").trim();
    const parts = path.split("/").map((part) => part.trim()).filter(Boolean);
    if (!parts.length) return;
    let children = root;
    let map = rootMap;
    parts.forEach((part, index) => {
      const nodePath = parts.slice(0, index + 1).join("/");
      const isFile = index === parts.length - 1;
      let node = map.get(part);
      if (!node) {
        node = {
          name: part,
          path: nodePath,
          type: isFile ? "file" : "directory",
          size: isFile ? Number(entry?.size || 0) : 0,
          children: [],
          _childMap: new Map(),
        };
        map.set(part, node);
        children.push(node);
      }
      children = node.children;
      map = node._childMap;
    });
  });
  const clean = (nodes) => nodes
    .sort((a, b) => Number(a.type === "file") - Number(b.type === "file") || a.name.localeCompare(b.name))
    .map((node) => {
      const children = clean(node.children || []);
      return {
        name: node.name,
        path: node.path,
        type: node.type,
        size: node.size,
        children,
      };
    });
  return clean(root);
}

function getDeployArtifactSubtitle(row) {
  const version = row.version || "未标记版本";
  if (isDeployArchiveArtifact(row)) {
    const fileCount = Number(row?.file_count || 0);
    return fileCount ? `${version} · 压缩包 · ${fileCount} 个文件` : `${version} · 压缩包`;
  }
  if (row.storage_kind === "directory") {
    return `${version} · 目录 · ${row.file_count} 个文件`;
  }
  return version;
}

function normalizeDeployArtifact(item) {
  const manifest = item?.manifest && typeof item.manifest === "object" ? item.manifest : {};
  const fileTree = Array.isArray(item?.file_tree)
    ? item.file_tree
    : (Array.isArray(manifest.file_tree) ? manifest.file_tree : []);
  const deployment = item?.deployment && typeof item.deployment === "object"
    ? normalizeDeployRun(item.deployment)
    : null;
  return {
    id: String(item?.id || "").trim(),
    project_id: String(item?.project_id || "").trim(),
    profile: String(item?.profile || "").trim(),
    component: String(item?.component || "").trim(),
    artifact_name: String(item?.artifact_name || "").trim(),
    artifact_kind: String(item?.artifact_kind || "").trim(),
    version: String(item?.version || "").trim(),
    checksum: String(item?.checksum || "").trim(),
    size: Number(item?.size || 0),
    status: String(item?.status || "").trim(),
    error: String(item?.error || "").trim(),
    deployment_id: String(item?.deployment_id || "").trim(),
    storage_kind: String(item?.storage_kind || manifest.source_type || "file").trim(),
    manifest,
    deployment,
    file_tree: fileTree,
    file_count: Number(manifest.file_count || countDeployFileTreeFiles(fileTree)),
    uploaded_at: String(item?.uploaded_at || "").trim(),
  };
}

function getDeployArtifactStatus(row) {
  const deploymentStatus = String(row?.deployment?.status || "").trim().toLowerCase();
  if (deploymentStatus === "success") return "deployed";
  if (deploymentStatus === "queued") return "deploy_queued";
  if (deploymentStatus) return deploymentStatus;
  return String(row?.status || "").trim();
}

function inferDeployApplicationType({ artifact, component }) {
  const haystack = [
    artifact?.artifact_kind,
    artifact?.artifact_name,
    artifact?.component,
    component?.artifact_kind,
    component?.id,
    component?.name,
  ]
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean)
    .join(" ");
  if (/(frontend|front-end|web|dist|h5|vue|react|next|nuxt|static|spa)/i.test(haystack)) {
    return "frontend";
  }
  if (/(backend|back-end|api|server|service|java|spring|node|nestjs|python|fastapi|django|go|gin)/i.test(haystack)) {
    return "backend";
  }
  if (/(fullstack|full-stack|monorepo|source-bundle|source)/i.test(haystack)) {
    return "fullstack_or_source_bundle";
  }
  return "unknown";
}

function isDeployArchiveArtifact(row) {
  const name = String(row?.artifact_name || "").trim().toLowerCase();
  return /\.(zip|tar|tgz|tar\.gz|tar\.bz2|tar\.xz)$/.test(name);
}

function buildAiDeployArtifactContext(row) {
  const profile = getDeployProfileById(row?.profile);
  const component = getDeployComponentById(row?.profile, row?.component);
  const targets = Array.isArray(component?.targets)
    ? component.targets
        .filter((target) => target && target.enabled !== false)
        .map((target) => ({
          id: String(target.id || "").trim(),
          name: String(target.name || "").trim(),
          remote_path: String(target.remote_path || "").trim(),
          has_deploy_command: Boolean(String(target.deploy_command || "").trim()),
          remote_command_mode: String(target.remote_command_mode || target.remote_executor?.mode || "").trim(),
        }))
    : [];
  return {
    source: "deploy_artifact_panel",
    intent: "ai_deploy_uploaded_artifact",
    project: {
      id: props.projectId,
      name: String(props.project?.name || "").trim(),
    },
    deploy_profile: {
      id: String(profile?.id || row?.profile || "").trim(),
      name: String(profile?.name || "").trim(),
      environment: String(profile?.environment || "").trim(),
    },
    deploy_component: {
      id: String(component?.id || row?.component || "").trim(),
      name: String(component?.name || "").trim(),
      artifact_kind: String(component?.artifact_kind || row?.artifact_kind || "").trim(),
      application_type: inferDeployApplicationType({ artifact: row, component }),
      auto_deploy_on_artifact_update: Boolean(component?.safety?.auto_deploy_on_artifact_update),
    },
    artifact: {
      id: String(row?.id || "").trim(),
      name: String(row?.artifact_name || "").trim(),
      artifact_kind: String(row?.artifact_kind || component?.artifact_kind || "").trim(),
      version: String(row?.version || "").trim(),
      status: getDeployArtifactStatus(row),
      storage_kind: String(row?.storage_kind || "").trim() || "file",
      is_archive: isDeployArchiveArtifact(row),
      file_count: Number(row?.file_count || 0),
      size: Number(row?.size || 0),
      checksum: String(row?.checksum || "").trim(),
      uploaded_at: String(row?.uploaded_at || "").trim(),
    },
    deployment: row?.deployment
      ? {
          id: String(row.deployment.id || "").trim(),
          status: String(row.deployment.status || "").trim(),
          stage: String(row.deployment.stage || "").trim(),
          updated_at: String(row.deployment.updated_at || "").trim(),
        }
      : null,
    deploy_targets: targets,
  };
}

function getAiDeployApplicationTypeLabel(value) {
  const normalized = String(value || "").trim();
  if (normalized === "frontend") return "前端";
  if (normalized === "backend") return "后端";
  if (normalized === "fullstack_or_source_bundle") return "源码包";
  return "未识别类型";
}

function getAiDeployStorageKindLabel(storageKind, isArchive) {
  const normalized = String(storageKind || "").trim();
  if (isArchive) return "压缩包产物";
  if (normalized === "directory") return "目录产物";
  if (normalized === "file") return "文件产物";
  return normalized || "未识别存储";
}

function resolveAiDeployArchiveUploadPolicy(context, requirement = "") {
  const requirementText = String(requirement || "").trim();
  if (/(不解压|不要解压|无需解压|不自动解压|不默认解压|不会(?:自动|默认|进行)?解压|没有明确解压|未明确解压|没有要求解压|未要求解压|原样上传|上传压缩包|保留压缩包|keep archive|upload archive|no extract|without extract)/i.test(requirementText)) {
    return "upload_archive";
  }
  if (/(解压|拆包|unzip|untar|extract)/i.test(requirementText)) {
    return "extract_before_upload";
  }
  return "auto";
}

function shouldAiDeployExtractBeforeUpload(context, requirement = "") {
  return resolveAiDeployArchiveUploadPolicy(context, requirement) === "extract_before_upload";
}

function getAiDeployTargetActionLabel(target) {
  const context = aiDeployContext.value;
  const policy = resolveAiDeployArchiveUploadPolicy(context, aiDeployRequirement.value);
  const storageKind = String(context?.artifact?.storage_kind || "").trim();
  let uploadLabel = "上传产物";
  if (policy === "extract_before_upload") {
    uploadLabel = "解压后上传";
  } else if (policy === "upload_archive") {
    uploadLabel = "原样上传压缩包";
  } else if (context?.artifact?.is_archive) {
    uploadLabel = "默认原样上传压缩包";
  } else if (storageKind === "directory") {
    uploadLabel = "目录递归上传";
  }
  return target?.has_deploy_command ? `${uploadLabel} + 远端命令` : `${uploadLabel}，无远端命令`;
}

function buildLocalAiDeployArtifactPlan(row, requirement = "") {
  const context = buildAiDeployArtifactContext(row);
  const targets = Array.isArray(context.deploy_targets) ? context.deploy_targets : [];
  const hasCommand = targets.some((target) => target.has_deploy_command);
  const missingRemotePath = targets.filter((target) => !target.remote_path).length;
  const archivePolicy = resolveAiDeployArchiveUploadPolicy(context, requirement);
  const extractBeforeUpload = archivePolicy === "extract_before_upload";
  const requirementText = String(requirement || "").trim();
  const wantsOriginalArchiveUpload = /(压缩包(?:也|都|一起|同时)?上传|原(?:始)?压缩包(?:也|都|一起|同时)?上传|跟\s*压缩包\s*都上传|同时上传.*压缩包)/i.test(requirementText);
  const extractPath = requirementText.match(/(?:解压到|解压至|文件(?:放到|放在|保存到)|放到|放在|保存到)\s*([~/][^\s，,。；;]+)/i)?.[1] || "";
  const steps = [
    `1. 识别产物：${getAiDeployApplicationTypeLabel(context.deploy_component.application_type)}，${getAiDeployStorageKindLabel(context.artifact.storage_kind, context.artifact.is_archive)}，版本 ${context.artifact.version || "未标记"}。`,
    "2. 点击执行部署后，后端会把完整部署要求、产物信息、部署目标和工具结果交给模型逐步决策。",
    "3. Agent 可动态调用工具：安全解压、列目录、读写文本、创建目录、上传目录、上传文件、上传原始包、执行工作区命令、触发已配置的远端命令。",
    extractBeforeUpload
      ? `4. 若模型计划确认解压：安全解压产物${extractPath ? `到 ${extractPath}` : ""}，按要求上传解压后的内容${wantsOriginalArchiveUpload ? "，并同时上传原压缩包" : ""}。`
      : archivePolicy === "upload_archive"
        ? "4. 若模型计划确认保留压缩包形态，系统会原样上传压缩包。"
        : context.artifact.storage_kind === "directory"
          ? "4. 产物是目录，系统会递归上传目录内容。"
          : context.artifact.is_archive
            ? "4. 当前是压缩包产物；没有明确解压要求时，模型应选择原样上传压缩包，不会默认解压。"
            : "4. 产物是文件，系统会直接上传文件。",
    hasCommand
      ? "5. 部署单元已配置部署命令；Agent 可按要求触发该已保存命令，并根据 stdout/stderr 继续判断。"
      : "5. 当前部署单元没有部署命令；系统只执行备份和上传。",
    "6. 如果工具执行失败或 Agent 判断无法继续，部署会失败或阻塞，并在失败日志中展示 Agent 轨迹和工具结果。",
  ];
  if (missingRemotePath) {
    steps.push(`阻塞项：${missingRemotePath} 个目标缺少远端目录。`);
  }
  if (requirementText) {
    steps.push(`补充要求：${requirementText}`);
  }
  return ["本地预览（最终以 Agent 动态执行为准）：", ...steps].join("\n");
}

async function openAiDeployArtifact(row) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  aiDeployArtifact.value = normalizeDeployArtifact(row);
  aiDeployRequirement.value = "";
  aiDeployPlan.value = buildLocalAiDeployArtifactPlan(row);
  aiDeployPlanMeta.value = "本地预览";
  aiDeployDialogVisible.value = true;
}

async function generateAiDeployArtifactPlan() {
  const row = aiDeployArtifact.value;
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  aiDeployPlanLoading.value = true;
  try {
    const data = await api.post(
      `/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}/plan/generate`,
      {
        requirement: aiDeployRequirement.value,
      },
    );
    aiDeployPlan.value = String(data?.plan || "").trim() || buildLocalAiDeployArtifactPlan(row, aiDeployRequirement.value);
    aiDeployPlanMeta.value = [data?.model_name, data?.provider_id].filter(Boolean).join(" · ") || "AI 生成";
  } catch (err) {
    aiDeployPlan.value = buildLocalAiDeployArtifactPlan(row, aiDeployRequirement.value);
    aiDeployPlanMeta.value = "本地预览";
    ElMessage.warning(err?.detail || err?.message || "AI 流程生成失败，已使用本地流程预览");
  } finally {
    aiDeployPlanLoading.value = false;
  }
}

async function executeAiDeployArtifact() {
  const row = aiDeployArtifact.value;
  if (!row) {
    return;
  }
  aiDeployExecuting.value = true;
  try {
    const deployed = await deployArtifactViaProjectAi(row, {
      requirement: aiDeployRequirement.value,
      plan: aiDeployPlan.value,
    });
    if (deployed) {
      aiDeployDialogVisible.value = false;
    }
  } finally {
    aiDeployExecuting.value = false;
  }
}

function resetAiDeployDialog() {
  aiDeployArtifact.value = null;
  aiDeployRequirement.value = "";
  aiDeployPlan.value = "";
  aiDeployPlanMeta.value = "";
}

function countDeployFileTreeFiles(nodes) {
  if (!Array.isArray(nodes)) return 0;
  return nodes.reduce((count, node) => {
    if (node?.type === "file") return count + 1;
    return count + countDeployFileTreeFiles(node?.children || []);
  }, 0);
}

function normalizeDeployRun(item) {
  return {
    id: String(item?.id || "").trim(),
    profile: String(item?.profile || "").trim(),
    component: String(item?.component || "").trim(),
    status: String(item?.status || "").trim(),
    stage: String(item?.stage || "").trim(),
    log_excerpt: String(item?.log_excerpt || "").trim(),
    artifact_summary: item?.artifact_summary && typeof item.artifact_summary === "object"
      ? item.artifact_summary
      : {},
    notify_result: Array.isArray(item?.notify_result) ? item.notify_result : [],
    updated_at: String(item?.updated_at || "").trim(),
    deleted_at: String(item?.deleted_at || "").trim(),
  };
}

async function fetchDeployArtifacts() {
  if (!props.projectId) {
    deployArtifacts.value = [];
    return;
  }
  deployArtifactsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-artifacts`);
    deployArtifacts.value = (data.artifacts || [])
      .map((item) => normalizeDeployArtifact(item))
      .filter((item) => item.id);
  } catch (err) {
    deployArtifacts.value = [];
    ElMessage.error(err?.detail || err?.message || "加载部署产物失败");
  } finally {
    deployArtifactsLoading.value = false;
  }
}

async function deleteDeployArtifact(row) {
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  deletingArtifactId.value = artifactId;
  try {
    await api.delete(`/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}`);
    deployArtifacts.value = deployArtifacts.value.filter((item) => item.id !== artifactId);
    ElMessage.success("打包产物文件已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除打包产物失败");
  } finally {
    deletingArtifactId.value = "";
  }
}

async function deployArtifactViaProjectAi(row, extraPayload = {}) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return false;
  }
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return false;
  }
  deployingArtifactId.value = artifactId;
  let deployed = false;
  try {
    const data = await api.post(
      `/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}/deploy/ai-execute`,
      extraPayload && typeof extraPayload === "object" ? extraPayload : {},
    );
    const aiExecution = data?.ai_execution && typeof data.ai_execution === "object"
      ? data.ai_execution
      : {};
    if (String(aiExecution.status || "").trim() === "handoff_required") {
      throw new Error("后端仍返回外部智能体交接，未创建真实部署运行");
    }
    const status = String(data?.deployment?.status || data?.status || "").trim().toLowerCase();
    const statusLabel = getDeployStatusLabel(status);
    const chatSessionId = String(data?.ai_execution?.chat_session_id || "").trim();
    if (status === "failed") {
      ElMessage.error(`AI 部署失败：${statusLabel}`);
    } else if (status === "blocked") {
      ElMessage.warning(`AI 部署已阻塞：${statusLabel}`);
    } else {
      ElMessage.success(chatSessionId ? `项目 AI 已触发部署：${statusLabel}` : `AI 部署已触发：${statusLabel}`);
    }
    await Promise.all([fetchDeployArtifacts(), fetchDeployRuns()]);
    deployed = status !== "failed" && status !== "blocked";
    if (!deployed) {
      await showDeployFailureLog(row, data);
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "项目 AI 部署失败");
    await showDeployFailureLog(row);
  } finally {
    deployingArtifactId.value = "";
  }
  return deployed;
}

async function deployArtifact(row, extraPayload = {}) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return false;
  }
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return false;
  }
  deployingArtifactId.value = artifactId;
  let deployed = false;
  try {
    const data = await api.post(
      `/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}/deploy`,
      extraPayload && typeof extraPayload === "object" ? extraPayload : {},
    );
    const status = String(data?.deployment?.status || data?.status || "").trim().toLowerCase();
    const statusLabel = getDeployStatusLabel(status);
    if (status === "failed") {
      ElMessage.error(`部署失败：${statusLabel}`);
    } else if (status === "blocked") {
      ElMessage.warning(`部署已阻塞：${statusLabel}`);
    } else {
      ElMessage.success(`已触发部署：${statusLabel}`);
    }
    await Promise.all([fetchDeployArtifacts(), fetchDeployRuns()]);
    deployed = status !== "failed" && status !== "blocked";
    if (!deployed) {
      await showDeployFailureLog(row, data);
    }
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "触发部署失败");
    await showDeployFailureLog(row);
  } finally {
    deployingArtifactId.value = "";
  }
  return deployed;
}

function hasDeployFailureLog(row) {
  const status = getDeployArtifactStatus(row).toLowerCase();
  return ["failed", "blocked"].includes(status) || Boolean(row?.error || row?.deployment_id);
}

async function openDeployLogDialog(row) {
  const artifactId = String(row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  deployLogArtifactId.value = artifactId;
  deployLogDialogVisible.value = true;
  deployLogLoading.value = true;
  deployLogDetail.value = { artifact: row, deployment: null };
  try {
    const data = await api.get(
      `/projects/${props.projectId}/deploy-artifacts/${encodeURIComponent(artifactId)}`,
    );
    deployLogDetail.value = {
      artifact: data?.artifact || row,
      deployment: data?.deployment || null,
    };
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "加载部署失败日志失败");
  } finally {
    deployLogLoading.value = false;
  }
}

async function showDeployFailureLog(row, response = null) {
  const artifact = response?.artifact || row;
  const artifactId = String(artifact?.id || row?.id || "").trim();
  if (!artifactId || !props.projectId) {
    return;
  }
  if (aiDeployDialogVisible.value) {
    aiDeployDialogVisible.value = false;
    await nextTick();
  }
  deployLogArtifactId.value = artifactId;
  deployLogDialogVisible.value = true;
  deployLogDetail.value = {
    artifact,
    deployment: response?.deployment || null,
  };
  await openDeployLogDialog({ ...artifact, id: artifactId });
}

function formatDeployMissingTarget(target) {
  const name = String(target?.target_name || target?.target_id || "未命名目标").trim();
  const missing = Array.isArray(target?.missing) ? target.missing.filter(Boolean).join(", ") : "";
  return missing ? `${name}: ${missing}` : name;
}

function formatDeployLogJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || "");
  }
}

async function copyDeployLog() {
  const text = deployLogText.value;
  if (!text) {
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("失败日志已复制");
  } catch (err) {
    ElMessage.error(err?.message || "复制失败，请手动选择日志内容");
  }
}

async function fetchDeployRuns() {
  if (!props.projectId) {
    deployRuns.value = [];
    return;
  }
  deployRunsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-runs`);
    deployRuns.value = (data.runs || []).map((item) => normalizeDeployRun(item)).filter((item) => item.id);
  } catch (err) {
    deployRuns.value = [];
    ElMessage.error(err?.detail || err?.message || "加载部署运行失败");
  } finally {
    deployRunsLoading.value = false;
  }
}

async function deleteDeployRun(row) {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  const runId = String(row?.id || "").trim();
  if (!runId || !props.projectId) {
    return;
  }
  deletingRunId.value = runId;
  try {
    await api.delete(`/projects/${props.projectId}/deploy-runs/${encodeURIComponent(runId)}`);
    deployRuns.value = deployRuns.value.filter((item) => item.id !== runId);
    ElMessage.success("部署运行记录已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除部署运行记录失败");
  } finally {
    deletingRunId.value = "";
  }
}

async function fetchFtpCredentials() {
  ftpCredentialsLoading.value = true;
  try {
    const data = await api.get("/ftp-credentials");
    ftpCredentials.value = Array.isArray(data?.items) ? data.items : [];
  } catch (err) {
    ftpCredentials.value = [];
    ElMessage.error(err?.detail || err?.message || "加载 FTP 连接失败");
  } finally {
    ftpCredentialsLoading.value = false;
  }
}

async function fetchDeployNotifyOptions() {
  if (!props.projectId) {
    deployNotifyConnectors.value = [];
    deployNotifyChats.value = [];
    return;
  }
  deployNotifyOptionsLoading.value = true;
  try {
    const data = await api.get(`/projects/${props.projectId}/deploy-notify-options`);
    deployNotifyConnectors.value = Array.isArray(data?.connectors)
      ? data.connectors.map((item) => normalizeDeployNotifyConnector(item)).filter((item) => item.id)
      : [];
    deployNotifyChats.value = Array.isArray(data?.chats)
      ? data.chats.map((item) => normalizeDeployNotifyChat(item)).filter((item) => item.chat_id)
      : [];
    if (notifyTargetForm.value.chat_id && !notifyTargetForm.value.chat_name) {
      notifyTargetForm.value.chat_name = getNotifyChatName(notifyTargetForm.value.chat_id);
      notifyChatName.value = notifyTargetForm.value.chat_name;
    }
  } catch (err) {
    deployNotifyConnectors.value = [];
    deployNotifyChats.value = [];
    ElMessage.error(err?.detail || err?.message || "加载通知机器人失败");
  } finally {
    deployNotifyOptionsLoading.value = false;
  }
}

async function refreshDeployStatus() {
  await Promise.all([fetchDeployArtifacts(), fetchDeployRuns(), fetchFtpCredentials(), fetchDeployNotifyOptions()]);
}

async function resolveNotifyChatByName() {
  if (!props.projectId || notifyTargetForm.value.platform !== "feishu") return;
  const chatName = notifyChatName.value.trim();
  if (!notifyTargetForm.value.connector_id) {
    ElMessage.warning("请先选择通知机器人");
    return;
  }
  if (!chatName) {
    ElMessage.warning("请输入飞书群名称");
    return;
  }
  deployNotifyResolving.value = true;
  try {
    const connector = selectedNotifyConnector.value;
    const data = await api.post(`/projects/${props.projectId}/deploy-notify-chat/resolve`, {
      platform: notifyTargetForm.value.platform,
      connector_id: notifyTargetForm.value.connector_id,
      chat_name: chatName,
      identity: connector?.reply_identity || notifyTargetForm.value.resolve_identity || "bot",
    });
    const chat = normalizeDeployNotifyChat(data?.chat);
    upsertNotifyChat(chat);
    notifyTargetForm.value.chat_id = chat.chat_id;
    notifyTargetForm.value.chat_name = chat.chat_name || chatName;
    notifyTargetForm.value.resolve_identity = data?.chat?.resolve_identity || connector?.reply_identity || "bot";
    notifyChatName.value = notifyTargetForm.value.chat_name;
    applyNotifyTargetToActiveComponent();
    await fetchDeployNotifyOptions();
    ElMessage.success("飞书群已解析");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "解析飞书群失败");
  } finally {
    deployNotifyResolving.value = false;
  }
}

async function validateDeploySettings() {
  if (!props.projectId) return false;
  deployValidating.value = true;
  try {
    const data = await api.post(`/projects/${props.projectId}/deploy-settings/validate`, {
      deploy_settings: buildDeploySettingsPayload(),
    });
    deployValidation.value = {
      valid: Boolean(data?.valid),
      issues: Array.isArray(data?.issues) ? data.issues : [],
    };
    ElMessage[deployValidation.value.valid ? "success" : "warning"](
      deployValidation.value.valid ? "部署配置校验通过" : firstDeployValidationMessage(),
    );
    return deployValidation.value.valid;
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "校验部署配置失败");
    return false;
  } finally {
    deployValidating.value = false;
  }
}

async function saveDeploySettings() {
  if (!props.canManageProject) {
    ElMessage.warning(props.manageBlockedMessage);
    return;
  }
  if (!props.projectId) return;
  deploySaving.value = true;
  try {
    const payload = buildDeploySettingsPayload();
    const validation = await api.post(`/projects/${props.projectId}/deploy-settings/validate`, {
      deploy_settings: payload,
    });
    deployValidation.value = {
      valid: Boolean(validation?.valid),
      issues: Array.isArray(validation?.issues) ? validation.issues : [],
    };
    if (!deployValidation.value.valid) {
      ElMessage.warning(firstDeployValidationMessage());
      return;
    }
    await api.put(`/projects/${props.projectId}`, { deploy_settings: payload });
    ElMessage.success("部署配置已保存");
    emit("project-updated");
    await refreshDeployStatus();
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "保存部署配置失败");
  } finally {
    deploySaving.value = false;
  }
}

function getDeployStatusTagType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["ready", "queued", "deploy_queued", "success", "deployed"].includes(normalized)) return "success";
  if (["failed", "blocked"].includes(normalized)) return "danger";
  if (["uploading", "running"].includes(normalized)) return "warning";
  return "info";
}

function getDeployStatusLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "uploading") return "上传中";
  if (normalized === "ready") return "已就绪";
  if (normalized === "queued" || normalized === "deploy_queued") return "已排队";
  if (normalized === "running") return "执行中";
  if (normalized === "success" || normalized === "deployed") return "已部署";
  if (normalized === "blocked") return "已阻塞";
  if (normalized === "failed") return "失败";
  return String(value || "未知").trim() || "未知";
}

function getDeployNotifyLabel(item) {
  const platform = String(item?.platform || "").trim() || "unknown";
  const status = String(item?.status || "").trim() || "pending";
  return `${platform} · ${status}`;
}

watch(
  () => props.project?.deploy_settings,
  (settings) => {
    syncDeployFormsFromSettings(settings || {});
  },
  { immediate: true },
);

watch(activeComponentId, () => {
  syncNotifyTargetForm();
});

watch(
  () => props.projectId,
  () => {
    deployValidation.value = null;
    void refreshDeployStatus();
  },
);

watch(aiDeployRequirement, () => {
  if (!aiDeployDialogVisible.value || !aiDeployArtifact.value || aiDeployPlanLoading.value || aiDeployExecuting.value) {
    return;
  }
  aiDeployPlan.value = buildLocalAiDeployArtifactPlan(aiDeployArtifact.value, aiDeployRequirement.value);
  aiDeployPlanMeta.value = "本地预览";
});

onMounted(() => {
  void refreshDeployStatus();
});
</script>

<style scoped>
.project-deploy-panel {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.project-deploy-panel__actions,
.project-deploy-panel__notify-tags,
.deploy-topbar,
.deploy-targets__head,
.deploy-editor__header,
.deploy-list__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.project-deploy-panel__actions,
.project-deploy-panel__notify-tags {
  flex-wrap: wrap;
}

.project-deploy-panel__actions {
  justify-content: flex-end;
}

.deploy-topbar {
  justify-content: space-between;
  margin-top: 10px;
}

.deploy-topbar__select {
  width: 220px;
}

.deploy-tabs-shell {
  padding: 12px 12px 0;
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.74);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.8),
    0 18px 34px rgba(15, 23, 42, 0.04);
}

.deploy-tabs {
  margin-top: 0;
}

.deploy-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.deploy-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0;
}

.deploy-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.deploy-tabs :deep(.el-tabs__nav-scroll) {
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
}

.deploy-tabs :deep(.el-tabs__nav-scroll::-webkit-scrollbar) {
  display: none;
}

.deploy-tabs :deep(.el-tabs__nav) {
  display: inline-flex;
  align-items: stretch;
  gap: 8px;
}

.deploy-tabs :deep(.el-tabs__item) {
  height: auto;
  padding: 0;
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
  transition:
    border-color 180ms ease,
    background 180ms ease,
    color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.deploy-tabs :deep(.el-tabs__item:hover) {
  color: #0f172a;
}

.deploy-tabs :deep(.el-tabs__item.is-active) {
  color: #0f172a;
}

.deploy-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, #38bdf8, #67e8f9);
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.35);
}

.deploy-tab-label {
  display: grid;
  gap: 2px;
  min-width: 168px;
  padding: 10px 14px 12px;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
  transition:
    background 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease,
    color 180ms ease;
}

.deploy-tab-label__title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.25;
}

.deploy-tab-label__meta {
  font-size: 11px;
  line-height: 1.4;
  color: inherit;
  opacity: 0.82;
}

.deploy-tabs :deep(.el-tabs__item.is-active) .deploy-tab-label {
  color: #0f172a;
  background: rgba(240, 249, 255, 0.96);
  border-color: rgba(125, 211, 252, 0.45);
  box-shadow:
    0 12px 24px rgba(14, 165, 233, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.deploy-tabs :deep(.el-tabs__item:not(.is-active):hover) .deploy-tab-label {
  background: rgba(248, 250, 252, 0.92);
  border-color: rgba(226, 232, 240, 0.92);
  transform: translateY(-1px);
}

.deploy-layout,
.deploy-subgrid {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.deploy-layout {
  grid-template-columns: 220px minmax(0, 1fr);
}

.deploy-subgrid {
  grid-template-columns: 190px minmax(0, 1fr);
}

.deploy-list,
.deploy-editor,
.deploy-component {
  min-width: 0;
}

.deploy-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deploy-list__head,
.deploy-editor__header,
.deploy-targets__head {
  justify-content: space-between;
}

.deploy-list__head {
  color: #475569;
  font-size: 13px;
  font-weight: 600;
}

.deploy-list__item {
  display: grid;
  gap: 4px;
  width: 100%;
  min-height: 54px;
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
}

.deploy-list__item.is-active {
  border-color: #2563eb;
  background: #eff6ff;
}

.deploy-list__item strong,
.deploy-list__item span,
.deploy-editor__header strong,
.deploy-editor__header span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deploy-list__item span,
.deploy-editor__header span {
  color: #64748b;
  font-size: 12px;
}

.deploy-editor,
.deploy-component {
  display: grid;
  gap: 14px;
}

.deploy-editor__header {
  min-height: 42px;
}

.deploy-editor__header > div {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.deploy-form__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  column-gap: 14px;
}

.deploy-notify-resolver {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  max-width: 520px;
}

.deploy-upload-form {
  display: grid;
  gap: 14px;
}

.deploy-upload-form__grid {
  margin: 0;
}

.deploy-upload-form__control {
  width: 100%;
}

.project-deploy-panel__file-input {
  display: none;
}

.deploy-upload-file {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  width: 100%;
  min-height: 58px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.deploy-upload-file__meta {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.deploy-upload-file__meta strong,
.deploy-upload-file__meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deploy-upload-file__meta strong {
  color: #0f172a;
  font-weight: 600;
}

.deploy-upload-file__meta span {
  color: #64748b;
  font-size: 12px;
}

.deploy-upload-file__actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.deploy-artifact-tree {
  display: grid;
  gap: 8px;
  margin: 8px 0;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.deploy-artifact-tree--preview {
  margin-top: 10px;
  background: #ffffff;
}

.deploy-artifact-tree__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.deploy-artifact-tree__actions {
  display: inline-flex;
  gap: 4px;
  margin-left: auto;
}

.deploy-artifact-tree__node {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
  color: #334155;
  font-size: 12px;
}

.deploy-upload-footer {
  display: inline-flex;
  gap: 8px;
}

.deploy-targets {
  display: grid;
  gap: 8px;
}

.deploy-targets__credential-select {
  width: 100%;
}

.deploy-targets__command-cell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
}

.deploy-table-wrap {
  width: 100%;
  overflow-x: auto;
  padding-bottom: 4px;
}

.deploy-targets-table,
.deploy-artifacts-table,
.deploy-runs-table {
  min-width: 880px;
}

.project-deploy-panel__validation {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.project-deploy-panel__validation ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 8px;
  background: rgba(255, 251, 235, 0.72);
  list-style: none;
}

.project-deploy-panel__validation li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #92400e;
  font-size: 13px;
  line-height: 1.5;
}

.section-table {
  margin-top: 8px;
  width: 100%;
}

.project-deploy-panel :deep(.el-table),
.project-deploy-panel :deep(.el-table__inner-wrapper) {
  border-radius: 8px;
  overflow: hidden;
  width: 100%;
}

.project-deploy-panel :deep(.el-table__fixed-right) {
  height: 100% !important;
}

.project-deploy-panel :deep(.el-table__fixed-right::before) {
  background-color: transparent;
}

.project-deploy-panel :deep(.el-table th.el-table__cell) {
  height: 48px;
  background: rgba(248, 250, 252, 0.9);
  color: #475569;
}

.project-deploy-panel :deep(.el-table td.el-table__cell) {
  padding-top: 10px;
  padding-bottom: 10px;
}

.project-deploy-panel :deep(.el-table .cell) {
  min-width: 0;
}

.project-deploy-panel__table-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.project-deploy-panel__table-main strong,
.project-deploy-panel__table-main span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-deploy-panel__table-main strong {
  color: #0f172a;
  font-weight: 600;
}

.project-deploy-panel__table-main span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.project-deploy-panel__row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.project-deploy-panel__fixed-actions :deep(.cell) {
  display: flex;
  justify-content: flex-end;
}

.ai-deploy-dialog :deep(.el-dialog) {
  max-width: calc(100vw - 32px);
}

.ai-deploy {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.ai-deploy__hero,
.ai-deploy__targets,
.ai-deploy__requirement,
.ai-deploy__plan {
  min-width: 0;
}

.ai-deploy__hero {
  display: grid;
  gap: 12px;
}

.ai-deploy__artifact,
.ai-deploy__section-head,
.ai-deploy__plan-head,
.ai-deploy__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ai-deploy__artifact-title {
  flex: 1;
}

.ai-deploy__meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ai-deploy__meta > div,
.ai-deploy__target-list > div {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
}

.ai-deploy__meta span,
.ai-deploy__meta strong,
.ai-deploy__target-list span,
.ai-deploy__target-list strong,
.ai-deploy__target-list em {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-deploy__meta span,
.ai-deploy__target-list em {
  color: #64748b;
  font-size: 12px;
  font-style: normal;
  line-height: 1.5;
}

.ai-deploy__meta strong,
.ai-deploy__target-list strong {
  margin-top: 2px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.ai-deploy__targets {
  display: grid;
  gap: 8px;
}

.ai-deploy__section-head strong,
.ai-deploy__plan-head strong {
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.ai-deploy__section-head span {
  min-width: 0;
  color: #64748b;
  font-size: 12px;
}

.ai-deploy__target-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.ai-deploy__requirement :deep(.el-form-item) {
  margin-bottom: 0;
}

.ai-deploy__plan {
  display: grid;
  gap: 8px;
}

.ai-deploy__plan-head span {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-deploy__plan pre {
  max-height: 280px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fafc;
  color: #1e293b;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 720px) {
  .ai-deploy__artifact,
  .ai-deploy__section-head,
  .ai-deploy__footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .ai-deploy__meta,
  .ai-deploy__target-list {
    grid-template-columns: minmax(0, 1fr);
  }
}

.deploy-log-detail {
  min-height: 160px;
}

.deploy-log-detail__head,
.deploy-log-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.deploy-log-detail__meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.deploy-log-detail__meta > div {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
}

.deploy-log-detail__meta span,
.deploy-log-detail__meta strong {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.deploy-log-detail__meta span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.deploy-log-detail__meta strong {
  margin-top: 2px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.deploy-log-detail__section {
  margin-top: 16px;
}

.deploy-log-detail__section > strong {
  display: block;
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
}

.deploy-log-detail__section pre {
  max-height: 260px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fff7f7;
  color: #7f1d1d;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.deploy-log-detail__missing {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 980px) {
  .project-deploy-panel__actions {
    justify-content: flex-start;
  }

  .deploy-tabs :deep(.el-tabs__item) {
    padding: 0;
  }

  .deploy-tab-label {
    min-width: 0;
    padding: 9px 12px 10px;
  }

  .deploy-layout,
  .deploy-subgrid,
  .deploy-form__grid,
  .deploy-log-detail__meta,
  .ai-deploy,
  .ai-deploy__meta,
  .deploy-upload-file {
    grid-template-columns: 1fr;
  }

  .deploy-notify-resolver {
    grid-template-columns: 1fr;
    max-width: none;
  }

  .deploy-topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .deploy-topbar__select {
    width: 100%;
  }

  .deploy-upload-file__actions {
    justify-content: flex-start;
  }

  .deploy-tabs-shell {
    padding: 10px 10px 0;
    border-radius: 18px;
  }
}
</style>
