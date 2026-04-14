# map.py
from __future__ import annotations

import io
import os
import zipfile
import tempfile
from dataclasses import dataclass
from typing import Optional, List, Tuple

import geopandas as gpd
import pandas as pd
import folium

SUPPORTED_SINGLE = {".geojson", ".json", ".gpkg", ".kml"}
SUPPORTED_IN_ZIP = {".shp", ".geojson", ".json", ".gpkg", ".kml"}


@dataclass
class ZipCandidates:
    candidates: List[str]  # nomes (paths) dentro do zip, ex: "data/camada.shp"


def list_geospatial_candidates_in_zip(zip_bytes: bytes) -> ZipCandidates:
    """Lista arquivos geoespaciais suportados dentro do ZIP."""
    if not zip_bytes:
        return ZipCandidates(candidates=[])

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = []
            for n in zf.namelist():
                low = n.lower()
                if low.endswith("/"):
                    continue
                _, ext = os.path.splitext(low)
                if ext in SUPPORTED_IN_ZIP:
                    names.append(n)

            # prioridade: .shp primeiro
            names.sort(key=lambda x: (0 if x.lower().endswith(".shp") else 1, x.lower()))
            return ZipCandidates(candidates=names)

    except zipfile.BadZipFile as e:
        raise ValueError("Arquivo .zip inválido ou corrompido.") from e


def _ensure_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Garante CRS EPSG:4326 (WGS84) para renderizar no Folium."""
    if gdf.crs is None:
        return gdf.set_crs(epsg=4326, allow_override=True)
    try:
        return gdf.to_crs(epsg=4326)
    except Exception:
        return gdf.set_crs(epsg=4326, allow_override=True)


def _clean_gdf(gdf: gpd.GeoDataFrame, max_features: int = 20000) -> gpd.GeoDataFrame:
    """Limpa e limita volume para não travar o app."""
    gdf = gdf.copy()
    gdf = gdf[~gdf.geometry.isna()]

    if len(gdf) > max_features:
        gdf = gdf.head(max_features)

    # serialização segura em tooltip/popup (evita JSON quebrando)
    for c in list(gdf.columns):
        if c == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[c]):
            gdf[c] = gdf[c].astype(str)
        elif pd.api.types.is_object_dtype(gdf[c]):
            gdf[c] = gdf[c].astype(str)

    return gdf


def _guess_geom_kind(gdf: gpd.GeoDataFrame) -> str:
    try:
        kinds = gdf.geom_type.dropna().unique().tolist()
    except Exception:
        return "unknown"
    if not kinds:
        return "unknown"
    s = " ".join(kinds).lower()
    if "point" in s:
        return "point"
    if "line" in s:
        return "line"
    if "polygon" in s:
        return "polygon"
    return "mixed"


def load_geospatial_from_upload(
    file_name: str,
    file_bytes: bytes,
    *,
    zip_inner_path: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """
    Suporta:
    - ZIP (shapefile/geojson/gpkg/kml) -> pode selecionar zip_inner_path
    - GeoJSON/JSON direto
    - GPKG direto
    - KML direto
    """
    if not file_bytes:
        raise ValueError("Arquivo geoespacial vazio (0 bytes).")

    low = (file_name or "").lower()
    _, ext = os.path.splitext(low)

    if ext == ".zip":
        with tempfile.TemporaryDirectory() as tmpdir:
            zpath = os.path.join(tmpdir, "upload.zip")
            with open(zpath, "wb") as f:
                f.write(file_bytes)

            with zipfile.ZipFile(zpath, "r") as zf:
                zf.extractall(tmpdir)

            # se não escolheu, pega o primeiro .shp (ou primeiro suportado)
            if not zip_inner_path:
                candidates = []
                for root, _, files in os.walk(tmpdir):
                    for fn in files:
                        _, e2 = os.path.splitext(fn.lower())
                        if e2 in SUPPORTED_IN_ZIP:
                            candidates.append(os.path.join(root, fn))

                if not candidates:
                    raise ValueError("ZIP não contém .shp/.geojson/.gpkg/.kml.")

                candidates.sort(key=lambda p: (0 if p.lower().endswith(".shp") else 1, p.lower()))
                target = candidates[0]
            else:
                target = os.path.join(tmpdir, zip_inner_path)

                if not os.path.exists(target):
                    # fallback: achar por basename
                    base = os.path.basename(zip_inner_path)
                    found = None
                    for root, _, files in os.walk(tmpdir):
                        if base in files:
                            found = os.path.join(root, base)
                            break
                    if not found:
                        raise ValueError(f"Não achei '{zip_inner_path}' dentro do ZIP.")
                    target = found

            gdf = gpd.read_file(target)

    elif ext in SUPPORTED_SINGLE:
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, os.path.basename(file_name))
            with open(fpath, "wb") as f:
                f.write(file_bytes)
            gdf = gpd.read_file(fpath)

    else:
        raise ValueError("Formato geoespacial não suportado. Use ZIP/GeoJSON/GPKG/KML.")

    if "geometry" not in gdf.columns:
        raise ValueError("Arquivo não tem coluna geometry. Isso não parece dado espacial.")

    gdf = _ensure_wgs84(gdf)
    gdf = _clean_gdf(gdf)
    return gdf


def compute_center(gdf: gpd.GeoDataFrame) -> Tuple[float, float]:
    minx, miny, maxx, maxy = gdf.total_bounds
    return (miny + maxy) / 2.0, (minx + maxx) / 2.0


def _row_popup_html(row: pd.Series, cols: List[str]) -> str:
    parts = []
    for c in cols:
        try:
            parts.append(f"<b>{c}:</b> {row.get(c, '')}")
        except Exception:
            pass
    return "<br/>".join(parts)


def build_folium_map(
    gdf: gpd.GeoDataFrame,
    *,
    name: str = "Camada",
    tooltip_cols: Optional[List[str]] = None,
    tiles: str = "CartoDB positron",
) -> folium.Map:
    lat, lon = compute_center(gdf)
    m = folium.Map(location=[lat, lon], zoom_start=11, tiles=tiles, control_scale=True)

    cols = [c for c in gdf.columns if c != "geometry"]
    use_cols = (tooltip_cols or cols[:10])
    use_cols = [c for c in use_cols if c in cols]

    kind = _guess_geom_kind(gdf)

    if kind == "point":
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            try:
                folium.CircleMarker(
                    location=[geom.y, geom.x],
                    radius=4,
                    weight=1,
                    fill=True,
                    fill_opacity=0.7,
                    popup=_row_popup_html(row, use_cols),
                ).add_to(m)
            except Exception:
                continue
    else:
        tooltip = folium.GeoJsonTooltip(fields=use_cols) if use_cols else None
        folium.GeoJson(
            data=gdf.__geo_interface__,
            name=name,
            tooltip=tooltip,
            style_function=lambda _: {"weight": 2, "fillOpacity": 0.25},
            highlight_function=lambda _: {"weight": 4, "fillOpacity": 0.35},
        ).add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    return m