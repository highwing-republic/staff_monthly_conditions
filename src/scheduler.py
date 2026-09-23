"""月間シフト自動作成 Solver（OR-Tools CP-SAT, §28〜§41）.

構造は T30 で固定（§40）。以降、大規模構造変更禁止。

    build_model()
        _create_variables()
        _add_*_constraints()      HC01〜HC12
        _create_*_terms()         Stage 1〜4 の目的関数項
    solve_lexicographically()     段階最適化（§36〜§38）
"""

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from src.constants import (
    PREFERENCE_PREFER_OFF,
    PREFERENCE_PREFER_WORK,
    PREFERENCE_UNAVAILABLE,
    SOLVER_CP_MODEL_PRESOLVE,
    SOLVER_NUM_WORKERS,
    SOLVER_RANDOM_SEED,
    SOLVER_STATUS_FEASIBLE,
    SOLVER_STATUS_INFEASIBLE,
    SOLVER_STATUS_OPTIMAL,
    SOLVER_STATUS_UNKNOWN,
    TOTAL_SOLVE_TIME_LIMIT_SECONDS,
)
from src.models import (
    AssignmentResult,
    DailyRequirementInput,
    MonthlyConditionInput,
    SchedulerInput,
    SchedulerResult,
    StaffInput,
    StageObjectiveResult,
)
from src.month_utils import get_month_dates, round_half_up_workdays, weekday_index

Key = tuple[int, str]  # (staff_id, work_date)

STAGES = (1, 2, 3, 4)

_STATUS_NAMES = {
    cp_model.OPTIMAL: SOLVER_STATUS_OPTIMAL,
    cp_model.FEASIBLE: SOLVER_STATUS_FEASIBLE,
    cp_model.INFEASIBLE: SOLVER_STATUS_INFEASIBLE,
    cp_model.UNKNOWN: SOLVER_STATUS_UNKNOWN,
}


@dataclass
class ScheduleModel:
    """build_model() の結果. Solverに渡すCP-SATモデルと入力の索引を保持する."""

    scheduler_input: SchedulerInput
    model: cp_model.CpModel
    staff: list[StaffInput]  # activeのみ, staff_id順
    dates: list[str]
    x: dict[Key, cp_model.IntVar] = field(default_factory=dict)

    conditions: dict[int, MonthlyConditionInput] = field(default_factory=dict)
    requirements: dict[str, DailyRequirementInput] = field(default_factory=dict)
    role_requirements: dict[tuple[str, int], int] = field(default_factory=dict)
    preferences: dict[Key, str] = field(default_factory=dict)
    locks: dict[Key, bool] = field(default_factory=dict)

    # Stage 1〜4 の目的関数（各項の合計を最小化）
    overstaff_terms: list = field(default_factory=list)
    target_deviation_terms: list = field(default_factory=list)
    prefer_off_terms: list = field(default_factory=list)
    prefer_work_terms: list = field(default_factory=list)

    def stage_objective(self, stage: int) -> cp_model.LinearExpr:
        terms = {
            1: self.overstaff_terms,
            2: self.target_deviation_terms,
            3: self.prefer_off_terms,
            4: self.prefer_work_terms,
        }[stage]
        return cp_model.LinearExpr.sum(terms)

    def day_total(self, work_date: str) -> cp_model.LinearExpr:
        return cp_model.LinearExpr.sum([self.x[s.staff_id, work_date] for s in self.staff])

    def actual_minutes(self, staff: StaffInput) -> cp_model.LinearExpr:
        """T38: actual_minutes[s] = Σd x[s,d] * daily_work_minutes[s]."""
        return self.actual_workdays(staff) * staff.daily_work_minutes

    def actual_workdays(self, staff: StaffInput) -> cp_model.LinearExpr:
        return cp_model.LinearExpr.sum([self.x[staff.staff_id, d] for d in self.dates])


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_model(scheduler_input: SchedulerInput) -> ScheduleModel:
    """入力からCP-SATモデルを構築する. 入力の妥当性は precheck 済みを前提とする."""
    dates = get_month_dates(scheduler_input.year_month)
    date_set = set(dates)
    staff = sorted((s for s in scheduler_input.staff if s.active), key=lambda s: s.staff_id)
    staff_ids = {s.staff_id for s in staff}

    sm = ScheduleModel(
        scheduler_input=scheduler_input,
        model=cp_model.CpModel(),
        staff=staff,
        dates=dates,
    )
    sm.conditions = {
        c.staff_id: c
        for c in scheduler_input.monthly_conditions
        if c.year_month == scheduler_input.year_month and c.staff_id in staff_ids
    }
    sm.requirements = {
        r.work_date: r for r in scheduler_input.daily_requirements if r.work_date in date_set
    }
    sm.role_requirements = {
        (r.work_date, r.role_id): r.required_count
        for r in scheduler_input.role_requirements
        if r.work_date in date_set
    }
    sm.preferences = {
        (p.staff_id, p.work_date): p.preference_type
        for p in scheduler_input.preferences
        if p.staff_id in staff_ids and p.work_date in date_set
    }
    sm.locks = {
        (a.staff_id, a.work_date): a.is_working
        for a in scheduler_input.locked_assignments
        if a.staff_id in staff_ids and a.work_date in date_set
    }

    _create_variables(sm)

    _add_weekday_constraints(sm)
    _add_unavailable_constraints(sm)
    _add_staffing_constraints(sm)
    _add_zero_staffing_constraints(sm)
    _add_max_staff_constraints(sm)
    _add_role_constraints(sm)
    _add_max_minutes_constraints(sm)
    _add_min_minutes_constraints(sm)
    _add_consecutive_constraints(sm)
    _add_carryover_constraints(sm)
    _add_lock_constraints(sm)

    _create_overstaff_terms(sm)
    _create_target_deviation_terms(sm)
    _create_prefer_off_terms(sm)
    _create_prefer_work_terms(sm)
    return sm


