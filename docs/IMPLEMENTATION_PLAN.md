# ホテル清掃スタッフ月間シフト自動作成アプリ
## MVP 実装計画書 v1.3
### Claude Code実装版

---

# 変更履歴

## v1.3（v1.2からの変更）

- §38 Solver設定：`num_search_workers` を廃止し `num_workers = 1` に変更
- §38 Solver設定：時間制限を「各Stage 10秒」から「4 Stage合計 10秒」（`TOTAL_SOLVE_TIME_LIMIT_SECONDS = 10.0`）に変更
- §38.1 追加：Stage別の残り時間計算
- §38.2 追加：Stage間のsolution hint（`model.add_hint()`）
- §38.3 追加：UNKNOWN時の扱い（Stage 1 / Stage 2～4）
- §37 変更：FEASIBLEの定義を明確化、Stage 2以降のUNKNOWNフォールバックを反映
- §41 変更：`SchedulerResult` の必須項目（`completed_stage`、各Stage目的値）を追加
- T45 / T56 のSolver設定記述をv1.3仕様に合わせて更新

---

# 0. この計画書の目的

本計画書は、Claude Codeが本アプリを安全に段階実装するための実装正本である。

実装は一括で行わず、

**T00 → T01 → T02 → …**

の順序で、小さなタスク単位に進める。

Claude Codeは各タスクについて、

```text
調査
↓
実装
↓
専用テスト
↓
既存テスト
↓
結果報告
```

まで行う。

ただし、設計判断は本計画書を優先し、独自の仕様変更を行わない。

---

# 1. 対象リポジトリ

Repository:

```text
highwing-republic/staff_monthly_conditions
```

URL:

```text
https://github.com/highwing-republic/staff_monthly_conditions
```

Default branch:

```text
main
```

---

# 2. Git運用

mainへの直接実装・pushは禁止。

（例外：空リポジトリ初期化時のREADME.mdのみのbootstrap commit。実施済み。）

作業branchを使用する。

例：

```text
feat/mvp-foundation
```

基本フロー：

```text
main
 ↓
作業branch
 ↓
実装
 ↓
pytest
 ↓
commit
 ↓
レビュー
 ↓
PR
 ↓
main
```

Claude Codeは、

- add
- commit

までは、ユーザーから明示的に許可された場合のみ実行してよい。

以下は明示指示なしに実行しない。

```text
git push
PR作成
merge
mainへの直接変更
force push
```

---

# 3. T00での安全確認

最初に必ず以下を実行する。

```bash
git rev-parse --show-toplevel
git remote -v
git branch --show-current
git status
python --version
```

正しい対象：

```text
highwing-republic/staff_monthly_conditions
```

正しいremote：

```text
https://github.com/highwing-republic/staff_monthly_conditions.git
```

mainではなく作業branch上であること。

working treeは原則clean。

別repositoryだった場合、

**一切変更せず停止して報告する。**

---

# 4. アプリの目的

本アプリは、

**ホテル客室清掃スタッフの1か月分の勤務シフトを自動作成するアプリ**

である。

清掃当日は、その日に出勤したスタッフ全員で清掃を行う。

したがって本アプリは、

```text
誰がどの客室を清掃するか
```

を決めない。

決めるのは、

```text
誰が何日に出勤するか
```

だけである。

---

# 5. 解決する業務

管理者が毎月考慮している、

```text
スタッフ人数
スタッフロール
通常勤務可能曜日
月間所定勤務量
最大勤務量
最大連続勤務
絶対休み
希望休
日別必要人数
日別必要ロール
```

を入力し、

```text
スタッフ × 日付
=
出勤 / 休み
```

の月間シフト案を自動生成する。

---

# 6. MVPの最終UX

```text
① スタッフ確認
↓
② 月間勤務条件入力
↓
③ 希望休入力
↓
④ 日別必要人数・ロール入力
↓
⑤ 事前チェック
↓
⑥ 自動シフト生成
↓
⑦ 管理者確認
↓
⑧ 手動修正
↓
⑨ 必要セルを固定
↓
⑩ 固定を残して再計算
↓
⑪ 確定
↓
⑫ Excel出力
```

MVPの目的は、

**人間がゼロから月間勤務表を作る作業をなくすこと**

である。

---

# 7. MVP対象外

以下は実装しない。

```text
客室担当割当
清掃ペア
チーム編成
フロア割当
清掃順序
PMS API
サイトコントローラー
稼働率から必要人数のAI予測
複数ロール
早番
遅番
夜勤
半日勤務
時間帯別必要人数
休憩管理
勤怠打刻
給与計算
有給残数
GPS
LINE
Slack
Gmail
生成AIシフト
機械学習
複数ホテル
```

