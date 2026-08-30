# deploy_workspace_files_to_target

## 作用

将 workspace 内指定文件、目录或文件清单直接部署到目标服务器。

## 选择时机

- 用户明确确认部署目标，并且已经先读取 `get_project_deploy_options`。

## 参数与权限

可使用 `artifact_path` 或 `artifact_paths`，并指定 `profile`、`component`、`target_ids` 等信息。属于高风险网络写操作，必须经过用户授权。

## 成功判定

只有工具返回 `deployment_confirmed_success=true` 且 `status=success` 时，才能向用户回复部署成功；否则必须如实说明状态。

