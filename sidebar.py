# sidebar.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

import streamlit as st
import pandas as pd


@dataclass
class SidebarState:
    x_col: Optional[str]
    y_col: Optional[str]
    sort_x: bool
    parse_dates: bool
    show_table: bool
    max_rows: int


def _suggest_xy(df: pd.DataFrame, cols: List[str]) -> tuple[Optional[str], Optional[str]]:
    if not cols:
        return None, None
    suggested_x = cols[0]

    numeric_cols = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().sum() > 0:
            numeric_cols.append(c)

    suggested_y = numeric_cols[0] if numeric_cols else (cols[1] if len(cols) > 1 else cols[0])
    return suggested_x, suggested_y


def render_sidebar(df: Optional[pd.DataFrame], available_cols: Optional[List[str]] = None) -> SidebarState:
    """
    Sidebar APENAS para configurações do gráfico analítico.
    Upload fica no app.py (dois uploaders independentes).
    """
    with st.sidebar:
        st.title("📌 Controles (Analítico)")

        st.markdown("### Gráfico de linhas")

        if df is None or df.empty:
            st.info("Carregue um arquivo analítico para liberar as opções.")
            return SidebarState(None, None, True, True, True, 200)

        all_cols = list(df.columns.astype(str))
        cols = available_cols if (available_cols is not None and len(available_cols) > 0) else all_cols

        if not cols:
            st.warning("Nenhuma coluna após filtro. Ajuste o filtro no topo do painel.")
            cols = all_cols

        suggested_x, suggested_y = _suggest_xy(df, cols)

        x_col = st.selectbox(
            "Eixo X (tempo/categoria)",
            options=cols,
            index=cols.index(suggested_x) if suggested_x in cols else 0,
            key="sb_x_col",
        )

        y_col = st.selectbox(
            "Eixo Y (valor numérico)",
            options=cols,
            index=cols.index(suggested_y) if suggested_y in cols else 0,
            key="sb_y_col",
        )

        st.markdown("#### Opções")
        sort_x = st.checkbox("Ordenar pelo eixo X", value=True, key="sb_sort_x")
        parse_dates = st.checkbox("Tentar interpretar X como data", value=True, key="sb_parse_dates")
        #adicção de opção para mostrar ou não a tabela e controlar o número de linhas exibidas
        st.markdown("---")
        st.markdown("### Tabela")
        show_table = st.checkbox("Mostrar prévia da tabela", value=True, key="sb_show_table")
        max_rows = st.slider(
            "Máximo de linhas na prévia",
            min_value=20,
            max_value=2000,
            value=200,
            step=20,
            key="sb_max_rows",
        )

        st.caption(f"Colunas disponíveis: **{len(cols)}** | Linhas: **{len(df)}**")

        return SidebarState(x_col, y_col, sort_x, parse_dates, show_table, max_rows)