def _create_variables(sm: ScheduleModel) -> None:
    """T31: x[s,d] ∈ {0,1}（1=出勤, 0=休み）."""
    for staff in sm.staff:
        for work_date in sm.dates:
            sm.x[staff.staff_id, work_date] = sm.model.new_bool_var(
                f"x_{staff.staff_id}_{work_date}"
            )


# ---------------------------------------------------------------------------
# Hard Constraints（§29）
# ---------------------------------------------------------------------------


def _add_weekday_constraints(sm: ScheduleModel) -> None:
    """HC01: 通常勤務不可曜日は休み."""
    for staff in sm.staff:
        for work_date in sm.dates:
            if not staff.is_available_on(weekday_index(work_date)):
                sm.model.add(sm.x[staff.staff_id, work_date] == 0)


def _add_unavailable_constraints(sm: ScheduleModel) -> None:
    """HC02: UNAVAILABLE は休み."""
    for key, preference_type in sm.preferences.items():
        if preference_type == PREFERENCE_UNAVAILABLE:
            sm.model.add(sm.x[key] == 0)


def _add_staffing_constraints(sm: ScheduleModel) -> None:
    """HC03: Σs x[s,d] >= required_total_staff[d]."""
    for work_date, req in sm.requirements.items():
        if req.required_total_staff > 0:
            sm.model.add(sm.day_total(work_date) >= req.required_total_staff)


def _add_zero_staffing_constraints(sm: ScheduleModel) -> None:
    """HC04: 必要人数0の日は Σs x[s,d] = 0."""
    for work_date, req in sm.requirements.items():
        if req.required_total_staff == 0:
            sm.model.add(sm.day_total(work_date) == 0)


def _add_max_staff_constraints(sm: ScheduleModel) -> None:
    """HC05: Σs x[s,d] <= max_total_staff[d]（設定時）."""
    for work_date, req in sm.requirements.items():
        if req.max_total_staff is not None:
            sm.model.add(sm.day_total(work_date) <= req.max_total_staff)


def _add_role_constraints(sm: ScheduleModel) -> None:
    """HC06: Σ(role[s]=r) x[s,d] >= required_role[d,r]（role_idベース）."""
    for (work_date, role_id), required_count in sm.role_requirements.items():
        if required_count <= 0:
            continue
        role_vars = [sm.x[s.staff_id, work_date] for s in sm.staff if s.role_id == role_id]
        sm.model.add(cp_model.LinearExpr.sum(role_vars) >= required_count)


def _add_max_minutes_constraints(sm: ScheduleModel) -> None:
    """HC07: actual_minutes[s] <= max_monthly_minutes[s]（設定時）."""
    for staff in sm.staff:
        cond = sm.conditions.get(staff.staff_id)
        if cond is not None and cond.max_monthly_minutes is not None:
            sm.model.add(sm.actual_minutes(staff) <= cond.max_monthly_minutes)


