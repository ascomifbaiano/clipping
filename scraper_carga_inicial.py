"""
scraper_carga_inicial.py - Motor de Varredura Histórica 2008-Hoje
Instituto Federal de Educação, Ciência e Tecnologia Baiano | v2.0.0 | 2026-08-07

Objetivo: Reconstrução completa da base histórica de menções ao IF Baiano
desde 2008 (ano de criação dos Institutos Federais) até a data atual.

Arquitetura Multi-Engine de 4 Camadas em modo Histórico:
  Camada 1: Serper API (Organic + News) com brackets anuais — cobertura ampla
  Camada 2: Google News RSS por ano (after/before) — complemento de indexação
  Camada 3: Scraping Direto de 60+ portais locais da Bahia
  (Bing RSS omitido por não suportar filtro de data histórico preciso)

Disparo: Exclusivamente manual via GitHub Actions (varredura_historica_2012.yml).
Timeout no GitHub Actions: 300 minutos.
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
    DIR_DATA, HEADERS_SCRAPER,
    padronizar_data, classificar_eixo, classificar_abrangencia,
    classificar_campus, resolver_url_direta, salvar_e_gerar_stats,
    validar_noticia, remover_acentos, normalizar_para_busca, limpar_html,
)

from scraper_clipping import (
    _carregar_base_conhecida, _processar_resultado,
    _busca_serper, _fetch_rss, _extrair_item_rss,
    DOMINIOS_LOCAIS_BAHIA,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

SERPER_API_KEY = os.environ.get('SERPER_API_KEY', '')
ANO_INICIO = 2008
ANO_FIM = datetime.now().year


# Queries históricas — mais abrangentes para cobertura desde 2008
QUERIES_HISTORICAS_SERPER_NEWS = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana"',
    '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
    '"Instituto Federal Baiano"',
]

QUERIES_HISTORICAS_SERPER_ORGANIC = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana" OR "Federal Baiano"',
    '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
    '"IF Baiano" concurso OR vagas OR "cursos técnicos" OR "processo seletivo"',
    '"IF Baiano" ProSel OR SISU OR matrícula OR ingresso',
    '"IF Baiano" pesquisa OR extensão OR premiação OR feira',
    '"IF Baiano" obra OR licitação OR convênio OR parceria',
    '("IFBA" OR "Instituto Federal da Bahia") Alagoinhas OR Guanambi OR Itaberaba',
    '("IFBA" OR "Instituto Federal da Bahia") Itapetinga OR Serrinha OR Catu',
    '("IFBA" OR "Instituto Federal da Bahia") "Bom Jesus da Lapa" OR "Governador Mangabeira"',
    '("IFBA" OR "Instituto Federal da Bahia") "Senhor do Bonfim" OR "Teixeira de Freitas"',
    '("IFBA" OR "Instituto Federal da Bahia") "Uruçuca" OR "Xique-Xique" OR "Santa Inês"',
    '("IFBA" OR "Instituto Federal da Bahia") "Santo Estêvão" OR "Ribeira do Pombal" OR Remanso',
]

QUERIES_HISTORICAS_RSS = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana"',
    '"IF Baiano" concurso OR vagas',
    '"IF Baiano" pesquisa OR extensão',
    '("IFBA" OR "Instituto Federal da Bahia") Alagoinhas OR Guanambi OR Itaberaba OR Itapetinga',
    '("IFBA" OR "Instituto Federal da Bahia") "Bom Jesus da Lapa" OR Catu OR "Senhor do Bonfim"',
    '("IFBA" OR "Instituto Federal da Bahia") "Teixeira de Freitas" OR Serrinha OR "Uruçuca"',
    '("IFBA" OR "Instituto Federal da Bahia") "Governador Mangabeira" OR "Santa Inês" OR "Xique-Xique"',
    '("IFBA" OR "Instituto Federal da Bahia") "Santo Estêvão" OR "Ribeira do Pombal" OR Remanso',
]


def coletar_serper_historico(
    ano: int,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    """Coleta via Serper API para um ano específico."""
    if not SERPER_API_KEY:
        return

    data_inicio = f'{ano}-01-01'
    data_fim = f'{ano}-12-31' if ano < ANO_FIM else datetime.now().strftime('%Y-%m-%d')

    print(f'\n  [Camada 1 / Ano {ano}] Serper API...', flush=True)

    for query in QUERIES_HISTORICAS_SERPER_NEWS:
        resultados = _busca_serper(query, tipo='news', data_inicio=data_inicio, data_fim=data_fim)
        if resultados:
            print(f'   -> Serper News [{ano}]: "{query[:50]}..." — {len(resultados)} resultado(s).', flush=True)
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
                print(f'      + NOVO [{registro["data"]}]: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.8)

    for query in QUERIES_HISTORICAS_SERPER_ORGANIC:
        resultados = _busca_serper(query, tipo='search', data_inicio=data_inicio, data_fim=data_fim)
        if resultados:
            print(f'   -> Serper Organic [{ano}]: "{query[:50]}..." — {len(resultados)} resultado(s).', flush=True)
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
                print(f'      + NOVO [{registro["data"]}]: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.8)


def coletar_rss_historico(
    ano: int,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    """Coleta via Google News RSS para um ano específico."""
    data_inicio = f'{ano}-01-01'
    data_fim = f'{ano}-12-31' if ano < ANO_FIM else datetime.now().strftime('%Y-%m-%d')

    print(f'  [Camada 2 / Ano {ano}] Google News RSS...', flush=True)

    for query in QUERIES_HISTORICAS_RSS:
        q_com_data = f'{query} after:{data_inicio} before:{data_fim}'
        q_enc = urllib.parse.quote_plus(q_com_data)
        url = f'https://news.google.com/rss/search?q={q_enc}&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        itens = _fetch_rss(url)
        if itens:
            print(f'   -> RSS [{ano}]: "{query[:50]}..." — {len(itens)} item(s).', flush=True)
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
                print(f'      + NOVO [{registro["data"]}]: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.4)


def coletar_portais_locais_historico(
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    """Varredura completa em portais locais da Bahia sem filtro de data (histórico total)."""
    if not SERPER_API_KEY:
        return

    print('\n  [Camada 3] Scraping Direto de Portais Locais (Histórico Completo)...', flush=True)
    query_base = '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano" OR "IF-Baiano" OR "IFBaiana"'

    for dominio in DOMINIOS_LOCAIS_BAHIA:
        query = f'({query_base}) site:{dominio}'
        resultados = _busca_serper(query, tipo='search')
        if resultados:
            print(f'   -> {dominio}: {len(resultados)} resultado(s) histórico(s).', flush=True)
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
                print(f'      + NOVO [{registro["data"]}]: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.3)

    # Salva a cada 10 domínios para não perder progresso em execuções longas
    if clipping_coletado:
        print('  [Checkpoint] Salvando progresso parcial...', flush=True)
        _, _, df_existente = _carregar_base_conhecida()
        df_novo = pd.DataFrame(clipping_coletado)
        df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente
        if not df_final.empty:
            salvar_e_gerar_stats(df_final)


def processar_carga_inicial():
    print(f'Iniciando Varredura Histórica Completa v2.0 (2008 – {ANO_FIM})...', flush=True)
    print('Arquitetura: Serper API Organic+News + Google RSS por ano + Portais Locais', flush=True)
    os.makedirs(DIR_DATA, exist_ok=True)

    links_conhecidos, titulos_veiculos_conhecidos, df_existente = _carregar_base_conhecida()
    print(f'  Base existente: {len(links_conhecidos)} links carregados.', flush=True)

    clipping_coletado = []

    # Camadas 1 e 2: varredura por ano (2008 até ANO_FIM)
    anos = list(range(ANO_INICIO, ANO_FIM + 1))
    for idx, ano in enumerate(anos, 1):
        print(f'\n========================================', flush=True)
        print(f'  Processando ano {ano} ({idx}/{len(anos)})...', flush=True)
        print(f'========================================', flush=True)

        coletar_serper_historico(ano, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado)
        coletar_rss_historico(ano, links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado)

        # Checkpoint a cada 3 anos para preservar progresso
        if idx % 3 == 0 and clipping_coletado:
            print(f'\n  [Checkpoint] Salvando {len(clipping_coletado)} novos registros...', flush=True)
            df_novo = pd.DataFrame(clipping_coletado)
            df_parcial = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente
            if not df_parcial.empty:
                salvar_e_gerar_stats(df_parcial)
                # Recarrega a base para continuar deduplicando corretamente
                links_conhecidos, titulos_veiculos_conhecidos, df_existente = _carregar_base_conhecida()
                clipping_coletado = []
                print(f'  [Checkpoint] Base atualizada: {len(links_conhecidos)} links.', flush=True)

        time.sleep(1.0)

    # Camada 3: portais locais (histórico completo sem filtro de ano)
    coletar_portais_locais_historico(links_conhecidos, titulos_veiculos_conhecidos, clipping_coletado)

    # Salvamento final
    print(f'\n  Total de novos registros coletados nesta sessão: {len(clipping_coletado)}', flush=True)
    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    if df_final.empty:
        print('  Nenhum dado para salvar.', flush=True)
        return

    salvar_e_gerar_stats(df_final)
    print(f'\nVarredura histórica concluída! Base total: {len(df_final)} registros.', flush=True)


if __name__ == '__main__':
    processar_carga_inicial()