Claude Codeは将来機能を先回り実装しない。

---

# 8. 技術構成

```text
Python 3.11+
Streamlit
Google OR-Tools CP-SAT
SQLite
sqlite3
pandas
openpyxl
pytest
```

MVPではSQLAlchemyを導入しない。

---

# 9. 勤務単位

MVPでは1日単位。

状態：

```text
出勤
休み
```

のみ。

---

# 10. 勤務時間

スタッフごとに、

```text
daily_work_minutes
```

を持つ。

例：

```text
8h → 480
6h → 360
5h → 300
```

内部計算は整数分。

日別必要人数では勤務時間に関係なく、

```text
出勤者1名 = 1名
```

として扱う。

勤務時間は月間勤務量計算に使用する。

---

# 11. ロール

1スタッフにつき主要ロール1つ。

初期値：

```text
LEADER
CHECKER
CLEANER
```

複数ロールは実装しない。

---

# 12. 希望種別

```text
UNAVAILABLE
PREFER_OFF
PREFER_WORK
```

## UNAVAILABLE

絶対休み。

Hard Constraint。

```text
x[s,d] = 0
```

## PREFER_OFF

できれば休み。

Soft Constraint。

## PREFER_WORK

できれば出勤。

Soft Constraint。

通常勤務不可曜日へのPREFER_WORKは禁止。

---

# 13. 不成立時の原則

Hard Constraintを満たすシフトが存在しない場合、

```text
シフト不成立
```

とする。

以下を勝手に緩和しない。

```text
絶対休み
固定
必要人数
必要ロール
最大勤務時間
最大連勤
```

---

# 14. ディレクトリ

```text
staff_monthly_conditions/

├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
│
├─ docs/
│  └─ IMPLEMENTATION_PLAN.md
│
├─ pages/
│  ├─ 01_staff.py
│  ├─ 02_monthly_conditions.py
│  ├─ 03_preferences.py
│  ├─ 04_requirements.py
│  ├─ 05_generate.py
│  └─ 06_schedule.py
│
├─ src/
│  ├─ __init__.py
│  ├─ constants.py
│  ├─ month_utils.py
│  ├─ models.py
│  ├─ database.py
│  ├─ repositories.py
│  ├─ validation.py
│  ├─ availability.py
│  ├─ precheck.py
│  ├─ scheduler.py
│  ├─ schedule_validation.py
│  └─ export_excel.py
│
├─ tests/
│  ├─ test_smoke.py
│  ├─ test_constants.py
│  ├─ test_models.py
│  ├─ test_month_utils.py
│  ├─ test_database.py
│  ├─ test_validation.py
│  ├─ test_availability.py
│  ├─ test_precheck.py
│  ├─ test_scheduler_basic.py
│  ├─ test_scheduler_roles.py
│  ├─ test_scheduler_hours.py
│  ├─ test_scheduler_consecutive.py
│  ├─ test_scheduler_locks.py
│  ├─ test_scheduler_objectives.py
│  ├─ test_schedule_validation.py
│  └─ test_export_excel.py
│
├─ sample/
│  ├─ sample_staff.csv
│  └─ sample_requirements.csv
│
└─ data/
   └─ .gitkeep
```

---

# 15. 日付形式

```text
work_date = YYYY-MM-DD
year_month = YYYY-MM
```

---

# 16. CSV文字コード

以下の順で読む。

```text
1. utf-8-sig
2. cp932
```

両方失敗したら入力エラー。

---

# 17. DBテーブル

```text
roles
staff
staff_weekday_availability
staff_monthly_conditions
staff_day_preferences
daily_requirements
daily_role_requirements
schedule_months
schedule_assignments
```

---

# 18. roles

```text
role_id INTEGER PRIMARY KEY
role_code TEXT UNIQUE NOT NULL
role_name TEXT NOT NULL
active INTEGER NOT NULL DEFAULT 1
```

初期値：

```text
LEADER
CHECKER
CLEANER
```

---

# 19. staff

```text
staff_id INTEGER PRIMARY KEY AUTOINCREMENT
staff_name TEXT NOT NULL
role_id INTEGER NOT NULL
daily_work_minutes INTEGER NOT NULL
max_consecutive_days INTEGER NOT NULL
active INTEGER NOT NULL DEFAULT 1
```

---

# 20. staff_weekday_availability

```text
staff_id INTEGER NOT NULL
weekday INTEGER NOT NULL
is_available INTEGER NOT NULL

PRIMARY KEY(staff_id, weekday)
```

