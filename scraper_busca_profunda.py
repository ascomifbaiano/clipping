"""
scraper_busca_profunda.py - Motor de Recuperação de Menções em Janela Temporal
Clipping Inteligente IF Baiano | v1.0.0 | 2026-08-07

Objetivo: Recuperar menções ao IF Baiano que foram perdidas durante períodos em que
o motor diário ficou inativo. Aceita um parâmetro de DIAS_ATRAS (padrão: 45) e
usa a API Serper.dev para fazer buscas com filtro de data preciso, complementando
o Google News RSS que só retorna os itens mais recentes.

Disparo: Exclusivamente manual via GitHub Actions (workflow_dispatch).
"""
import os
import sys
import glob
import time
import html
import json
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import pandas as pd
import requests
import urllib3

from clipping_utils import (
    DIR_DATA, padronizar_data, classificar_eixo,
    classificar_abrangencia, classificar_campus,
    resolver_url_direta, salvar_e_gerar_stats, validar_noticia
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Configuração via variável de ambiente (definida no workflow)
# ---------------------------------------------------------------------------
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
DIAS_ATRAS = int(os.environ.get("DIAS_ATRAS", "45"))


def _carregar_base_conhecida():
    """Carrega todos os CSVs existentes e retorna sets de links e chaves título|veículo."""
    links_conhecidos = set()
    titulos_veiculos_conhecidos = set()
    dfs_existentes = []

    for arq in glob.glob(os.path.join(DIR_DATA, 'clipping_*.csv')):
        if 'clipping_geral.csv' in arq:
            continue
        try:
            df_temp = pd.read_csv(arq, encoding='utf-8-sig')
            if not df_temp.empty:
                dfs_existentes.append(df_temp)
                if 'link' in df_temp.columns:
                    links_conhecidos.update(df_temp['link'].dropna().tolist())
                if 'assunto' in df_temp.columns and 'veiculo' in df_temp.columns:
                    for _, row in df_temp.iterrows():
                        chave = f"{str(row['assunto']).strip().lower()}|{str(row['veiculo']).strip().lower()}"
                        titulos_veiculos_conhecidos.add(chave)
        except Exception as exc:
            print(f"Aviso ao ler {arq}: {exc}", flush=True)

    df_existente = pd.concat(dfs_existentes, ignore_index=True) if dfs_existentes else pd.DataFrame()
    return links_conhecidos, titulos_veiculos_conhecidos, df_existente


def _busca_serper(query: str, data_inicio: str, data_fim: str) -> list:
    """
    Executa uma busca no Serper.dev com filtro de data.
    Retorna lista de dicts com keys: title, link, snippet, source, date.
    """
    if not SERPER_API_KEY:
        print("   ! SERPER_API_KEY não configurada. Pulando busca Serper.", flush=True)
        return []

    url = "https://google.serper.dev/news"
    payload = json.dumps({
        "q": query,
        "gl": "br",
        "hl": "pt-br",
        "num": 100,
        "tbs": f"cdr:1,cd_min:{data_inicio},cd_max:{data_fim}"
    })
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=30)
        if response.status_code == 200:
            dados = response.json()
            return dados.get("news", [])
    except Exception as exc:
        print(f"   X Erro na API Serper: {exc}", flush=True)
    return []


def _busca_rss_periodo(query: str, data_inicio: str, data_fim: str) -> list:
    """
    Complemento via Google News RSS com parâmetros after/before.
    Retorna lista de elementos XML item.
    """
    q_com_datas = f"{query} after:{data_inicio} before:{data_fim}"
    q_encoded = urllib.parse.quote_plus(q_com_datas)
    url_rss = f"https://news.google.com/rss/search?q={q_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    try:
        response = requests.get(url_rss, headers=headers, timeout=20)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            return root.findall('./channel/item')
    except Exception as exc:
        print(f"   X Erro no RSS: {exc}", flush=True)
    return []


