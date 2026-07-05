import os
import re
import json
import html
import unicodedata
import requests
import pandas as pd
from datetime import datetime
from email.utils import parsedate_to_datetime

DIR_DATA = 'data'

def remover_acentos(texto):
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto)) if not unicodedata.combining(c)).lower()

def padronizar_data(data_str, ano_referencia=str(datetime.now().year)):
    if not data_str: return f"{ano_referencia}-01-01"
    d_str = remover_acentos(data_str).strip()
    
    meses = {'janeiro':'01','fevereiro':'02','marco':'03','abril':'04','maio':'05','junho':'06',
             'julho':'07','agosto':'08','setembro':'09','outubro':'10','novembro':'11','dezembro':'12'}
    for pt, num in meses.items():
        d_str = d_str.replace(pt, num)
        
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', d_str)
    if match: return match.group(0)

    match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{2,4})', d_str)
    if match:
        d, m, y = match.groups()
        if len(y) == 2: y = '20' + y
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    try:
        dt = parsedate_to_datetime(data_str)
        return dt.strftime('%Y-%m-%d')
    except: pass

    return f"{ano_referencia}-01-01"

def classificar_eixo(titulo):
    t = remover_acentos(titulo)
    if any(w in t for w in ['professor', 'substituto', 'concurso', 'processo seletivo', 'selecao', 'vaga', 'servidor', 'docente', 'edital']): return 'Gestão e RH'
    if any(w in t for w in ['sisu', 'prosel', 'curso', 'graduacao', 'especializacao', 'tecnico', 'matricula', 'ensino', 'aluno', 'estudante', 'aula', 'partiu if']): return 'Ensino'
    if any(w in t for w in ['pesquisa', 'ciencia', 'tecnologia', 'inovacao', 'patente', 'cnpq', 'artigo', 'fapesb', 'cientifica', 'pesquisador', 'desenvolve', 'biofilme']): return 'Pesquisa'
    if any(w in t for w in ['extensao', 'comunidade', 'projeto', 'feira', 'evento', 'seminario', 'agricultura familiar', 'mulheres mil', 'oficina', 'tenda', 'jornada']): return 'Extensão'
    return 'Institucional'

def classificar_abrangencia(veiculo):
    v = remover_acentos(veiculo)
    if any(w in v for w in ['g1', 'cnn', 'r7', 'terra', 'estadao', 'msn', 'uol', 'record', 'band', 'catraca livre', 'o tempo', 'folha']): return 'Imprensa (Nacional)'
    if any(w in v for w in ['a tarde', 'correio', 'bnews', 'aratu', 'ibahia', 'tribuna da bahia', 'bahia noticias', 'farol da bahia', 'bahia.ba', 'bahia ja']): return 'Imprensa Regional (Bahia)'
    
    # Outras Instituições de Ensino (Universidades e outros IFs)
    termos_edu = [
        'ufba', 'uesb', 'ifba', 'ufrb', 'ufob', 'univasf', 'ifsc', 'ifsp', 'ifsertao', 
        'ifpe', 'ifpb', 'ifrn', 'ifce', 'ifma', 'ifpi', 'ifal', 'ifse', 'ifmg', 
        'ifsudestemg', 'ifnmg', 'ifgoiano', 'ifg', 'ifms', 'ifmt', 'ifpr', 'ifsul', 
        'ifrs', 'iff', 'ifrj', 'coluni', 'ufmg', 'ufrj', 'usp', 'unicamp', 'unesp', 
        'unb', 'ufrgs', 'cefet', 'universidade', 'faculdade', 'instituto federal', 
        'ifes', 'ifs', 'reitoria'
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
        
    if any(w in v for w in ['concurso', 'pci', 'qconcursos', 'ache', 'direcao', 'estrategia', 'educacao', 'agro', 'rural', 'defesa', 'tecnologia', 'focus', 'gran', 'vestibular']): return 'Especializados (Nichos)'
    
    cidades_e_portais = [
        'alagoinhas', 'lapa', 'catu', 'mangabeira', 'guanambi', 'itaberaba', 'itapetinga', 
        'santa ines', 'bonfim', 'serrinha', 'teixeira', 'urucuca', 'valenca', 'xique-xique', 
        'santo estevao', 'pombal', 'remanso', 'ruy barbosa', 'alta pressao', 'se liga alagoinhas', 
        'fala alagoinhas', 'alagonews', 'agencia sertao', 'iguanambi', 'alo cidade', 
        'folha do vale', 'sudoeste bahia', 'lapa oeste', 'blog regional', 'gazeta da lapa', 
        'central da lapa', 'eloilton cajuhy', 'ivan silva', 'bonfim digital', 'netto maravilha', 
        'cleber vieira', 'teixeira news', 'extremosul', 'teixeira urgente', 'texas news', 
        'povo news', 'liberdade news', 'sulbahianews', 'voz do campo', 'pimenta blog', 'politicos do sul'
    ]
    if any(w in v for w in cidades_e_portais):
        return 'Imprensa Local'
    return 'Imprensa Local'

def classificar_campus(titulo, veiculo):
    t_v = remover_acentos(str(titulo) + " " + str(veiculo))
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
        'Ruy Barbosa': ['ruy barbosa']
    }
    for campus, termos in campuses.items():
        if any(termo in t_v for termo in termos):
            return campus
    if 'reitoria' in t_v or 'salvador' in t_v:
        return 'Reitoria (Salvador)'
    return 'Geral / Não Especificado'

