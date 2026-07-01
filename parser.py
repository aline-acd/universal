import re
from collections import defaultdict

import fitz
import pandas as pd


PADRAO_TOTAL_OBRA = re.compile(
    r"Total\s+da\s+obra\s+R\$?\s*([0-9.,]+)\s+R\$?\s*([0-9.,]+)",
    re.IGNORECASE
)

PADRAO_CLIENTE = re.compile(
    r"(?:Cliente|Favorecido)\s+(.+?)(?:\s+Per[ií]odo\s+de\s+Royalty:|\n|$)",
    re.IGNORECASE
)

PADRAO_PERIODO = re.compile(
    r"Per[ií]odo\s+de\s+Royalty:\s*(.+?)(?:\n|$)",
    re.IGNORECASE
)


def limpar_texto(texto: str) -> str:
    texto = texto or ""
    texto = texto.replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def valor_br_para_float(valor: str) -> float:
    if valor is None:
        return 0.0

    valor = str(valor).strip()
    valor = valor.replace("R$", "").replace(" ", "")

    if not valor:
        return 0.0

    # Universal costuma vir no padrão americano: 1,093.26 ou 13.93
    # Mas também aceitamos padrão brasileiro: 1.093,26
    if "," in valor and "." in valor:
        if valor.rfind(".") > valor.rfind(","):
            # americano: 1,093.26
            valor = valor.replace(",", "")
        else:
            # brasileiro: 1.093,26
            valor = valor.replace(".", "").replace(",", ".")
    elif "," in valor and "." not in valor:
        # brasileiro simples: 13,93
        valor = valor.replace(",", ".")

    try:
        return float(valor)
    except Exception:
        return 0.0


def float_para_br(valor: float) -> str:
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return ""


def extrair_cliente_periodo(texto: str):
    texto = limpar_texto(texto)

    cliente = ""
    periodo = ""

    m_cliente = PADRAO_CLIENTE.search(texto)
    if m_cliente:
        cliente = m_cliente.group(1).strip()

    m_periodo = PADRAO_PERIODO.search(texto)
    if m_periodo:
        periodo = m_periodo.group(1).strip()

    return cliente, periodo


def linha_inutil_para_obra(linha: str) -> bool:
    up = linha.upper().strip()

    termos = [
        "TITULO & COMPOSITORES",
        "TÍTULO & COMPOSITORES",
        "TERRITÓRIO",
        "TERRITORIO",
        "EXPLORAÇÃO",
        "EXPLORACAO",
        "FONTE DE RENDA",
        "TIPO DE",
        "NÚMERO DE",
        "NUMERO DE",
        "CATÁLOGO",
        "CATALOGO",
        "RECEBIMENTOS",
        "UNIDADES",
        "VALORES",
        "SUA COTA",
        "VALOR DEVIDO",
        "RELATÓRIO DE ROYALTY",
        "RELATORIO DE ROYALTY",
        "UNIVERSAL MUSIC",
        "PÁGINA",
        "PAGINA",
        "TOTAL DA OBRA",
        "TOTAIS FINAIS",
        "FAVORECIDO",
        "PERÍODO DE ROYALTY",
        "PERIODO DE ROYALTY",
    ]

    if any(t in up for t in termos):
        return True

    if re.fullmatch(r"\d+", up):
        return True

    return False


def parece_obra(linha: str) -> bool:
    linha = limpar_texto(linha)
    up = linha.upper()

    if not linha or linha_inutil_para_obra(linha):
        return False

    # Obra costuma vir em caixa alta e sem valores.
    if re.search(r"R\$|[0-9]+[.,][0-9]{2}", linha):
        return False

    # Evita compositor/autor.
    if "..." in linha:
        return False

    # Evita fontes/territórios mais comuns.
    bloqueios = [
        "BRAZIL",
        "PORTUGAL",
        "SPAIN",
        "FRANCE",
        "USA AND",
        "DOMINIONS",
        "TERRITORIES",
        "SPOTIFY",
        "YOUTUBE",
        "BACKOFFICE",
        "ABRAMUS",
        "UBC",
        "SACEM",
        "PRS",
        "APPLE",
        "DEEZER",
        "FACEBOOK",
        "NAPSTER",
        "STREAMING",
        "PERFORMANCE",
        "MECH",
        "PERF",
        "RADIO",
        "LIVE",
    ]

    if any(b in up for b in bloqueios):
        return False

    letras = re.sub(r"[^A-ZÀ-Ü]", "", up)
    if len(letras) < 3:
        return False

    # Aceita títulos com números, tipo "15 MINUTOS", desde que a maior parte seja caixa alta.
    return up == linha.upper()