def _processar_resultado_serper(resultado: dict, links_conhecidos: set, titulos_veiculos_conhecidos: set) -> dict | None:
    """
    Processa um resultado da API Serper e retorna um dict de clipping ou None se descartado.
    """
    link_original = resultado.get("link", "")
    if not link_original or link_original in links_conhecidos:
        return None

    link_direto = resolver_url_direta(link_original)
    if link_direto in links_conhecidos:
        return None
    if "ifbaiano.edu.br" in link_direto:
        return None

    titulo = html.unescape(resultado.get("title", "Sem Título"))
    veiculo = html.unescape(resultado.get("source", "Mídia Externa"))

    # Remove o nome do veículo do título se vier concatenado
    if " - " in titulo and veiculo in titulo:
        titulo = titulo.rsplit(" - ", 1)[0]

    chave_nova = f"{titulo.strip().lower()}|{veiculo.strip().lower()}"
    if chave_nova in titulos_veiculos_conhecidos:
        return None

    if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=False):
        return None

    data_pub = padronizar_data(resultado.get("date", ""))

    links_conhecidos.add(link_direto)
    titulos_veiculos_conhecidos.add(chave_nova)

    return {
        "data": data_pub, "assunto": titulo, "veiculo": veiculo, "link": link_direto,
        "eixo_institucional": classificar_eixo(titulo),
        "abrangencia": classificar_abrangencia(veiculo),
        "campus": classificar_campus(titulo, veiculo)
    }


def _processar_item_rss(item, links_conhecidos: set, titulos_veiculos_conhecidos: set) -> dict | None:
    """
    Processa um item XML do RSS e retorna um dict de clipping ou None se descartado.
    """
    link_original = getattr(item.find("link"), "text", "") or ""
    if not link_original or link_original in links_conhecidos:
        return None

    link_direto = resolver_url_direta(link_original)
    if link_direto in links_conhecidos:
        return None
    if "ifbaiano.edu.br" in link_direto:
        return None

    titulo_completo = getattr(item.find("title"), "text", None) or "Sem Título"
    veiculo = "Mídia Externa"
    source_tag = item.find("source")
    if source_tag is not None and source_tag.text:
        veiculo = html.unescape(source_tag.text)
        if " - " in titulo_completo and veiculo in titulo_completo:
            titulo_completo = titulo_completo.rsplit(" - ", 1)[0]
        titulo = html.unescape(titulo_completo)
    else:
        if " - " in titulo_completo:
            partes = titulo_completo.rsplit(" - ", 1)
            titulo = html.unescape(partes[0].strip())
            veiculo = html.unescape(partes[1].strip())
        else:
            titulo = html.unescape(titulo_completo)

    chave_nova = f"{titulo.strip().lower()}|{veiculo.strip().lower()}"
    if chave_nova in titulos_veiculos_conhecidos:
        return None

    if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=False):
        return None

    data_pub = padronizar_data(getattr(item.find("pubDate"), "text", ""))

    links_conhecidos.add(link_direto)
    titulos_veiculos_conhecidos.add(chave_nova)

    return {
        "data": data_pub, "assunto": titulo, "veiculo": veiculo, "link": link_direto,
        "eixo_institucional": classificar_eixo(titulo),
        "abrangencia": classificar_abrangencia(veiculo),
        "campus": classificar_campus(titulo, veiculo)
    }


