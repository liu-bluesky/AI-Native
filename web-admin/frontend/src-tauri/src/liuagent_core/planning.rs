//! 规划机制 — 需求清晰度评估、任务树与阻塞记录。
//!
//! 这一层在 run_agent_loop 之前运行。对 Implementation 型请求，先生成任务树并
//! 等待用户确认；Query 型请求直接放行。

use serde::Serialize;

// ── 需求类型 ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum RequestType {
    Query,
    Implementation,
}

/// 基于关键词启发式判断请求类型。
/// 不做模型调用，只做字面匹配；Query 前缀信号优先于 Implementation 关键词。
pub fn assess_request_type(message: &str) -> RequestType {
    let lower = message.to_lowercase();

    // 以下前缀/词组明确是查询，不触发规划门
    const QUERY_SIGNALS: &[&str] = &[
        "检查", "查看", "查询", "列出", "显示", "展示", "解释", "说明",
        "是什么", "有哪些", "告诉我", "帮我看",
        "show", "list", "what is", "explain", "describe",
    ];
    for kw in QUERY_SIGNALS {
        if lower.starts_with(kw) || lower.contains(&format!(" {kw}")) {
            return RequestType::Query;
        }
    }

    // 以下动词说明请求会改变状态，触发规划门
    const IMPL_SIGNALS: &[&str] = &[
        "创建", "新建", "添加", "修改", "更新", "重构", "实现", "开发",
        "编写", "删除", "移除", "部署", "配置", "构建", "生成", "修复",
        "安装", "初始化", "迁移", "接入", "集成", "改造",
        "create", "add", "modify", "update", "refactor", "implement", "develop",
        "delete", "remove", "deploy", "configure", "build", "generate",
        "fix", "install", "init", "migrate", "setup", "integrate",
    ];
    for kw in IMPL_SIGNALS {
        if lower.contains(kw) {
            return RequestType::Implementation;
        }
    }

    RequestType::Query
}

// ── 任务树 ──────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskNode {
    pub node_id: String,
    pub title: String,
    #[serde(rename = "type")]
    pub node_type: String, // "goal" | "task" | "step"
    pub status: String,    // "pending" | "running" | "done" | "failed" | "blocked"
    pub parent_id: Option<String>,
    pub is_destructive: bool,
    pub verification_result: Option<String>,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskTree {
    pub tree_id: String,
    pub root_goal: String,
    pub nodes: Vec<TaskNode>,
    pub current_node_id: String,
    pub session_id: String,
}

impl TaskTree {
    /// 根据执行结果更新节点状态，返回带最终状态的任务树。
    pub fn finalize(
        session_id: &str,
        goal: &str,
        stopped_reason: &str,
        awaiting_permission: bool,
        run_ok: bool,
    ) -> Self {
        let mut tree = Self::for_implementation(session_id, goal);
        let execute_id = format!("node-execute-{session_id}");
        let verify_id = format!("node-verify-{session_id}");
        let goal_id = format!("node-goal-{session_id}");
        for node in &mut tree.nodes {
            node.status = if node.node_id == goal_id {
                if run_ok {
                    "done".to_string()
                } else if awaiting_permission {
                    "running".to_string()
                } else {
                    "failed".to_string()
                }
            } else if node.node_id == execute_id {
                if awaiting_permission {
                    "blocked".to_string()
                } else if run_ok {
                    "done".to_string()
                } else {
                    "failed".to_string()
                }
            } else if node.node_id == verify_id {
                if stopped_reason == "verification_failed" {
                    "blocked".to_string()
                } else if run_ok {
                    "done".to_string()
                } else {
                    "pending".to_string()
                }
            } else {
                // analyze node: model ran, so always done
                "done".to_string()
            };
        }
        if awaiting_permission {
            tree.current_node_id = execute_id;
        } else if run_ok {
            tree.current_node_id = goal_id;
        }
        tree
    }

