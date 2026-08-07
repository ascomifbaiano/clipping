"""
clipping_utils.py - Biblioteca Central de Heurísticas e Utilitários
Motor de Clipping Inteligente | IF Baiano | v2.0.0 | 2026-08-07

Changelog v2.0.0:
  - resolver_url_direta: Decodificação robusta de URLs do Google News (Base64),
    extração de tag canonical e metatag og:url. Timeout ampliado e retentativas.
  - validar_noticia: Full-Text Content Scan em portais .edu.br e .gov.br
    quando o título não contém explicitamente "IF Baiano". Resolve o caso
    de matérias como "Univerciência apresenta pesquisas..." (UESB) que mencionam
    o IF Baiano somente no corpo do texto.
  - Mantidas 100% intactas as funções de classificação usadas pelo frontend:
    classificar_eixo, classificar_abrangencia, classificar_campus, salvar_e_gerar_stats.
"""
import os
import re
import sys
import json
import html
import base64
import unicodedata
import requests
import pandas as pd
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, unquote

sys.stdout.reconfigure(encoding='utf-8')

DIR_DATA = 'data'

VARIANTES_BAIANO = [
    'if baiano', 'ifbaiano', 'instituto federal baiano',
    'ifbaiana', 'if baiana', 'federal baiano',
    'if-baiano', 'if.baiano', 'if_baiano',
    'instituto federal de educacao, ciencia e tecnologia baiano',
    'instituto federal de educacao ciencia e tecnologia baiano',
]

CIDADES_EXCLUSIVAS_IF_BAIANO = [
    'alagoinhas', 'lapa', 'bom jesus da lapa', 'catu',
    'mangabeira', 'governador mangabeira',
    'guanambi', 'itaberaba', 'itapetinga', 'santa ines',
    'bonfim', 'senhor do bonfim', 'serrinha',
    'teixeira', 'teixeira de freitas', 'urucuca', 'urucuca',
    'xique-xique', 'xique xique',
    'santo estevao', 'pombal', 'ribeira do pombal',
    'remanso', 'ruy barbosa',
]

CAMPI_REAIS_IFBA = [
    'salvador', 'feira de santana', 'camacari', 'barreiras', 'jequie',
    'eunapolis', 'ilheus', 'irece', 'jacobina', 'paulo afonso',
    'porto seguro', 'santo amaro', 'seabra', 'simoes filho', 'valenca',
    'vitoria da conquista', 'brumado', 'juazeiro',
    'lauro de freitas', 'santo antonio de jesus',
]

HEADERS_SCRAPER = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


# ---------------------------------------------------------------------------
# Utilitários de String
# ---------------------------------------------------------------------------

def remover_acentos(texto):
    if not texto:
        return ''
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(texto))
        if not unicodedata.combining(c)
    ).lower()


def normalizar_para_busca(texto):
    t = remover_acentos(texto)
    # Remove termos ambíguos para evitar falsos positivos geográficos/culturais
    termos_excluir = [
        'anisio teixeira', 'lavagem do bonfim', 'festa do bonfim',
        'igreja do bonfim', 'estacao da lapa', 'shopping lapa', 'nova lapa',
        'mercado da lapa', 'beco da lapa', 'terreiro',
    ]
    for termo in termos_excluir:
        t = t.replace(termo, '')
    return t


# ---------------------------------------------------------------------------
# Resolução de URLs — Versão 2.0 (Base64 Google + Canonical Tag + og:url)
# ---------------------------------------------------------------------------

