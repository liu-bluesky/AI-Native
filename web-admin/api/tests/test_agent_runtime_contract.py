import pytest


def test_contract_builds_full_agent_event_envelope():
    from services.agent_runtime.contract import build_agent_event

    event = build_agent_event(
        event_type="state_changed",
        session_id="sess_1",
        run_id="run_1",
        payload={
            "from": "running",
            "to": "waiting_approval",
            "waiting_for": "approval",
            "pending_request_id": "perm_1",
        },
    )

    assert event["event_id"].startswith("evt_")
    assert event["type"] == "state_changed"
    assert event["session_id"] == "sess_1"
    assert event["payload"]["pending_request_id"] == "perm_1"
    assert event["payload"]["pending_tool_call_ids"] == []


def test_contract_rejects_mixed_pending_fields():
    from services.agent_runtime.contract import ContractError, build_agent_event

    with pytest.raises(ContractError, match="pending_request_id"):
        build_agent_event(
            event_type="state_changed",
            session_id="sess_1",
            payload={
                "from": "running",
                "to": "waiting_tool",
                "waiting_for": "tool",
                "pending_request_id": "perm_wrong",
                "pending_tool_call_ids": ["call_1"],
            },
        )


def test_contract_matches_permission_decision_to_presented_option():
    from services.agent_runtime.contract import validate_permission_decision_against_options

    decision = validate_permission_decision_against_options(
        {"decision": "approve_run", "grant_scope": "run"},
        [
            {"decision": "approve_run", "grant_scope": "run", "label": "允许本次运行"},
            {"decision": "deny", "label": "拒绝"},
        ],
    )

    assert decision["decision"] == "approve_run"
    assert decision["grant_scope"] == "run"


def test_contract_rejects_permission_decision_scope_mismatch():
    from services.agent_runtime.contract import (
        ContractError,
        validate_permission_decision_against_options,
    )

    with pytest.raises(ContractError, match="does not match"):
        validate_permission_decision_against_options(
            {"decision": "approve_session", "grant_scope": "session"},
            [
                {"decision": "approve_once", "grant_scope": "once", "label": "允许一次"},
                {"decision": "deny", "label": "拒绝"},
            ],
        )


def test_contract_requires_adapter_command_idempotency_for_resume_actions():
    from services.agent_runtime.contract import ContractError, validate_adapter_command

    with pytest.raises(ContractError, match="requires idempotency_key"):
        validate_adapter_command(
            {
                "command_id": "cmd_1",
                "type": "open_url_done",
                "payload": {"open_url_id": "url_1", "status": "completed"},
            }
        )


def test_contract_validates_adapter_command_payload_idempotency_match():
    from services.agent_runtime.contract import validate_adapter_command

    command = validate_adapter_command(
        {
            "command_id": "cmd_1",
            "type": "open_url_done",
            "idempotency_key": "idem_1",
            "payload": {
                "open_url_id": "url_1",
                "status": "completed",
                "idempotency_key": "idem_1",
            },
        }
    )

    assert command["idempotency_key"] == "idem_1"


def test_runtime_event_log_writes_compatible_contract_envelope(tmp_path):
    from services.agent_runtime.core.event_log import RuntimeEventLog

    event_log = RuntimeEventLog(tmp_path / "events")
    event = event_log.append(
        "run_1",
        "tool_started",
        {"tool_call_id": "call_1"},
        session_id="sess_1",
    )
    reloaded = event_log.list_events("run_1")[0]

    assert event.to_dict()["type"] == "tool_started"
    assert event.to_dict()["event_type"] == "tool_started"
    assert reloaded.session_id == "sess_1"
    assert reloaded.to_agent_event()["session_id"] == "sess_1"


def test_transcript_store_keeps_session_id_for_replay(tmp_path):
    from services.agent_runtime.core.transcript_store import TranscriptStore

    store = TranscriptStore(tmp_path / "transcripts")
    store.append(
        "run_1",
        "model_output",
        {"content": "ok"},
        session_id="sess_1",
    )

    event = store.list_events("run_1")[0]
    assert event["type"] == "model_output"
    assert event["session_id"] == "sess_1"


def test_tool_observation_exposes_canonical_tool_result_id():
    from services.agent_runtime.shared.tool_results import ToolResultNormalizer

    observation = ToolResultNormalizer().normalize(
        run_id="run_1",
        call_id="call_1",
        tool_name="read_file",
        raw_result={"ok": True, "summary": "读取完成"},
    )
    payload = observation.to_dict()

    assert payload["tool_result_id"] == payload["observation_id"]
    assert payload["summary"] == "读取完成"
    assert payload["created_at"]


def test_permission_decision_exposes_canonical_decision_fields():
    from services.agent_runtime.v2.permission_store import PermissionDecision

    decision = PermissionDecision(
        decision_id="perm_1",
        run_id="run_1",
        call_id="call_1",
        tool_name="project_host_run_command",
        behavior="allow_once",
    )
    payload = decision.to_dict()

    assert payload["request_id"] == "perm_1"
    assert payload["decision"] == "approve_once"
    assert payload["grant_scope"] == "once"
    assert payload["canonical_decision"]["idempotency_key"]