```text
0 Monday
...
6 Sunday
```

新規スタッフ作成時は7曜日すべてavailable。

---

# 21. staff_monthly_conditions

```text
staff_id INTEGER NOT NULL
year_month TEXT NOT NULL
target_monthly_minutes INTEGER NOT NULL
min_monthly_minutes INTEGER NULL
max_monthly_minutes INTEGER NULL
carryover_consecutive_days INTEGER NOT NULL DEFAULT 0

PRIMARY KEY(staff_id, year_month)
```

---

# 22. staff_day_preferences

```text
staff_id INTEGER NOT NULL
work_date TEXT NOT NULL
preference_type TEXT NOT NULL

PRIMARY KEY(staff_id, work_date)
```

---

# 23. daily_requirements

```text
work_date TEXT PRIMARY KEY
occupancy_rate REAL NULL
required_total_staff INTEGER NOT NULL
max_total_staff INTEGER NULL
note TEXT NULL
```

---

# 24. daily_role_requirements

```text
work_date TEXT NOT NULL
role_id INTEGER NOT NULL
required_count INTEGER NOT NULL

PRIMARY KEY(work_date, role_id)
```

---

# 25. schedule_months

```text
year_month TEXT PRIMARY KEY
status TEXT NOT NULL
solver_status TEXT NULL

objective_overstaff INTEGER NULL
objective_target_deviation INTEGER NULL
objective_prefer_off INTEGER NULL
objective_prefer_work INTEGER NULL

generated_at TEXT NULL
confirmed_at TEXT NULL
```

status：

```text
DRAFT
CONFIRMED
```

---

# 26. schedule_assignments

```text
staff_id INTEGER NOT NULL
work_date TEXT NOT NULL
is_working INTEGER NOT NULL
is_locked INTEGER NOT NULL DEFAULT 0
source TEXT NOT NULL

PRIMARY KEY(staff_id, work_date)
```

source：

```text
OPTIMIZED
MANUAL
```

---

# 27. 未入力時の仕様

## daily_requirements

対象月の1日でも存在しない：

```text
エラー
```

休館日でも行を作り、

```text
required_total_staff = 0
```

とする。

## daily_role_requirements

行がなければ：

```text
required_count = 0
```

## staff_monthly_conditions

activeスタッフに対象月データがなければ：

```text
エラー
```

## weekday availability

7曜日揃っていなければ：

```text
データ不整合エラー
```

## preferences

行なし：

```text
指定なし
```

## min/max

NULLならそのHard Constraintなし。

---

# 28. Decision Variable

```text
x[s,d] ∈ {0,1}
```

```text
1 = 出勤
0 = 休み
```

---

# 29. Hard Constraints

## HC01 通常勤務不可曜日

```text
x[s,d] = 0
```

## HC02 UNAVAILABLE

```text
x[s,d] = 0
```

## HC03 必要人数

```text
Σs x[s,d] >= required_total_staff[d]
```

## HC04 必要人数0

```text
Σs x[s,d] = 0
```

## HC05 最大人数

設定時：

```text
Σs x[s,d] <= max_total_staff[d]
```

## HC06 必要ロール

```text
Σ(role[s]=r) x[s,d] >= required_role[d,r]
```

## HC07 最大月間勤務時間

```text
actual_minutes[s]
=
Σd x[s,d] * daily_work_minutes[s]
```

設定時：

```text
actual_minutes[s] <= max_monthly_minutes[s]
```

## HC08 最低月間勤務時間

設定時のみ：

```text
actual_minutes[s] >= min_monthly_minutes[s]
```

## HC09 最大連勤

最大Mなら任意のM+1日について：

```text
Σ x <= M
```

## HC10 前月連勤

```text
M = max_consecutive_days
C = carryover_consecutive_days
```

```text
0 <= C <= M
```

月初：

```text
最初の(M-C+1)日間の勤務数 <= M-C
```

## HC11 固定出勤

```text
x[s,d] = 1
```

## HC12 固定休日

```text
x[s,d] = 0
```

---

# 30. Soft Constraint方式

固定ウェイトによる一括最適化は採用しない。

**段階最適化**を使用する。

---

# 31. 最適化優先順位

```text
Stage 1
過剰配置人数最小化

↓

Stage 2
所定勤務日数との差最小化

↓

Stage 3
PREFER_OFF違反最小化

↓

Stage 4
PREFER_WORK未反映最小化
```

この順序を変更しない。

---

# 32. Stage 1

```text
overstaff[d]
=
actual_staff[d]
-
required_total_staff[d]
```

```text
minimize Σ overstaff[d]
```

