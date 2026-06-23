//! 规划机制 — 任务树与阻塞记录。

use serde::Serialize;

// ── 任务树 ──────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct TaskNode {
    pub node_id: String,
    pub title: String,
    #[serde(rename = "type")]
    pub node_type: String, // "goal" | "task" | "step"
    pub status: String, // "pending" | "running" | "done" | "failed" | "blocked"
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
    fn task_tree_has_goal_and_three_tasks() {
        let tree = TaskTree::for_implementation("sess-1", "开发规划机制");
        assert_eq!(tree.nodes.len(), 4); // 1 goal + 3 tasks
        assert_eq!(tree.nodes[0].node_type, "goal");
        assert!(tree.nodes[1..].iter().all(|n| n.node_type == "task"));
    }
}