def extrair_linhas_pagina(pagina) -> list[str]:
    # sort=False mantém a ordem original da página, que é importante nesse layout.
    texto = pagina.get_text("text", sort=False) or ""

    linhas = []
    for raw in texto.splitlines():
        linha = limpar_texto(raw)
        if linha:
            linhas.append(linha)

    return linhas


def processar_pdf_universal(
    caminho_pdf: str,
    nome_arquivo: str,
    pagina_inicio: int = 1,
    pagina_fim: int | None = None,
    max_paginas: int | None = None,
    agrupar: bool = True,
) -> pd.DataFrame:
    registros = []
    acumulado = defaultdict(lambda: {
        "Arquivo": nome_arquivo,
        "Cliente": "",
        "Periodo": "",
        "Obra": "",
        "Recebimentos_Num": 0.0,
        "Valor_Devido_Num": 0.0,
        "Paginas_Set": set(),
    })

    cliente_atual = ""
    periodo_atual = ""
    obra_atual = ""

    doc = fitz.open(caminho_pdf)

    try:
        total_paginas = len(doc)
        paginas_processadas = 0

        for indice in range(total_paginas):
            numero_pagina = indice + 1

            if numero_pagina < pagina_inicio:
                continue

            if pagina_fim is not None and numero_pagina > pagina_fim:
                break

            if max_paginas is not None and paginas_processadas >= max_paginas:
                break

            pagina = doc[indice]
            texto_pagina = pagina.get_text("text", sort=False) or ""
            linhas = extrair_linhas_pagina(pagina)

            cliente, periodo = extrair_cliente_periodo(texto_pagina)
            if cliente:
                cliente_atual = cliente
            if periodo:
                periodo_atual = periodo

            for linha in linhas:
                total_match = PADRAO_TOTAL_OBRA.search(linha)

                if total_match and obra_atual:
                    recebimentos = valor_br_para_float(total_match.group(1))
                    valor_devido = valor_br_para_float(total_match.group(2))

                    if agrupar:
                        chave = (nome_arquivo, obra_atual)
                        item = acumulado[chave]
                        item["Cliente"] = cliente_atual
                        item["Periodo"] = periodo_atual
                        item["Obra"] = obra_atual
                        item["Recebimentos_Num"] += recebimentos
                        item["Valor_Devido_Num"] += valor_devido
                        item["Paginas_Set"].add(numero_pagina)
                    else:
                        registros.append({
                            "Arquivo": nome_arquivo,
                            "Cliente": cliente_atual,
                            "Periodo": periodo_atual,
                            "Obra": obra_atual,
                            "Recebimentos": recebimentos,
                            "Valor_Devido": valor_devido,
                            "Paginas": str(numero_pagina),
                        })

                    continue

                if parece_obra(linha):
                    obra_atual = linha.strip()

            paginas_processadas += 1

    finally:
        doc.close()

    if agrupar:
        for item in acumulado.values():
            registros.append({
                "Arquivo": item["Arquivo"],
                "Cliente": item["Cliente"],
                "Periodo": item["Periodo"],
                "Obra": item["Obra"],
                "Recebimentos": item["Recebimentos_Num"],
                "Valor_Devido": item["Valor_Devido_Num"],
                "Paginas": ", ".join(map(str, sorted(item["Paginas_Set"]))),
            })

    df = pd.DataFrame(registros)

    if df.empty:
        return df

    df = df.sort_values(["Arquivo", "Obra"]).reset_index(drop=True)

    df["Recebimentos"] = df["Recebimentos"].apply(float_para_br)
    df["Valor_Devido"] = df["Valor_Devido"].apply(float_para_br)

    return df
