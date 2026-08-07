"""
scraper_busca_profunda.py - Motor de Recuperação de Menções em Janela Temporal
Instituto Federal de Educação, Ciência e Tecnologia Baiano | v2.0.0 | 2026-08-07

Objetivo: Recuperar menções ao IF Baiano que foram perdidas durante períodos em que
o motor diário ficou inativo. Opera com arquitetura Multi-Engine de 4 Camadas com
intensidade maior que o diário (mais queries, paginação, inspeção de corpo de texto).

Parâmetro: DIAS_ATRAS (env) — padrão: 45 dias.
Disparo: Exclusivamente manual via GitHub Actions (workflow_dispatch).
"""
import os
import sys
import glob
import html
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import pandas as pd
import requests
import urllib3

from clipping_utils import (
    DIR_DATA, VARIANTES_BAIANO, CIDADES_EXCLUSIVAS_IF_BAIANO,
    HEADERS_SCRAPER,
    padronizar_data, classificar_eixo, classificar_abrangencia,
    classificar_campus, resolver_url_direta, salvar_e_gerar_stats,
    validar_noticia, remover_acentos, normalizar_para_busca, limpar_html,
)

# Importa as funções de coleta reutilizáveis do scraper diário
from scraper_clipping import (
    _carregar_base_conhecida, _processar_resultado,
    _busca_serper, _fetch_rss, _extrair_item_rss,
    DOMINIOS_LOCAIS_BAHIA,
    coletar_bing_rss,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

SERPER_API_KEY = os.environ.get('SERPER_API_KEY', '')
DIAS_ATRAS = int(os.environ.get('DIAS_ATRAS', '45'))

# Queries mais amplas e com mais variações para a busca profunda
QUERIES_PROFUNDA_SERPER_NEWS = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana" OR "Federal Baiano"',
    '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
    '"IF Baiano" concurso OR vagas OR "cursos técnicos" OR "processo seletivo"',
    '"IF Baiano" ProSel OR SISU OR ENEM OR ingresso OR matrícula',
    '"IF Baiano" obra OR licitação OR pavimentação OR convênio OR parceria',
    '"IF Baiano" pesquisa OR extensão OR projeto OR premiação OR feira',
    '"IF Baiano" servidor OR professor OR substituto OR edital OR TAE',
]

QUERIES_PROFUNDA_SERPER_ORGANIC = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana"',
    '"Instituto Federal Baiano" bahia',
    '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
    '"IF Baiano" concurso OR vagas OR "cursos técnicos"',
    '"IF Baiano" educação OR ensino OR pesquisa OR extensão',
    '("IFBA" OR "Instituto Federal da Bahia") (Alagoinhas OR Guanambi OR Itaberaba OR Itapetinga OR Serrinha)',
    '("IFBA" OR "Instituto Federal da Bahia") ("Bom Jesus da Lapa" OR Catu OR "Senhor do Bonfim" OR "Teixeira de Freitas")',
    '("IFBA" OR "Instituto Federal da Bahia") ("Governador Mangabeira" OR "Santa Inês" OR "Uruçuca" OR "Xique-Xique")',
    '("IFBA" OR "Instituto Federal da Bahia") ("Santo Estêvão" OR "Ribeira do Pombal" OR Remanso OR "Ruy Barbosa")',
]

QUERIES_PROFUNDA_RSS_GOOGLE = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana"',
    '"IF Baiano" concurso OR vagas',
    '"IF Baiano" pesquisa OR extensão OR projeto',
    '"IF Baiano" obra OR licitação OR convênio',
    '"Instituto Federal Baiano" bahia',
    '("IFBA" OR "Instituto Federal da Bahia") Alagoinhas OR Guanambi OR Itaberaba',
    '("IFBA" OR "Instituto Federal da Bahia") Itapetinga OR Serrinha OR Catu',
    '("IFBA" OR "Instituto Federal da Bahia") "Bom Jesus da Lapa" OR "Governador Mangabeira"',
    '("IFBA" OR "Instituto Federal da Bahia") "Senhor do Bonfim" OR "Teixeira de Freitas"',
    '("IFBA" OR "Instituto Federal da Bahia") "Uruçuca" OR "Xique-Xique" OR "Santa Inês"',
    '("IFBA" OR "Instituto Federal da Bahia") "Santo Estêvão" OR "Ribeira do Pombal" OR Remanso',
]