    /// 为 Implementation 请求生成最小任务树（分析→执行→验证）。
    pub fn for_implementation(session_id: &str, goal: &str) -> Self {
        let goal_id = format!("node-goal-{session_id}");
        let analyze_id = format!("node-analyze-{session_id}");
        let execute_id = format!("node-execute-{session_id}");
        let verify_id = format!("node-verify-{session_id}");
        Self {
            tree_id: format!("tree-{session_id}"),
            root_goal: goal.to_string(),
            current_node_id: analyze_id.clone(),
            session_id: session_id.to_string(),
            nodes: vec![
                TaskNode {
                    node_id: goal_id.clone(),
                    title: goal.chars().take(80).collect(),
                    node_type: "goal".to_string(),
                    status: "pending".to_string(),
                    parent_id: None,
                    is_destructive: false,
                    verification_result: None,
                },
                TaskNode {
                    node_id: analyze_id,
                    title: "分析现有代码与需求".to_string(),
                    node_type: "task".to_string(),
                    status: "pending".to_string(),
                    parent_id: Some(goal_id.clone()),
                    is_destructive: false,
                    verification_result: None,
                },
                TaskNode {
                    node_id: execute_id,
                    title: "执行工具调用与代码变更".to_string(),
                    node_type: "task".to_string(),
                    status: "pending".to_string(),
                    parent_id: Some(goal_id.clone()),
                    is_destructive: false,
                    verification_result: None,
                },
                TaskNode {
                    node_id: verify_id,
                    title: "验证结果与完成节点".to_string(),
                    node_type: "task".to_string(),
                    status: "pending".to_string(),
                    parent_id: Some(goal_id),
                    is_destructive: false,
                    verification_result: None,
                },
            ],
        }
    }
}

// ── 阻塞记录 ────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct BlockerRecord {
    pub blocker_id: String,
    pub node_id: String,
    pub blocker_type: String,
    pub reason: String,
    pub recovery_condition: String,
}

impl BlockerRecord {
    pub fn permission_required(session_id: &str, node_id: &str, tool_name: &str) -> Self {
        Self {
            blocker_id: format!("blocker-perm-{session_id}"),
            node_id: node_id.to_string(),
            blocker_type: "permission_denied".to_string(),
            reason: format!("工具 {tool_name} 需要用户授权"),
            recovery_condition: "提供权限决策后重新提交".to_string(),
        }
    }

    pub fn verification_failed(session_id: &str, node_id: &str) -> Self {
        Self {
            blocker_id: format!("blocker-verify-{session_id}"),
            node_id: node_id.to_string(),
            blocker_type: "verification_failed".to_string(),
            reason: "工具执行未通过验证".to_string(),
            recovery_condition: "查看错误输出并调整后重试".to_string(),
        }
    }
}

// ── 单元测试 ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn query_signals_are_not_implementation() {
        assert_eq!(assess_request_type("检查工作区"), RequestType::Query);
        assert_eq!(assess_request_type("查看文件列表"), RequestType::Query);
        assert_eq!(assess_request_type("解释这段代码"), RequestType::Query);
    }

    #[test]
    fn implementation_signals_trigger_planning() {
        assert_eq!(assess_request_type("开发规划机制"), RequestType::Implementation);
        assert_eq!(assess_request_type("实现新功能"), RequestType::Implementation);
        assert_eq!(assess_request_type("修改 runtime.rs"), RequestType::Implementation);
        assert_eq!(assess_request_type("create a new module"), RequestType::Implementation);
    }

    #[test]
    fn task_tree_has_goal_and_three_tasks() {
        let tree = TaskTree::for_implementation("sess-1", "开发规划机制");
        assert_eq!(tree.nodes.len(), 4); // 1 goal + 3 tasks
        assert_eq!(tree.nodes[0].node_type, "goal");
        assert!(tree.nodes[1..].iter().all(|n| n.node_type == "task"));
    }
}