def _decodificar_url_google_news(url: str) -> str:
    """
    O Google News codifica os links reais em Base64 dentro de um parâmetro
    da URL de redirecionamento. Esta função decodifica o link real sem
    precisar fazer requisição HTTP.

    Formatos conhecidos:
      - https://news.google.com/articles/CBMi<base64>
      - https://news.google.com/rss/articles/CBMi<base64>
    """
    try:
        match = re.search(r'articles/CBMi([A-Za-z0-9+/=_-]+)', url)
        if match:
            # Google usa URL-safe Base64 sem padding
            b64 = match.group(1)
            # Adiciona padding se necessário
            b64 += '=' * (-len(b64) % 4)
            b64 = b64.replace('-', '+').replace('_', '/')
            decoded = base64.b64decode(b64).decode('utf-8', errors='ignore')
            # O link real começa tipicamente com http
            url_match = re.search(r'(https?://[^\x00-\x1f\s]+)', decoded)
            if url_match:
                return url_match.group(1)
    except Exception:
        pass
    return url


def _extrair_canonical(html_content: str, url_fallback: str) -> str:
    """
    Extrai a URL canônica do HTML via tag <link rel="canonical"> ou <meta property="og:url">.
    """
    try:
        match = re.search(
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
            html_content, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
        match = re.search(
            r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
            html_content, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return url_fallback


def resolver_url_direta(url_rss: str, timeout: int = 8) -> str:
    """
    Resolve a URL real a partir de redirecionamentos do Google News / Bing News.

    Estratégia em cascata:
    1. Tenta decodificar Base64 do Google News (rápido, sem requisição HTTP).
    2. Tenta seguir redirecionamentos HTTP (GET com allow_redirects=True).
    3. Se o HTML de destino contiver tag canonical, retorna a URL canônica.
    """
    if not url_rss:
        return url_rss

    # Passo 1: Decodificação Base64 (Google News)
    if 'news.google.com' in url_rss:
        url_decodificada = _decodificar_url_google_news(url_rss)
        if url_decodificada != url_rss:
            return url_decodificada

    # Passo 2: Seguir redirecionamentos HTTP
    # Só executa se for um link de redirecionamento conhecido
    dominios_redirect = (
        'news.google.com', 'bing.com/news', 'google.com/rss',
        'news.yahoo.com', 'feedly.com', 'flipboard.com'
    )
    if not any(d in url_rss for d in dominios_redirect):
        return url_rss

    for tentativa in range(2):
        try:
            resp = requests.get(
                url_rss,
                headers=HEADERS_SCRAPER,
                allow_redirects=True,
                timeout=timeout,
                verify=False,
            )
            url_final = resp.url

            # Passo 3: Extrai canonical se o HTML ainda for um intermediário
            if resp.status_code == 200 and 'text/html' in resp.headers.get('Content-Type', ''):
                canonical = _extrair_canonical(resp.text, url_final)
                if canonical and canonical.startswith('http') and canonical != url_rss:
                    return canonical

            if url_final and url_final.startswith('http') and url_final != url_rss:
                return url_final

            break  # Sem redirecionamento, retorna original

        except requests.exceptions.Timeout:
            if tentativa == 0:
                timeout = timeout // 2  # Tenta com metade do tempo
                continue
            break
        except Exception:
            break

    return url_rss


# ---------------------------------------------------------------------------
# Normalização e Classificação de Datas
# ---------------------------------------------------------------------------

def padronizar_data(data_str, ano_referencia=str(datetime.now().year)):
    if not data_str:
        return f'{ano_referencia}-01-01'
    d_str = remover_acentos(data_str).strip()

    meses = {
        'janeiro': '01', 'fevereiro': '02', 'marco': '03', 'abril': '04',
        'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
        'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12',
    }
    for pt, num in meses.items():
        d_str = d_str.replace(pt, num)

    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', d_str)
    if match:
        return match.group(0)

    match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{2,4})', d_str)
    if match:
        d, m, y = match.groups()
        if len(y) == 2:
            y = '20' + y
        return f'{y}-{m.zfill(2)}-{d.zfill(2)}'

    try:
        dt = parsedate_to_datetime(data_str)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        pass

    return f'{ano_referencia}-01-01'


# ---------------------------------------------------------------------------
# Classificação Heurística de Eixos, Abrangência e Campus
# (Mantidas 100% intactas para não quebrar o frontend)
# ---------------------------------------------------------------------------

def classificar_eixo(titulo):
    t = remover_acentos(titulo)
    if any(w in t for w in [
        'professor', 'substituto', 'concurso', 'processo seletivo', 'selecao',
        'vaga', 'servidor', 'docente', 'edital'
    ]):
        return 'Gestão e RH'
    if any(w in t for w in [
        'sisu', 'prosel', 'curso', 'graduacao', 'especializacao', 'tecnico',
        'matricula', 'ensino', 'aluno', 'estudante', 'aula', 'partiu if',
        'bolsa', 'enem', 'vestibular', 'ingresso'
    ]):
        return 'Ensino'
    if any(w in t for w in [
        'pesquisa', 'ciencia', 'tecnologia', 'inovacao', 'patente', 'cnpq',
        'artigo', 'fapesb', 'cientifica', 'pesquisador', 'desenvolve', 'biofilme',
        'univerciencia', 'universidade', 'mamona', 'construcao naval', 'qualidade do ar'
    ]):
        return 'Pesquisa'
    if any(w in t for w in [
        'extensao', 'comunidade', 'projeto', 'feira', 'evento', 'seminario',
        'agricultura familiar', 'mulheres mil', 'oficina', 'tenda', 'jornada',
        'redacao', 'olimpiada', 'competicao'
    ]):
        return 'Extensão'
    return 'Institucional'


def classificar_abrangencia(veiculo):
    v = remover_acentos(veiculo)
    if any(w in v for w in [
        'g1', 'cnn', 'r7', 'terra', 'estadao', 'msn', 'uol', 'record',
        'band', 'catraca livre', 'o tempo', 'folha', 'globo', 'agencia brasil',
        'metropoles', 'correio braziliense', 'veja', 'isto e'
    ]):
        return 'Imprensa (Nacional)'
    if any(w in v for w in [
        'a tarde', 'correio', 'bnews', 'aratu', 'ibahia', 'tribuna da bahia',
        'bahia noticias', 'farol da bahia', 'bahia.ba', 'bahia ja',
        'jornal grande bahia', 'salvador noticias', 'radio educadora bahia',
        'acorda cidade', 'bahia urgente'
    ]):
        return 'Imprensa Regional (Bahia)'

    # Outras Instituições de Ensino (Universidades e outros IFs)
    termos_edu = [
        'ufba', 'uesb', 'ifba', 'ufrb', 'ufob', 'univasf', 'ifsc', 'ifsp',
        'ifsertao', 'ifpe', 'ifpb', 'ifrn', 'ifce', 'ifma', 'ifpi', 'ifal',
        'ifse', 'ifmg', 'ifsudestemg', 'ifnmg', 'ifgoiano', 'ifg', 'ifms',
        'ifmt', 'ifpr', 'ifsul', 'ifrs', 'iff', 'ifrj', 'coluni', 'ufmg',
        'ufrj', 'usp', 'unicamp', 'unesp', 'unb', 'ufrgs', 'cefet',
        'universidade', 'faculdade', 'instituto federal', 'ifes', 'ifs', 'reitoria'
    ]
    if any(w in v for w in termos_edu):
        return 'Outras Instituições de Ensino'

    # Governamental e órgãos públicos
    termos_gov = [
        'prefeitura', 'gov.br', 'conif', 'mec', 'adab', 'codevasf', 'embrapa',
        'governo', 'secretaria', 'ministerio', 'planalto', 'senado', 'camara'
    ]
    if any(w in v for w in termos_gov) or 'if baiano' in v:
        return 'Governamental'

    if any(w in v for w in [
        'concurso', 'pci', 'qconcursos', 'ache', 'direcao', 'estrategia',
        'educacao', 'agro', 'rural', 'defesa', 'tecnologia', 'focus', 'gran',
        'vestibular', 'noticias concurso', 'blog do emprego', 'notícias concursos'
    ]):
        return 'Especializados (Nichos)'

    cidades_e_portais = [
        'alagoinhas', 'lapa', 'catu', 'mangabeira', 'guanambi', 'itaberaba',
        'itapetinga', 'santa ines', 'bonfim', 'serrinha', 'teixeira', 'urucuca',
        'valenca', 'xique-xique', 'santo estevao', 'pombal', 'remanso',
        'ruy barbosa', 'alta pressao', 'se liga alagoinhas', 'fala alagoinhas',
        'alagonews', 'agencia sertao', 'iguanambi', 'alo cidade', 'folha do vale',
        'sudoeste bahia', 'lapa oeste', 'blog regional', 'gazeta da lapa',
        'central da lapa', 'eloilton cajuhy', 'ivan silva', 'bonfim digital',
        'netto maravilha', 'cleber vieira', 'teixeira news', 'extremosul',
        'teixeira urgente', 'texas news', 'povo news', 'liberdade news',
        'sulbahianews', 'voz do campo', 'pimenta blog', 'politicos do sul',
        'fala voce', 'falavoce', 'portal do sertao', 'jornal grande bahia',
        'bahia extremo sul', 'vale do mucuri', 'noroeste baiano',
    ]
    if any(w in v for w in cidades_e_portais):
        return 'Imprensa Local'

    return 'Imprensa Local'


def classificar_campus(titulo, veiculo):
    t_v = normalizar_para_busca(str(titulo) + ' ' + str(veiculo))
    campuses = {
        'Alagoinhas': ['alagoinhas'],
        'Bom Jesus da Lapa': ['lapa', 'bom jesus da lapa'],
        'Catu': ['catu'],
        'Governador Mangabeira': ['mangabeira', 'governador mangabeira'],
        'Guanambi': ['guanambi'],
        'Itaberaba': ['itaberaba'],
        'Itapetinga': ['itapetinga'],
        'Santa Inês': ['santa ines'],
        'Senhor do Bonfim': ['bonfim', 'senhor do bonfim'],
        'Serrinha': ['serrinha'],
        'Teixeira de Freitas': ['teixeira', 'teixeira de freitas'],
        'Uruçuca': ['urucuca'],
        'Valença': ['valenca'],
        'Xique-Xique': ['xique-xique', 'xique xique'],
        'Santo Estêvão': ['santo estevao'],
        'Ribeira do Pombal': ['pombal', 'ribeira do pombal'],
        'Remanso': ['remanso'],
        'Ruy Barbosa': ['ruy barbosa'],
    }
    for campus, termos in campuses.items():
        if any(termo in t_v for termo in termos):
            return campus
    if 'reitoria' in t_v or 'salvador' in t_v:
        return 'Reitoria (Salvador)'
    return 'Geral / Não Especificado'


# ---------------------------------------------------------------------------
# Limpeza de HTML
# ---------------------------------------------------------------------------

def limpar_html(html_content):
    if not html_content:
        return ''
    text = re.sub(
        r'<(script|style)\b[^>]*>([\s\S]*?)<\/\1>',
        ' ', html_content, flags=re.IGNORECASE
    )
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Validação de Notícia — Versão 2.0 com Full-Text Scan
# ---------------------------------------------------------------------------

def validar_noticia(titulo: str, veiculo: str, link: str = None, puxar_conteudo: bool = False) -> bool:
    """
    Determina se uma matéria encontrada é realmente sobre o IF Baiano.

    Fluxo de decisão (cascata):
    1. Descarta imediatamente se o link for do portal institucional ifbaiano.edu.br.
    2. Descarta imediatamente se o veículo for o próprio IF Baiano (auto-clipping).
    3. Aprova imediatamente se o título/veículo contiver qualquer variante de "IF Baiano".
    4. Se o link vier de portal .edu.br ou .gov.br (e puxar_conteudo=True), faz
       Full-Text Scan: baixa o HTML da página e busca "IF Baiano" no corpo inteiro.
    5. Verifica cidades exclusivas do IF Baiano no título.
    6. Trata caso de ambiguidade IFBA vs IF Baiano com cidades.
    """
    # Regra 1: Excluir auto-clipping institucional
    if link and 'ifbaiano.edu.br' in str(link).lower():
        return False

    # Regra 2: Excluir veículo = IF Baiano
    veiculo_norm = remover_acentos(str(veiculo))
    if any(term in veiculo_norm for term in VARIANTES_BAIANO):
        return False

    t_v = normalizar_para_busca(str(titulo) + ' ' + str(veiculo))

    # Regra 3: Aprovação imediata por variante explícita no título/veículo
    if any(var in t_v for var in VARIANTES_BAIANO):
        return True

    # Regra 4: Full-Text Content Scan para fontes confiáveis mas com título genérico
    # Ativado quando:
    #   a) puxar_conteudo=True (explicitamente solicitado), OU
    #   b) link de portal .edu.br ou .gov.br (sempre merece inspeção profunda)
    link_str = str(link).lower() if link else ''
    link_merece_scan = link and (
        puxar_conteudo
        or '.edu.br' in link_str
        or '.gov.br' in link_str
        or 'conif.org.br' in link_str
    )

    if link_merece_scan:
        try:
            resp = requests.get(
                link, headers=HEADERS_SCRAPER,
                timeout=8, verify=False,
                stream=False,
            )
            if resp.status_code == 200:
                # Limita a leitura a 500 KB para performance
                conteudo = normalizar_para_busca(limpar_html(resp.text[:500_000]))

                # Aprovação imediata: "IF Baiano" no corpo
                if any(var in conteudo for var in VARIANTES_BAIANO):
                    return True

                # Cidades exclusivas do IF Baiano mencionadas no corpo + ausência de campi IFBA
                if any(c in conteudo for c in CIDADES_EXCLUSIVAS_IF_BAIANO):
                    if not any(camp in conteudo for camp in CAMPI_REAIS_IFBA):
                        return True

                # Confusão de sigla: "IFBA <cidade-do-IF-Baiano>"
                termos_confusao = (
                    [f'ifba {c}' for c in CIDADES_EXCLUSIVAS_IF_BAIANO]
                    + [f'ifba de {c}' for c in CIDADES_EXCLUSIVAS_IF_BAIANO]
                    + [f'campus {c}' for c in CIDADES_EXCLUSIVAS_IF_BAIANO]
                )
                if any(tc in conteudo for tc in termos_confusao):
                    return True

                return False

        except Exception:
            # Em caso de falha na requisição, cai para as regras heurísticas abaixo
            pass

    # Regra 5: Cidades exclusivas do IF Baiano no título/veículo (sem inspeção de corpo)
    if any(c in t_v for c in CIDADES_EXCLUSIVAS_IF_BAIANO):
        # Verifica se não é um portal genérico de cidades sem relação com o IF Baiano
        variantes_ifba = ['ifba', 'instituto federal da bahia']
        if any(var in t_v for var in variantes_ifba):
            # Caso ambíguo: tem IFBA + cidade do IF Baiano, mas pode ser IFBA legítimo
            termos_ifba_real = ['ufba', 'uneb', 'ufrb', 'uesb', 'ufob', 'engenharia', 'grupo petropolis']
            if any(term in t_v for term in termos_ifba_real):
                return False
        return True

    # Regra 6: Valença + termos agrícolas (campus agropecuário)
    if 'valenca' in t_v:
        termos_valenca = [
            'agropecuaria', 'zootecnia', 'agronomia', 'agricultura',
            'agroecologia', 'florestas', 'alimento', 'alimentos', 'agroecologico'
        ]
        if any(term in t_v for term in termos_valenca):
            return True

    return False


# ---------------------------------------------------------------------------
# Salvamento e Geração de Estatísticas
# (Mantida 100% intacta para não quebrar o frontend)
# ---------------------------------------------------------------------------

def salvar_e_gerar_stats(df_final, dir_data=DIR_DATA):
    if df_final.empty:
        print('Nenhum dado para salvar.', flush=True)
        return

    os.makedirs(dir_data, exist_ok=True)
    df_final['assunto'] = df_final['assunto'].astype(str).str.strip()
    df_final['veiculo'] = df_final['veiculo'].astype(str).str.strip()

    df_final = df_final.drop_duplicates(subset=['link'], keep='first')
    df_final['tmp_key'] = df_final['assunto'].str.lower() + '|' + df_final['veiculo'].str.lower()
    df_final = df_final.drop_duplicates(subset=['tmp_key'], keep='first').drop(columns=['tmp_key'])

    df_final['eixo_institucional'] = df_final['assunto'].apply(classificar_eixo)
    df_final['abrangencia'] = df_final['veiculo'].apply(classificar_abrangencia)
    df_final['campus'] = df_final.apply(
        lambda row: classificar_campus(row['assunto'], row['veiculo']), axis=1
    )

    df_final['data'] = df_final['data'].astype(str)
    df_final['ano_num'] = df_final['data'].apply(
        lambda x: int(x[:4]) if len(x) >= 4 else 0
    )

    def definir_arquivo(data_str):
        try:
            ano = int(str(data_str)[:4])
            return 'clipping_ate_2021.csv' if ano <= 2021 else f'clipping_{ano}.csv'
        except Exception:
            return 'clipping_extra.csv'

    df_final['arquivo_destino'] = df_final['data'].apply(definir_arquivo)

    contagem_por_ano_real = df_final['ano_num'].value_counts().to_dict()

    # CSV geral (todos os anos)
    caminho_geral = os.path.join(dir_data, 'clipping_geral.csv')
    (
        df_final
        .sort_values(by=['data'], ascending=False)
        .drop(columns=['arquivo_destino', 'ano_num'])
        .to_csv(caminho_geral, index=False, encoding='utf-8-sig')
    )

    def gerar_stats_dict(df, key_name):
        if key_name == 'geral':
            ano_ref = datetime.now().year
        elif key_name == 'ate_2021':
            ano_ref = 2021
        else:
            try:
                ano_ref = int(key_name)
            except ValueError:
                ano_ref = datetime.now().year

        historico = [
            {'ano': a, 'total': int(contagem_por_ano_real[a])}
            for a in range(ano_ref, 2007, -1)
            if a in contagem_por_ano_real
        ]
        return {
            'total': len(df),
            'eixos': df['eixo_institucional'].value_counts().to_dict(),
            'abrangencia': df['abrangencia'].value_counts().to_dict(),
            'top_veiculos': df['veiculo'].value_counts().head(10).to_dict(),
            'meses': df['data'].str[5:7].value_counts().to_dict(),
            'campuses': df['campus'].value_counts().to_dict(),
            'historico': historico,
        }

    stats_por_ano = {'geral': gerar_stats_dict(df_final, 'geral')}

    for arquivo, df_grupo in df_final.groupby('arquivo_destino'):
        ano_key = arquivo.replace('clipping_', '').replace('.csv', '')
        df_grupo_sorted = df_grupo.sort_values(by=['data'], ascending=False)
        stats_por_ano[ano_key] = gerar_stats_dict(df_grupo_sorted, ano_key)
        caminho = os.path.join(dir_data, arquivo)
        (
            df_grupo_sorted
            .drop(columns=['arquivo_destino', 'ano_num'])
            .to_csv(caminho, index=False, encoding='utf-8-sig')
        )

    arquivo_stats = os.path.join(dir_data, 'stats.json')
    with open(arquivo_stats, 'w', encoding='utf-8') as f:
        json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)

    print(
        f'Sucesso! {len(df_final)} registros limpos. '
        f'CSV Geral e Stats JSON atualizados em {dir_data}/',
        flush=True
    )