def coletar_serper_profunda(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    if not SERPER_API_KEY:
        print('  [Camada 1 Profunda] SERPER_API_KEY ausente. Camada 1 ignorada.', flush=True)
        return

    print('\n  [Camada 1] Serper API Profunda (Organic + News)...', flush=True)

    for query in QUERIES_PROFUNDA_SERPER_NEWS:
        print(f'   -> Serper News: {query[:65]}', flush=True)
        resultados = _busca_serper(query, tipo='news', data_inicio=data_inicio, data_fim=data_fim)
        print(f'      {len(resultados)} resultado(s).', flush=True)
        for res in resultados:
            registro = _processar_resultado(
                titulo_raw=res.get('title', ''),
                veiculo_raw=res.get('source', 'Mídia Externa'),
                link_original=res.get('link', ''),
                data_raw=res.get('date', ''),
                links_conhecidos=links_conhecidos,
                titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
                puxar_conteudo=False,
            )
            if registro:
                clipping_coletado.append(registro)
                print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.8)

    for query in QUERIES_PROFUNDA_SERPER_ORGANIC:
        print(f'   -> Serper Organic: {query[:65]}', flush=True)
        resultados = _busca_serper(query, tipo='search', data_inicio=data_inicio, data_fim=data_fim)
        print(f'      {len(resultados)} resultado(s).', flush=True)
        for res in resultados:
            registro = _processar_resultado(
                titulo_raw=res.get('title', ''),
                veiculo_raw=res.get('displayLink', res.get('link', 'Mídia Externa')),
                link_original=res.get('link', ''),
                data_raw=res.get('date', ''),
                links_conhecidos=links_conhecidos,
                titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
                puxar_conteudo=True,
            )
            if registro:
                clipping_coletado.append(registro)
                print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.8)


def coletar_google_rss_profunda(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    print('\n  [Camada 2] Google News RSS Profundo...', flush=True)
    for query in QUERIES_PROFUNDA_RSS_GOOGLE:
        q_com_data = f'{query} after:{data_inicio} before:{data_fim}'
        q_enc = urllib.parse.quote_plus(q_com_data)
        url = f'https://news.google.com/rss/search?q={q_enc}&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        print(f'   -> RSS Google: {query[:65]}', flush=True)
        itens = _fetch_rss(url)
        print(f'      {len(itens)} item(s) no feed.', flush=True)
        for item in itens:
            titulo_completo, veiculo, link, data_raw = _extrair_item_rss(item)
            registro = _processar_resultado(
                titulo_raw=titulo_completo, veiculo_raw=veiculo,
                link_original=link, data_raw=data_raw,
                links_conhecidos=links_conhecidos,
                titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
                puxar_conteudo=False,
            )
            if registro:
                clipping_coletado.append(registro)
                print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.4)


def coletar_portais_locais_profunda(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    if not SERPER_API_KEY:
        return

    print('\n  [Camada 4] Scraping Direto de Portais Locais (Profundo)...', flush=True)
    query_base = '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano" OR "IF-Baiano"'

    for dominio in DOMINIOS_LOCAIS_BAHIA:
        query = f'({query_base}) site:{dominio}'
        resultados = _busca_serper(query, tipo='search', data_inicio=data_inicio, data_fim=data_fim)
        if resultados:
            print(f'   -> {dominio}: {len(resultados)} resultado(s).', flush=True)
        for res in resultados:
            registro = _processar_resultado(
                titulo_raw=res.get('title', ''),
                veiculo_raw=res.get('displayLink', dominio),
                link_original=res.get('link', ''),
                data_raw=res.get('date', ''),
                links_conhecidos=links_conhecidos,
                titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
                puxar_conteudo=True,
            )
            if registro:
                clipping_coletado.append(registro)
                print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.3)


def processar_busca_profunda():
    print(f'Iniciando Motor de Busca Profunda v2.0 — Janela: últimos {DIAS_ATRAS} dias...', flush=True)
    os.makedirs(DIR_DATA, exist_ok=True)

    data_hoje = datetime.now()
    data_inicio_dt = data_hoje - timedelta(days=DIAS_ATRAS)
    data_inicio = data_inicio_dt.strftime('%Y-%m-%d')
    data_fim = data_hoje.strftime('%Y-%m-%d')

    print(f'  Período de busca: {data_inicio} a {data_fim}', flush=True)

    links_conhecidos, titulos_veiculos_conhecidos, df_existente = _carregar_base_conhecida()
    print(f'  Base existente: {len(links_conhecidos)} links carregados.', flush=True)

    clipping_coletado = []

    # 4 Camadas — modo intensivo
    coletar_serper_profunda(
        data_inicio, data_fim, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado
    )
    coletar_google_rss_profunda(
        data_inicio, data_fim, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado
    )
    coletar_bing_rss(
        data_inicio, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado
    )
    coletar_portais_locais_profunda(
        data_inicio, data_fim, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado
    )

    print(f'\n  Total de novas menções encontradas: {len(clipping_coletado)}', flush=True)

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    if df_final.empty:
        print('  Nenhum dado para salvar.', flush=True)
        return

    salvar_e_gerar_stats(df_final)
    print(f'  Busca profunda concluída. Base total: {len(df_final)} registros.', flush=True)


if __name__ == '__main__':
    processar_busca_profunda()
