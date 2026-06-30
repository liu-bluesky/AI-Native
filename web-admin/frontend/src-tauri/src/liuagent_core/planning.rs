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
    pub fn finalize_for_goal(
        session_id: &str,
        task_goal: &TaskGoal,
        stopped_reason: &str,
        awaiting_permission: bool,
        run_ok: bool,
    ) -> Self {
        let mut tree = Self::for_goal(session_id, task_goal);
        tree.apply_runtime_status(stopped_reason, awaiting_permission, run_ok);
        tree
    }

    fn apply_runtime_status(
        &mut self,
        stopped_reason: &str,
        awaiting_permission: bool,
        run_ok: bool,
    ) {
        let session_id = self.session_id.as_str();
        let execute_id = format!("node-execute-{session_id}");
        let verify_id = format!("node-verify-{session_id}");
        let goal_id = format!("node-goal-{session_id}");
        for node in &mut self.nodes {
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
            self.current_node_id = execute_id;
        } else if run_ok {
            self.current_node_id = goal_id;
        } else if stopped_reason == "verification_failed" {
            self.current_node_id = verify_id;
        }
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

    pub fn for_goal(session_id: &str, task_goal: &TaskGoal) -> Self {
        let goal_id = format!("node-goal-{session_id}");
        let target = task_goal.target_object.trim();
        let target_suffix = if target.is_empty() || target == "current user request" {
            String::new()
        } else {
            format!("：{target}")
        };
        let mut nodes = vec![TaskNode {
            node_id: goal_id.clone(),
            title: task_goal.title.chars().take(80).collect(),
            node_type: "goal".to_string(),
            status: "pending".to_string(),
            parent_id: None,
            is_destructive: false,
            verification_result: None,
        }];
        let child_specs: Vec<(&str, String, bool)> = match task_goal.intent.as_str() {
            "question" | "history_recall" => {
                vec![("answer", format!("回答用户问题{target_suffix}"), false)]
            }
            "analysis" => vec![
                ("scope", format!("界定分析对象{target_suffix}"), false),
                (
                    "inspect",
                    format!("读取证据并定位原因{target_suffix}"),
                    false,
                ),
                ("conclude", format!("形成分析结论{target_suffix}"), false),
            ],
            "documentation" => vec![
                (
                    "doc-target",
                    format!("确认文档目标路径{target_suffix}"),
                    false,
                ),
                (
                    "doc-review",
                    format!("梳理现有文档结构{target_suffix}"),
                    false,
                ),
                (
                    "doc-write",
                    format!("写入或更新文档内容{target_suffix}"),
                    false,
                ),
                (
                    "doc-verify",
                    format!("回读校对文档结果{target_suffix}"),
                    false,
                ),
            ],
            "bugfix" => vec![
                (
                    "reproduce",
                    format!("复现或确认问题现象{target_suffix}"),
                    false,
                ),
                (
                    "locate",
                    format!("定位根因和影响范围{target_suffix}"),
                    false,
                ),
                ("fix", format!("实施最小修复{target_suffix}"), false),
                ("regress", format!("运行回归验证{target_suffix}"), false),
            ],
            "governance" => vec![
                ("entry", format!("梳理执行入口链路{target_suffix}"), false),
                (
                    "state",
                    format!("改造目标和节点状态流{target_suffix}"),
                    false,
                ),
                (
                    "recovery",
                    format!("完善恢复续跑与进度反馈{target_suffix}"),
                    false,
                ),
                ("verify", format!("验证执行流闭环{target_suffix}"), false),
            ],
            "modification" => vec![
                (
                    "locate",
                    format!("定位需要修改的对象{target_suffix}"),
                    false,
                ),
                (
                    "change",
                    format!("实施目标范围内的修改{target_suffix}"),
                    false,
                ),
                ("verify", format!("验证修改满足目标{target_suffix}"), false),
            ],
            "deployment" => vec![
                (
                    "target",
                    format!("确认部署目标和配置{target_suffix}"),
                    false,
                ),
                ("artifact", format!("准备部署产物{target_suffix}"), false),
                (
                    "release",
                    format!("触发部署并记录结果{target_suffix}"),
                    true,
                ),
                ("verify", format!("验证部署状态{target_suffix}"), false),
            ],
            "destructive" => vec![
                ("scope", format!("确认高风险影响范围{target_suffix}"), true),
                (
                    "approval",
                    format!("等待用户明确授权{target_suffix}"),
                    false,
                ),
                ("execute", format!("执行已授权动作{target_suffix}"), true),
                (
                    "verify",
                    format!("验证可恢复性和结果{target_suffix}"),
                    false,
                ),
            ],
            _ => vec![
                (
                    "analyze",
                    format!("理解目标和现有上下文{target_suffix}"),
                    false,
                ),
                ("execute", format!("推进当前目标{target_suffix}"), false),
                ("verify", format!("验证目标完成情况{target_suffix}"), false),
            ],
        };
        let current_node_id = child_specs
            .first()
            .map(|(key, _, _)| format!("node-{key}-{session_id}"))
            .unwrap_or_else(|| goal_id.clone());
        nodes.extend(
            child_specs
                .into_iter()
                .map(|(key, title, is_destructive)| TaskNode {
                    node_id: format!("node-{key}-{session_id}"),
                    title,
                    node_type: "task".to_string(),
                    status: "pending".to_string(),
                    parent_id: Some(goal_id.clone()),
                    is_destructive,
                    verification_result: None,
                }),
        );
        Self {
            tree_id: format!("tree-{session_id}"),
            root_goal: task_goal.user_request.clone(),
            nodes,
            current_node_id,
            session_id: session_id.to_string(),
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

    #[test]
    fn task_tree_for_question_stays_single_answer_node() {
        let goal = TaskGoal {
            version: "task-goal/test".to_string(),
            goal_id: "goal-test".to_string(),
            title: "这个字段干嘛的？".to_string(),
            user_request: "这个字段干嘛的？".to_string(),
            intent: "question".to_string(),
            target_object: "current user request".to_string(),
            success_criteria: Vec::new(),
            constraints: Vec::new(),
            created_at_epoch_ms: 1,
        };
        let tree = TaskTree::for_goal("sess-2", &goal);
        assert_eq!(tree.nodes.len(), 2);
        assert_eq!(tree.current_node_id, "node-answer-sess-2");
        assert!(tree.nodes[1].title.contains("回答用户问题"));
    }

    #[test]
    fn task_tree_for_modification_mentions_target_object() {
        let goal = TaskGoal {
            version: "task-goal/test".to_string(),
            goal_id: "goal-test".to_string(),
            title: "修复 runtime.rs".to_string(),
            user_request: "修复 runtime.rs".to_string(),
            intent: "modification".to_string(),
            target_object: "runtime.rs".to_string(),
            success_criteria: Vec::new(),
            constraints: Vec::new(),
            created_at_epoch_ms: 1,
        };
        let tree = TaskTree::for_goal("sess-3", &goal);
        assert_eq!(tree.nodes.len(), 4);
        assert!(tree.nodes[1..]
            .iter()
            .all(|node| node.title.contains("runtime.rs")));
    }

    #[test]
    fn task_tree_for_bugfix_uses_repair_specific_nodes() {
        let goal = TaskGoal {
            version: "task-goal/test".to_string(),
            goal_id: "goal-test".to_string(),
            title: "修复关键词分类".to_string(),
            user_request: "修复关键词分类导致执行偏离".to_string(),
            intent: "bugfix".to_string(),
            target_object: "runtime.rs".to_string(),
            success_criteria: Vec::new(),
            constraints: Vec::new(),
            created_at_epoch_ms: 1,
        };
        let tree = TaskTree::for_goal("sess-4", &goal);
        let titles = tree
            .nodes
            .iter()
            .map(|node| node.title.as_str())
            .collect::<Vec<_>>()
            .join("\n");

        assert_eq!(tree.nodes.len(), 5);
        assert!(titles.contains("复现或确认问题现象"));
        assert!(titles.contains("定位根因和影响范围"));
        assert!(titles.contains("实施最小修复"));
        assert!(titles.contains("运行回归验证"));
    }

    #[test]
    fn task_tree_for_governance_is_not_fixed_three_step_template() {
        let goal = TaskGoal {
            version: "task-goal/test".to_string(),
            goal_id: "goal-test".to_string(),
            title: "改造执行流".to_string(),
            user_request: "改造桌面智能体目标驱动执行流".to_string(),
            intent: "governance".to_string(),
            target_object: "liuagent_core".to_string(),
            success_criteria: Vec::new(),
            constraints: Vec::new(),
            created_at_epoch_ms: 1,
        };
        let tree = TaskTree::for_goal("sess-5", &goal);
        let titles = tree
            .nodes
            .iter()
            .map(|node| node.title.as_str())
            .collect::<Vec<_>>()
            .join("\n");

        assert_eq!(tree.nodes.len(), 5);
        assert!(!titles.contains("理解目标和现有上下文"));
        assert!(titles.contains("梳理执行入口链路"));
        assert!(titles.contains("改造目标和节点状态流"));
        assert!(titles.contains("完善恢复续跑与进度反馈"));
    }
}