---

# 33. Stage 2

目標勤務日数：

```text
target_workdays
=
(target_monthly_minutes + daily_work_minutes // 2)
// daily_work_minutes
```

実勤務日数：

```text
actual_workdays = Σd x[s,d]
```

偏差：

```text
abs(actual_workdays - target_workdays)
```

合計を最小化。

---

# 34. Stage 3

PREFER_OFFなのに出勤した件数を最小化。

---

# 35. Stage 4

PREFER_WORKなのに休日になった件数を最小化。

---

# 36. 段階最適化

各Stage終了後に目的値を取得。

次Stageでは、

```text
前Stage目的値 == 取得した最良値
```

を制約として追加。

前Stageの目的値の維持は、このHard Constraintによってのみ行う（§38.2のhintは目的値維持の手段ではない）。

---

# 37. 最終ステータス

## FEASIBLEの意味

本アプリでFEASIBLEは、

```text
すべてのHard Constraintを満たす有効なシフトだが、
すべてのSoft Constraintについて最適性を確認できていない
```

という意味とする。

## 判定

```text
Stage 1 が INFEASIBLE
→ INFEASIBLE（assignments = []）

Stage 1 が UNKNOWN
→ UNKNOWN（assignments = []）

全Stage OPTIMAL
→ OPTIMAL

上記以外で、有効解を1つ以上取得済み
→ FEASIBLE
```

「上記以外」には以下を含む。

```text
いずれかのStageがFEASIBLE（時間切れで最適性未証明）
Stage 2～4 が UNKNOWN（§38.3によりフォールバック）
残り時間切れで以降のStageを実行しなかった
```

---

# 38. Solver設定

```text
TOTAL_SOLVE_TIME_LIMIT_SECONDS = 10.0
random_seed = 42
num_workers = 1
```

`num_search_workers` は使用しない（deprecated）。

時間制限は **各Stageごとではなく、4 Stage合計の上限** とする。

---

## 38.1 Stage別の残り時間

`time.monotonic()` 等でSolver全体の経過時間を測定する。

各Stage開始時に、

```text
remaining_seconds
=
TOTAL_SOLVE_TIME_LIMIT_SECONDS
-
elapsed_seconds
```

を計算し、

```text
solver.parameters.max_time_in_seconds = remaining_seconds
```

を設定する。

`remaining_seconds <= 0` の場合、そのStage以降は実行しない。

その時点で取得済みの最新Stageの解を最終結果とする。

---

## 38.2 Stage間のsolution hint

Stage Nで取得した解について、全ての

```text
x[staff,date]
```

の値を、次Stageのmodelへ

```text
model.add_hint(variable, value)
```

で渡す。

HintはHard Constraintではない。

Hintは次Stageで解を早く見つけるためだけに使用する。

前Stageの目的値の維持は、§36の

```text
前Stage目的値 == best_value
```

というHard Constraintで行う。

---

## 38.3 UNKNOWN時の扱い

### Stage 1

Stage 1が `UNKNOWN` の場合：

```text
overall status = UNKNOWN
assignments = []
completed_stage = 0
```

として終了する。

Hard Constraintを満たす解が確認できていないため、シフトを返してはいけない。

### Stage 2～4

Stage 2以降が `UNKNOWN` になった場合：

直前Stageで取得済みのシフトへフォールバックして終了する。

例：

```text
Stage 1 OPTIMAL
Stage 2 OPTIMAL
Stage 3 UNKNOWN
```

なら、

```text
Stage 2のsolution
```

を最終シフトとして返す。

```text
overall status = FEASIBLE
completed_stage = 2
```

直前Stageの解はHard Constraintを満たす有効なシフトであるため、返してよい。

---

## 38.4 completed_stage

どのStageまで最適化結果を取得できたかを表す。

```text
0 = 最適化Stage未完了
1 = 過剰配置まで
2 = 所定勤務日数まで
3 = PREFER_OFFまで
4 = 全Stage完了
```

StageがFEASIBLE（時間切れで最適性未証明だが解あり）で終わった場合も、そのStageの解は取得済みとして `completed_stage` に数える。

ただしその場合、overall statusはOPTIMALにならない（§37）。

---

# 39. Solverテスト

セルの完全一致を要求しない。

検証対象：

```text
制約充足
目的値
絶対休み
必要人数
ロール
勤務上限
連勤
```

---

# 40. scheduler.py骨格

T30で固定。

