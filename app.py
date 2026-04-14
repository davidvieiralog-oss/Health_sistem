# app.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

import process_data          # analítico
import map as mapmod         # geoespacial
from sidebar import render_sidebar


st.set_page_config(page_title="Painel Analítico + Mapa", layout="wide")
st.title("📊 Painel de Dados (Analítico + Geoespacial)")
st.caption("Sobe tabela e camada espacial ao mesmo tempo, sem um matar o outro.")


# -----------------------------
# Estado separado (essencial)
# -----------------------------
st.session_state.setdefault("df", None)
st.session_state.setdefault("ana_last_file", None)
st.session_state.setdefault("ana_error", None)

st.session_state.setdefault("gdf", None)
st.session_state.setdefault("geo_last_file", None)
st.session_state.setdefault("geo_error", None)
st.session_state.setdefault("geo_zip_bytes", None)
st.session_state.setdefault("geo_candidates", [])
st.session_state.setdefault("geo_inner_choice", None)

# filtros analíticos fora da sidebar
st.session_state.setdefault("col_query", "")
st.session_state.setdefault("col_type", "todas")
st.session_state.setdefault("fav_cols", [])


# -----------------------------
# Helpers (analítico)
# -----------------------------
def infer_col_type(series: pd.Series) -> str:
    s = series
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "data"
    if pd.api.types.is_numeric_dtype(s):
        return "num"

    if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
        sample = s.dropna().astype(str).head(50)
        if len(sample) > 0:
            parsed = pd.to_datetime(sample, errors="coerce", dayfirst=True)
            if parsed.notna().mean() >= 0.7:
                return "data"

    return "texto"


def get_filtered_columns(df: pd.DataFrame, query: str, type_filter: str, fav_cols: list[str]) -> list[str]:
    cols = list(df.columns.astype(str))

    q = (query or "").strip()
    if q:
        cols = [c for c in cols if q.casefold() in c.casefold()]

    if type_filter and type_filter != "todas":
        cols = [c for c in cols if infer_col_type(df[c]) == type_filter]

    if fav_cols:
        fav_in = [c for c in fav_cols if c in df.columns.astype(str).tolist()]
        cols = list(dict.fromkeys([*fav_in, *cols]))

    return cols


# -----------------------------
# Sidebar: dois uploaders + ações
# -----------------------------
with st.sidebar:
    st.header("📦 Uploads")

    st.markdown("#### Analítico (CSV/XLSX/XLS/ZIP)")
    ana_file = st.file_uploader(
        "Arquivo analítico",
        type=["csv", "xlsx", "xls", "zip"],
        accept_multiple_files=False,
        key="uploader_analytic",
    )
    a1, a2 = st.columns(2)
    with a1:
        ana_reload = st.button("🔄 Recarregar analítico", use_container_width=True, key="btn_ana_reload")
    with a2:
        ana_clear = st.button("🧹 Limpar analítico", use_container_width=True, key="btn_ana_clear")

    st.markdown("---")

    st.markdown("#### Geoespacial (ZIP/GeoJSON/GPKG/KML)")
    geo_file = st.file_uploader(
        "Arquivo geoespacial",
        type=["zip", "geojson", "json", "gpkg", "kml"],
        accept_multiple_files=False,
        key="uploader_geo",
    )
    g1, g2 = st.columns(2)
    with g1:
        geo_reload = st.button("🔄 Recarregar mapa", use_container_width=True, key="btn_geo_reload")
    with g2:
        geo_clear = st.button("🧹 Limpar mapa", use_container_width=True, key="btn_geo_clear")

    st.markdown("---")
    st.markdown("### Status rápido")
    st.write("Analítico:", "✅" if st.session_state.df is not None else ("❌" if st.session_state.ana_error else "—"))
    st.write("Mapa:", "✅" if st.session_state.gdf is not None else ("❌" if st.session_state.geo_error else "—"))


