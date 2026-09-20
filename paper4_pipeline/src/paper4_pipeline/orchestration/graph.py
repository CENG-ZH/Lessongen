"""LangGraph implementation of the Paper#4 real-model vertical slice."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

from langgraph.graph import END, START, StateGraph

from paper4_pipeline.agents.profiles import validate_profile_references
from paper4_pipeline.agents.protocols import AgentOutput
from paper4_pipeline.agents.suite import AgentSuite
from paper4_pipeline.control.lifecycle import (
    DEFAULT_MAX_ACCEPTS_PER_ROUND,
    actionable_critiques,
    apply_rewrite_outcome,
    apply_validation,
    detect_regressions,
    merge_critique_history,
    reopen_cap_deferred_for_validation,
    transition_critique,
    verify_rewrite,
)
from paper4_pipeline.control.evidence import build_task_evidence_profile
from paper4_pipeline.control.optimization import content_hash, optimization_quality_gate
from paper4_pipeline.control.routing import (
    route_after_evaluation,
    route_after_validation,
)
from paper4_pipeline.control.rules import check_lesson_plan
from paper4_pipeline.control.versioning import document_hash, select_best_version
from paper4_pipeline.domain.models import (
    CritiqueBatch,
    CritiqueItem,
    CritiqueStatus,
    EvaluationReport,
    ExperimentConfig,
    IterationRecord,
    LessonDesignBlueprint,
    LessonPlanVersion,
    LessonTask,
    PipelineResult,
    RewriteRecord,
    RouteAction,
    RouteDecision,
    RunStatus,
    StopReason,
    TaskMode,
    TokenUsage,
    ValidationBatch,
    VersionSelection,
)
from paper4_pipeline.domain.ids import stable_id
from paper4_pipeline.domain.naming import automatic_run_id
from paper4_pipeline.knowledge.registry import build_knowledge_bundle
from paper4_pipeline.observability.trace import TraceStore
from paper4_pipeline.orchestration.state import PipelineState, assert_json_safe_state


class _NodeExecutionError(RuntimeError):
    """A multi-call node failure with all in-node usage preserved for projection."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        usage: TokenUsage,
        estimated_cost: float,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.usage = usage
        self.estimated_cost = estimated_cost