def processar_busca_profunda():
    print(f"Iniciando Motor de Busca Profunda — Janela: últimos {DIAS_ATRAS} dias...", flush=True)
    os.makedirs(DIR_DATA, exist_ok=True)

    data_hoje = datetime.now()
    data_inicio_dt = data_hoje - timedelta(days=DIAS_ATRAS)
    data_inicio = data_inicio_dt.strftime("%Y-%m-%d")
    data_fim = data_hoje.strftime("%Y-%m-%d")

    print(f"  Período de busca: {data_inicio} a {data_fim}", flush=True)

    links_conhecidos, titulos_veiculos_conhecidos, df_existente = _carregar_base_conhecida()
    print(f"  Base existente: {len(links_conhecidos)} links carregados.", flush=True)

    clipping_coletado = []

    # Estratégia 1: Serper API (busca com filtro de data preciso)
    queries_serper = [
        '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
        '"IF-Baiano" OR "IFBaiana" OR "Federal Baiano"',
        '("IFBA" OR "Instituto Federal da Bahia") ("Alagoinhas" OR "Bom Jesus da Lapa" OR "Catu" OR "Governador Mangabeira" OR "Guanambi" OR "Itaberaba" OR "Itapetinga" OR "Santa Inês" OR "Senhor do Bonfim" OR "Serrinha" OR "Teixeira de Freitas" OR "Uruçuca" OR "Xique-Xique")',
        '"Instituto Federal Baiano" (educação OR ensino OR pesquisa OR extensão OR concurso OR ProSel OR SISU OR processo seletivo)',
    ]

    if SERPER_API_KEY:
        print("\n  [Fase 1] Varredura via Serper API com filtro de data...", flush=True)
        for query in queries_serper:
            print(f"   -> Serper: {query[:60]}...", flush=True)
            resultados = _busca_serper(query, data_inicio, data_fim)
            print(f"      {len(resultados)} resultado(s) recebido(s).", flush=True)
            for resultado in resultados:
                registro = _processar_resultado_serper(resultado, links_conhecidos, titulos_veiculos_conhecidos)
                if registro:
                    clipping_coletado.append(registro)
                    print(f"      + NOVO: {registro['assunto'][:70]}", flush=True)
            time.sleep(1.0)
    else:
        print("\n  [Fase 1] SERPER_API_KEY ausente. Fase 1 ignorada.", flush=True)

    # Estratégia 2: Google News RSS com filtro after/before (complemento sem custo de API)
    queries_rss = [
        '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
        '("IFBA" OR "Instituto Federal da Bahia") ("Alagoinhas" OR "Catu" OR "Guanambi" OR "Itaberaba" OR "Itapetinga" OR "Serrinha" OR "Bonfim" OR "Teixeira de Freitas")',
        '"Instituto Federal Baiano" processo seletivo OR ProSel OR SISU OR concurso',
    ]

    print("\n  [Fase 2] Complemento via Google News RSS com filtro de data...", flush=True)
    for query in queries_rss:
        print(f"   -> RSS: {query[:60]}...", flush=True)
        itens = _busca_rss_periodo(query, data_inicio, data_fim)
        print(f"      {len(itens)} item(s) no feed.", flush=True)
        for item in itens:
            registro = _processar_item_rss(item, links_conhecidos, titulos_veiculos_conhecidos)
            if registro:
                clipping_coletado.append(registro)
                print(f"      + NOVO: {registro['assunto'][:70]}", flush=True)
        time.sleep(0.5)

    # Estratégia 3: Bing News RSS (terceiro motor — diversidade de fontes)
    print("\n  [Fase 3] Complemento via Bing News RSS...", flush=True)
    bing_queries = [
        '"IF Baiano" OR "Instituto Federal Baiano"',
        '"IFBAIANO" OR "IF-Baiano"',
    ]
    for query in bing_queries:
        q_enc = urllib.parse.quote_plus(query)
        url_bing = f"https://www.bing.com/news/search?q={q_enc}&format=rss"
        headers_req = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
        try:
            response = requests.get(url_bing, headers=headers_req, timeout=15)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                itens = root.findall('./channel/item')
                print(f"      {len(itens)} item(s) no feed Bing.", flush=True)
                for item in itens:
                    registro = _processar_item_rss(item, links_conhecidos, titulos_veiculos_conhecidos)
                    if registro:
                        # Filtrar apenas os itens dentro da janela temporal
                        if registro["data"] >= data_inicio:
                            clipping_coletado.append(registro)
                            print(f"      + NOVO: {registro['assunto'][:70]}", flush=True)
        except Exception as exc:
            print(f"   X Erro Bing RSS: {exc}", flush=True)
        time.sleep(0.5)

    # Consolidação e persistência
    print(f"\n  Total de novas menções encontradas: {len(clipping_coletado)}", flush=True)

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    if df_final.empty:
        print("  Nenhum dado para salvar.", flush=True)
        return

    salvar_e_gerar_stats(df_final)
    print(f"  Busca profunda concluída com sucesso. Base total: {len(df_final)} registros.", flush=True)


if __name__ == "__main__":
    processar_busca_profunda()
