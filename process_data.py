"""
processing_data.py
------------------
Importação + validação + gráfico.

Mudança principal:
- Agora a função principal é load_dataframe_from_bytes(file_name, file_bytes)
  para evitar o bug de "ler upload duas vezes".
"""

from __future__ import annotations

import io
import zipfile
from typing import Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt


SUPPORTED_IN_ZIP = (".csv", ".xlsx", ".xls")


def _read_csv_bytes(raw: bytes) -> pd.DataFrame:
    if not raw or len(raw) < 5:
        raise ValueError("Arquivo CSV vazio (bytes=0).")

    # tentativa 1
    try:
        return pd.read_csv(io.BytesIO(raw))
    except Exception:
        pass

    # tentativa 2 (Brasil)
    try:
        return pd.read_csv(io.BytesIO(raw), sep=";")
    except Exception:
        pass

    # tentativa 3 (latin-1)
    try:
        return pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1")
    except Exception as e:
        raise ValueError(f"Falha ao ler CSV: {e}") from e


def _looks_like_xlsx(raw: bytes) -> bool:
    return len(raw) >= 2 and raw[:2] == b"PK"


def _read_xlsx_bytes(raw: bytes) -> pd.DataFrame:
    if not _looks_like_xlsx(raw):
        raise ValueError("Extensão .xlsx mas assinatura inválida (não parece XLSX real).")
    try:
        return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    except Exception as e:
        raise ValueError(f"Falha ao ler XLSX com openpyxl: {e}") from e


def _read_xls_bytes(raw: bytes) -> pd.DataFrame:
    try:
        return pd.read_excel(io.BytesIO(raw), engine="xlrd")
    except Exception as e:
        raise ValueError(
            f"Falha ao ler XLS. Se precisar suportar .xls, instale xlrd. Erro: {e}"
        ) from e


def _extract_first_supported_from_zip(zip_bytes: bytes) -> Tuple[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(SUPPORTED_IN_ZIP)]
            if not names:
                raise ValueError("ZIP não contém CSV/XLSX/XLS.")
            chosen = names[0]
            return chosen, zf.read(chosen)
    except zipfile.BadZipFile as e:
        raise ValueError("Arquivo .zip inválido ou corrompido.") from e


def load_dataframe_from_bytes(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """
    Entrada única do sistema:
    - file_name: nome do arquivo (pra detectar extensão)
    - file_bytes: bytes do conteúdo (nunca lê duas vezes)
    """
    filename = (file_name or "").lower()
    raw = file_bytes

    if not raw:
        raise ValueError("Arquivo recebido está vazio (0 bytes).")

    if filename.endswith(".csv"):
        df = _read_csv_bytes(raw)

    elif filename.endswith(".xlsx"):
        try:
            df = _read_xlsx_bytes(raw)
        except ValueError:
            # fallback: .xlsx fake (às vezes é CSV renomeado)
            df = _read_csv_bytes(raw)

    elif filename.endswith(".xls"):
        df = _read_xls_bytes(raw)

    elif filename.endswith(".zip"):
        inner_name, inner_raw = _extract_first_supported_from_zip(raw)
        inner_name = inner_name.lower()

        if inner_name.endswith(".csv"):
            df = _read_csv_bytes(inner_raw)
        elif inner_name.endswith(".xlsx"):
            try:
                df = _read_xlsx_bytes(inner_raw)
            except ValueError:
                df = _read_csv_bytes(inner_raw)
        elif inner_name.endswith(".xls"):
            df = _read_xls_bytes(inner_raw)
        else:
            raise ValueError("Arquivo dentro do ZIP não suportado.")

    else:
        raise ValueError("Formato não suportado. Use CSV, XLSX, XLS ou ZIP.")

    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return df


def validate_columns_for_line_chart(df: pd.DataFrame, x_col: Optional[str], y_col: Optional[str]) -> None:
    if not x_col or not y_col:
        raise ValueError("Selecione as colunas X e Y na sidebar.")
    if x_col not in df.columns or y_col not in df.columns:
        raise ValueError("As colunas escolhidas não existem no DataFrame.")

    y = pd.to_numeric(df[y_col], errors="coerce")
    if y.notna().sum() == 0:
        raise ValueError(f"A coluna Y ('{y_col}') não tem valores numéricos válidos.")


def build_line_chart(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    sort_x: bool = True,
    parse_dates: bool = True,
):
    work = df[[x_col, y_col]].copy()
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")

    if parse_dates:
        parsed = pd.to_datetime(work[x_col], errors="coerce", dayfirst=True)
        if parsed.notna().sum() >= max(3, int(0.3 * len(parsed))):
            work[x_col] = parsed

    work = work.dropna(subset=[y_col])

    if sort_x:
        work = work.sort_values(by=x_col)

    fig = plt.figure()
    plt.plot(work[x_col], work[y_col])
    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.title(f"{y_col} por {x_col}")
    plt.xticks(rotation=30)
    plt.tight_layout()
    return fig


if __name__ == "__main__":
    print("criado com sucesso")