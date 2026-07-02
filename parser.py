import re
from collections import defaultdict
from typing import Optional

import fitz
import pandas as pd

PADRAO_DINHEIRO = re.compile(r"R\$?\s*([0-9.,]+)", re.IGNORECASE)
PADRAO_CLIENTE = re.compile(r"(?:Cliente|Favorecido)\s+(.+?)(?:\s+Per[ií]odo\s+de\s+Royalty:|\n|$)", re.IGNORECASE)
PADRAO_PERIODO = re.compile(r"Per[ií]odo\s+de\s+Royalty:\s*(.+?)(?:\n|$)", re.IGNORECASE)
PADRAO_PERIODO_LINHA = re.compile(r"\d{2}/\d{2}-\d{2}/\d{2}")


def limpar_texto(texto: str) -> str:
    texto = texto or ""
    texto = texto.replace("\u00a0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    return texto.strip()


def valor_para_float(valor: str) -> float:
    if valor is None:
        return 0.0
    valor = str(valor).strip().replace("R$", "").replace(" ", "")
    if not valor:
        return 0.0
    if "," in valor and "." in valor:
        if valor.rfind(".") > valor.rfind(","):
            valor = valor.replace(",", "")
        else:
            valor = valor.replace(".", "").replace(",", ".")
    elif "," in valor and "." not in valor:
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
        "TITULO & COMPOSITORES", "TÍTULO & COMPOSITORES", "TERRITÓRIO", "TERRITORIO",
        "EXPLORAÇÃO", "EXPLORACAO", "FONTE DE RENDA", "TIPO DE", "RENDA",
        "NÚMERO DE", "NUMERO DE", "CATÁLOGO", "CATALOGO", "RECEBIMENTOS",
        "DO PERÍODO", "DO PERIODO", "UNIDADES", "VALORES", "RECEBIDOS",
        "SUA COTA", "VALOR DEVIDO", "RELATÓRIO DE ROYALTY", "RELATORIO DE ROYALTY",
        "UNIVERSAL MUSIC", "PÁGINA", "PAGINA", "TOTAL DA OBRA", "TOTAIS FINAIS",
        "FAVORECIDO", "PERÍODO DE ROYALTY", "PERIODO DE ROYALTY", "AV. DAS AMERICAS",
        "RJ, BRASIL", "CUSTSERVPUBBR", "VEJA OU FAÇA", "OU PORQUE",
    ]
    if any(t in up for t in termos):
        return True
    if re.fullmatch(r"\d+", up):
        return True
    return False


def parece_titulo_obra(linha: str) -> bool:
    linha = limpar_texto(linha)
    up = linha.upper()
    if not linha or linha_inutil_para_obra(linha):
        return False
    if "..." in linha:
        return False
    if re.search(r"R\$|[0-9]+[.,][0-9]{2}", linha):
        return False
    bloqueios = [
        "BRAZIL", "PORTUGAL", "SPAIN", "FRANCE", "BELGIUM", "LUXEMBOURG", "USA AND",
        "DOMINIONS", "TERRITORIES", "SPOTIFY", "YOUTUBE", "BACKOFFICE", "ABRAMUS", "UBC",
        "SACEM", "PRS", "APPLE", "DEEZER", "FACEBOOK", "NAPSTER", "STREAMING", "PERFORMANCE",
        "MECH", "PERF", "RADIO", "LIVE", "COMPOSITORES", "MUSIC", "PREMIUM", "FAMILY",
        "INDIV", "TRIAL", "MATCH", "STUDENT", "TIKTOK", "AMAZON", "GLOBOPLAY", "ITUNES",
        "RHAPSODY", "MUMO",
    ]
    if any(b in up for b in bloqueios):
        return False
    letras = re.sub(r"[^A-ZÀ-Ü]", "", up)
    if len(letras) < 3:
        return False
    return linha == up


def eh_linha_obra(linhas: list[str], indice: int) -> bool:
    if not parece_titulo_obra(linhas[indice]):
        return False
    for j in range(indice + 1, min(indice + 4, len(linhas))):
        if "..." in linhas[j]:
            return True
        if linhas[j].upper().startswith("TOTAL DA OBRA"):
            return False
    return False


