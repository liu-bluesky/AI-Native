from scripts import repair_project_memory_bindings as repair_script


def test_plan_memory_repair_backfills_binding_from_task_tree_trace():
    trace_index = repair_script.TraceIndex(
        project_names={"proj-2": "项目二"},
        task_session_projects={"tts-2": "proj-2"},
        chat_session_projects={},
        work_session_projects={},
    )
    row = repair_script.MemoryRow(
        id="mem-1",
        employee_id="emp-1",
        created_at="2026-04-14T08:00:00+00:00",
        payload={
            "project_name": "项目一",
            "content": (
                "问题：串项目记录\n"
                "[项目名称] 旧项目\n"
                "[执行轨迹JSON] "
                '{"task_tree_session_id":"tts-2","chat_session_id":"chat-2"}'
            ),
            "purpose_tags": ["query-mcp", "manual-write"],
        },
    )

    plan, reason = repair_script._plan_memory_repair(row, trace_index)

    assert reason == "repairable"
    assert plan is not None
    assert plan.resolved_project_id == "proj-2"
    assert plan.resolved_project_name == "项目二"
    assert plan.matched_sources == ("task_tree_session_id",)
    assert plan.updated_payload["project_name"] == "项目二"
    assert "project-id:proj-2" in plan.updated_payload["purpose_tags"]
    assert plan.updated_payload["content"].count("[项目名称]") == 1
    assert "[项目ID] proj-2" in plan.updated_payload["content"]
    assert "[项目名称] 项目二" in plan.updated_payload["content"]


def test_plan_memory_repair_skips_conflicting_strong_trace_signals():
    trace_index = repair_script.TraceIndex(
        project_names={"proj-1": "项目一", "proj-2": "项目二"},
        task_session_projects={"tts-1": "proj-1"},
        chat_session_projects={},
        work_session_projects={"ws-2": "proj-2"},
    )
    row = repair_script.MemoryRow(
        id="mem-2",
        employee_id="emp-1",
        created_at="2026-04-14T08:00:00+00:00",
        payload={
            "project_name": "项目一",
            "content": (
                "问题：冲突轨迹\n"
                "[执行轨迹JSON] "
                '{"task_tree_session_id":"tts-1","session_id":"ws-2"}'
            ),
            "purpose_tags": ["query-mcp"],
        },
    )

    plan, reason = repair_script._plan_memory_repair(row, trace_index)

    assert plan is None
    assert reason == "conflicting-strong-signals"