# -----------------------------
# Clears (independentes)
# -----------------------------
if ana_clear:
    st.session_state.df = None
    st.session_state.ana_last_file = None
    st.session_state.ana_error = None

if geo_clear:
    st.session_state.gdf = None
    st.session_state.geo_last_file = None
    st.session_state.geo_error = None
    st.session_state.geo_zip_bytes = None
    st.session_state.geo_candidates = []
    st.session_state.geo_inner_choice = None


# -----------------------------
# LOAD analítico
# -----------------------------
ana_should_load = (
    ana_file is not None and (
        ana_reload or st.session_state.ana_last_file != ana_file.name
    )
)

if ana_should_load:
    try:
        df_loaded = process_data.load_dataframe_from_bytes(ana_file.name, ana_file.getvalue())
        st.session_state.df = df_loaded
        st.session_state.ana_last_file = ana_file.name
        st.session_state.ana_error = None
    except Exception as e:
        st.session_state.df = None
        st.session_state.ana_error = str(e)


# -----------------------------
# LOAD geoespacial
# -----------------------------
geo_should_load = (
    geo_file is not None and (
        geo_reload or st.session_state.geo_last_file != geo_file.name
    )
)

if geo_should_load:
    try:
        raw = geo_file.getvalue()
        st.session_state.geo_last_file = geo_file.name
        st.session_state.geo_error = None

        if geo_file.name.lower().endswith(".zip"):
            st.session_state.geo_zip_bytes = raw
            cand = mapmod.list_geospatial_candidates_in_zip(raw).candidates
            if not cand:
                raise ValueError("ZIP não contém .shp/.geojson/.gpkg/.kml.")

            st.session_state.geo_candidates = cand
            st.session_state.geo_inner_choice = cand[0]  # default
            gdf_loaded = mapmod.load_geospatial_from_upload(
                geo_file.name, raw, zip_inner_path=st.session_state.geo_inner_choice
            )
        else:
            st.session_state.geo_zip_bytes = None
            st.session_state.geo_candidates = []
            st.session_state.geo_inner_choice = None
            gdf_loaded = mapmod.load_geospatial_from_upload(geo_file.name, raw)

        st.session_state.gdf = gdf_loaded

    except Exception as e:
        st.session_state.gdf = None
        st.session_state.geo_error = str(e)


# -----------------------------
# Status GLOBAL (fora das abas) -> você vê na hora
# -----------------------------
t1, t2 = st.columns(2)

with t1:
    if st.session_state.df is not None:
        st.success(f"✅ Analítico: {st.session_state.ana_last_file} ({len(st.session_state.df)} linhas)")
    elif st.session_state.ana_error:
        st.error(f"❌ Analítico: {st.session_state.ana_error}")
    else:
        st.info("Analítico: nenhum arquivo carregado.")

with t2:
    if st.session_state.gdf is not None:
        st.success(f"✅ Mapa: {st.session_state.geo_last_file} ({len(st.session_state.gdf)} feições)")
    elif st.session_state.geo_error:
        st.error(f"❌ Mapa: {st.session_state.geo_error}")
    else:
        st.info("Mapa: nenhum arquivo carregado.")

st.markdown("---")


# -----------------------------
# Abas
# -----------------------------
tab_ana, tab_map = st.tabs(["📈 Analítico", "🗺️ Mapa"])


