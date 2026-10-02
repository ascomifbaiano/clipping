"""
ingestao_clipping_manual.py - Ingestor de Curadoria Manual DICOM (Google Docs)
Instituto Federal de Educação, Ciência e Tecnologia Baiano
Diretriz Mandatória: Operação Estritamente SOMENTE LEITURA (READ-ONLY) na fonte original.

Funcionalidade:
1. Conecta-se via HTTP GET (modo somente leitura) ao endpoint de exportação pública HTML do Google Docs.
2. Extrai e normaliza todas as matérias catalogadas manualmente pelos jornalistas da DICOM.
3. Desduplica os registros contra o acervo consolidado (clipping_geral.csv) só pela
   URL canônica (sem UTMs, redirecionamentos e protocolo). Desde a v3.0 (02/10/2026),
   a mesma pauta em veículos diferentes conta como repercussão, as tabelas são lidas
   pelo nome das colunas e cada linha recebe origem = curadoria_dicom.
4. Aplica os classificadores heurísticos de clipping_utils (Eixo, Abrangência e Campus).
5. Se executado com --dry-run (padrão em testes), apenas audita e exibe métricas sem alterar arquivos.
6. Se executado com --apply (ou em ambiente de CI/CD), consolida e particiona os CSVs e stats.json.
"""

import os
import re
import sys
import argparse
import urllib.parse
from datetime import datetime
from difflib import SequenceMatcher

import requests
import urllib3
import pandas as pd
from bs4 import BeautifulSoup

from clipping_utils import (
    DIR_DATA,
    classificar_eixo,
    classificar_abrangencia,
    classificar_campus,
    salvar_e_gerar_stats,
    remover_acentos,
    normalizar_campus_curadoria,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

# URL Oficial da Curadoria Manual DICOM (Acesso estritamente READ-ONLY via exportação HTML)
DOC_EXPORT_URL = (
    "https://docs.google.com/document/d/"
    "1zsI6248qboGF5PVj8FM2O-GcIKCcaMC5whaifuR-EHg/export?format=html"
)


def normalizar_url_canonica(url_bruta: str) -> str:
    """
    Normaliza URLs para comparação desconsiderando protocolo, www, barras finais e tags UTM.
    Também decodifica redirecionamentos do Google (url?q=...).
    """
    if not url_bruta:
        return ""
    
    url = url_bruta.strip()
    
    # Decodifica redirecionamento do Google
    if "google.com/url?" in url:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if "q" in params and params["q"]:
            url = params["q"][0]

    # Remove fragmentos (#)
    url = url.split("#")[0]

    # Parse da URL limpa
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        
        path = parsed.path.rstrip("/")
        
        # Filtra query params removendo rastreadores
        if parsed.query:
            query_params = urllib.parse.parse_qs(parsed.query)
            params_limpos = {
                k: v for k, v in query_params.items()
                if not k.lower().startswith("utm_")
                and k.lower() not in ["fbclid", "gclid", "ref", "source"]
            }
            if params_limpos:
                query_str = urllib.parse.urlencode(params_limpos, doseq=True)
                return f"{netloc}{path}?{query_str}".lower()

        return f"{netloc}{path}".lower()
    except Exception:
        return url.lower().rstrip("/")


def gerar_slug_titulo_veiculo(assunto: str, veiculo: str) -> str:
    """Chave de título e veículo sem acentos e pontuação (mantida para compatibilidade)."""
    a = remover_acentos(str(assunto)).strip().lower()
    v = remover_acentos(str(veiculo)).strip().lower()
    a_clean = re.sub(r'[^a-z0-9]', '', a)
    v_clean = re.sub(r'[^a-z0-9]', '', v)
    return f"{a_clean}|{v_clean}"


def desembrulhar_link(url: str) -> str:
    """Troca https://www.google.com/url?q=<real>&sa=... pelo endereço real."""
    url = (url or "").strip()
    if "google.com/url?" in url:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q")
        if q and q[0].startswith("http"):
            return q[0]
    return url


def veiculo_pelo_dominio(url: str) -> str:
    netloc = urllib.parse.urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _veiculo_suspeito(valor: str) -> bool:
    """Veículo que na verdade é campus, a própria instituição ou texto genérico."""
    v = remover_acentos(valor).strip()
    if not v or v in ("portal de noticias", "midia externa", "nan"):
        return True
    if "if baiano" in v or "ifbaiano" in v:
        return True
    return bool(normalizar_campus_curadoria(valor)) and len(v.split()) <= 4 and not re.search(r"noticia|news|blog|portal|jornal|radio|tv|agencia|folha|gazeta", v)


def _mapear_colunas(cabecalho: list) -> dict:
    """Localiza as colunas pelo nome; as tabelas do documento mudaram de formato ao longo dos anos."""
    mapa = {}
    for i, nome in enumerate(cabecalho):
        n = remover_acentos(nome).strip()
        if n.startswith("data") and "data" not in mapa:
            mapa["data"] = i
        elif n.startswith("assunto"):
            mapa["assunto"] = i
        elif n.startswith("veiculo"):
            mapa["veiculo"] = i
        elif n.startswith("campus") or n.startswith("unidade"):
            mapa["campus"] = i
        elif n.startswith("link"):
            mapa["link"] = i
    return mapa if {"data", "assunto"} <= mapa.keys() else {}


def _converter_data(data_raw: str, link: str, ano_corrente: int) -> str:
    m = re.search(r"^(\d{1,2})/(\d{1,2})/(20\d{2})", data_raw)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"^(\d{1,2})/(\d{1,2})/(\d{2})\b", data_raw)
    if m:
        return f"20{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"^(\d{1,2})/(\d{1,2})", data_raw)
    if m:
        m_ano = re.search(r"/(20[2-3]\d)/", link)
        ano = int(m_ano.group(1)) if m_ano else ano_corrente
        return f"{ano}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"/(20[2-3]\d)/(\d{2})/(\d{2})/", link)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(20[2-3]\d)/(\d{2})/", link)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return f"{ano_corrente}-01-01"