```text
build_model()

_create_variables()

_add_weekday_constraints()
_add_unavailable_constraints()
_add_staffing_constraints()
_add_zero_staffing_constraints()
_add_max_staff_constraints()
_add_role_constraints()
_add_max_minutes_constraints()
_add_min_minutes_constraints()
_add_consecutive_constraints()
_add_carryover_constraints()
_add_lock_constraints()

_create_overstaff_terms()
_create_target_deviation_terms()
_create_prefer_off_terms()
_create_prefer_work_terms()

solve_lexicographically()
```

以降、大規模構造変更は禁止。

必要な小規模内部整理は、テストを維持する場合のみ許可。

---

# 41. Models

先に以下を定義する。

```text
StaffInput
MonthlyConditionInput
DailyRequirementInput
RoleRequirementInput
PreferenceInput
LockedAssignmentInput
SchedulerInput

AssignmentResult
StageObjectiveResult
SchedulerResult
ValidationError
PrecheckResult
```

Repositoryは可能な限りこれらへ変換して返す。

## SchedulerResult 必須項目

```text
status
assignments
completed_stage

objective_overstaff
objective_target_deviation
objective_prefer_off
objective_prefer_work
```

- `status`：`OPTIMAL` / `FEASIBLE` / `INFEASIBLE` / `UNKNOWN`
- `assignments`：`AssignmentResult` の一覧。INFEASIBLE / UNKNOWN時は空
- `completed_stage`：§38.4
- 未実行Stageのobjective値は `None`

---

# 42. 事前チェック

## PC01

activeスタッフ0。

## PC02

daily_requirements不足。

## PC03

monthly_conditions不足。

## PC04

weekdayデータ不足。

## PC05

必要人数 > 勤務可能人数。

勤務可能人数から除外：

```text
inactive
通常勤務不可
UNAVAILABLE
固定休日
```

## PC06

必要ロール > そのロールの勤務可能人数。

## PC07

```text
sum(required roles) > required_total_staff
```

## PC08

```text
required_total_staff > max_total_staff
```

## PC09

```text
sum(required roles) > max_total_staff
```

## PC10

```text
min > target
```

## PC11

```text
target > max
```

## PC12

```text
carryover < 0
```

## PC13

```text
carryover > max_consecutive_days
```

## PC14

固定出勤 + UNAVAILABLE。

## PC15

固定出勤 + 通常勤務不可曜日。

## PC16

必要人数0 + 固定出勤。

## PC17

固定出勤人数 > max_total_staff。

## PC18

固定だけでmax勤務時間超過。

## PC19

固定だけで最大連勤違反。

---

# 43. INFEASIBLE表示

原因が事前に特定可能：

```text
10月12日
必要人数8
勤務可能7

1名不足しています。
```

SolverのみがINFEASIBLE：

```text
現在の条件ではシフトを作成できません。

以下を確認してください。

・必要人数
・必要ロール
・絶対休み
・通常勤務可能曜日
・最大勤務時間
・最低勤務時間
・最大連続勤務
・固定条件
```

原因を推測しない。

---

# 44. 手動変更

表は基本read-only。

編集パネル：

```text
スタッフ
日付
出勤 / 休み
固定 / 未固定
```

---

# 45. 手動変更後

`schedule_validation`を必ず実行。

検証：

```text
通常勤務曜日
UNAVAILABLE
必要人数
必要ロール
max_total_staff
min/max勤務時間
最大連勤
carryover
```

Hard違反状態では確定不可。

---

# 46. Lock

手動変更だけでは固定されない。

未LockのMANUAL変更は再計算で消えてよい。

Lockされたセルのみ再計算で維持。

---

# 47. 再計算

```text
LOCK → 維持
MANUAL + 未LOCK → 上書き可能
OPTIMIZED → 上書き
```

UI表示：

```text
固定していない手動変更は再計算で変更されます
```

---

# 48. CONFIRMED

CONFIRMED月では、

```text
edit
generate
regenerate
lock変更
```

を禁止。

UIだけでなくrepository/serviceロジックでも拒否。

確定解除はMVP対象外。

---

# 49. 過去履歴

MVPではスタッフマスターの履歴スナップショットを持たない。

過去月再検証時に現在のstaff情報が使用される可能性を許容。

確定時Excelを正式な確定記録として扱う。

---

# 50. UI

## 01_staff

```text
一覧
新規
編集
無効化
通常勤務可能曜日
```

## 02_monthly_conditions

```text
target
min
max
carryover
```

## 03_preferences

```text
指定なし
絶対休み
できれば休み
できれば勤務
```

## 04_requirements

```text
日付
曜日
稼働率
必要人数
最大人数
ロール別必要人数
備考
```

## 05_generate

```text
入力状況
事前チェック
シフト生成
Solver結果
不成立理由
```

