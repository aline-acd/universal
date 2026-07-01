import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from parser import processar_pdf_universal
from excel import criar_excel


st.set_page_config(
    page_title="Universal Royalty - Resumo por Obra",
    layout="wide"
)

st.title("Universal Royalty - Resumo por Obra")
st.write(
    "Envie relatórios PDF da Universal. O sistema lê página por página e extrai "
    "**Obra**, **Recebimentos** e **Valor Devido** a partir do campo **Total da obra**."
)

st.info(
    "Para PDFs grandes, comece pelo modo teste. Se o resultado estiver correto, "
    "desmarque o teste e processe o arquivo inteiro."
)

uploaded_files = st.file_uploader(
    "Envie um ou mais PDFs Universal Royalty",
    type=["pdf"],
    accept_multiple_files=True
)

col1, col2, col3 = st.columns(3)

with col1:
    modo_teste = st.checkbox("Modo teste: processar só 10 páginas", value=True)

with col2:
    usar_intervalo = st.checkbox("Processar intervalo de páginas", value=False)

with col3:
    agrupar_arquivos = st.checkbox("Somar obras repetidas por arquivo", value=True)

pagina_inicio = 1
pagina_fim = None

if usar_intervalo:
    col_a, col_b = st.columns(2)
    with col_a:
        pagina_inicio = st.number_input("Página inicial", min_value=1, value=1, step=1)
    with col_b:
        pagina_fim_input = st.number_input("Página final", min_value=1, value=50, step=1)
        pagina_fim = int(pagina_fim_input)

if uploaded_files:
    if st.button("Gerar resumo"):
        todos = []
        progress = st.progress(0)
        status = st.empty()

        for idx, arquivo in enumerate(uploaded_files, start=1):
            status.write(f"Processando: **{arquivo.name}**")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(arquivo.read())
                caminho_pdf = tmp.name

            try:
                max_paginas = 10 if modo_teste else None

                df = processar_pdf_universal(
                    caminho_pdf=caminho_pdf,
                    nome_arquivo=arquivo.name,
                    pagina_inicio=int(pagina_inicio),
                    pagina_fim=pagina_fim,
                    max_paginas=max_paginas,
                    agrupar=agrupar_arquivos,
                )

                if not df.empty:
                    todos.append(df)

            except Exception as e:
                st.error(f"Erro ao processar {arquivo.name}: {e}")

            finally:
                try:
                    Path(caminho_pdf).unlink(missing_ok=True)
                except Exception:
                    pass

            progress.progress(idx / len(uploaded_files))

        status.empty()

        if todos:
            final = pd.concat(todos, ignore_index=True)

            st.subheader("Resultado")
            st.dataframe(final, use_container_width=True)

            st.success(f"Total de linhas encontradas: {len(final)}")

            excel = criar_excel(final)

            st.download_button(
                "Baixar Excel",
                data=excel,
                file_name="resumo_universal_royalty.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.warning("Nenhuma obra foi encontrada. Verifique se o PDF possui linhas 'Total da obra'.")
