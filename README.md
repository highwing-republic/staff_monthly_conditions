# staff_monthly_conditions

ホテル清掃スタッフの月間勤務シフトを
OR-Tools CP-SATで自動作成するMVP。

実装計画: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)

## セットアップ

Python 3.11 以上。

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## デモデータ

15名・2026年10月分の条件・必要人数・希望を `data/app.db` に投入します。

```bash
python -m src.demo_data 2026-10
```

## 起動

```bash
streamlit run app.py
```

## テスト

```bash
pytest
```