# ========== TAB ANALÍTICO ==========
with tab_ana:
    df: pd.DataFrame | None = st.session_state.df
    if df is None or df.empty:
        st.info("Carregue um arquivo analítico na sidebar.")
    else:
        st.markdown("### 🎯 Filtros rápidos de colunas (fora da sidebar)")
        c1, c2, c3 = st.columns([2, 1, 2])

        with c1:
            st.session_state.col_query = st.text_input(
                "Buscar coluna (nome)",
                value=st.session_state.col_query,
                placeholder="Ex: data, mês, valor, total, município...",
                key="col_query_input",
            )
        with c2:
            st.session_state.col_type = st.selectbox(
                "Tipo",
                ["todas", "num", "texto", "data", "bool"],
                index=["todas", "num", "texto", "data", "bool"].index(st.session_state.col_type),
                key="col_type_select",
            )
        with c3:
            st.session_state.fav_cols = st.multiselect(
                "Favoritas (atalho)",
                options=list(df.columns.astype(str)),
                default=st.session_state.fav_cols,
                key="fav_cols_select",
            )

        filtered_cols = get_filtered_columns(
            df, st.session_state.col_query, st.session_state.col_type, st.session_state.fav_cols
        )
        st.caption(f"Colunas após filtro: **{len(filtered_cols)}** (de {len(df.columns)} totais)")
        st.markdown("---")

        sb = render_sidebar(df, available_cols=filtered_cols)

        if sb.show_table:
            st.subheader("📋 Prévia dos dados")
            st.dataframe(df.head(sb.max_rows), use_container_width=True)

        st.markdown("---")
        st.subheader("📈 Gráfico de linhas")

        try:
            process_data.validate_columns_for_line_chart(df, sb.x_col, sb.y_col)
            fig = process_data.build_line_chart(
                df=df,
                x_col=sb.x_col,
                y_col=sb.y_col,
                sort_x=sb.sort_x,
                parse_dates=sb.parse_dates,
            )
            st.pyplot(fig, clear_figure=True, use_container_width=True)
        except Exception as e:
            st.error(str(e))


# ========== TAB MAPA ==========
with tab_map:
    gdf = st.session_state.gdf
    if gdf is None or len(gdf) == 0:
        st.info("Carregue um arquivo geoespacial na sidebar.")
    else:
        # ZIP: escolha a camada interna (sem precisar re-upload)
        if st.session_state.geo_zip_bytes and st.session_state.geo_candidates:
            st.markdown("### 📦 ZIP: escolha a camada interna")
            choice = st.selectbox(
                "Arquivo dentro do ZIP",
                options=st.session_state.geo_candidates,
                index=st.session_state.geo_candidates.index(st.session_state.geo_inner_choice)
                if st.session_state.geo_inner_choice in st.session_state.geo_candidates
                else 0,
                key="geo_inner_select",
            )

            if choice != st.session_state.geo_inner_choice:
                try:
                    st.session_state.geo_inner_choice = choice
                    gdf2 = mapmod.load_geospatial_from_upload(
                        st.session_state.geo_last_file,
                        st.session_state.geo_zip_bytes,
                        zip_inner_path=choice,
                    )
                    st.session_state.gdf = gdf2
                    gdf = gdf2
                    st.success(f"Camada interna carregada: {choice}")
                except Exception as e:
                    st.session_state.geo_error = str(e)
                    st.error(str(e))

        st.markdown("### 🎛️ Controles do mapa (fora da sidebar)")
        cols = [c for c in gdf.columns if c != "geometry"]

        m1, m2, m3 = st.columns([2, 3, 2])
        with m1:
            layer_name = st.text_input("Nome da camada", value="Camada", key="map_layer_name")
        with m2:
            tooltip_cols = st.multiselect(
                "Campos no tooltip",
                options=cols,
                default=cols[:8] if len(cols) >= 8 else cols,
                key="map_tooltip_cols",
            )
        with m3:
            tiles = st.selectbox(
                "Mapa base",
                ["CartoDB positron", "OpenStreetMap", "CartoDB dark_matter"],
                index=0,
                key="map_tiles",
            )

        st.markdown("---")
        m = mapmod.build_folium_map(
            gdf=gdf,
            name=layer_name,
            tooltip_cols=tooltip_cols,
            tiles=tiles,
        )
        st_folium(m, height=650, width=None, returned_objects=[])

        with st.expander("🔎 Diagnóstico da camada", expanded=False):
            st.write("CRS:", str(gdf.crs))
            st.write("Geom types:", gdf.geom_type.value_counts().to_dict())
            st.write("Colunas:", cols)