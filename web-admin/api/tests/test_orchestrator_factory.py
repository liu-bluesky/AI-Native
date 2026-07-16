from unittest.mock import MagicMock

import pytest

from services.runtime.orchestrator_factory import (
    BackendAgentRuntimeRetiredError,
    build_agent_orchestrator,
)


def test_build_agent_orchestrator_rejects_retired_backend_runtime():
    with pytest.raises(
        BackendAgentRuntimeRetiredError,
        match="use the desktop liuagent runtime",
    ):
        build_agent_orchestrator(MagicMock(), MagicMock(), {})