def extrair_linhas_pagina(pagina) -> list[str]:
    texto = pagina.get_text("text", sort=False) or ""
    return [limpar_texto(raw) for raw in texto.splitlines() if limpar_texto(raw)]


def extrair_totais_apos_total_da_obra(linhas: list[str], indice: int):
    valores = []
    for j in range(indice, min(indice + 5, len(linhas))):
        valores.extend(PADRAO_DINHEIRO.findall(linhas[j]))
    if len(valores) >= 2:
        return valor_para_float(valores[0]), valor_para_float(valores[1])
    return None, None


def extrair_unidades_da_linha(linha: str) -> int:
    """
    Soma unidades/plays das linhas detalhadas.
    Streaming com unidades: 08/20-08/20 21 0.05 75.00 0.04
    Performance sem unidades: 01/21-03/21 13.07 50.00 6.53
    """
    linha = limpar_texto(linha)
    m = PADRAO_PERIODO_LINHA.search(linha)
    if not m:
        return 0
    depois = linha[m.end():].strip()
    nums = re.findall(r"\d+(?:[.,]\d+)?", depois)
    if len(nums) < 4:
        return 0
    candidato = nums[0]
    if re.fullmatch(r"\d+", candidato):
        try:
            return int(candidato)
        except Exception:
            return 0
    return 0


def processar_pdf_universal(
    caminho_pdf: str,
    nome_arquivo: str,
    pagina_inicio: int = 1,
    pagina_fim: Optional[int] = None,
    max_paginas: Optional[int] = None,
    agrupar: bool = True,
) -> pd.DataFrame:
    registros = []
    acumulado = defaultdict(lambda: {
        "Arquivo": nome_arquivo,
        "Cliente": "",
        "Periodo": "",
        "Obra": "",
        "Unidades_Num": 0,
        "Recebimentos_Num": 0.0,
        "Valor_Devido_Num": 0.0,
        "Paginas_Set": set(),
    })
    cliente_atual = ""
    periodo_atual = ""
    obra_atual = ""
    unidades_obra_atual = 0
    doc = fitz.open(caminho_pdf)
    try:
        paginas_processadas = 0
        for indice in range(len(doc)):
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
            for i, linha in enumerate(linhas):
                if eh_linha_obra(linhas, i):
                    obra_atual = linha.strip()
                    unidades_obra_atual = 0
                    continue
                if obra_atual and not linha.upper().startswith("TOTAL DA OBRA"):
                    unidades_obra_atual += extrair_unidades_da_linha(linha)
                if linha.upper().startswith("TOTAL DA OBRA") and obra_atual:
                    recebimentos, valor_devido = extrair_totais_apos_total_da_obra(linhas, i)
                    if recebimentos is None or valor_devido is None:
                        continue
                    if agrupar:
                        chave = (nome_arquivo, obra_atual)
                        item = acumulado[chave]
                        item["Cliente"] = cliente_atual
                        item["Periodo"] = periodo_atual
                        item["Obra"] = obra_atual
                        item["Unidades_Num"] += unidades_obra_atual
                        item["Recebimentos_Num"] += recebimentos
                        item["Valor_Devido_Num"] += valor_devido
                        item["Paginas_Set"].add(numero_pagina)
                    else:
                        registros.append({
                            "Arquivo": nome_arquivo,
                            "Cliente": cliente_atual,
                            "Periodo": periodo_atual,
                            "Obra": obra_atual,
                            "Unidades": unidades_obra_atual,
                            "Recebimentos": recebimentos,
                            "Valor_Devido": valor_devido,
                            "Paginas": str(numero_pagina),
                        })
                    unidades_obra_atual = 0
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
                "Unidades": item["Unidades_Num"],
                "Recebimentos": item["Recebimentos_Num"],
                "Valor_Devido": item["Valor_Devido_Num"],
                "Paginas": ", ".join(map(str, sorted(item["Paginas_Set"]))),
            })
    df = pd.DataFrame(registros)
    if df.empty:
        return df
    df = df.sort_values(["Arquivo", "Obra"]).reset_index(drop=True)
    df["Unidades"] = df["Unidades"].fillna(0).astype(int)
    df["Recebimentos"] = df["Recebimentos"].apply(float_para_br)
    df["Valor_Devido"] = df["Valor_Devido"].apply(float_para_br)
    return df
