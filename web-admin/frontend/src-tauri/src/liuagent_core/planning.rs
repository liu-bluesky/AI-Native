//! 规划机制 — 任务树与阻塞记录。

use serde::Serialize;

use super::types::TaskGoal;

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
    pub fn without_plan(session_id: &str, task_goal: &TaskGoal) -> Self {
        let goal_id = format!("node-goal-{session_id}");
        Self {
            tree_id: format!("tree-{session_id}"),
            root_goal: task_goal.user_request.clone(),
            nodes: vec![TaskNode {
                node_id: goal_id.clone(),
                title: task_goal.title.chars().take(80).collect(),
                node_type: "goal".to_string(),
                status: "pending".to_string(),
                parent_id: None,
                is_destructive: false,
                verification_result: None,
            }],
            current_node_id: goal_id,
            session_id: session_id.to_string(),
        }
    }

    pub fn from_model_steps(
        session_id: &str,
        task_goal: &TaskGoal,
        steps: &[(String, String)],
    ) -> Self {
        let goal_id = format!("node-goal-{session_id}");
        let mut nodes = Self::without_plan(session_id, task_goal).nodes;
        nodes.extend(steps.iter().map(|(title, status)| TaskNode {
            node_id: format!(
                "node-plan-{:016x}-{session_id}",
                stable_plan_step_hash(title)
            ),
            title: title.clone(),
            node_type: "task".to_string(),
            status: match status.as_str() {
                "completed" => "done".to_string(),
                "in_progress" => "running".to_string(),
                "blocked" => "blocked".to_string(),
                _ => "pending".to_string(),
            },
            parent_id: Some(goal_id.clone()),
            is_destructive: false,
            verification_result: None,
        }));
        let current_node_id = nodes
            .iter()
            .find(|node| node.status == "running")
            .or_else(|| {
                nodes
                    .iter()
                    .find(|node| node.node_type != "goal" && node.status == "pending")
            })
            .map(|node| node.node_id.clone())
            .unwrap_or_else(|| goal_id.clone());
        Self {
            tree_id: format!("tree-{session_id}"),
            root_goal: task_goal.user_request.clone(),
            nodes,
            current_node_id,
            session_id: session_id.to_string(),
        }
    }

    pub fn finalize_model_plan(&mut self, awaiting_permission: bool, run_ok: bool) {
        let goal_id = format!("node-goal-{}", self.session_id);
        for node in &mut self.nodes {
            if node.node_type == "goal" {
                node.status = if run_ok {
                    "done"
                } else if awaiting_permission {
                    "running"
                } else {
                    "failed"
                }
                .to_string();
            } else if run_ok {
                node.status = "done".to_string();
            } else if node.status == "running" {
                node.status = if awaiting_permission {
                    "blocked"
                } else {
                    "failed"
                }
                .to_string();
            }
        }
        self.current_node_id = if run_ok {
            goal_id
        } else {
            self.nodes
                .iter()
                .find(|node| matches!(node.status.as_str(), "blocked" | "failed" | "running"))
                .map(|node| node.node_id.clone())
                .unwrap_or(goal_id)
        };
    }
}

fn stable_plan_step_hash(title: &str) -> u64 {
    let normalized = title.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in normalized.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
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
    fn task_tree_without_plan_only_contains_goal() {
        let goal = test_goal("解释当前路由", "question");
        let tree = TaskTree::without_plan("sess-1", &goal);
        assert_eq!(tree.nodes.len(), 1);
        assert_eq!(tree.nodes[0].node_type, "goal");
    }

    #[test]
    fn model_steps_keep_stable_ids_when_reordered() {
        let goal = test_goal("实现模型计划", "agentic_request");
        let first = TaskTree::from_model_steps(
            "sess-2",
            &goal,
            &[
                ("定义计划协议".to_string(), "completed".to_string()),
                ("接入计划事件".to_string(), "in_progress".to_string()),
            ],
        );
        let reordered = TaskTree::from_model_steps(
            "sess-2",
            &goal,
            &[
                ("接入计划事件".to_string(), "in_progress".to_string()),
                ("定义计划协议".to_string(), "completed".to_string()),
            ],
        );
        let first_id = first
            .nodes
            .iter()
            .find(|node| node.title == "定义计划协议")
            .unwrap()
            .node_id
            .clone();
        let reordered_id = reordered
            .nodes
            .iter()
            .find(|node| node.title == "定义计划协议")
            .unwrap()
            .node_id
            .clone();
        assert_eq!(first_id, reordered_id);
    }

    fn test_goal(title: &str, intent: &str) -> TaskGoal {
        TaskGoal {
            version: "task-goal/test".to_string(),
            goal_id: "goal-test".to_string(),
            title: title.to_string(),
            user_request: title.to_string(),
            intent: intent.to_string(),
            target_object: "current user request".to_string(),
            success_criteria: Vec::new(),
            constraints: Vec::new(),
            created_at_epoch_ms: 1,
        }
    }
}