## 06_schedule

```text
月間表
日別サマリー
スタッフ集計
希望反映
編集
固定
再計算
確定
Excel
```

---

# 51. Claude Code共通実装ルール

各タスクについて以下を守る。

```text
・今回のタスクの目的を優先する
・本計画書の仕様を変更しない
・MVP対象外を実装しない
・新規依存追加は原則禁止
・DBスキーマ変更は対象タスクで指定された場合のみ
・Hard/Softの分類を変更しない
・最適化優先順位を変更しない
・関係ないリファクタリングをしない
・mainへ直接変更しない
・push/mergeしない
```

ただしClaude Codeは、指定タスクを正しく成立させるために必要な場合、

```text
import修正
型整合
小規模な既存関数修正
テストfixture修正
```

までは許可する。

その場合、必ず終了報告に明記する。

---

# 52. 各タスク終了時の必須作業

毎タスク、

1. 指定テスト実行
2. 関連テスト実行
3. 可能なら全pytest実行
4. git diff確認
5. 変更ファイル報告

を行う。

報告形式：

```text
## TXX 実装結果

### 変更ファイル

### 実装内容

### テスト
- command:
- result:

### 追加で必要だった軽微な修正

### 残課題

### 次に進める状態か
READY / BLOCKED
```

---

# Phase 0 — Repository

## T00 Repository Safety Check

変更：

```text
なし
```

確認：

```text
git root
remote
branch
status
Python version
```

誤repoなら停止。

---

# Phase 1 — Foundation

## T01 Minimal Project

作成：

```text
requirements.txt
.gitignore
README.md
app.py
src/__init__.py
```

完了：

Streamlit最小画面が起動。

---

## T02 Smoke Test

```text
tests/test_smoke.py
```

pytest成功。

---

## T03 Constants

```text
src/constants.py
tests/test_constants.py
```

定義：

```text
ROLE_CODES
PREFERENCE_TYPES
SCHEDULE_STATUS
SOURCE_TYPES
SOLVER設定（TOTAL_SOLVE_TIME_LIMIT_SECONDS / random_seed / num_workers）
```

---

## T04 Month Utils

```text
src/month_utils.py
tests/test_month_utils.py
```

実装：

```text
parse_year_month()
get_month_dates()
weekday_index()
round_half_up_workdays()
```

28/29/30/31日テスト。

---

## T05 Models

```text
src/models.py
tests/test_models.py
```

型を固定。

`SchedulerResult` は§41の必須項目を含める。

以降、破壊的変更禁止。

---

# Phase 2 — Database

## T06 DB Connection

```text
src/database.py
tests/test_database.py
```

```text
get_connection()
initialize_database()
```

---

## T07 roles / staff

rolesとstaffのみ追加。

seed：

```text
LEADER
CHECKER
CLEANER
```

---

## T08 weekday availability

テーブル追加。

スタッフ作成時7曜日初期化。

---

## T09 monthly conditions

追加。

---

## T10 preferences

追加。

---

## T11 requirements

```text
daily_requirements
daily_role_requirements
```

---

## T12 schedule storage

```text
schedule_months
schedule_assignments
```

---

# Phase 3 — Repositories

## T13 Staff Repository

```text
list_staff
get_staff
create_staff
update_staff
deactivate_staff
```

---

## T14 Weekday Repository

```text
get
save
```

---

## T15 Monthly Conditions Repository

```text
get
save
```

---

## T16 Preferences Repository

```text
get
save
delete
```

---

## T17 Requirements Repository

```text
daily requirements
role requirements
```

---

## T18 Schedule Repository

```text
load
save
manual update
locks
month status
```

---

# Phase 4 — Validation

## T19 Staff Validation

```text
name
daily_work_minutes
max_consecutive_days
```

---

## T20 Monthly Conditions Validation

```text
target
min
max
carryover
```

---

## T21 Requirements Validation

```text
required
max
role
sum(role)
```

---

## T22 Preference Validation

通常勤務不可曜日へのPREFER_WORK禁止。

---

# Phase 5 — Availability

## T23 Availability Resolver

```text
src/availability.py
tests/test_availability.py
```

判定順：

```text
inactive
↓
weekday unavailable
↓
UNAVAILABLE
↓
locked off
↓
available
```

---

# Phase 6 — Precheck

## T24 Missing Data Checks

```text
requirements missing
monthly conditions missing
weekday rows missing
```

---

## T25 Daily Staffing Check

必要人数不足。

---

## T26 Role Check

ロール不足。

---

## T27 Input Conflict Check

PC07～PC17。

---

