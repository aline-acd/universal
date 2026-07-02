import io
import pandas as pd


def ajustar_largura_colunas(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 2, 60)


def criar_excel(df: pd.DataFrame, total_unidades: pd.DataFrame | None = None) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resumo Universal")
        if total_unidades is None:
            if "Obra" in df.columns and "Unidades" in df.columns:
                total_unidades = (
                    df.groupby("Obra", as_index=False)["Unidades"]
                    .sum()
                    .rename(columns={"Unidades": "Total_Unidades"})
                    .sort_values("Obra")
                    .reset_index(drop=True)
                )
            else:
                total_unidades = pd.DataFrame(columns=["Obra", "Total_Unidades"])
        total_unidades.to_excel(writer, index=False, sheet_name="Total Unidades")
        ajustar_largura_colunas(writer.sheets["Resumo Universal"])
        ajustar_largura_colunas(writer.sheets["Total Unidades"])
    output.seek(0)
    return output
