"""Streamlit エントリポイント."""

import streamlit as st

APP_TITLE = "月間シフト自動作成"


USAGE_STEPS = [
    "① スタッフ確認",
    "② 月間勤務条件入力",
    "③ 希望休入力",
    "④ 日別必要人数・ロール入力",
    "⑤ 事前チェック",
    "⑥ 自動シフト生成",
    "⑦ 管理者確認",
    "⑧ 手動修正",
    "⑨ 必要セルを固定",
    "⑩ 固定を残して再計算",
    "⑪ 確定",
    "⑫ Excel出力",
]


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.write("ホテル客室清掃スタッフの月間勤務シフトを自動作成します。")
    st.caption("左のメニューから各画面へ移動してください。")

    st.subheader("使い方")
    for step in USAGE_STEPS:
        st.write(step)


if __name__ == "__main__":
    main()
