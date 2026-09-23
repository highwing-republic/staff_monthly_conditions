"""Streamlit エントリポイント."""

import streamlit as st

APP_TITLE = "月間シフト自動作成"


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.write("ホテル客室清掃スタッフの月間勤務シフトを自動作成します。")
    st.caption("左のメニューから各画面へ移動してください。")


if __name__ == "__main__":
    main()