## T28 Fixed Hours Check

固定だけでmax勤務超過。

---

## T29 Fixed Consecutive Check

固定だけで連勤超過。

---

# Phase 7 — Scheduler Skeleton

## T30 Scheduler Skeleton

```text
src/scheduler.py
tests/test_scheduler_basic.py
```

最終構造を固定。

以降、大規模構造変更禁止。

このタスク完了後は、上位モデルレビュー推奨。

---

## T31 Decision Variables

```text
x[s,d]
```

のみ。

---

# Phase 8 — Hard Constraints

## T32 HC01 Weekday

---

## T33 HC02 UNAVAILABLE

---

## T34 HC03 Staffing Minimum

---

## T35 HC04 Zero Staffing

---

## T36 HC05 Staffing Maximum

---

## T37 HC06 Role Requirement

role_idベース。

---

## T38 Actual Minutes

式作成のみ。

---

## T39 HC07 Max Minutes

---

## T40 HC08 Min Minutes

---

## T41 HC09 Consecutive

月内。

上位モデルレビュー推奨。

---

## T42 HC10 Carryover

テスト：

```text
M5 C2
3連勤 OK
4連勤 NG

M5 C5
1日勤務 NG
```

上位モデルレビュー必須。

---

## T43 HC11 Locked Work

---

## T44 HC12 Locked Off

---

# Phase 9 — Solver Status

## T45 Basic Solve

Hard Constraintのみ。

Solver：

```text
max_time_in_seconds = TOTAL_SOLVE_TIME_LIMIT_SECONDS（10.0）
random_seed = 42
num_workers = 1
```

---

## T46 Status Conversion

```text
OPTIMAL
FEASIBLE
INFEASIBLE
UNKNOWN
```

---

## T47 Assignment Conversion

```text
staff_id
work_date
is_working
```

---

# Phase 10 — Lexicographic Optimization

## T48 Stage 1 Terms

overstaff。

---

## T49 Stage 1 Optimize

過剰配置最小化。

Stage 1 UNKNOWN → overall UNKNOWN / assignments=[]（§38.3）。

レビュー推奨。

---

## T50 Stage 2 Terms

```text
target_workdays
actual_workdays
deviation
```

---

## T51 Stage 2 Optimize

Stage1固定。

Stage 1の解をhintとして渡す（§38.2）。

UNKNOWN時はStage 1解へフォールバック（§38.3）。

レビュー推奨。

---

## T52 Stage 3 Terms

PREFER_OFF。

---

## T53 Stage 3 Optimize

Stage1/2固定。

hint / フォールバックはT51と同様。

---

## T54 Stage 4 Terms

PREFER_WORK。

---

## T55 Stage 4 Optimize

Stage1/2/3固定。

hint / フォールバックはT51と同様。

---

## T56 Overall Solver Result

全Stage集約。

以下を満たすこと：

```text
4 Stage合計でTOTAL_SOLVE_TIME_LIMIT_SECONDS以内（§38.1）
各Stageに残り時間を設定
completed_stageを正しく設定（§38.4）
overall statusを§37に従って決定
未実行Stageのobjective値はNone
```

上位モデルレビュー必須。

---

# Phase 11 — Schedule Validation

## T57 Basic Validation

```text
weekday
UNAVAILABLE
人数
role
max staff
```

---

## T58 Hours Validation

```text
min
max
actual
```

---

## T59 Consecutive Validation

```text
monthly
carryover
```

---

# Phase 12 — Staff UI

## T60 Staff List

---

## T61 Staff Create

---

## T62 Staff Edit

---

## T63 Weekday UI

---

# Phase 13 — Monthly Conditions UI

## T64 Month Selector

---

## T65 Monthly Conditions Editor

---

# Phase 14 — Preferences UI

## T66 Viewer

---

## T67 Editor

---

# Phase 15 — Requirements UI

## T68 Daily Requirements

---

## T69 Role Requirements

---

## T70 CSV Import

```text
utf-8-sig
cp932
```

全件成功時のみ保存。

---

## T71 Excel Import

CSV共通正規化を再利用。

---

# Phase 16 — Generation UI

## T72 Precheck UI

---

## T73 Scheduler Connection

---

## T74 Save Generated Schedule

OPTIMAL / FEASIBLE時のみ保存。

INFEASIBLEなら既存データを変更しない。

UNKNOWNの場合も既存データを変更しない。

---

# Phase 17 — Schedule Viewer

## T75 Monthly Table

---

## T76 Daily Summary

---

## T77 Staff Summary

---

## T78 Preference Summary

UNAVAILABLE反映100%。

---

