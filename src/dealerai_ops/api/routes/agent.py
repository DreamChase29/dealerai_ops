"""Agent orchestration endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dealerai_ops.agents.factory import build_default_retriever, build_llm_provider
from dealerai_ops.agents.guardrails import default_agent_guardrail_policy
from dealerai_ops.agents.orchestrator import AgentOrchestrator
from dealerai_ops.agents.schemas import AgentRunRequest, AgentRunResult
from dealerai_ops.api.routes.ml import NoShowServiceDependency, SettingsDependency
from dealerai_ops.db.session import get_session
from dealerai_ops.tools.executor import ToolExecutor

router = APIRouter(prefix="/agent", tags=["agent"])

SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("/run", response_model=AgentRunResult)
def run_agent(
    request: AgentRunRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    no_show_service: NoShowServiceDependency,
) -> AgentRunResult:
    """Run one provider-independent agent turn."""
    try:
        provider = build_llm_provider(settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tool_executor = ToolExecutor(session, no_show_service=no_show_service)
    orchestrator = AgentOrchestrator(
        provider=provider,
        tool_executor=tool_executor,
        retriever=build_default_retriever(),
        max_tool_iterations=settings.agent_max_tool_iterations,
        timeout_seconds=settings.agent_timeout_seconds,
        guardrail_policy=default_agent_guardrail_policy(
            allowed_tools=frozenset(tool_executor.registry),
            max_retrieval_chunks=settings.agent_max_retrieval_chunks,
        ),
        agent_version=settings.agent_version,
        prompt_version=settings.prompt_version,
        model_version=settings.llm_model_version,
    )
    return orchestrator.run(request)