class Paper4Workflow:
    """A reusable graph whose checkpoint state contains JSON values only."""

    def __init__(
        self,
        agents: AgentSuite,
        output_root: Path,
        clock: Callable[[], datetime] | None = None,
        run_id_factory: Callable[[LessonTask], str] | None = None,
    ) -> None:
        self.agents = agents
        self.output_root = output_root.resolve()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._run_id_factory = run_id_factory or (
            lambda task: automatic_run_id(task, now=self._aware_now().astimezone())
        )
        self._profiles = agents.profiles
        self._traces: dict[str, TraceStore] = {}
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PipelineState)
        builder.add_node("design", self._design)
        builder.add_node("bootstrap", self._bootstrap)
        builder.add_node("judge", self._judge)
        builder.add_node("evaluation_router", self._evaluation_router)
        builder.add_node("critics", self._critics)
        builder.add_node("validator", self._validator)
        builder.add_node("validation_router", self._validation_router)
        builder.add_node("rewriter", self._rewriter)
        builder.add_node("verifier", self._verifier)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "design")
        builder.add_edge("design", "bootstrap")
        builder.add_edge("bootstrap", "judge")
        builder.add_edge("judge", "evaluation_router")
        builder.add_conditional_edges(
            "evaluation_router",
            self._evaluation_edge,
            {"review": "critics", "finish": "finalize"},
        )
        builder.add_edge("critics", "validator")
        builder.add_edge("validator", "validation_router")
        builder.add_conditional_edges(
            "validation_router",
            self._validation_edge,
            {"rewrite": "rewriter", "finish": "finalize"},
        )
        builder.add_conditional_edges(
            "rewriter",
            self._rewrite_edge,
            {"rewrite_ok": "verifier", "rewrite_failed": "finalize"},
        )
        builder.add_edge("verifier", "judge")
        builder.add_edge("finalize", END)
        return builder.compile()

    def run(
        self,
        task: LessonTask,
        config: ExperimentConfig,
        run_id: str | None = None,
    ) -> PipelineResult:
        config = self._effective_config(task, config)
        if config.execution_mode != self.agents.execution_mode:
            raise ValueError(
                "workflow and agent suite execution modes do not match: "
                f"{config.execution_mode!r} != {self.agents.execution_mode!r}"
            )
        if config.interaction_protocol != "independent_review":
            raise ValueError(
                "v0.1 implements only interaction_protocol='independent_review'"
            )
        if config.knowledge_policy != "heterogeneous":
            raise ValueError("v0.1 currently implements only heterogeneous knowledge")
        if config.enable_paper3:
            raise ValueError(
                "Paper#3 is available as an adapter but is not enabled in the v0.1 graph"
            )
        profile_ids = [
            config.designer_profile_id,
            config.writer_profile_id,
            *config.critic_profile_ids,
            config.validator_profile_id,
            config.judge_profile_id,
            config.rewriter_profile_id,
        ]
        validate_profile_references(profile_ids, self._profiles)
        bootstrap_profile_ids = [config.judge_profile_id]
        if task.mode == TaskMode.GENERATE:
            bootstrap_profile_ids = [
                config.designer_profile_id,
                config.writer_profile_id,
                config.judge_profile_id,
            ]
        bootstrap_attempt_reserve = self._worst_case_attempts(
            config, bootstrap_profile_ids
        )
        if config.max_model_calls < bootstrap_attempt_reserve:
            raise ValueError(
                "max_model_calls is too small for the initial pipeline with retries: "
                f"need at least {bootstrap_attempt_reserve}, got {config.max_model_calls}"
            )
        actual_run_id = run_id or self._run_id_factory(task)
        workspace = self.output_root / actual_run_id
        reserved_outputs = (
            "trace.jsonl",
            "run_result.json",
            "manifest.json",
            "best_lesson_plan.json",
            "best_lesson_plan.md",
            "best_lesson_plan.docx",
            "optimization_report.json",
            "optimization_report.md",
            "recovery_lesson_plan.json",
            "recovery_lesson_plan.md",
        )
        collisions = [name for name in reserved_outputs if (workspace / name).exists()]
        if collisions:
            raise FileExistsError(
                f"run_id {actual_run_id!r} already contains run artifacts: {collisions}; "
                "use a new run_id to keep traces and outputs isolated"
            )
        trace = TraceStore(workspace, actual_run_id, task.task_id, self._clock)
        self._traces[actual_run_id] = trace
        started_at = self._aware_now().isoformat()
        initial: PipelineState = {
            "schema_version": "paper4-graph-state-v0.1",
            "run_id": actual_run_id,
            "task": task.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "started_at": started_at,
            "workspace_dir": str(workspace),
            "trace_path": str(trace.path),
            "design_blueprint": None,
            "versions": [],
            "critique_history": [],
            "current_critique_batch": None,
            "validation_batches": [],
            "rewrite_records": [],
            "route_decisions": [],
            "version_selections": [],
            "iterations": [],
            "optimization_quality_gate": None,
            "optimization_comparison": None,
            "knowledge_bundles": [],
            "model_call_count": 0,
            "token_usage": TokenUsage().model_dump(mode="json"),
            "estimated_cost": 0.0,
            "score_deltas": [],
            "cycle_start": None,
            "pending_iteration": None,
            "stop_reason": None,
            "status": RunStatus.RUNNING.value,
            "errors": [],
        }
        assert_json_safe_state(initial)
        trace.append(
            event_type="run_started",
            stage="run",
            input_summary={
                "task": task.model_dump(mode="json"),
                "experiment_config": config.model_dump(mode="json"),
                "profile_ids": profile_ids,
            },
        )
        last_state = initial
        try:
            for snapshot in self.graph.stream(initial, stream_mode="values"):
                last_state = snapshot
                assert_json_safe_state(last_state)
        except Exception as exc:  # preserve trace and last completed graph snapshot
            message = f"{type(exc).__name__}: {exc}"
            failed_attempts = int(getattr(exc, "attempts", 0))
            failed_usage = getattr(exc, "usage", TokenUsage())
            if not isinstance(failed_usage, TokenUsage):
                failed_usage = TokenUsage()
            failed_cost = float(getattr(exc, "estimated_cost", 0.0))
            trace.append(
                event_type="run_failed",
                stage="run",
                status="error",
                error=message,
                output_summary={"last_completed_state_status": last_state.get("status")},
                token_usage=failed_usage,
                estimated_cost=failed_cost,
            )
            last_state = {
                **last_state,
                "status": RunStatus.FAILED.value,
                "stop_reason": StopReason.RUNTIME_ERROR.value,
                "errors": [*last_state.get("errors", []), message],
                "model_call_count": last_state.get("model_call_count", 0)
                + failed_attempts,
                "token_usage": self._sum_usage(
                    self._usage(last_state), failed_usage
                ).model_dump(mode="json"),
                "estimated_cost": last_state.get("estimated_cost", 0.0)
                + failed_cost,
            }
        result = self._project_result(last_state)
        del self._traces[actual_run_id]
        return result

    def _design(self, state: PipelineState) -> PipelineState:
        task = self._task(state)
        if task.mode != TaskMode.GENERATE:
            return {"design_blueprint": None}
        started = perf_counter()
        config = self._config(state)
        profile = self._profiles[config.designer_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.designer.design(task, knowledge)
        usage = self._sum_usage(self._usage(state), output.usage)
        self._trace(state).append(
            event_type="design_blueprint_completed",
            stage="design_architect",
            actor_profile_id=self.agents.designer.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            input_summary={
                "task": task.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "design_blueprint": output.value.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "design_blueprint": output.value.model_dump(mode="json"),
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": state["estimated_cost"] + output.estimated_cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }

    def _bootstrap(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        calls = state["model_call_count"]
        usage = self._usage(state)
        cost = state["estimated_cost"]
        bundles = list(state["knowledge_bundles"])
        if task.mode == TaskMode.GENERATE:
            profile = self._profiles[config.writer_profile_id]
            knowledge = build_knowledge_bundle(profile, task)
            blueprint = LessonDesignBlueprint.model_validate(
                state["design_blueprint"]
            )
            output = self.agents.writer.generate(task, knowledge, blueprint)
            document = output.value
            calls += self._attempt_count(output)
            usage = self._sum_usage(usage, output.usage)
            cost += output.estimated_cost
            bundles.append(knowledge.model_dump(mode="json"))
            actor = self.agents.writer.profile_id
            event_type = "writer_completed"
            trace_input = {
                "task": task.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            }
            trace_output = document.model_dump(mode="json")
            call_usage = output.usage
            call_cost = output.estimated_cost
            knowledge_id = knowledge.bundle_id
            call_metadata = self._call_metadata(output)
        else:
            assert task.initial_plan is not None
            document = task.initial_plan
            actor = "human_input"
            event_type = "input_version_registered"
            trace_input = {"task_mode": task.mode.value}
            trace_output = document.model_dump(mode="json")
            call_usage = TokenUsage()
            call_cost = 0.0
            knowledge_id = ""
            call_metadata = None

        rule_report = check_lesson_plan(
            document,
            task,
            config.duration_tolerance_minutes,
            report_id=f"rule-v0",
        )
        version = LessonPlanVersion(
            version_id="v0",
            iteration=0,
            document=document,
            created_by_profile_id=actor,
            created_at=self._aware_now(),
            document_hash=document_hash(document),
            rule_check_report=rule_report,
            diff_summary="初始生成稿" if task.mode == TaskMode.GENERATE else "用户输入稿",
            estimated_cost=cost,
        )
        self._trace(state).append(
            event_type=event_type,
            stage="bootstrap",
            actor_profile_id=actor,
            knowledge_bundle_id=knowledge_id,
            version_id=version.version_id,
            input_summary=trace_input,
            output_summary={
                "document": trace_output,
                "rule_report": rule_report.model_dump(mode="json"),
                "model_call": call_metadata,
            },
            token_usage=call_usage,
            estimated_cost=call_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [version.model_dump(mode="json")],
            "current_version_id": version.version_id,
            "model_call_count": calls,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": bundles,
        }

    def _judge(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        history = self._critique_history(state)
        unresolved_statuses = {
            CritiqueStatus.ACCEPTED,
            CritiqueStatus.PARTIALLY_IMPLEMENTED,
            CritiqueStatus.UNRESOLVED,
            CritiqueStatus.REOPENED,
            CritiqueStatus.REGRESSION,
        }
        unresolved = sum(item.status in unresolved_statuses for item in history)
        profile = self._profiles[config.judge_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.judge.evaluate(
            task, current, unresolved, knowledge
        )
        regressions = [
            item.critique_id
            for item in history
            if item.status == CritiqueStatus.REGRESSION
        ]
        report_data = output.value.model_dump(mode="python")
        report_data["regressions"] = regressions
        report_data["unresolved_issue_count"] = unresolved
        report = EvaluationReport.model_validate(report_data)
        version_data = current.model_dump(mode="python")
        version_data["internal_evaluation"] = report
        updated_current = LessonPlanVersion.model_validate(version_data)
        versions = [
            updated_current if item.version_id == current.version_id else item
            for item in self._versions(state)
        ]
        selection = select_best_version(
            versions, config,
            dedupe_equivalent_content=self._task(state).mode == TaskMode.OPTIMIZE,
            task_mode=task.mode,
        )
        usage = self._sum_usage(self._usage(state), output.usage)
        cost = state["estimated_cost"] + output.estimated_cost
        self._trace(state).append(
            event_type="judge_completed",
            stage="judge",
            actor_profile_id=self.agents.judge.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=current.iteration,
            version_id=current.version_id,
            input_summary={
                "document_hash": current.document_hash,
                "rule_report": current.rule_check_report.model_dump(mode="json"),
                "unresolved_issue_count": unresolved,
                "task_evidence_profile": build_task_evidence_profile(task),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "evaluation": report.model_dump(mode="json"),
                "version_selection": selection.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [item.model_dump(mode="json") for item in versions],
            "version_selections": [
                *state["version_selections"],
                selection.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }

    def _evaluation_router(self, state: PipelineState) -> PipelineState:
        current = self._current_version(state)
        assert current.internal_evaluation is not None
        config = self._config(state)
        task = self._task(state)
        score_deltas = list(state["score_deltas"])
        pending = state.get("pending_iteration")
        if pending:
            parent = self._version_by_id(state, str(pending["input_version_id"]))
            assert parent.internal_evaluation is not None
            score_deltas.append(
                current.internal_evaluation.overall_score
                - parent.internal_evaluation.overall_score
            )
        next_profiles = [
            *(critic.profile_id for critic in self.agents.critics),
            config.validator_profile_id,
            config.judge_profile_id,
        ]
        if task.mode != TaskMode.OPTIMIZE or not getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            next_profiles.append(config.rewriter_profile_id)
        required_calls = self._worst_case_attempts(config, next_profiles)
        if task.mode == TaskMode.OPTIMIZE and getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            required_calls += DEFAULT_MAX_ACCEPTS_PER_ROUND
        decision = route_after_evaluation(
            report=current.internal_evaluation,
            rule_report=current.rule_check_report,
            versions=self._versions(state),
            config=config,
            model_call_count=state["model_call_count"],
            token_usage=self._usage(state),
            estimated_cost=state["estimated_cost"],
            score_deltas=score_deltas,
            required_next_model_calls=required_calls,
            elapsed_seconds=self._elapsed_seconds(state),
            require_initial_review=(
                task.mode == TaskMode.OPTIMIZE
                and current.iteration == 0
            ),
            task_mode=task.mode,
        )
        routes = [*state["route_decisions"], decision.model_dump(mode="json")]
        iterations = list(state["iterations"])
        if pending:
            start_usage = TokenUsage.model_validate(pending["start_token_usage"])
            total_usage = self._usage(state)
            iteration = IterationRecord(
                iteration_id=str(pending["iteration_id"]),
                round_index=current.iteration,
                input_version_id=str(pending["input_version_id"]),
                output_version_id=current.version_id,
                critique_ids=list(pending["critique_ids"]),
                validation_decision_ids=list(pending["validation_decision_ids"]),
                evaluation_id=current.internal_evaluation.evaluation_id,
                rewrite_id=str(pending["rewrite_id"]),
                regressions=list(current.internal_evaluation.regressions),
                score_delta=score_deltas[-1],
                duration_seconds=max(
                    0.0,
                    self._elapsed_from_iso(str(pending["started_at"])),
                ),
                token_usage=TokenUsage(
                    input_tokens=max(
                        0, total_usage.input_tokens - start_usage.input_tokens
                    ),
                    output_tokens=max(
                        0, total_usage.output_tokens - start_usage.output_tokens
                    ),
                ),
                estimated_cost=max(
                    0.0,
                    state["estimated_cost"] - float(pending["start_cost"]),
                ),
                route=decision.next_action,
                route_decision_id=decision.decision_id,
            )
            iterations.append(iteration.model_dump(mode="json"))
        self._trace(state).append(
            event_type="route_decided",
            stage="evaluation_router",
            round_index=current.iteration,
            version_id=current.version_id,
            input_summary={
                "evaluation_id": current.internal_evaluation.evaluation_id,
                "model_call_count": state["model_call_count"],
                "token_usage": state["token_usage"],
                "elapsed_seconds": self._elapsed_seconds(state),
            },
            output_summary=decision.model_dump(mode="json"),
        )
        return {
            "route_decisions": routes,
            "iterations": iterations,
            "score_deltas": score_deltas,
            "pending_iteration": None,
            "stop_reason": decision.primary_reason.value
            if decision.primary_reason
            else None,
        }

    def _critics(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        cycle_started_at = self._aware_now().isoformat()
        task = self._task(state)
        current = self._current_version(state)
        round_index = current.iteration + 1
        config = self._config(state)
        history = self._critique_history(state)
        calls = state["model_call_count"]
        usage = self._usage(state)
        cost = state["estimated_cost"]
        bundles = list(state["knowledge_bundles"])
        all_items: list[CritiqueItem] = []
        node_attempts = 0
        node_usage = TokenUsage()
        node_cost = 0.0
        for critic in self.agents.critics:
            profile = self._profiles[critic.profile_id]
            knowledge = build_knowledge_bundle(profile, task)
            try:
                output = critic.review(
                    task,
                    current,
                    round_index,
                    knowledge,
                    prior_critiques=history,
                )
            except Exception as exc:
                failed_attempts = int(getattr(exc, "attempts", 0))
                failed_usage = getattr(exc, "usage", TokenUsage())
                if not isinstance(failed_usage, TokenUsage):
                    failed_usage = TokenUsage()
                failed_cost = float(getattr(exc, "estimated_cost", 0.0))
                self._trace(state).append(
                    event_type="critic_failed",
                    stage="critics",
                    actor_profile_id=critic.profile_id,
                    knowledge_bundle_id=knowledge.bundle_id,
                    round_index=round_index,
                    version_id=current.version_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    token_usage=failed_usage,
                    estimated_cost=failed_cost,
                    duration_seconds=perf_counter() - started,
                )
                raise _NodeExecutionError(
                    f"critic {critic.profile_id} failed: {type(exc).__name__}: {exc}",
                    attempts=node_attempts + failed_attempts,
                    usage=self._sum_usage(node_usage, failed_usage),
                    estimated_cost=node_cost + failed_cost,
                ) from exc
            attempt_count = self._attempt_count(output)
            node_attempts += attempt_count
            node_usage = self._sum_usage(node_usage, output.usage)
            node_cost += output.estimated_cost
            calls += attempt_count
            usage = self._sum_usage(usage, output.usage)
            cost += output.estimated_cost
            bundles.append(knowledge.model_dump(mode="json"))
            all_items.extend(output.value.items)
            self._trace(state).append(
                event_type="critic_completed",
                stage="critics",
                actor_profile_id=critic.profile_id,
                knowledge_bundle_id=knowledge.bundle_id,
                round_index=round_index,
                version_id=current.version_id,
                input_summary={
                    "document_hash": current.document_hash,
                    "agent_profile": profile.model_dump(mode="json"),
                    "knowledge_bundle": knowledge.model_dump(mode="json"),
                    "prior_critique_statuses": {
                        item.critique_id: item.status.value for item in history
                    },
                },
                output_summary={
                    "critique_batch": output.value.model_dump(mode="json"),
                    "model_call": self._call_metadata(output),
                },
                token_usage=output.usage,
                estimated_cost=output.estimated_cost,
            )
        reopened_history, reopened = reopen_cap_deferred_for_validation(
            history,
            round_index=round_index,
            version_id=current.version_id,
            exclude_ids={item.critique_id for item in all_items},
        )
        combined = CritiqueBatch(
            batch_id=stable_id("combined", current.version_id, round_index),
            plan_version_id=current.version_id,
            round_index=round_index,
            items=[*all_items, *reopened],
        )
        self._trace(state).append(
            event_type="critiques_aggregated",
            stage="critique_aggregator",
            round_index=round_index,
            version_id=current.version_id,
            output_summary={
                "critique_batch": combined.model_dump(mode="json"),
                "reopened_cap_deferred_ids": [
                    item.critique_id for item in reopened
                ],
            },
            duration_seconds=perf_counter() - started,
        )
        return {
            "current_critique_batch": combined.model_dump(mode="json"),
            "critique_history": [
                item.model_dump(mode="json") for item in reopened_history
            ],
            "model_call_count": calls,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "knowledge_bundles": bundles,
            "cycle_start": {
                "started_at": cycle_started_at,
                "token_usage": state["token_usage"],
                "cost": state["estimated_cost"],
            },
        }

    def _validator(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        batch = self._current_batch(state)
        profile = self._profiles[config.validator_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        output = self.agents.validator.validate(
            task, current, batch, batch.round_index, knowledge
        )
        validated = apply_validation(batch, output.value)
        history = merge_critique_history(self._critique_history(state), validated)
        usage = self._sum_usage(self._usage(state), output.usage)
        self._trace(state).append(
            event_type="validation_completed",
            stage="validator",
            actor_profile_id=self.agents.validator.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=current.version_id,
            input_summary={
                "critique_batch": batch.model_dump(mode="json"),
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "decisions": output.value.model_dump(mode="json"),
                "critique_lifecycle": validated.model_dump(mode="json"),
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "current_critique_batch": validated.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "validation_batches": [
                *state["validation_batches"],
                output.value.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": state["estimated_cost"] + output.estimated_cost,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }

    def _validation_router(self, state: PipelineState) -> PipelineState:
        batch = self._current_batch(state)
        config = self._config(state)
        task = self._task(state)
        required_calls = self._worst_case_attempts(
            config, [config.rewriter_profile_id, config.judge_profile_id],
        )
        if task.mode.value == "optimize" and getattr(
            self.agents.rewriter, "uses_per_critique_patches", False,
        ):
            # Optimization patches allow one schema-repair retry per accepted
            # critique. Reserve both attempts so the configured call budget
            # remains a hard boundary rather than being exceeded mid-round.
            required_calls = 2 * len(actionable_critiques(batch)) + self._worst_case_attempts(
                config, [config.judge_profile_id],
            )
        decision = route_after_validation(
            critiques=batch,
            config=config,
            model_call_count=state["model_call_count"],
            token_usage=self._usage(state),
            estimated_cost=state["estimated_cost"],
            required_next_model_calls=required_calls,
            elapsed_seconds=self._elapsed_seconds(state),
        )
        self._trace(state).append(
            event_type="route_decided",
            stage="validation_router",
            round_index=batch.round_index,
            version_id=batch.plan_version_id,
            input_summary={
                "critique_statuses": {
                    item.critique_id: item.status.value for item in batch.items
                }
            },
            output_summary=decision.model_dump(mode="json"),
        )
        return {
            "route_decisions": [
                *state["route_decisions"],
                decision.model_dump(mode="json"),
            ],
            "stop_reason": decision.primary_reason.value
            if decision.primary_reason
            else None,
        }

    def _rewriter(self, state: PipelineState) -> PipelineState:
        started = perf_counter()
        task = self._task(state)
        config = self._config(state)
        current = self._current_version(state)
        batch = self._current_batch(state)
        accepted = actionable_critiques(batch)
        profile = self._profiles[config.rewriter_profile_id]
        knowledge = build_knowledge_bundle(profile, task)
        try:
            output = self.agents.rewriter.rewrite(
                task,
                current,
                accepted,
                batch.round_index,
                knowledge,
            )
        except Exception as exc:
            # A rewrite is the only step that turns a reviewed draft into the
            # next version.  If the real model cannot produce a contract-valid
            # full-document rewrite after its capped retries, that must not
            # discard the whole run: mark the accepted critiques unresolved,
            # record the failure, and finish on the last safe version.
            return self._abort_rewrite(
                state,
                task=task,
                current=current,
                batch=batch,
                accepted=accepted,
                exc=exc,
                started=started,
                profile=profile,
                knowledge=knowledge,
            )
        new_version_id = f"v{batch.round_index}"
        rule_report = check_lesson_plan(
            output.value.document,
            task,
            config.duration_tolerance_minutes,
            report_id=f"rule-{new_version_id}",
        )
        updated_batch = apply_rewrite_outcome(
            batch,
            output.value,
            batch.round_index,
            new_version_id,
        )
        history = merge_critique_history(self._critique_history(state), updated_batch)
        rewrite_record = RewriteRecord(
            rewrite_id=stable_id("rewrite", current.version_id, new_version_id),
            input_version_id=current.version_id,
            output_version_id=new_version_id,
            strategy=(
                "targeted_patch" if output.metadata and
                output.metadata.prompt_id == "rewrite_patch_prompt"
                else "full_document" if output.metadata else "legacy_unknown"
            ),
            accepted_critique_ids=[item.critique_id for item in accepted],
            changes=output.value.changes,
            unresolved_critique_ids=output.value.unresolved_critique_ids,
            unresolved_reasons=output.value.unresolved_reasons,
        )
        usage = self._sum_usage(self._usage(state), output.usage)
        total_cost = state["estimated_cost"] + output.estimated_cost
        new_version = LessonPlanVersion(
            version_id=new_version_id,
            parent_version_id=current.version_id,
            iteration=batch.round_index,
            document=output.value.document,
            created_by_profile_id=self.agents.rewriter.profile_id,
            created_at=self._aware_now(),
            document_hash=document_hash(output.value.document),
            addressed_critique_ids=[
                item.critique_id
                for item in updated_batch.items
                if item.status
                in {
                    CritiqueStatus.IMPLEMENTED,
                    CritiqueStatus.PARTIALLY_IMPLEMENTED,
                }
            ],
            unresolved_critique_ids=list(output.value.unresolved_critique_ids),
            diff_summary=f"按 {len(output.value.changes)} 条已验证意见做局部修改",
            rule_check_report=rule_report,
            change_count=len(output.value.changes),
            estimated_cost=total_cost,
        )
        validation = ValidationBatch.model_validate(state["validation_batches"][-1])
        cycle = state.get("cycle_start") or {
            "started_at": self._aware_now().isoformat(),
            "token_usage": state["token_usage"],
            "cost": state["estimated_cost"],
        }
        pending = {
            "iteration_id": stable_id("iteration", state["run_id"], batch.round_index),
            "input_version_id": current.version_id,
            "output_version_id": new_version_id,
            "critique_ids": [item.critique_id for item in batch.items],
            "validation_decision_ids": [
                item.decision_id for item in validation.decisions
            ],
            "rewrite_id": rewrite_record.rewrite_id,
            "started_at": cycle["started_at"],
            "start_token_usage": cycle["token_usage"],
            "start_cost": cycle["cost"],
        }
        self._trace(state).append(
            event_type="rewrite_completed",
            stage="rewriter",
            actor_profile_id=self.agents.rewriter.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=new_version_id,
            input_summary={
                "input_version_id": current.version_id,
                "accepted_critiques": [
                    item.model_dump(mode="json") for item in accepted
                ],
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "rewrite_outcome": output.value.model_dump(mode="json"),
                "rewrite_record": rewrite_record.model_dump(mode="json"),
                "rule_report": rule_report.model_dump(mode="json"),
                "document_hash": new_version.document_hash,
                "model_call": self._call_metadata(output),
            },
            token_usage=output.usage,
            estimated_cost=output.estimated_cost,
            duration_seconds=perf_counter() - started,
        )
        return {
            "versions": [
                *state["versions"],
                new_version.model_dump(mode="json"),
            ],
            "current_version_id": new_version_id,
            "current_critique_batch": updated_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "rewrite_records": [
                *state["rewrite_records"],
                rewrite_record.model_dump(mode="json"),
            ],
            "model_call_count": state["model_call_count"]
            + self._attempt_count(output),
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": total_cost,
            "pending_iteration": pending,
            "knowledge_bundles": [
                *state["knowledge_bundles"],
                knowledge.model_dump(mode="json"),
            ],
        }

    def _abort_rewrite(
        self,
        state: PipelineState,
        *,
        task: LessonTask,
        current: LessonPlanVersion,
        batch: CritiqueBatch,
        accepted: list[CritiqueItem],
        exc: Exception,
        started: float,
        profile: AgentProfile,
        knowledge: KnowledgeBundle,
    ) -> PipelineState:
        """Turn a failed rewrite into a recorded, reviewable stop.

        Accepted critiques are transitioned to UNRESOLVED so the ledger never
        claims an implemented fix that does not exist, the failure is preserved
        in ``errors`` and the trace, and routing finishes on the best
        already-reviewed version.  A usable prior version means this is a
        NEEDS_HUMAN outcome, not a total pipeline failure: no unverified edit
        is accepted, while the successfully generated draft remains a normal
        deliverable for manual review.
        """
        message = f"{type(exc).__name__}: {exc}"
        failed_attempts = int(getattr(exc, "attempts", 1))
        failed_usage = getattr(exc, "usage", TokenUsage())
        if not isinstance(failed_usage, TokenUsage):
            failed_usage = TokenUsage()
        failed_cost = float(getattr(exc, "estimated_cost", 0.0))
        usage = self._sum_usage(self._usage(state), failed_usage)
        cost = state["estimated_cost"] + failed_cost

        updated_items: list[CritiqueItem] = []
        for item in batch.items:
            if item.status == CritiqueStatus.ACCEPTED:
                item = transition_critique(
                    item,
                    CritiqueStatus.UNRESOLVED,
                    round_index=batch.round_index,
                    version_id=current.version_id,
                    note="rewriter failed; accepted critique was not implemented",
                )
            updated_items.append(item)
        updated_batch_payload = batch.model_dump(mode="python")
        updated_batch_payload["items"] = updated_items
        updated_batch = CritiqueBatch.model_validate(updated_batch_payload)
        history = merge_critique_history(self._critique_history(state), updated_batch)
        if not accepted:
            # Nothing was accepted, so this is effectively a validation_router
            # stop rather than a failed rewrite attempt.
            decision = RouteDecision(
                decision_id=f"route-rewrite-empty-{batch.round_index}",
                next_action=RouteAction.FINALIZE,
                primary_reason=StopReason.NO_ACTIONABLE_FEEDBACK,
                triggered_reasons=[],
                explanation="没有可执行的已接受意见，无法进入改写。",
            )
        else:
            decision = RouteDecision(
                decision_id=f"route-rewrite-abort-{batch.round_index}",
                next_action=RouteAction.HUMAN_REVIEW,
                primary_reason=StopReason.REWRITE_FAILED,
                triggered_reasons=[StopReason.REWRITE_FAILED],
                explanation=(
                    "改写多次尝试仍无法产出满足契约的新版本；已将本轮接受意见"
                    "标为未解决，保留上一个安全版本并转人工复核。"
                ),
            )
        self._trace(state).append(
            event_type="rewrite_aborted",
            stage="rewriter",
            actor_profile_id=self.agents.rewriter.profile_id,
            knowledge_bundle_id=knowledge.bundle_id,
            round_index=batch.round_index,
            version_id=current.version_id,
            error=message,
            input_summary={
                "accepted_critique_ids": [
                    item.critique_id for item in accepted
                ],
                "agent_profile": profile.model_dump(mode="json"),
                "knowledge_bundle": knowledge.model_dump(mode="json"),
            },
            output_summary={
                "decision": decision.model_dump(mode="json"),
                "critique_statuses": {
                    item.critique_id: item.status.value for item in history
                },
            },
            token_usage=failed_usage,
            estimated_cost=failed_cost,
            duration_seconds=perf_counter() - started,
            status="error",
        )
        return {
            "current_critique_batch": updated_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
            "route_decisions": [
                *state["route_decisions"],
                decision.model_dump(mode="json"),
            ],
            "stop_reason": decision.primary_reason.value,
            "pending_iteration": None,
            "model_call_count": state["model_call_count"] + failed_attempts,
            "token_usage": usage.model_dump(mode="json"),
            "estimated_cost": cost,
            "errors": [*state.get("errors", []), message],
        }

    def _verifier(self, state: PipelineState) -> PipelineState:
        current = self._current_version(state)
        batch = self._current_batch(state)
        verified_batch = verify_rewrite(
            batch,
            current.document,
            batch.round_index,
            current.version_id,
        )
        history = merge_critique_history(
            self._critique_history(state), verified_batch
        )
        history = detect_regressions(
            history,
            current.document,
            batch.round_index,
            current.version_id,
        )
        replacements = {item.critique_id: item for item in history}
        verified_payload = verified_batch.model_dump(mode="python")
        verified_payload["items"] = [
            replacements[item.critique_id] for item in verified_batch.items
        ]
        verified_batch = CritiqueBatch.model_validate(verified_payload)
        self._trace(state).append(
            event_type="rewrite_verified",
            stage="verifier",
            round_index=batch.round_index,
            version_id=current.version_id,
            input_summary={"rewrite_version_hash": current.document_hash},
            output_summary={
                "critique_statuses": {
                    item.critique_id: item.status.value for item in history
                }
            },
        )
        return {
            "current_critique_batch": verified_batch.model_dump(mode="json"),
            "critique_history": [item.model_dump(mode="json") for item in history],
        }

    def _finalize(self, state: PipelineState) -> PipelineState:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        selection = VersionSelection.model_validate(state["version_selections"][-1])
        updates: PipelineState = {}
        if self._task(state).mode == TaskMode.OPTIMIZE:
            versions = self._versions(state)
            baseline = min(versions, key=lambda item: (item.iteration, item.version_id))
            candidate = next(
                item for item in versions if item.version_id == selection.selected_version_id
            )
            quality_gate = optimization_quality_gate(baseline, candidate, self._config(state))
            updates["optimization_quality_gate"] = quality_gate
            comparator = getattr(self.agents.judge, "compare_optimization", None)
            if (
                callable(comparator)
                and decision.next_action not in {RouteAction.FAIL, RouteAction.ROLLBACK}
                and content_hash(baseline.document) != content_hash(candidate.document)
                and state["model_call_count"] + 2 <= self._config(state).max_model_calls
                and self._usage(state).total_tokens + 80_000
                <= self._config(state).max_total_tokens
                and state["estimated_cost"] + 0.5
                <= self._config(state).max_estimated_cost
            ):
                started = perf_counter()
                comparison_output = comparator(self._task(state), baseline, candidate)
                comparison = comparison_output.value.model_dump(mode="json")
                updates["optimization_comparison"] = comparison
                updates["model_call_count"] = (
                    state["model_call_count"]
                    + (comparison_output.metadata.attempts if comparison_output.metadata else 0)
                )
                updates["token_usage"] = self._sum_usage(
                    self._usage(state), comparison_output.usage
                ).model_dump(mode="json")
                updates["estimated_cost"] = (
                    state["estimated_cost"] + comparison_output.estimated_cost
                )
                self._trace(state).append(
                    event_type="optimization_pairwise_compared",
                    stage="optimization_compare",
                    actor_profile_id=self.agents.judge.profile_id,
                    version_id=candidate.version_id,
                    input_summary={
                        "baseline_version_id": baseline.version_id,
                        "candidate_version_id": candidate.version_id,
                        "changed_sections": comparison["changed_sections"],
                    },
                    output_summary={
                        "comparison": comparison,
                        "model_call": self._call_metadata(comparison_output),
                    },
                    token_usage=comparison_output.usage,
                    estimated_cost=comparison_output.estimated_cost,
                    duration_seconds=perf_counter() - started,
                )
                if (
                    comparison["verdict"] == "baseline_preferred"
                    and baseline.version_id in selection.eligible_candidate_ids
                ):
                    payload = selection.model_dump(mode="python")
                    payload["selected_version_id"] = baseline.version_id
                    payload["requires_human"] = True
                    payload["selection_reason"] = (
                        "双向独立比较均倾向原稿；保留原稿为交付稿，"
                        "修订候选稿仍可供教师对照复核。"
                    )
                    selection = VersionSelection.model_validate(payload)
                    updates["optimization_quality_gate"] = optimization_quality_gate(
                        baseline, baseline, self._config(state)
                    )
                elif comparison["verdict"] == "candidate_preferred" and quality_gate["passed"]:
                    payload = selection.model_dump(mode="python")
                    payload["requires_human"] = False
                    payload["ambiguous_candidate_ids"] = []
                    payload["selection_reason"] = (
                        "真实内容变化通过内部质量门槛，且双向独立比较均偏好修订稿；"
                        "仍非真实课堂效果证明。"
                    )
                    selection = VersionSelection.model_validate(payload)
                updates["version_selections"] = [
                    *state["version_selections"][:-1], selection.model_dump(mode="json")
                ]
            elif content_hash(baseline.document) != content_hash(candidate.document):
                updates["optimization_comparison"] = {
                    "baseline_version_id": baseline.version_id,
                    "candidate_version_id": candidate.version_id,
                    "verdict": "uncertain",
                    "target_issue_progress": "uncertain",
                    "changed_sections": [],
                    "regression_flags": [],
                    "evidence": [],
                    "votes": [],
                    "failed_calls": 0,
                    "reason": (
                        "双顺序对照未执行：比较器不可用。"
                        if not callable(comparator)
                        else "双顺序对照未执行：运行状态或预算不足，修订稿只能待教师复核。"
                    ),
                }
        # ``requires_human`` is set by best-version selection when the top two
        # candidates are statistically tied (or when every candidate was
        # eliminated and the earliest safe draft is a fallback).  Consume it at
        # the final stop: if the run is ending on an ambiguous or fallback
        # choice (and quality was not cleanly passed), surface NEEDS_HUMAN
        # instead of silently exporting an arbitrary pick.
        if decision.next_action in {RouteAction.FAIL, RouteAction.ROLLBACK}:
            # A regression guard has no rollback node in v0.1, so stopping on
            # ROLLBACK is a safety failure, never a false "completed": the run
            # stops and an explicitly named recovery draft is exported for review.
            status = RunStatus.FAILED
        elif decision.next_action == RouteAction.HUMAN_REVIEW or (
            decision.next_action == RouteAction.FINALIZE
            and selection.requires_human
            and (
                self._task(state).mode == TaskMode.OPTIMIZE
                or decision.primary_reason != StopReason.QUALITY_PASSED
            )
        ):
            status = RunStatus.NEEDS_HUMAN
        else:
            status = RunStatus.COMPLETED
        stop_reason = decision.primary_reason or StopReason.RUNTIME_ERROR
        if (
            self._task(state).mode == TaskMode.OPTIMIZE
            and decision.primary_reason == StopReason.QUALITY_PASSED
            and selection.requires_human
        ):
            stop_reason = StopReason.HUMAN_STOP
        self._trace(state).append(
            event_type="run_completed",
            stage="finalize",
            version_id=selection.selected_version_id,
            output_summary={
                "status": status.value,
                "stop_reason": stop_reason.value,
                "best_version_id": selection.selected_version_id,
                "last_version_id": state["current_version_id"],
            },
            status="ok" if status == RunStatus.COMPLETED else status.value,
        )
        return {**updates, "status": status.value, "stop_reason": stop_reason.value}

    @staticmethod
    def _evaluation_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "review" if decision.next_action == RouteAction.CONTINUE_REVIEW else "finish"

    @staticmethod
    def _validation_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "rewrite" if decision.next_action == RouteAction.REWRITE else "finish"

    @staticmethod
    def _rewrite_edge(state: PipelineState) -> str:
        decision = RouteDecision.model_validate(state["route_decisions"][-1])
        return "rewrite_ok" if decision.next_action == RouteAction.REWRITE else "rewrite_failed"

    def _project_result(self, state: PipelineState) -> PipelineResult:
        versions = self._versions(state)
        selections = [
            VersionSelection.model_validate(item)
            for item in state.get("version_selections", [])
        ]
        best_id = selections[-1].selected_version_id if selections else (
            versions[0].version_id if versions else ""
        )
        last_id = state.get("current_version_id", "") if versions else ""
        stop_raw = state.get("stop_reason")
        return PipelineResult(
            run_id=state["run_id"],
            task_id=self._task(state).task_id,
            task_mode=self._task(state).mode,
            experiment_id=self._config(state).experiment_id,
            method_id=self._config(state).method_id,
            status=RunStatus(state.get("status", RunStatus.FAILED.value)),
            stop_reason=StopReason(stop_raw) if stop_raw else None,
            best_version_id=best_id,
            last_version_id=last_id,
            design_blueprint=(
                LessonDesignBlueprint.model_validate(state["design_blueprint"])
                if state.get("design_blueprint")
                else None
            ),
            versions=versions,
            critiques=self._critique_history(state),
            validation_batches=[
                ValidationBatch.model_validate(item)
                for item in state.get("validation_batches", [])
            ],
            rewrite_records=[
                RewriteRecord.model_validate(item)
                for item in state.get("rewrite_records", [])
            ],
            route_decisions=[
                RouteDecision.model_validate(item)
                for item in state.get("route_decisions", [])
            ],
            version_selections=selections,
            iterations=[
                IterationRecord.model_validate(item)
                for item in state.get("iterations", [])
            ],
            optimization_quality_gate=state.get("optimization_quality_gate"),
            optimization_comparison=state.get("optimization_comparison"),
            model_call_count=state.get("model_call_count", 0),
            token_usage=TokenUsage.model_validate(
                state.get("token_usage", TokenUsage().model_dump(mode="json"))
            ),
            estimated_cost=state.get("estimated_cost", 0.0),
            trace_path=state.get("trace_path", ""),
            errors=state.get("errors", []),
        )

    def _trace(self, state: PipelineState) -> TraceStore:
        return self._traces[state["run_id"]]

    @staticmethod
    def _task(state: PipelineState) -> LessonTask:
        return LessonTask.model_validate(state["task"])

    @staticmethod
    def _config(state: PipelineState) -> ExperimentConfig:
        return ExperimentConfig.model_validate(state["config"])

    @staticmethod
    def _effective_config(task: LessonTask, config: ExperimentConfig) -> ExperimentConfig:
        """Keep generation's budget unchanged while giving revision its own cap."""

        if task.mode != TaskMode.OPTIMIZE:
            return config
        payload = config.model_dump(mode="python")
        if config.optimization_max_model_calls is not None:
            payload["max_model_calls"] = config.optimization_max_model_calls
        if config.optimization_max_total_tokens is not None:
            payload["max_total_tokens"] = config.optimization_max_total_tokens
        return ExperimentConfig.model_validate(payload)

    @staticmethod
    def _versions(state: PipelineState) -> list[LessonPlanVersion]:
        return [LessonPlanVersion.model_validate(item) for item in state.get("versions", [])]

    def _current_version(self, state: PipelineState) -> LessonPlanVersion:
        return self._version_by_id(state, state["current_version_id"])

    def _version_by_id(self, state: PipelineState, version_id: str) -> LessonPlanVersion:
        return next(item for item in self._versions(state) if item.version_id == version_id)

    @staticmethod
    def _critique_history(state: PipelineState) -> list[CritiqueItem]:
        return [
            CritiqueItem.model_validate(item)
            for item in state.get("critique_history", [])
        ]

    @staticmethod
    def _current_batch(state: PipelineState) -> CritiqueBatch:
        raw = state.get("current_critique_batch")
        if raw is None:
            raise ValueError("current critique batch is missing")
        return CritiqueBatch.model_validate(raw)

    @staticmethod
    def _usage(state: PipelineState) -> TokenUsage:
        return TokenUsage.model_validate(state["token_usage"])

    @staticmethod
    def _sum_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=left.input_tokens + right.input_tokens,
            output_tokens=left.output_tokens + right.output_tokens,
        )

    @staticmethod
    def _attempt_count(output: AgentOutput) -> int:
        return output.metadata.attempts if output.metadata else 1

    @staticmethod
    def _worst_case_attempts(
        config: ExperimentConfig,
        profile_ids: list[str],
    ) -> int:
        """Reserve every configured retry so max_model_calls is a hard boundary."""

        return sum(
            config.role_model_configs[profile_id].max_retries + 1
            for profile_id in profile_ids
        )

    @staticmethod
    def _call_metadata(output: AgentOutput) -> dict[str, object] | None:
        return asdict(output.metadata) if output.metadata else None

    def _aware_now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _elapsed_seconds(self, state: PipelineState) -> float:
        return self._elapsed_from_iso(state["started_at"])

    def _elapsed_from_iso(self, raw: str) -> float:
        started = datetime.fromisoformat(raw)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (self._aware_now() - started).total_seconds())
