"""
scraper_clipping.py - Motor Diário de Clipping Inteligente
Instituto Federal de Educação, Ciência e Tecnologia Baiano | v2.0.0 | 2026-08-07

Arquitetura Multi-Engine de 4 Camadas (vide planejamento_reestruturacao_motores_clipping.md):
  Camada 1: Serper API (Organic + News) — Busca orgânica ampla com cobertura de portais locais
  Camada 2: Google News RSS — Fragmentado em sub-queries curtas e limpas
  Camada 3: Bing News RSS — Motor de contingência e diversidade de indexação
  Camada 4: Scraping Direto de Portais Locais — Lista de 60+ domínios curados da Bahia

Garante janela móvel de 7 dias a cada execução para capturar matérias indexadas com atraso.
Disparo: 3x/dia via GitHub Actions (06:00, 12:00 e 18:00 BRT).
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

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

SERPER_API_KEY = os.environ.get('SERPER_API_KEY', '')
ARQUIVO_ANTIGO = os.path.join(DIR_DATA, 'clipping.csv')

# Janela móvel: garante que matérias indexadas com atraso sejam capturadas
DIAS_JANELA_MOVEL = 7

# ---------------------------------------------------------------------------
# Queries de Busca — simples, diretas, sem truncamento
# ---------------------------------------------------------------------------

QUERIES_SERPER_ORGANIC = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana"',
    '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
    '"IF Baiano" concurso OR vagas OR "cursos técnicos" OR "processo seletivo" OR ProSel OR SISU',
    '"IF Baiano" obra OR licitação OR pavimentação OR infraestrutura OR convênio',
    '"IF Baiano" pesquisa OR extensão OR projeto OR feira OR evento OR premiação',
]

QUERIES_SERPER_NEWS = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF Baiano" concurso OR vagas OR "cursos técnicos"',
    '"Instituto Federal Baiano" educação OR ensino OR bahia',
]

QUERIES_RSS_GOOGLE = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF-Baiano" OR "IFBaiana" OR "IF Baiana" OR "Federal Baiano"',
    '"IF Baiano" concurso OR vagas',
    '"Instituto Federal Baiano" bahia',
    '("IFBA" OR "Instituto Federal da Bahia") (Alagoinhas OR Guanambi OR Itaberaba OR Itapetinga OR Serrinha)',
    '("IFBA" OR "Instituto Federal da Bahia") ("Bom Jesus da Lapa" OR Catu OR "Senhor do Bonfim" OR "Teixeira de Freitas")',
    '("IFBA" OR "Instituto Federal da Bahia") ("Governador Mangabeira" OR "Santa Inês" OR "Uruçuca" OR "Xique-Xique")',
    '("IFBA" OR "Instituto Federal da Bahia") ("Santo Estêvão" OR "Ribeira do Pombal" OR Remanso OR "Ruy Barbosa")',
]

QUERIES_RSS_BING = [
    '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"',
    '"IF Baiano" vagas OR concurso OR cursos',
]

# ---------------------------------------------------------------------------
# Portais Locais e Regionais da Bahia para Scraping Direto
# ---------------------------------------------------------------------------

DOMINIOS_LOCAIS_BAHIA = [
    # Regionais e nacionais parceiros
    'jornalgrandebahia.com.br',
    'correio24horas.com.br', 'atarde.com.br', 'bnews.com.br',
    'bahianoticias.com.br', 'ibahia.com', 'farolda bahia.com.br',
    # Portais de concursos (frequentemente citam vagas do IF Baiano)
    'pciconcursos.com.br', 'qconcursos.com', 'estrategiaconcursos.com.br',
    'grancursosonline.com.br', 'noticias.concursos.com.br',
    # Portais locais — Bom Jesus da Lapa
    'portallapaoeste.com.br', 'bomjesusdalapanoticias.com.br',
    'centraldalapa.com', 'rbjfm.com.br',
    # Portais locais — Guanambi / Sertão
    'agenciasertao.com', 'iguanambi.com.br', 'falavoce.com.br',
    # Portais locais — Senhor do Bonfim
    'ivansilvanoticia.com.br', 'blogdoeloiltoncajuhy.com.br',
    'nettomaravilha.com.br', 'bonfimdital.com.br',
    # Portais locais — Teixeira de Freitas / Extremo Sul
    'clebervieiranews.com.br', 'teixeiranews.com.br',
    'bahiaextremosul.com.br', 'extremosul.com.br',
    'liberdadenews.com.br', 'sulbahianews.com.br',
    # Portais locais — Alagoinhas
    'seligaalagoinhas.com.br', 'alta-pressao.com', 'alagonews.com.br',
    # Portais locais — Itapetinga / SW Bahia
    'itapetingaagora.com.br', 'pimenta.blog.br', 'vozdocampo.com.br',
    'sudoestebahia.com.br',
    # Portais locais — Serrinha / Território do Sisal
    'clicnews.com.br', 'serrinha.ba.gov.br',
    # Portais locais — Valença
    'valencaagora.com.br',
    # Portais locais — Catu / Recôncavo
    'catunoticias.com.br',
    # Portais locais — Itaberaba / Chapada
    'jornaldachapada.com.br', 'seabrahoje.com.br',
    # Portais locais — Santa Inês / Baixo Sul
    'baixosulnews.com.br',
    # Portais acadêmicos / governamentais relevantes
    'mec.gov.br', 'portal.mec.gov.br', 'gov.br', 'conif.org.br',
    'ufba.br', 'uneb.br', 'uesb.br', 'ufrb.edu.br',
    'embrapa.br', 'codevasf.gov.br',
]


# ---------------------------------------------------------------------------
# Funções auxiliares de coleta
# ---------------------------------------------------------------------------

def _carregar_base_conhecida():
    links_conhecidos = set()
    titulos_veiculos_conhecidos = set()
    dfs_existentes = []

    arquivos = glob.glob(os.path.join(DIR_DATA, 'clipping_*.csv'))
    if os.path.exists(ARQUIVO_ANTIGO):
        arquivos.append(ARQUIVO_ANTIGO)

    for arq in arquivos:
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
            print(f'Aviso ao ler {arq}: {exc}', flush=True)

    df_existente = pd.concat(dfs_existentes, ignore_index=True) if dfs_existentes else pd.DataFrame()
    return links_conhecidos, titulos_veiculos_conhecidos, df_existente


def _processar_resultado(
    titulo_raw: str, veiculo_raw: str, link_original: str,
    data_raw: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    puxar_conteudo: bool = False,
) -> dict | None:
    """
    Valida e monta um dict de registro de clipping a partir dos dados brutos.
    Retorna None se o item deve ser descartado.
    """
    if not link_original:
        return None

    link_direto = resolver_url_direta(link_original)

    if link_direto in links_conhecidos or link_original in links_conhecidos:
        return None

    if 'ifbaiano.edu.br' in link_direto.lower():
        return None

    # Separa veículo do título quando vêm concatenados com " - "
    titulo_completo = html.unescape(titulo_raw or 'Sem Título')
    veiculo = html.unescape(veiculo_raw or 'Mídia Externa')

    if ' - ' in titulo_completo and veiculo in titulo_completo:
        titulo_completo = titulo_completo.rsplit(' - ', 1)[0]
    titulo = titulo_completo.strip()

    chave_nova = f'{titulo.strip().lower()}|{veiculo.strip().lower()}'
    if chave_nova in titulos_veiculos_conhecidos:
        return None

    if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=puxar_conteudo):
        return None

    data_pub = padronizar_data(data_raw)

    links_conhecidos.add(link_direto)
    links_conhecidos.add(link_original)
    titulos_veiculos_conhecidos.add(chave_nova)

    return {
        'data': data_pub,
        'assunto': titulo,
        'veiculo': veiculo,
        'link': link_direto,
        'eixo_institucional': classificar_eixo(titulo),
        'abrangencia': classificar_abrangencia(veiculo),
        'campus': classificar_campus(titulo, veiculo),
    }


# ---------------------------------------------------------------------------
# Camada 1: Serper API (Organic + News)
# ---------------------------------------------------------------------------

def _busca_serper(query: str, tipo: str = 'news', data_inicio: str = None, data_fim: str = None) -> list:
    """Busca via Serper.dev. tipo: 'news' ou 'search' (organic)."""
    if not SERPER_API_KEY:
        return []

    endpoint = 'https://google.serper.dev/news' if tipo == 'news' else 'https://google.serper.dev/search'
    payload = {'q': query, 'gl': 'br', 'hl': 'pt-br', 'num': 50}

    if data_inicio and data_fim:
        payload['tbs'] = f'cdr:1,cd_min:{data_inicio},cd_max:{data_fim}'

    try:
        resp = requests.post(
            endpoint,
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            data=json.dumps(payload),
            timeout=20,
        )
        if resp.status_code == 200:
            dados = resp.json()
            return dados.get('news' if tipo == 'news' else 'organic', [])
    except Exception as exc:
        print(f'   X Erro Serper ({tipo}): {exc}', flush=True)
    return []


def coletar_serper(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    if not SERPER_API_KEY:
        print('  [Camada 1] SERPER_API_KEY ausente. Camada 1 ignorada.', flush=True)
        return

    print('\n  [Camada 1] Serper API (Organic + News)...', flush=True)

    # News API
    for query in QUERIES_SERPER_NEWS:
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

    # Organic Search API
    for query in QUERIES_SERPER_ORGANIC:
        print(f'   -> Serper Organic: {query[:65]}', flush=True)
        resultados = _busca_serper(query, tipo='search', data_inicio=data_inicio, data_fim=data_fim)
        print(f'      {len(resultados)} resultado(s).', flush=True)
        for res in resultados:
            # Resultados orgânicos têm estrutura diferente
            registro = _processar_resultado(
                titulo_raw=res.get('title', ''),
                veiculo_raw=res.get('displayLink', res.get('link', 'Mídia Externa')),
                link_original=res.get('link', ''),
                data_raw=res.get('date', ''),
                links_conhecidos=links_conhecidos,
                titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
                puxar_conteudo=True,   # Organic merece inspeção de corpo para títulos genéricos
            )
            if registro:
                clipping_coletado.append(registro)
                print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.8)


# ---------------------------------------------------------------------------
# Camada 2: Google News RSS
# ---------------------------------------------------------------------------

def _fetch_rss(url: str, timeout: int = 15) -> list:
    """Retorna lista de elementos XML <item> do feed RSS."""
    try:
        resp = requests.get(url, headers=HEADERS_SCRAPER, timeout=timeout, verify=False)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            return root.findall('./channel/item')
    except Exception as exc:
        print(f'   X Erro RSS: {exc}', flush=True)
    return []


def _extrair_item_rss(item) -> tuple:
    """Extrai (titulo_completo, veiculo, link, data_pub) de um elemento XML <item>."""
    link = getattr(item.find('link'), 'text', '') or ''
    titulo_completo = getattr(item.find('title'), 'text', None) or 'Sem Título'
    data_pub_str = getattr(item.find('pubDate'), 'text', '')

    veiculo = 'Mídia Externa'
    source_tag = item.find('source')
    if source_tag is not None and source_tag.text:
        veiculo = source_tag.text
    elif ' - ' in titulo_completo:
        partes = titulo_completo.rsplit(' - ', 1)
        titulo_completo = partes[0].strip()
        veiculo = partes[1].strip()

    return titulo_completo, veiculo, link, data_pub_str


def coletar_google_rss(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    print('\n  [Camada 2] Google News RSS...', flush=True)
    for query in QUERIES_RSS_GOOGLE:
        # Adiciona filtro de datas à query
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


# ---------------------------------------------------------------------------
# Camada 3: Bing News RSS
# ---------------------------------------------------------------------------

def coletar_bing_rss(
    data_inicio: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    print('\n  [Camada 3] Bing News RSS...', flush=True)
    for query in QUERIES_RSS_BING:
        q_enc = urllib.parse.quote_plus(query)
        url = f'https://www.bing.com/news/search?q={q_enc}&format=rss'
        print(f'   -> Bing RSS: {query[:65]}', flush=True)
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
                # Filtra apenas itens dentro da janela temporal
                if registro['data'] >= data_inicio:
                    clipping_coletado.append(registro)
                    print(f'      + NOVO: {registro["assunto"][:70]}', flush=True)
        time.sleep(0.4)


# ---------------------------------------------------------------------------
# Camada 4: Scraping Direto de Portais Locais via Serper site:domínio
# ---------------------------------------------------------------------------

def coletar_portais_locais(
    data_inicio: str, data_fim: str,
    links_conhecidos: set, titulos_veiculos_conhecidos: set,
    clipping_coletado: list,
):
    """
    Para cada domínio local da lista curada, usa o Serper Organic com
    operador site: para garantir que matérias relevantes sejam coletadas
    mesmo que o Google News não as tenha indexado em seu feed RSS.
    """
    if not SERPER_API_KEY:
        print('  [Camada 4] SERPER_API_KEY ausente. Camada 4 ignorada.', flush=True)
        return

    print('\n  [Camada 4] Scraping Direto de Portais Locais via Serper site:...', flush=True)
    query_base = '"IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano"'

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


# ---------------------------------------------------------------------------
# Motor Principal
# ---------------------------------------------------------------------------

def processar_clipping():
    print('Iniciando Motor de Clipping Inteligente v2.0 (Multi-Engine 4 Camadas)...', flush=True)
    os.makedirs(DIR_DATA, exist_ok=True)

    data_hoje = datetime.now()
    data_janela_inicio = (data_hoje - timedelta(days=DIAS_JANELA_MOVEL)).strftime('%Y-%m-%d')
    data_hoje_str = data_hoje.strftime('%Y-%m-%d')

    print(f'  Janela de coleta: {data_janela_inicio} a {data_hoje_str}', flush=True)

    links_conhecidos, titulos_veiculos_conhecidos, df_existente = _carregar_base_conhecida()
    print(f'  Base existente: {len(links_conhecidos)} links carregados.', flush=True)

    clipping_coletado = []

    # --- 4 Camadas de Coleta ---
    coletar_serper(
        data_inicio=data_janela_inicio, data_fim=data_hoje_str,
        links_conhecidos=links_conhecidos,
        titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
        clipping_coletado=clipping_coletado,
    )
    coletar_google_rss(
        data_inicio=data_janela_inicio, data_fim=data_hoje_str,
        links_conhecidos=links_conhecidos,
        titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
        clipping_coletado=clipping_coletado,
    )
    coletar_bing_rss(
        data_inicio=data_janela_inicio,
        links_conhecidos=links_conhecidos,
        titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
        clipping_coletado=clipping_coletado,
    )
    coletar_portais_locais(
        data_inicio=data_janela_inicio, data_fim=data_hoje_str,
        links_conhecidos=links_conhecidos,
        titulos_veiculos_conhecidos=titulos_veiculos_conhecidos,
        clipping_coletado=clipping_coletado,
    )

    print(f'\n  Total de novas menções encontradas: {len(clipping_coletado)}', flush=True)

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    # Remove o CSV antigo monolítico se ainda existir
    if os.path.exists(ARQUIVO_ANTIGO):
        os.remove(ARQUIVO_ANTIGO)

    salvar_e_gerar_stats(df_final)


if __name__ == '__main__':
    processar_clipping()
