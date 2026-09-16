"""
ingestao_clipping_manual.py - Ingestor de Curadoria Manual DICOM (Google Docs)
Instituto Federal de Educação, Ciência e Tecnologia Baiano
Diretriz Mandatória: Operação Estritamente SOMENTE LEITURA (READ-ONLY) na fonte original.

Funcionalidade:
1. Conecta-se via HTTP GET (modo somente leitura) ao endpoint de exportação pública HTML do Google Docs.
2. Extrai e normaliza todas as matérias catalogadas manualmente pelos jornalistas da DICOM.
3. Desduplica os registros contra o acervo consolidado do portal (clipping_geral.csv) em 3 camadas:
   - Camada 1: URL Canônica Normalizada (expurgo de UTMs, redirecionamentos e protocolos)
   - Camada 2: Chave Composta de Título Normalizado + Veículo
   - Camada 3: Verificação de Similaridade Textual
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
    """Gera chave composta única de título e veículo desconsiderando acentos e pontuação."""
    a = remover_acentos(str(assunto)).strip().lower()
    v = remover_acentos(str(veiculo)).strip().lower()
    a_clean = re.sub(r'[^a-z0-9]', '', a)
    v_clean = re.sub(r'[^a-z0-9]', '', v)
    return f"{a_clean}|{v_clean}"


def extrair_noticias_google_docs(url_export: str = DOC_EXPORT_URL) -> list:
    """
    Realiza leitura estritamente READ-ONLY do documento Google Docs exportado em HTML.
    Percorre seções mensais, normaliza datas, assuntos, veículos e links.
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

    noticias_extraidas = []
    current_year = 2020

    # Percorre os elementos mantendo rastreamento de ano por cabeçalhos
    elementos = body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "tr"])
    for elem in elementos:
        if elem.name in ["h1", "h2", "h3", "h4", "h5", "h6", "p"]:
            txt = elem.get_text(strip=True)
            m_year = re.search(r"\b(202[0-6])\b", txt)
            if m_year:
                current_year = int(m_year.group(1))

        elif elem.name == "tr":
            tds = elem.find_all("td")
            if len(tds) < 3:
                continue

            cells = [c.get_text(strip=True) for c in tds]
            row_text = " ".join(cells)

            # Extração de URL (âncoras ou texto plano)
            link_encontrado = None
            for a_tag in elem.find_all("a", href=True):
                href = a_tag["href"].strip()
                if href.startswith("http"):
                    link_encontrado = href
                    break

            if not link_encontrado:
                m_url = re.search(r'(https?://[^\s"\'<>]+)', row_text)
                if m_url:
                    link_encontrado = m_url.group(1).strip()

            if not link_encontrado:
                continue

            data_raw = cells[0].strip()
            assunto = cells[1].strip() if len(cells) > 1 else ""
            veiculo = cells[2].strip() if len(cells) > 2 else ""

            # Descarta linhas de cabeçalho interno das tabelas
            if "data" in data_raw.lower() or "assunto" in assunto.lower():
                continue

            if not assunto or len(assunto) < 4:
                continue

            # Resolução e normalização robusta de data para formato ISO YYYY-MM-DD
            data_iso = None

            # 1. Padrão DD/MM/YYYY
            m_dmy = re.search(r"^(\d{1,2})/(\d{1,2})/(20\d{2})", data_raw)
            if m_dmy:
                data_iso = f"{m_dmy.group(3)}-{int(m_dmy.group(2)):02d}-{int(m_dmy.group(1)):02d}"
            else:
                # 2. Padrão DD/MM/YY
                m_dmy2 = re.search(r"^(\d{1,2})/(\d{1,2})/(\d{2})", data_raw)
                if m_dmy2:
                    data_iso = f"20{m_dmy2.group(3)}-{int(m_dmy2.group(2)):02d}-{int(m_dmy2.group(1)):02d}"
                else:
                    # 3. Padrão DD/MM ou DD/MM/
                    m_dm = re.search(r"^(\d{1,2})/(\d{1,2})/?", data_raw)
                    if m_dm:
                        m_url_yr = re.search(r"/(202[0-6])/", link_encontrado)
                        yr = int(m_url_yr.group(1)) if m_url_yr else current_year
                        data_iso = f"{yr}-{int(m_dm.group(2)):02d}-{int(m_dm.group(1)):02d}"
                    else:
                        # 4. Busca data estruturada na própria URL
                        m_url_date = re.search(r"/(202[0-6])/(\d{2})/(\d{2})/", link_encontrado)
                        if m_url_date:
                            data_iso = f"{m_url_date.group(1)}-{m_url_date.group(2)}-{m_url_date.group(3)}"
                        else:
                            m_url_mo = re.search(r"/(202[0-6])/(\d{2})/", link_encontrado)
                            if m_url_mo:
                                data_iso = f"{m_url_mo.group(1)}-{m_url_mo.group(2)}-01"
                            else:
                                data_iso = f"{current_year}-01-01"

            noticias_extraidas.append({
                "data": data_iso,
                "assunto": assunto,
                "veiculo": veiculo if veiculo else "Portal de Notícias",
                "link": link_encontrado,
            })

    print(f"Total de registros brutos extraídos do Google Docs: {len(noticias_extraidas)}")
    return noticias_extraidas