def _add_min_minutes_constraints(sm: ScheduleModel) -> None:
    """HC08: actual_minutes[s] >= min_monthly_minutes[s]（設定時）."""
    for staff in sm.staff:
        cond = sm.conditions.get(staff.staff_id)
        if cond is not None and cond.min_monthly_minutes is not None:
            sm.model.add(sm.actual_minutes(staff) >= cond.min_monthly_minutes)


def _add_consecutive_constraints(sm: ScheduleModel) -> None:
    """HC09: 最大連勤M → 月内の任意のM+1日間で Σx <= M."""
    for staff in sm.staff:
        window = staff.max_consecutive_days + 1
        for start in range(len(sm.dates) - window + 1):
            window_vars = [sm.x[staff.staff_id, d] for d in sm.dates[start : start + window]]
            sm.model.add(cp_model.LinearExpr.sum(window_vars) <= staff.max_consecutive_days)


def _add_carryover_constraints(sm: ScheduleModel) -> None:
    """HC10: 前月連勤C → 最初の(M-C+1)日間の勤務数 <= M-C.

    前月末から続く連勤が月をまたいで M を超えないようにする。
    月初から始まる窓以外（前月にかからない窓）は HC09 が担う。
    """
    for staff in sm.staff:
        cond = sm.conditions.get(staff.staff_id)
        carryover = cond.carryover_consecutive_days if cond is not None else 0
        if carryover <= 0:
            continue
        limit = staff.max_consecutive_days - carryover
        if limit < 0:
            # C > M は precheck(PC13) で弾く入力。緩和せず不成立にする
            sm.model.add_bool_or([])
            continue
        window_vars = [sm.x[staff.staff_id, d] for d in sm.dates[: limit + 1]]
        sm.model.add(cp_model.LinearExpr.sum(window_vars) <= limit)


def _add_lock_constraints(sm: ScheduleModel) -> None:
    """HC11: 固定出勤 x=1 / HC12: 固定休日 x=0."""
    for key, is_working in sm.locks.items():
        sm.model.add(sm.x[key] == (1 if is_working else 0))


# ---------------------------------------------------------------------------
# Objective terms（§32〜§35）
# ---------------------------------------------------------------------------


def _create_overstaff_terms(sm: ScheduleModel) -> None:
    """Stage 1: overstaff[d] = actual_staff[d] - required_total_staff[d].

    HC03/HC04 により各項は常に0以上。下限0を変数の定義域で明示しないと
    CP-SAT（num_workers=1）が目的値の下界を証明できず時間切れになるため、変数として持つ。
    """
    for work_date, req in sm.requirements.items():
        overstaff = sm.model.new_int_var(
            0, max(0, len(sm.staff) - req.required_total_staff), f"overstaff_{work_date}"
        )
        sm.model.add(overstaff == sm.day_total(work_date) - req.required_total_staff)
        sm.overstaff_terms.append(overstaff)


def _create_target_deviation_terms(sm: ScheduleModel) -> None:
    """Stage 2: |actual_workdays - target_workdays| をスタッフごとに作る."""
    days = len(sm.dates)
    for staff in sm.staff:
        cond = sm.conditions.get(staff.staff_id)
        if cond is None:
            continue
        target_workdays = round_half_up_workdays(
            cond.target_monthly_minutes, staff.daily_work_minutes
        )
        deviation = sm.model.new_int_var(
            0, max(days, target_workdays), f"deviation_{staff.staff_id}"
        )
        sm.model.add_abs_equality(deviation, sm.actual_workdays(staff) - target_workdays)
        sm.target_deviation_terms.append(deviation)


def _create_prefer_off_terms(sm: ScheduleModel) -> None:
    """Stage 3: PREFER_OFF なのに出勤した件数."""
    for key, preference_type in sorted(sm.preferences.items()):
        if preference_type == PREFERENCE_PREFER_OFF:
            sm.prefer_off_terms.append(sm.x[key])


def _create_prefer_work_terms(sm: ScheduleModel) -> None:
    """Stage 4: PREFER_WORK なのに休日になった件数."""
    for key, preference_type in sorted(sm.preferences.items()):
        if preference_type == PREFERENCE_PREFER_WORK:
            sm.prefer_work_terms.append(1 - sm.x[key])