def extrair_noticias_google_docs(url_export: str = DOC_EXPORT_URL) -> list:
    """
    Leitura estritamente READ-ONLY do documento exportado em HTML.
    Cada tabela é lida pelo seu cabeçalho (Data, Assunto, Tema, Campus/Unidade,
    Veículo, Link), porque a ordem das colunas mudou ao longo dos anos. Tabelas
    sem cabeçalho seguem o formato antigo: Data, Assunto, Veículo, Link.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print(f"Iniciando leitura em modo SOMENTE LEITURA de: {url_export}")
    resp = requests.get(url_export, headers=headers, verify=False, timeout=45)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("body")
    if not body:
        print("Erro: Estrutura HTML do documento nao contem elemento body.")
        return []

    noticias = []
    ano_corrente = 2020
    mapa_padrao = {"data": 0, "assunto": 1, "veiculo": 2, "link": 3}

    for elem in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table"]):
        if elem.name != "table":
            # Títulos de mês e ano fora das tabelas definem o ano corrente
            if elem.find_parent("table") is None:
                m_ano = re.search(r"\b(20[2-3]\d)\b", elem.get_text(strip=True))
                if m_ano:
                    ano_corrente = int(m_ano.group(1))
            continue

        linhas = elem.find_all("tr")
        if not linhas:
            continue
        mapa = _mapear_colunas([td.get_text(strip=True) for td in linhas[0].find_all("td")])
        if mapa:
            linhas = linhas[1:]
        else:
            mapa = mapa_padrao

        for tr in linhas:
            tds = tr.find_all("td")
            celulas = [c.get_text(" ", strip=True) for c in tds]
            if len(celulas) < 3:
                continue

            link = None
            for a_tag in tr.find_all("a", href=True):
                if a_tag["href"].strip().startswith("http"):
                    link = a_tag["href"].strip()
                    break
            if not link:
                m_url = re.search(r'(https?://[^\s"\'<>]+)', " ".join(celulas))
                link = m_url.group(1) if m_url else None
            if not link:
                continue
            link = desembrulhar_link(link)

            def celula(chave):
                i = mapa.get(chave)
                return celulas[i].strip() if i is not None and i < len(celulas) else ""

            assunto = celula("assunto")
            if len(assunto) < 4 or remover_acentos(assunto).startswith("assunto"):
                continue

            veiculo = celula("veiculo")
            campus_bruto = celula("campus")
            if _veiculo_suspeito(veiculo):
                # No formato antigo o "veículo" às vezes trazia o campus
                if not campus_bruto:
                    campus_bruto = veiculo
                veiculo = veiculo_pelo_dominio(link) or "Mídia Externa"

            noticias.append({
                "data": _converter_data(celula("data"), link, ano_corrente),
                "assunto": assunto,
                "veiculo": veiculo,
                "link": link,
                "campus": normalizar_campus_curadoria(campus_bruto),
                "origem": "curadoria_dicom",
            })

    print(f"Total de registros brutos extraídos do Google Docs: {len(noticias)}")
    return noticias


def executar_pipeline_ingestao(dry_run: bool = True, dir_data: str = DIR_DATA):
    """
    Cruza a curadoria manual com o acervo. A deduplicação é só por URL canônica:
    a mesma pauta em veículos diferentes é repercussão e conta mais de uma vez.
    Linhas da curadoria já presentes no acervo são corrigidas (origem, veículo
    e campus), porque versões anteriores gravavam o campus no lugar do veículo.
    """
    print("=" * 70)
    print("INGESTÃO DA CURADORIA MANUAL DICOM (GOOGLE DOCS READ-ONLY)")
    print(f"Modo: {'DRY-RUN (simulação)' if dry_run else 'APPLY (grava em disco)'}")
    print("=" * 70)

    caminho_geral = os.path.join(dir_data, "clipping_geral.csv")
    if os.path.exists(caminho_geral):
        df_existente = pd.read_csv(caminho_geral, encoding="utf-8-sig")
        print(f"Acervo atual: {len(df_existente)} notícias.")
    else:
        df_existente = pd.DataFrame(columns=["data", "assunto", "veiculo", "link"])
        print("Aviso: acervo não encontrado. Uma nova base será iniciada.")

    for col in ("campus", "origem", "tipo_mencao"):
        if col not in df_existente.columns:
            df_existente[col] = ""
    df_existente = df_existente.fillna("")

    indice_existente = {}
    for idx, url in df_existente["link"].astype(str).items():
        chave = normalizar_url_canonica(url)
        if chave:
            indice_existente.setdefault(chave, idx)

    registros = extrair_noticias_google_docs()
    if not registros:
        print("Nenhum registro recuperado da curadoria. Encerrando.")
        return

    novos, vistos = [], set()
    duplicados_internos = corrigidos = autoclipping = 0

    for item in registros:
        if "ifbaiano.edu.br" in item["link"].lower():
            autoclipping += 1
            continue
        chave = normalizar_url_canonica(item["link"])
        if chave in vistos:
            duplicados_internos += 1
            continue
        vistos.add(chave)

        idx = indice_existente.get(chave)
        if idx is None:
            novos.append(item)
            continue

        # Já está no acervo: a curadoria é a fonte confiável de origem e campus
        linha = df_existente.loc[idx]
        df_existente.at[idx, "origem"] = "curadoria_dicom"
        df_existente.at[idx, "link"] = desembrulhar_link(str(linha["link"]))
        if _veiculo_suspeito(str(linha["veiculo"])):
            df_existente.at[idx, "veiculo"] = item["veiculo"]
        if item["campus"]:
            df_existente.at[idx, "campus"] = item["campus"]
        corrigidos += 1

    print("\n--- Relatório ---")
    print(f"Registros na fonte: {len(registros)}")
    print(f"Links do próprio portal ifbaiano.edu.br (ignorados): {autoclipping}")
    print(f"Links repetidos dentro do documento: {duplicados_internos}")
    print(f"Já presentes no acervo (origem e veículo conferidos): {corrigidos}")
    print(f"Novas notícias: {len(novos)}")

    df_novos = pd.DataFrame(novos)
    if not df_novos.empty:
        print("Novas por campus (5 maiores):")
        for campus, n in df_novos["campus"].replace("", "Não informado").value_counts().head(5).items():
            print(f"  - {campus}: {n}")

    if dry_run:
        print("\nDRY-RUN concluído. Nenhum arquivo alterado. Use --apply para gravar.")
        return

    colunas = ["data", "assunto", "veiculo", "link", "eixo_institucional",
               "abrangencia", "campus", "origem", "tipo_mencao"]
    for df in (df_existente, df_novos):
        for col in colunas:
            if col not in df.columns:
                df[col] = ""
    partes = [df_existente[colunas]] + ([df_novos[colunas]] if not df_novos.empty else [])
    df_completo = pd.concat(partes, ignore_index=True)
    salvar_e_gerar_stats(df_completo, dir_data=dir_data)
    print(f"Consolidação concluída: {len(df_completo)} linhas antes da deduplicação final.")



def main():
    parser = argparse.ArgumentParser(
        description="Ingestor de Curadoria Manual DICOM do IF Baiano (Google Docs Read-Only)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica e salva as novas notícias no disco (padrão é simulação --dry-run)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo de simulação estrita sem alterar nenhum arquivo de dados local"
    )
    parser.add_argument(
        "--dir-data",
        default=DIR_DATA,
        help="Diretório dos arquivos de dados (padrão: data)"
    )

    args = parser.parse_args()
    
    # Se --apply for passado explicitamente, desativa o dry_run. Caso contrário, mantém seguro.
    dry_run_mode = not args.apply

    executar_pipeline_ingestao(dry_run=dry_run_mode, dir_data=args.dir_data)


if __name__ == "__main__":
    main()