# Phase 18 — Manual Edit

## T79 Edit Panel

---

## T80 Manual Validation

---

## T81 Lock

---

## T82 Regenerate With Locks

LOCK維持。

未Lock MANUALは上書き可。

上位モデルレビュー必須。

---

# Phase 19 — Confirm

## T83 Confirm

全validation成功時のみ。

---

## T84 Confirmed Protection

UI・repository双方で禁止。

上位モデルレビュー推奨。

---

# Phase 20 — Excel

## T85 Monthly Schedule Sheet

---

## T86 Daily Staffing Sheet

---

## T87 Staff Summary Sheet

---

# Phase 21 — Demo / E2E

## T88 Demo Staff

```text
15名
LEADER 3
CHECKER 3
CLEANER 9
```

---

## T89 Demo Requirements

31日。

---

## T90 Demo Preferences

全3種混在。

---

## T91 Normal E2E

```text
登録
→ 条件
→ 希望
→ 必要人数
→ generate
→ edit
→ lock
→ regenerate
→ confirm
→ Excel
```

---

## T92 INFEASIBLE E2E

人員不足を確認。

---

## T93 UNAVAILABLE E2E

絶対休み100%。

---

# 53. Claude Codeに渡すタスク実行テンプレート

```text
対象リポジトリ:
highwing-republic/staff_monthly_conditions

実装計画書:
docs/IMPLEMENTATION_PLAN.md

今回実行するタスク:
TXX <タスク名>

まず実装計画書の以下だけ確認してください:
- 共通実装ルール
- 今回のTXX
- TXXが依存する直前タスク

今回のタスク以外には進まないでください。

実装前:
1. git status
2. 現在branch
3. 関連ファイル
4. 関連テスト
を確認してください。

実装:
計画書どおり実装してください。

許可:
- タスク成立に必要なimport修正
- 型整合の軽微な変更
- 関連fixtureの変更

禁止:
- 設計変更
- DB仕様変更（当該タスクで指定されたものを除く）
- 他Phaseの先行実装
- 新規依存追加
- 大規模リファクタリング
- mainへの変更
- push / merge

テスト:
まず今回の専用テストを実行してください。
その後、影響する既存テストを実行してください。
可能であれば最後にpytest全体を実行してください。

テスト失敗時:
今回の変更範囲で安全に直せる場合だけ修正してください。
他タスクの仕様変更が必要なら実装を止めて報告してください。

最後に以下を報告してください:

## TXX 実装結果

### 変更ファイル
### 実装内容
### テストコマンド
### テスト結果
### 軽微な追加修正
### 残課題
### 次タスクへ進めるか
READY / BLOCKED

TXX完了後、自動的にTXX+1へ進まないでください。
```

---

# 54. Claude Codeにまとめて渡してよい範囲

基本は1タスクずつ。

ただし以下は、十分安定した後ならまとめてもよい。

```text
T01 + T02
T03 + T04
T13 + T14
T15 + T16
T60 + T61
```

以下は絶対にまとめない。

```text
T30
T41
T42
T49
T51
T53
T55
T56
T82
T84
```

---

# 55. 上位レビュー必須ポイント

特に確認する。

```text
T30 Scheduler architecture
T41 Consecutive
T42 Carryover
T49～T56 Lexicographic optimization（時間配分・hint・UNKNOWNフォールバック含む）
T82 Lock再計算
T84 CONFIRMED protection
```

Claude Code自身で実装した場合でも、これらは実装後に別レビューを行う。

---

# 56. 必須E2E

完成時に以下を満たす。

```text
UNAVAILABLE → 必ず休み

通常勤務不可曜日 → 出勤0

必要人数 → 全日充足

必要ロール → 全日充足

max人数 → 超過なし

max勤務時間 → 超過なし

設定されたmin勤務量 → 未達なし

最大連勤 → 超過なし

carryover → 正しく反映

LOCK → 再計算でも維持

未LOCK MANUAL → 再計算で上書き可能

CONFIRMED → 編集不可

INFEASIBLE → 条件を自動緩和しない

Solver全体 → 10秒以内に結果を返す
```

---

# 57. 最終成功条件

管理者が自動作成結果を、

```text
そのまま使える
```

または、

```text
少し修正すれば使える
```

と評価できること。

---

# 58. 実装開始時の指示

最初に実行するのは、

```text
T00 Repository Safety Check
```

のみ。

以下すべて確認できるまでT01へ進まない。

```text
正しいrepository
正しいremote
mainではない作業branch
git status clean
Python 3.11以上
```

問題があれば、

**変更せずBLOCKEDとして報告すること。**
