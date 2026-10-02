"""
clipping_utils.py - Biblioteca Central de Heurísticas e Utilitários
Motor de Clipping Inteligente | IF Baiano | v3.0.0 | 2026-10-02

Changelog v3.0.0:
  - Unidades do IF Baiano (Painel-DICOM) e campi do IFBA (portal.ifba.edu.br)
    em listas únicas, com Salvador e Valença tratadas como cidades compartilhadas.
  - classificar_mencao: detecção nos dois sentidos (IFBA no lugar de IF Baiano
    e IF Baiano no lugar de IFBA) pela construção da frase, gravada na coluna
    tipo_mencao. Substitui as regras repetidas no index.html e no saneamento.
  - validar_noticia: comparação por palavra inteira, sem a variante
    "federal baiano", regra de cidade exigindo termo de instituição, uso do
    trecho de resumo da fonte e opção de rodar sem acesso à rede.
  - resolver_url_direta: decodifica o formato novo do Google News (batchexecute),
    com a ScraperAPI como contingência quando o Google recusar a requisição.
  - padronizar_data: datas relativas ("3 days ago", "há 2 dias") e abreviadas.
  - salvar_e_gerar_stats: colunas origem e tipo_mencao, campus da curadoria
    preservado, ordenação estável e estatísticas sem as menções do IFBA.

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
import time
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, unquote, quote

sys.stdout.reconfigure(encoding='utf-8')

DIR_DATA = 'data'
SCRAPER_API_KEY = os.environ.get('SCRAPER_API_KEY', '')

VARIANTES_BAIANO = [
    'if baiano', 'ifbaiano', 'instituto federal baiano',
    'ifbaiana', 'if baiana',
    'if-baiano', 'if.baiano', 'if_baiano',
    'instituto federal de educacao, ciencia e tecnologia baiano',
    'instituto federal de educacao ciencia e tecnologia baiano',
]

# Unidades do IF Baiano (fonte: Painel-DICOM). O primeiro termo de cada lista é
# o nome completo; os seguintes são formas curtas, aceitas só quando aparecem
# coladas à sigla ou à palavra "campus", porque sozinhas são ambíguas
# (Lapa, Bonfim e Teixeira também são bairros, festas e sobrenomes).
UNIDADES_IF_BAIANO = {
    'Alagoinhas': ['alagoinhas'],
    'Bom Jesus da Lapa': ['bom jesus da lapa', 'lapa'],
    'Catu': ['catu'],
    'Governador Mangabeira': ['governador mangabeira', 'mangabeira'],
    'Guanambi': ['guanambi'],
    'Itaberaba': ['itaberaba'],
    'Itapetinga': ['itapetinga'],
    'Santa Inês': ['santa ines'],
    'Senhor do Bonfim': ['senhor do bonfim', 'bonfim'],
    'Serrinha': ['serrinha'],
    'Teixeira de Freitas': ['teixeira de freitas', 'teixeira'],
    'Uruçuca': ['urucuca'],
    'Valença': ['valenca'],
    'Xique-Xique': ['xique-xique', 'xique xique'],
    'Santo Estêvão': ['santo estevao'],
    'Ribeira do Pombal': ['ribeira do pombal', 'pombal'],
    'Remanso': ['remanso'],
    'Ruy Barbosa': ['ruy barbosa', 'rui barbosa'],
}

# Campi do IFBA (fonte: portal.ifba.edu.br, lista enviada por Yuri em 02/10/2026).
CAMPI_IFBA = [
    'barreiras', 'brumado', 'camacari', 'euclides da cunha', 'eunapolis',
    'feira de santana', 'ilheus', 'irece', 'jacobina', 'jequie', 'juazeiro',
    'lauro de freitas', 'paulo afonso', 'porto seguro', 'salvador',
    'santo amaro', 'santo antonio de jesus', 'seabra', 'simoes filho',
    'ubaitaba', 'valenca', 'vitoria da conquista',
]

# Cidades com unidades das duas instituições: nunca decidem sozinhas a direção.
CIDADES_COMPARTILHADAS = ['salvador', 'valenca']

CIDADES_EXCLUSIVAS_IF_BAIANO = [
    termo for nome, termos in UNIDADES_IF_BAIANO.items()
    if nome != 'Valença' for termo in termos
]
NOMES_COMPLETOS_IF_BAIANO = [
    termos[0] for nome, termos in UNIDADES_IF_BAIANO.items() if nome != 'Valença'
]
CAMPI_EXCLUSIVOS_IFBA = [c for c in CAMPI_IFBA if c not in CIDADES_COMPARTILHADAS]
CAMPI_REAIS_IFBA = CAMPI_IFBA  # nome mantido para scripts antigos

TIPOS_MENCAO_IF_BAIANO = ('correta', 'ambos_citados', 'ifba_no_lugar_do_ifbaiano')
TIPO_INVERSO = 'ifbaiano_no_lugar_do_ifba'

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


def _baixar_pagina_google_news(url_artigo: str, timeout: int):
    """GET direto; se o Google recusar (429/403), tenta pela ScraperAPI."""
    try:
        resp = requests.get(url_artigo, headers=HEADERS_SCRAPER, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    if SCRAPER_API_KEY:
        try:
            resp = requests.get(
                'https://api.scraperapi.com/',
                params={'api_key': SCRAPER_API_KEY, 'url': url_artigo},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
    return ''


def decodificar_google_news_novo(url: str, timeout: int = 15) -> str:
    """
    Formato atual do Google News (CBMi...AU_yqL...): a URL real não está mais
    no Base64. A página do artigo traz uma assinatura (data-n-a-sg) e um carimbo
    de tempo (data-n-a-ts), que o endpoint batchexecute troca pela URL real.
    Retorna a URL original quando não consegue decodificar.
    """
    try:
        gid = urlparse(url).path.rstrip('/').split('/')[-1]
        if not gid:
            return url
        pagina = _baixar_pagina_google_news(f'https://news.google.com/rss/articles/{gid}', timeout)
        sg = re.search(r'data-n-a-sg="([^"]+)"', pagina)
        ts = re.search(r'data-n-a-ts="([^"]+)"', pagina)
        if not (sg and ts):
            return url
        req = [
            'Fbv4je',
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,'
            'null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{gid}",{ts.group(1)},"{sg.group(1)}"]',
        ]
        resp = requests.post(
            'https://news.google.com/_/DotsSplashUi/data/batchexecute',
            headers={**HEADERS_SCRAPER, 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            data='f.req=' + quote(json.dumps([[req]])),
            timeout=timeout, verify=False,
        )
        corpo = json.loads(resp.text.split('\n\n')[1])[:-2]
        url_real = json.loads(corpo[0][2])[1]
        if isinstance(url_real, str) and url_real.startswith('http'):
            return url_real
    except Exception:
        pass
    return url


def link_pendente_google(url: str) -> bool:
    return 'news.google.com' in str(url)


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

    # Desembrulha links de redirecionamento do Google (google.com/url?q=...)
    if 'google.com/url?' in url_rss:
        q = parse_qs(urlparse(url_rss).query).get('q')
        if q and q[0].startswith('http'):
            return q[0]

    # Passo 1: Google News, formato novo (batchexecute) e antigo (Base64)
    if 'news.google.com' in url_rss:
        url_decodificada = decodificar_google_news_novo(url_rss)
        if url_decodificada != url_rss:
            return url_decodificada
        url_decodificada = _decodificar_url_google_news(url_rss)
        if url_decodificada != url_rss and 'news.google.com' not in url_decodificada:
            return url_decodificada
        return url_rss

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

    # Datas relativas do Serper e de portais ("3 days ago", "ha 2 dias", "1 hour ago")
    m_rel = re.search(
        r'(\d+)\s*(minuto|minute|min|hora|hour|h\b|dia|day|semana|week|mes|month)', d_str
    )
    if m_rel and ('ago' in d_str or d_str.startswith('ha ') or 'atras' in d_str):
        qtd, unidade = int(m_rel.group(1)), m_rel.group(2)
        if unidade.startswith(('dia', 'day')):
            delta = timedelta(days=qtd)
        elif unidade.startswith(('semana', 'week')):
            delta = timedelta(weeks=qtd)
        elif unidade.startswith(('mes', 'month')):
            delta = timedelta(days=30 * qtd)
        else:
            delta = timedelta(0)
        return (datetime.now() - delta).strftime('%Y-%m-%d')
    if d_str in ('ontem', 'yesterday'):
        return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    meses = {
        'janeiro': '01', 'fevereiro': '02', 'marco': '03', 'abril': '04',
        'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
        'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12',
    }
    for pt, num in meses.items():
        d_str = d_str.replace(pt, num)

    # Abreviadas: "Sep 30, 2026", "30 de set. de 2026", "30 set 2026"
    abrev = {
        'jan': 1, 'fev': 2, 'feb': 2, 'mar': 3, 'abr': 4, 'apr': 4, 'mai': 5,
        'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'aug': 8, 'set': 9, 'sep': 9,
        'out': 10, 'oct': 10, 'nov': 11, 'dez': 12, 'dec': 12,
    }
    m_en = re.search(r'\b([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})', d_str)
    m_pt = re.search(r'\b(\d{1,2})\s+(?:de\s+)?([a-z]{3})[a-z]*\.?\s+(?:de\s+)?(\d{4})', d_str)
    if m_en and m_en.group(1) in abrev:
        return f'{m_en.group(3)}-{abrev[m_en.group(1)]:02d}-{int(m_en.group(2)):02d}'
    if m_pt and m_pt.group(2) in abrev:
        return f'{m_pt.group(3)}-{abrev[m_pt.group(2)]:02d}-{int(m_pt.group(1)):02d}'

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


def _tem_palavra(texto, termo):
    return re.search(r'(?<![a-z0-9])' + re.escape(termo) + r'(?![a-z0-9])', texto) is not None


def _campus_no_texto(t):
    for campus, termos in UNIDADES_IF_BAIANO.items():
        # Nome completo vale sozinho; forma curta só colada a campus ou sigla
        if _tem_palavra(t, termos[0]):
            return campus
        for curto in termos[1:]:
            if re.search(r'(?:campus|if ?baiano|ifba)\s*(?:de |do |da |em )?' + re.escape(curto) + r'\b', t):
                return campus
    if re.search(r'\breitori[ao]\b', t) or _tem_palavra(t, 'salvador'):
        return 'Reitoria (Salvador)'
    return None


def classificar_campus(titulo, veiculo):
    # O título decide primeiro; o nome do veículo só entra se o título não
    # citar nenhuma unidade (evita "IFBA Barreiras" virar campus Lapa porque o
    # veículo se chama "Notícias de Bom Jesus da Lapa").
    t = normalizar_para_busca(titulo)
    campus = _campus_no_texto(t)
    if campus:
        return campus
    if any(_tem_palavra(t, c) for c in CAMPI_EXCLUSIVOS_IFBA):
        return 'Geral / Não Especificado'
    campus = _campus_no_texto(normalizar_para_busca(veiculo))
    return campus or 'Geral / Não Especificado'


def normalizar_campus_curadoria(valor):
    """Converte o texto da coluna Campus/Unidade da curadoria para o nome oficial."""
    t = remover_acentos(valor)
    if not t.strip():
        return ''
    for campus, termos in UNIDADES_IF_BAIANO.items():
        if any(_tem_palavra(t, termo) for termo in termos):
            return campus
    if any(p in t for p in ('reitoria', 'institucional', 'if baiano', 'geral', 'todos')):
        return 'Reitoria (Salvador)'
    return ''


# ---------------------------------------------------------------------------
# Classificação da Menção (IF Baiano x IFBA, nos dois sentidos)
# ---------------------------------------------------------------------------

_RE_SIGLA_BAIANO = (
    r'(?:\bif[\s\-._]?baian[oa]s?\b|\binstituto federal baian[oa]\b'
    r'|\binstituto federal de educacao,? ciencia e tecnologia baiano\b)'
)
_RE_SIGLA_IFBA = (
    r'(?:\bifba\b|\binstituto federal da bahia\b|\bif da bahia\b'
    r'|\binstituto federal de educacao,? ciencia e tecnologia da bahia\b)'
)
_RE_LIGACAO = r'\s*[-,:(]?\s*(?:(?:campus|campi|unidade|polo)\s*)?(?:(?:de|do|da|em|no|na)\s+)?'


def _alternativas(termos):
    return '(?:' + '|'.join(re.escape(t) for t in sorted(termos, key=len, reverse=True)) + r')\b'


def _sigla_colada_a_cidade(t, re_sigla, cidades):
    """'IFBA Serrinha', 'IFBA de Santa Inês', 'campus Uruçuca do IFBA'."""
    alt = _alternativas(cidades)
    if re.search(re_sigla + _RE_LIGACAO + alt, t):
        return True
    return re.search(r'\bcampus\s+(?:de\s+)?' + alt + r'\s*(?:,|-)?\s*(?:do|da)\s+' + re_sigla, t) is not None


def classificar_mencao(texto):
    """
    Retorna um destes tipos:
      correta, ambos_citados, ifba_no_lugar_do_ifbaiano,
      ifbaiano_no_lugar_do_ifba, ifba_legitimo, sem_sigla.
    A direção do erro é decidida pela sigla colada à cidade; a simples presença
    das duas palavras no texto não basta, porque Salvador, Valença, Ilhéus e
    Ubaitaba aparecem em notícias legítimas das duas instituições.
    """
    t = normalizar_para_busca(texto)
    tem_baiano = re.search(_RE_SIGLA_BAIANO, t) is not None
    tem_ifba = re.search(_RE_SIGLA_IFBA, t) is not None

    if tem_baiano:
        inverso = _sigla_colada_a_cidade(t, _RE_SIGLA_BAIANO, CAMPI_EXCLUSIVOS_IFBA)
        proprio = _sigla_colada_a_cidade(t, _RE_SIGLA_BAIANO, CIDADES_EXCLUSIVAS_IF_BAIANO)
        if inverso and not proprio and not tem_ifba:
            return TIPO_INVERSO
        return 'ambos_citados' if tem_ifba else 'correta'

    if tem_ifba:
        if _sigla_colada_a_cidade(t, _RE_SIGLA_IFBA, CIDADES_EXCLUSIVAS_IF_BAIANO):
            return 'ifba_no_lugar_do_ifbaiano'
        cita_unidade_baiano = any(_tem_palavra(t, c) for c in NOMES_COMPLETOS_IF_BAIANO)
        cita_campus_ifba = any(_tem_palavra(t, c) for c in CAMPI_EXCLUSIVOS_IFBA)
        termos_ifba_real = ('ufba', 'uneb', 'ufrb', 'uesb', 'ufob', 'grupo petropolis')
        if cita_unidade_baiano and not cita_campus_ifba and not any(_tem_palavra(t, x) for x in termos_ifba_real):
            return 'ifba_no_lugar_do_ifbaiano'
        return 'ifba_legitimo'

    return 'sem_sigla'


_RE_TERMO_INSTITUICAO = (
    r'\b(?:instituto federal|institutos federais|campus|campi|prosel|partiu if'
    r'|rede federal|if)\b'
)


def _sem_sigla_mas_relevante(t):
    """Sem sigla: aceita nome completo de unidade do IF Baiano junto de termo de instituição."""
    if not re.search(_RE_TERMO_INSTITUICAO, t):
        return False
    return any(_tem_palavra(t, c) for c in NOMES_COMPLETOS_IF_BAIANO + ['valenca'])


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
# Validação de Notícia (v3.0, com leitura do corpo quando necessário)
# ---------------------------------------------------------------------------

REDES_SOCIAIS = (
    'instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'x.com',
    'youtube.com', 'youtu.be', 'tiktok.com', 'linkedin.com', 'threads.net',
    'pinterest.com', 'kwai.com', 'whatsapp.com', 't.me',
)
_RE_PAGINA_SEM_MATERIA = re.compile(
    r'/(?:tag|tags|categoria|category|categorias|author|autor|page|pagina|busca|search|secao|editoria)(?:/|$)'
    r'|[?&](?:s|q|busca)='
    r'|\.pdf$'
)


def link_descartavel(url):
    """Redes sociais (inclusive os perfis do próprio IF Baiano) e páginas de listagem."""
    u = str(url or '').lower()
    if not u:
        return False
    dominio = urlparse(u).netloc
    if dominio.startswith('www.'):
        dominio = dominio[4:]
    if any(dominio == r or dominio.endswith('.' + r) for r in REDES_SOCIAIS):
        return True
    caminho = urlparse(u).path
    if caminho in ('', '/'):
        return True  # página inicial do portal, não uma matéria
    return _RE_PAGINA_SEM_MATERIA.search(u) is not None


def avaliar_noticia(titulo, veiculo='', link=None, puxar_conteudo=False,
                    trecho='', permitir_rede=True):
    """
    Decide se a matéria é sobre o IF Baiano e devolve (aceita, tipo_mencao).

    1. Links do portal ifbaiano.edu.br são autoclipping e ficam de fora.
    2. Título mais trecho de resumo da fonte passam por classificar_mencao.
       O nome do veículo não entra, para que "Notícias de Bom Jesus da Lapa"
       não transforme qualquer notícia em menção a um campus.
    3. Sem sigla, aceita nome completo de unidade junto de termo de instituição.
    4. Se ainda houver dúvida e a rede for permitida, lê o corpo da página,
       só em .edu.br, .gov.br e conif. Em portais de notícia a leitura do corpo
       aprovava páginas sem relação, porque a barra lateral citava o IF Baiano;
       por isso puxar_conteudo ficou sem efeito (mantido na assinatura).
    """
    link_str = str(link).lower() if link else ''
    if 'ifbaiano.edu.br' in link_str or link_descartavel(link_str):
        return False, None

    texto = f'{titulo or ""} {trecho or ""}'
    tipo = classificar_mencao(texto)
    if tipo in TIPOS_MENCAO_IF_BAIANO or tipo == TIPO_INVERSO:
        return True, tipo
    if tipo == 'ifba_legitimo':
        return False, tipo
    if _sem_sigla_mas_relevante(normalizar_para_busca(texto)):
        return True, 'correta'

    merece_scan = permitir_rede and link and (
        '.edu.br' in link_str or '.gov.br' in link_str or 'conif.org.br' in link_str
    )
    if merece_scan:
        try:
            resp = requests.get(link, headers=HEADERS_SCRAPER, timeout=8, verify=False)
            if resp.status_code == 200:
                corpo = limpar_html(resp.text[:500_000])
                tipo_corpo = classificar_mencao(f'{titulo} {corpo}')
                if tipo_corpo in TIPOS_MENCAO_IF_BAIANO or tipo_corpo == TIPO_INVERSO:
                    return True, tipo_corpo
                if tipo_corpo == 'sem_sigla' and _sem_sigla_mas_relevante(normalizar_para_busca(corpo)):
                    return True, 'correta'
        except Exception:
            pass

    return False, tipo


def validar_noticia(titulo: str, veiculo: str = '', link: str = None,
                    puxar_conteudo: bool = False, trecho: str = '',
                    permitir_rede: bool = True) -> bool:
    """Atalho booleano de avaliar_noticia, mantido para os scripts existentes."""
    return avaliar_noticia(titulo, veiculo, link, puxar_conteudo, trecho, permitir_rede)[0]

# ---------------------------------------------------------------------------
# Salvamento e Geração de Estatísticas
# ---------------------------------------------------------------------------

def _tipo_mencao_da_linha(row):
    atual = str(row.get('tipo_mencao', '') or '').strip()
    if atual and atual != 'nan':
        return atual
    tipo = classificar_mencao(row['assunto'])
    # Linha já aceita na base sem sigla no título conta como menção correta
    return 'correta' if tipo in ('sem_sigla', 'ifba_legitimo') else tipo


def _ordenar(df):
    # Ordenação estável (data e link) para o commit do robô mostrar só mudanças reais
    return df.sort_values(by=['data', 'link'], ascending=[False, True], kind='mergesort')


def salvar_e_gerar_stats(df_final, dir_data=DIR_DATA):
    if df_final.empty:
        print('Nenhum dado para salvar.', flush=True)
        return

    os.makedirs(dir_data, exist_ok=True)
    df_final = df_final.copy()
    df_final['assunto'] = df_final['assunto'].astype(str).str.strip()
    df_final['veiculo'] = df_final['veiculo'].astype(str).str.strip()
    df_final['link'] = df_final['link'].astype(str).str.strip()

    for col in ('campus', 'origem', 'tipo_mencao'):
        if col not in df_final.columns:
            df_final[col] = ''
    df_final['origem'] = df_final['origem'].fillna('').astype(str).replace({'': 'busca_automatica', 'nan': 'busca_automatica'})

    df_final = df_final.drop_duplicates(subset=['link'], keep='first')
    # Título + veículo; na curadoria a pauta é curta ("Prosel") e se repete
    # no mesmo veículo em anos diferentes, por isso a data entra na chave.
    df_final['tmp_key'] = df_final['assunto'].str.lower() + '|' + df_final['veiculo'].str.lower()
    curadoria = df_final['origem'] == 'curadoria_dicom'
    df_final.loc[curadoria, 'tmp_key'] = df_final.loc[curadoria, 'tmp_key'] + '|' + df_final.loc[curadoria, 'data'].astype(str)
    df_final = df_final.drop_duplicates(subset=['tmp_key'], keep='first').drop(columns=['tmp_key'])

    df_final['eixo_institucional'] = df_final['assunto'].apply(classificar_eixo)
    df_final['abrangencia'] = df_final['veiculo'].apply(classificar_abrangencia)

    # A curadoria informa o campus; nos demais casos ele é inferido do título
    campus_curadoria = df_final['campus'].fillna('').astype(str)
    usar_curadoria = (df_final['origem'] == 'curadoria_dicom') & campus_curadoria.str.strip().ne('') & campus_curadoria.ne('nan')
    df_final['campus'] = [
        c if manter else classificar_campus(a, v)
        for c, manter, a, v in zip(campus_curadoria, usar_curadoria, df_final['assunto'], df_final['veiculo'])
    ]
    df_final['tipo_mencao'] = df_final.apply(_tipo_mencao_da_linha, axis=1)

    df_final['data'] = df_final['data'].astype(str)
    df_final['ano_num'] = df_final['data'].apply(
        lambda x: int(x[:4]) if len(x) >= 4 and x[:4].isdigit() else 0
    )

    def definir_arquivo(data_str):
        try:
            ano = int(str(data_str)[:4])
            return 'clipping_ate_2021.csv' if ano <= 2021 else f'clipping_{ano}.csv'
        except Exception:
            return 'clipping_extra.csv'

    df_final['arquivo_destino'] = df_final['data'].apply(definir_arquivo)

    # Menções do IF Baiano usadas no lugar do IFBA ficam nos CSVs (aba "Nós Somos"),
    # mas não entram nas estatísticas gerais (decisão D1 de 02/10/2026).
    df_conta = df_final[df_final['tipo_mencao'] != TIPO_INVERSO]
    contagem_por_ano_real = df_conta['ano_num'].value_counts().to_dict()

    caminho_geral = os.path.join(dir_data, 'clipping_geral.csv')
    _ordenar(df_final).drop(columns=['arquivo_destino', 'ano_num']).to_csv(
        caminho_geral, index=False, encoding='utf-8-sig'
    )

    def gerar_stats_dict(df_todos, key_name):
        if key_name == 'geral':
            ano_ref = datetime.now().year
        elif key_name == 'ate_2021':
            ano_ref = 2021
        else:
            try:
                ano_ref = int(key_name)
            except ValueError:
                ano_ref = datetime.now().year

        df = df_todos[df_todos['tipo_mencao'] != TIPO_INVERSO]
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
            'origem': df['origem'].value_counts().to_dict(),
            'confusoes': {
                'ifba_no_lugar_do_ifbaiano': int((df_todos['tipo_mencao'] == 'ifba_no_lugar_do_ifbaiano').sum()),
                TIPO_INVERSO: int((df_todos['tipo_mencao'] == TIPO_INVERSO).sum()),
            },
        }

    stats_por_ano = {'geral': gerar_stats_dict(df_final, 'geral')}

    for arquivo, df_grupo in df_final.groupby('arquivo_destino'):
        ano_key = arquivo.replace('clipping_', '').replace('.csv', '')
        df_grupo_sorted = _ordenar(df_grupo)
        stats_por_ano[ano_key] = gerar_stats_dict(df_grupo_sorted, ano_key)
        caminho = os.path.join(dir_data, arquivo)
        df_grupo_sorted.drop(columns=['arquivo_destino', 'ano_num']).to_csv(
            caminho, index=False, encoding='utf-8-sig'
        )

    arquivo_stats = os.path.join(dir_data, 'stats.json')
    with open(arquivo_stats, 'w', encoding='utf-8') as f:
        json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)

    print(
        f'Sucesso! {len(df_final)} registros ({len(df_conta)} contam nas estatísticas). '
        f'CSV Geral e Stats JSON atualizados em {dir_data}/',
        flush=True
    )