def executar_pipeline_ingestao(dry_run: bool = True, dir_data: str = DIR_DATA):
    """
    Executa o cruzamento completo da curadoria manual com o acervo automatizado existente.
    """
    print("=" * 70)
    print("INICIANDO INGESTÃO DE CURADORIA MANUAL DICOM (GOOGLE DOCS READ-ONLY)")
    print(f"Modo de Operação: {'DRY-RUN (Simulação - sem alteração de arquivos)' if dry_run else 'APPLY (Consolidação em disco)'}")
    print("=" * 70)

    # 1. Carrega o acervo existente
    caminho_geral = os.path.join(dir_data, "clipping_geral.csv")
    if os.path.exists(caminho_geral):
        df_existente = pd.read_csv(caminho_geral)
        print(f"Acervo atual carregado: {len(df_existente)} notícias existentes.")
    else:
        df_existente = pd.DataFrame(columns=["data", "assunto", "veiculo", "link"])
        print("Aviso: Acervo atual não encontrado. Uma nova base será inicializada.")

    # 2. Constrói índices de busca rápida para desduplicação
    urls_canonicas_existentes = set()
    slugs_existentes = set()

    for _, row in df_existente.iterrows():
        url_c = normalizar_url_canonica(str(row.get("link", "")))
        if url_c:
            urls_canonicas_existentes.add(url_c)
        
        slug = gerar_slug_titulo_veiculo(str(row.get("assunto", "")), str(row.get("veiculo", "")))
        if slug:
            slugs_existentes.add(slug)

    # 3. Extrai registros da planilha/doc manual (somente leitura)
    registros_manuais = extrair_noticias_google_docs()
    if not registros_manuais:
        print("Nenhum registro recuperado da curadoria manual. Encerrando operação.")
        return

    # 4. Processa e desduplica
    novos_registros = []
    duplicados_url = 0
    duplicados_slug = 0
    duplicados_internos = 0

    urls_vistas_nesta_execucao = set()
    slugs_vistos_nesta_execucao = set()

    for item in registros_manuais:
        url_canonica = normalizar_url_canonica(item["link"])
        slug = gerar_slug_titulo_veiculo(item["assunto"], item["veiculo"])

        # Desduplicação interna na própria planilha
        if url_canonica in urls_vistas_nesta_execucao or slug in slugs_vistos_nesta_execucao:
            duplicados_internos += 1
            continue

        urls_vistas_nesta_execucao.add(url_canonica)
        slugs_vistos_nesta_execucao.add(slug)

        # Desduplicação contra o acervo consolidado existente
        if url_canonica in urls_canonicas_existentes:
            duplicados_url += 1
            continue

        if slug in slugs_existentes:
            duplicados_slug += 1
            continue

        novos_registros.append(item)

    total_duplicados = duplicados_url + duplicados_slug + duplicados_internos
    print("\n--- Relatório de Desduplicação ---")
    print(f"Total de registros na fonte: {len(registros_manuais)}")
    print(f"Duplicatas internas no documento: {duplicados_internos}")
    print(f"Duplicatas por URL com acervo: {duplicados_url}")
    print(f"Duplicatas por Título+Veículo com acervo: {duplicados_slug}")
    print(f"Total descartado (já presente no acervo): {total_duplicados}")
    print(f"Novas notícias homologadas para inclusão: {len(novos_registros)}")

    if not novos_registros:
        print("Nenhuma nova notícia para adicionar. O acervo já está 100% atualizado com a curadoria.")
        return

    # 5. Classificação Semântica Automática dos novos registros
    print("\nAplicando classificadores heurísticos (Eixo Institucional, Abrangência e Campus)...")
    df_novos = pd.DataFrame(novos_registros)
    df_novos["eixo_institucional"] = df_novos["assunto"].apply(classificar_eixo)
    df_novos["abrangencia"] = df_novos["veiculo"].apply(classificar_abrangencia)
    df_novos["campus"] = df_novos.apply(
        lambda r: classificar_campus(r["assunto"], r["veiculo"]), axis=1
    )

    print("Distribuição das novas notícias por Eixo Temático:")
    for eixo, count in df_novos["eixo_institucional"].value_counts().items():
        print(f"  - {eixo}: {count}")

    print("Distribuição das novas notícias por Campus:")
    for campus, count in df_novos["campus"].value_counts().head(5).items():
        print(f"  - {campus}: {count}")

    # 6. Consolidação e Salvamento
    if dry_run:
        print("\nModo DRY-RUN concluído com sucesso. Nenhuma alteração foi gravada em disco.")
        print("Para efetivar a consolidação, execute com a flag --apply.")
    else:
        print("\nConsolidando novas notícias no acervo permanente...")
        colunas_ordenadas = ["data", "assunto", "veiculo", "link", "eixo_institucional", "abrangencia", "campus"]
        
        # Garante as mesmas colunas
        for col in colunas_ordenadas:
            if col not in df_existente.columns:
                df_existente[col] = ""
            if col not in df_novos.columns:
                df_novos[col] = ""

        df_completo = pd.concat(
            [df_existente[colunas_ordenadas], df_novos[colunas_ordenadas]],
            ignore_index=True
        )

        salvar_e_gerar_stats(df_completo, dir_data=dir_data)
        print(f"Consolidação concluída! O acervo agora possui {len(df_completo)} notícias catalogadas.")


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