# ---------------------------------------------------------------------------
# Solve（§36〜§38）
# ---------------------------------------------------------------------------


def generate_schedule(scheduler_input: SchedulerInput) -> SchedulerResult:
    """build_model → solve_lexicographically."""
    return solve_lexicographically(build_model(scheduler_input))


def solve_lexicographically(
    sm: ScheduleModel,
    time_limit_seconds: float = TOTAL_SOLVE_TIME_LIMIT_SECONDS,
) -> SchedulerResult:
    """Stage 1→4 の段階最適化. 時間制限は4 Stage合計（§38.1）."""
    started = time.monotonic()
    objectives: dict[int, int] = {}
    stage_results: list[StageObjectiveResult] = []
    solution: dict[Key, bool] | None = None
    completed_stage = 0
    all_optimal = True

    for stage in STAGES:
        remaining = time_limit_seconds - (time.monotonic() - started)
        if remaining <= 0:
            if solution is None:
                # Stage 1 を実行できず解なし → UNKNOWN（§38.3）
                return SchedulerResult(status=SOLVER_STATUS_UNKNOWN, stage_results=stage_results)
            # §38.1: 以降のStageは実行せず、取得済みの最新Stageの解を返す
            all_optimal = False
            break

        objective = sm.stage_objective(stage)
        sm.model.minimize(objective)
        sm.model.clear_hints()
        if solution is not None:
            # §38.2: hint は探索の高速化のみ。目的値の維持は下の == 制約で行う
            for key, var in sm.x.items():
                sm.model.add_hint(var, solution[key])

        status, solver = _run_solver(sm.model, remaining)

        if status in (SOLVER_STATUS_OPTIMAL, SOLVER_STATUS_FEASIBLE):
            value = round(solver.objective_value)
            objectives[stage] = value
            stage_results.append(StageObjectiveResult(stage, status, value))
            solution = {key: solver.boolean_value(var) for key, var in sm.x.items()}
            completed_stage = stage
            if status != SOLVER_STATUS_OPTIMAL:
                all_optimal = False
            # §36: 前Stage目的値 == 取得した最良値
            sm.model.add(objective == value)
            continue

        stage_results.append(StageObjectiveResult(stage, status))
        if stage == 1:
            # §37 / §38.3: Hard Constraintを満たす解が未確認 → シフトを返さない
            return SchedulerResult(status=status, stage_results=stage_results)
        # §38.3: Stage 2〜4 が解なし → 直前Stageの解へフォールバック
        all_optimal = False
        break

    overall = (
        SOLVER_STATUS_OPTIMAL if all_optimal and completed_stage == 4 else SOLVER_STATUS_FEASIBLE
    )
    return SchedulerResult(
        status=overall,
        assignments=_to_assignments(sm, solution),
        completed_stage=completed_stage,
        objective_overstaff=objectives.get(1),
        objective_target_deviation=objectives.get(2),
        objective_prefer_off=objectives.get(3),
        objective_prefer_work=objectives.get(4),
        stage_results=stage_results,
    )


def _run_solver(model: cp_model.CpModel, max_time_in_seconds: float) -> tuple[str, cp_model.CpSolver]:
    """1 Stage分を解く（T45/T46）."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_in_seconds
    solver.parameters.random_seed = SOLVER_RANDOM_SEED
    solver.parameters.num_workers = SOLVER_NUM_WORKERS
    solver.parameters.cp_model_presolve = SOLVER_CP_MODEL_PRESOLVE
    raw_status = solver.solve(model)
    return _convert_status(raw_status), solver


def _convert_status(raw_status: int) -> str:
    """T46: CP-SATのステータスをアプリのステータスへ変換する."""
    if raw_status not in _STATUS_NAMES:
        # MODEL_INVALID はモデル構築の不具合
        raise RuntimeError(f"CP-SAT returned unexpected status: {raw_status!r}")
    return _STATUS_NAMES[raw_status]


def _to_assignments(sm: ScheduleModel, solution: dict[Key, bool]) -> list[AssignmentResult]:
    """T47: 解を staff_id, work_date 順の AssignmentResult に変換する."""
    return [
        AssignmentResult(staff.staff_id, work_date, bool(solution[staff.staff_id, work_date]))
        for staff in sm.staff
        for work_date in sm.dates
    ]
