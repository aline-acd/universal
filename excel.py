import io
import pandas as pd


def criar_excel(df: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Resumo Universal")

        ws = writer.sheets["Resumo Universal"]

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter

            for cell in col:
                try:
                    max_len = max(max_len, len(str(cell.value or "")))
                except Exception:
                    pass

            ws.column_dimensions[col_letter].width = min(max_len + 2, 60)

    output.seek(0)
    return output