def validar_noticia(titulo, veiculo):
    t_v = remover_acentos(str(titulo) + " " + str(veiculo))
    
    # 1. Se contiver explicitamente alguma das variantes de "IF Baiano"
    variantes_baiano = ['if baiano', 'ifbaiano', 'instituto federal baiano', 'ifbaiana', 'if baiana', 'federal baiano']
    if any(var in t_v for var in variantes_baiano):
        return True
        
    # 2. Se não contiver "IF Baiano", mas contiver variantes de "IFBA"
    variantes_ifba = ['ifba', 'instituto federal da bahia']
    if any(var in t_v for var in variantes_ifba):
        # Somente é válida se houver indício de confusão com cidades exclusivas ou termos do IF Baiano
        cidades_exclusivas = [
            'alagoinhas', 'lapa', 'bom jesus da lapa', 'catu', 'mangabeira', 'governador mangabeira',
            'guanambi', 'itaberaba', 'itapetinga', 'santa ines', 'bonfim', 'senhor do bonfim',
            'serrinha', 'teixeira', 'teixeira de freitas', 'urucuca', 'xique-xique', 'xique xique',
            'santo estevao', 'pombal', 'ribeira do pombal', 'remanso', 'ruy barbosa'
        ]
        if any(c in t_v for c in cidades_exclusivas):
            return True
            
        # Caso especial para Valença
        if 'valenca' in t_v:
            termos_valenca = ['agropecuaria', 'zootecnia', 'agronomia', 'agricultura', 'agroecologia', 'florestas', 'alimento', 'reitor', 'substituto', 'edital']
            if any(term in t_v for term in termos_valenca):
                return True
                
        # Caso especial para Salvador/Reitoria
        if 'reitoria' in t_v or 'salvador' in t_v:
            termos_reitoria = ['reitor', 'reitoria', 'licitacao', 'licitaca', 'concurso']
            if any(term in t_v for term in termos_reitoria):
                return True
                
    # 3. Caso não se enquadre em nenhuma das regras acima, não é sobre o IF Baiano
    return False

def resolver_url_direta(url_rss):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
        res = requests.head(url_rss, headers=headers, allow_redirects=True, timeout=5)
        return res.url
    except:
        return url_rss

def salvar_e_gerar_stats(df_final, dir_data=DIR_DATA):
    if df_final.empty:
        return

    os.makedirs(dir_data, exist_ok=True)
    df_final['assunto'] = df_final['assunto'].astype(str).str.strip()
    df_final['veiculo'] = df_final['veiculo'].astype(str).str.strip()
    
    df_final = df_final.drop_duplicates(subset=['link'], keep='first')
    df_final['tmp_key'] = df_final['assunto'].str.lower() + df_final['veiculo'].str.lower()
    df_final = df_final.drop_duplicates(subset=['tmp_key'], keep='first').drop(columns=['tmp_key'])
    
    df_final['eixo_institucional'] = df_final['assunto'].apply(classificar_eixo)
    df_final['abrangencia'] = df_final['veiculo'].apply(classificar_abrangencia)
    df_final['campus'] = df_final.apply(lambda row: classificar_campus(row['assunto'], row['veiculo']), axis=1)
    
    df_final['data'] = df_final['data'].astype(str)
    df_final['ano_num'] = df_final['data'].apply(lambda x: int(x[:4]) if len(x) >= 4 else 0)

    def definir_arquivo(data_str):
        try:
            ano = int(str(data_str)[:4])
            return 'clipping_ate_2021.csv' if ano <= 2021 else f'clipping_{ano}.csv'
        except: return 'clipping_extra.csv'

    df_final['arquivo_destino'] = df_final['data'].apply(definir_arquivo)
    
    stats_por_ano = {}
    contagem_por_ano_real = df_final['ano_num'].value_counts().to_dict()
    
    caminho_geral = os.path.join(dir_data, 'clipping_geral.csv')
    df_final.sort_values(by=['data'], ascending=False).drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho_geral, index=False, encoding='utf-8-sig')

    def gerar_stats_dict(df, key_name):
        ano_ref = datetime.now().year if key_name == 'geral' else (2021 if key_name == 'ate_2021' else int(key_name))
        historico = [{"ano": a, "total": int(contagem_por_ano_real[a])} for a in range(ano_ref, 2011, -1) if a in contagem_por_ano_real]
        
        return {
            "total": len(df),
            "eixos": df['eixo_institucional'].value_counts().to_dict(),
            "abrangencia": df['abrangencia'].value_counts().to_dict(),
            "top_veiculos": df['veiculo'].value_counts().head(10).to_dict(),
            "meses": df['data'].str[5:7].value_counts().to_dict(),
            "campuses": df['campus'].value_counts().to_dict(),
            "historico": historico
        }

    stats_por_ano['geral'] = gerar_stats_dict(df_final, 'geral')

    for arquivo, df_grupo in df_final.groupby('arquivo_destino'):
        ano_key = arquivo.replace('clipping_', '').replace('.csv', '')
        df_grupo_sorted = df_grupo.sort_values(by=['data'], ascending=False)
        stats_por_ano[ano_key] = gerar_stats_dict(df_grupo_sorted, ano_key)
        caminho = os.path.join(dir_data, arquivo)
        df_grupo_sorted.drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho, index=False, encoding='utf-8-sig')

    arquivo_stats = os.path.join(dir_data, 'stats.json')
    with open(arquivo_stats, 'w', encoding='utf-8') as f:
        json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)
    
    print(f"Sucesso! Dados limpos, CSV Geral e Stats JSON atualizados em {dir_data}/")
