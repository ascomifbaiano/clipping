import os
import time
import json
import html
import re
import glob
import urllib.parse
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import urllib3
from datetime import datetime
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DIR_DATA = 'data'
ARQUIVO_STATS = os.path.join(DIR_DATA, 'stats.json')

def padronizar_data(data_str, ano_referencia=str(datetime.now().year)):
    if not data_str: return f"{ano_referencia}-01-01"
    d_str = str(data_str).strip().lower()
    
    meses = {'janeiro':'01','fevereiro':'02','março':'03','marco':'03','abril':'04','maio':'05','junho':'06',
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
    t = str(titulo).lower()
    if any(w in t for w in ['professor', 'substituto', 'concurso', 'processo seletivo', 'seleção', 'vaga', 'servidor', 'docente', 'edital']): return 'Gestão e RH'
    if any(w in t for w in ['sisu', 'prosel', 'curso', 'graduação', 'especialização', 'técnico', 'matrícula', 'ensino', 'aluno', 'estudante', 'aula', 'partiu if']): return 'Ensino'
    if any(w in t for w in ['pesquisa', 'ciência', 'tecnologia', 'inovação', 'patente', 'cnpq', 'artigo', 'fapesb', 'científica', 'pesquisador', 'desenvolve', 'biofilme']): return 'Pesquisa'
    if any(w in t for w in ['extensão', 'comunidade', 'projeto', 'feira', 'evento', 'seminário', 'agricultura familiar', 'mulheres mil', 'oficina', 'tenda', 'jornada']): return 'Extensão'
    return 'Institucional'

def classificar_abrangencia(veiculo):
    v = str(veiculo).lower()
    if any(w in v for w in ['g1', 'cnn', 'r7', 'terra', 'estadao', 'msn', 'uol', 'record', 'band', 'catraca livre', 'o tempo', 'folha']): return 'Imprensa (Nacional)'
    if any(w in v for w in ['a tarde', 'correio', 'bnews', 'aratu', 'ibahia', 'tribuna da bahia', 'bahia notícias', 'farol da bahia', 'bahia.ba', 'bahia já']): return 'Imprensa Regional (Bahia)'
    if any(w in v for w in ['prefeitura', 'gov.br', 'conif', 'mec', 'if baiano', 'ufba', 'uesb', 'ifba', 'adab', 'codevasf', 'embrapa']): return 'Institucional / Governamental'
    if any(w in v for w in ['concurso', 'pci', 'qconcursos', 'ache', 'direção', 'estrategia', 'educação', 'agro', 'rural', 'defesa', 'tecnologia', 'focus', 'gran', 'vestibular']): return 'Especializados (Nichos)'
    
    cidades_e_portais = [
        'alagoinhas', 'lapa', 'catu', 'mangabeira', 'guanambi', 'itaberaba', 'itapetinga', 
        'santa inês', 'santa ines', 'bonfim', 'serrinha', 'teixeira', 'uruçuca', 'urucuca', 
        'valença', 'valenca', 'xique-xique', 'santo estêvão', 'santo estevao', 'pombal', 
        'remanso', 'ruy barbosa', 'alta pressão', 'alta pressao', 'se liga alagoinhas', 
        'fala alagoinhas', 'alagonews', 'agência sertão', 'agencia sertao', 'iguanambi', 
        'alô cidade', 'alo cidade', 'folha do vale', 'sudoeste bahia', 'lapa oeste', 
        'blog regional', 'gazeta da lapa', 'central da lapa', 'eloilton cajuhy', 
        'ivan silva', 'bonfim digital', 'netto maravilha', 'cleber vieira', 
        'teixeira news', 'extremosul', 'teixeira urgente', 'texas news', 'povo news', 
        'liberdade news', 'sulbahianews', 'voz do campo', 'pimenta blog', 'politicos do sul'
    ]
    if any(w in v for w in cidades_e_portais):
        return 'Imprensa Local'
    return 'Imprensa Local'

def classificar_campus(titulo, veiculo):
    t_v = (str(titulo) + " " + str(veiculo)).lower()
    campuses = {
        'Alagoinhas': ['alagoinhas'],
        'Bom Jesus da Lapa': ['lapa', 'bom jesus da lapa'],
        'Catu': ['catu'],
        'Governador Mangabeira': ['mangabeira', 'governador mangabeira'],
        'Guanambi': ['guanambi'],
        'Itaberaba': ['itaberaba'],
        'Itapetinga': ['itapetinga'],
        'Santa Inês': ['santa inês', 'santa ines'],
        'Senhor do Bonfim': ['bonfim', 'senhor do bonfim'],
        'Serrinha': ['serrinha'],
        'Teixeira de Freitas': ['teixeira', 'teixeira de freitas'],
        'Uruçuca': ['uruçuca', 'urucuca'],
        'Valença': ['valença', 'valenca'],
        'Xique-Xique': ['xique-xique', 'xique xique'],
        'Santo Estêvão': ['santo estêvão', 'santo estevao'],
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

def resolver_url_direta(url_rss):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.head(url_rss, headers=headers, allow_redirects=True, timeout=5)
        return res.url
    except:
        return url_rss

termos_diretos = [
    'if baiano', 'ifbaiano', 'if-baiano', 'if.baiano', 'if_baiano', 
    'instituto federal baiano', 'ifbaiana', 'if baiana', 
    'instituto federal baiana', 'federal baiano'
]

cidades_exclusivas = [
    'alagoinhas', 'bom jesus da lapa', 'lapa', 'catu', 'governador mangabeira', 'mangabeira', 
    'guanambi', 'itaberaba', 'itapetinga', 'santa inês', 'santa ines', 'senhor do bonfim', 'bonfim', 
    'serrinha', 'teixeira de freitas', 'teixeira', 'uruçuca', 'urucuca', 'xique-xique', 'xique xique', 
    'santo estêvão', 'santo estevao', 'ribeira do pombal', 'pombal', 'remanso', 'ruy barbosa'
]

termos_valenca_baiano = [
    'agropecuária', 'agropecuaria', 'zootecnia', 'agronomia', 
    'agricultura', 'agroecologia', 'florestas', 'alimento', 
    'reitor', 'substituto', 'edital', 'estudante do if baiano'
]

def e_valido_baiano(titulo, campus):
    t = str(titulo).lower()
    c = str(campus)
    
    # 1. Se tem menções explícitas ao IF Baiano, é sempre válido
    if any(term in t for term in termos_diretos):
        return True
        
    # 2. Se fala de IFBA ou Instituto Federal da Bahia, vamos ver se é uma confusão
    has_ifba_term = 'ifba' in t or 'instituto federal da bahia' in t
    if has_ifba_term:
        # Confusão em cidades exclusivas do IF Baiano (onde não há IFBA)
        if any(cid in t for cid in cidades_exclusivas) or c in [x.title() for x in cidades_exclusivas]:
            return True
            
        # Confusão em Valença (onde existem ambos)
        if 'valença' in t or 'valenca' in t or c == 'Valença':
            if any(term in t for term in termos_valenca_baiano):
                return True
                
        # Confusão na Reitoria / Salvador (Imbuí)
        if 'imbuí' in t or 'imbui' in t:
            return True
            
        return False # Legítimo do IFBA (desprezar)
        
    # 3. Se menciona "Instituto Federal" generico e tem campus associado
    has_generic_if = 'instituto federal' in t or 'institutos federais' in t or 'federal de educação' in t or 'rede federal' in t
    if has_generic_if:
        if c != 'Geral / Não Especificado':
            return True
            
    # 4. Se menciona "campus" ou "reitoria" + cidade/campus
    has_campus_ref = 'campus' in t or 'campi' in t or 'reitoria' in t
    if has_campus_ref:
        if c != 'Geral / Não Especificado':
            if c == 'Valença':
                if 'ifba' in t:
                    return any(term in t for term in termos_valenca_baiano)
            return True

    return False

def processar_carga_inicial():
    print("Iniciando Carga Inicial Avançada via RSS Brackets (29/12/2008 - Hoje)...")
    os.makedirs(DIR_DATA, exist_ok=True)
    
    links_conhecidos = set()
    ARQUIVO_DESCARTADOS = os.path.join(DIR_DATA, 'links_descartados.txt')
    if os.path.exists(ARQUIVO_DESCARTADOS):
        try:
            with open(ARQUIVO_DESCARTADOS, 'r', encoding='utf-8') as f:
                for line in f:
                    lnk = line.strip()
                    if lnk:
                        links_conhecidos.add(lnk)
        except Exception as e:
            print(f"Aviso ao ler {ARQUIVO_DESCARTADOS}: {e}")

    titulos_veiculos_conhecidos = set() 
    dfs_existentes = []

    # 1. Carrega dados históricos existentes
    arquivos_historicos = glob.glob(os.path.join(DIR_DATA, 'clipping_*.csv'))
    for arq in arquivos_historicos:
        if 'clipping_geral.csv' in arq: continue
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
        except Exception as e:
            print(f"Aviso ao ler {arq}: {e}")

    df_existente = pd.concat(dfs_existentes, ignore_index=True) if dfs_existentes else pd.DataFrame()

    # 2. Gera os Brackets de Anos de 2008 a 2026
    anos = list(range(2008, datetime.now().year + 1))
    brackets = []
    
    for a in anos:
        if a == 2008:
            start_date = '2008-12-29'
            end_date = '2009-12-31'
        else:
            start_date = f'{a}-01-01'
            end_date = f'{a}-12-31' if a < datetime.now().year else datetime.now().strftime('%Y-%m-%d')
        brackets.append((start_date, end_date))

    # 3. Queries principais
    query_templates = [
        # Query 1: Termos diretos do IF Baiano
        '("IF Baiano" OR "IFBAIANO" OR "IF-Baiano" OR "Instituto Federal Baiano") after:{start} before:{end}',
        
        # Query 2: Erros (IFBA) em cidades exclusivas
        '(("IFBA" OR "Instituto Federal da Bahia") AND ("Alagoinhas" OR "Bom Jesus da Lapa" OR "Catu" OR "Governador Mangabeira" OR "Guanambi" OR "Itaberaba" OR "Itapetinga" OR "Santa Inês" OR "Senhor do Bonfim" OR "Serrinha" OR "Teixeira de Freitas" OR "Uruçuca" OR "Xique-Xique" OR "Santo Estêvão" OR "Ribeira do Pombal" OR "Remanso" OR "Ruy Barbosa")) after:{start} before:{end}'
    ]

    clipping_coletado = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    # 4. Executa a varredura por ano
    for start, end in brackets:
        print(f"\n -> Escaneando período: {start} até {end}...")
        
        for q_tpl in query_templates:
            q_text = q_tpl.format(start=start, end=end)
            q_encoded = urllib.parse.quote_plus(q_text)
            
            # Usando o motor de busca RSS do Google News
            url_rss = f'https://news.google.com/rss/search?q={q_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419'
            
            try:
                response = requests.get(url_rss, headers=headers, timeout=20)
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    items = root.findall('./channel/item')
                    print(f"    - Encontrados {len(items)} registros via RSS.")
                    
                    for item in items:
                        link_original = item.find('link').text
                        if link_original in links_conhecidos: continue
                        
                        link_direto = resolver_url_direta(link_original)
                        if link_direto in links_conhecidos: continue
                        
                        titulo_completo = item.find('title').text or 'Sem Título'
                        veiculo = "Mídia Externa"
                        source_tag = item.find('source')
                        if source_tag is not None and source_tag.text:
                            veiculo = html.unescape(source_tag.text)
                            if ' - ' in titulo_completo and veiculo in titulo_completo:
                                titulo_completo = titulo_completo.rsplit(' - ', 1)[0]
                            titulo = html.unescape(titulo_completo)
                        else:
                            if ' - ' in titulo_completo:
                                partes = titulo_completo.rsplit(' - ', 1)
                                titulo = html.unescape(partes[0].strip())
                                veiculo = html.unescape(partes[1].strip())
                            else:
                                titulo = html.unescape(titulo_completo)

                        chave_nova = f"{titulo.strip().lower()}|{veiculo.strip().lower()}"
                        if chave_nova in titulos_veiculos_conhecidos: continue

                        data_pub = padronizar_data(item.find('pubDate').text)
                        
                        clipping_coletado.append({
                            'data': data_pub,
                            'assunto': titulo,
                            'veiculo': veiculo,
                            'link': link_direto,
                            'eixo_institucional': classificar_eixo(titulo),
                            'abrangencia': classificar_abrangencia(veiculo),
                            'campus': classificar_campus(titulo, veiculo)
                        })
                        
                        links_conhecidos.add(link_direto)
                        titulos_veiculos_conhecidos.add(chave_nova)
                else:
                    print(f"    X Erro HTTP ao buscar RSS ({response.status_code})")
                
                # Atraso rápido entre as requisições
                time.sleep(0.5)
            except Exception as e:
                print(f"    X Falha ao processar RSS: {e}")
                time.sleep(1)

    dominios_alvo = [
        # Oficiais
        "mec.gov.br", "portal.mec.gov.br", "gov.br", "planalto.gov.br", "conif.org.br",
        # Grandes portais da Bahia
        "atarde.com.br", "correio24horas.com.br", "bnews.com.br", "bahianoticias.com.br", "ibahia.com",
        # Portais Locais/Regionais das cidades do IF Baiano
        "portallapaoeste.com.br", "bomjesusdalapanoticias.com.br", "centraldalapa.com", "rbjfm.com.br",
        "agenciasertao.com", "iguanambi.com.br", "ivansilvanoticia.com.br", "blogdoeloiltoncajuhy.com.br",
        "clebervieiranews.com.br", "nettomaravilha.com.br", "teixeiranews.com.br", "bahiaextremosul.com.br",
        "liberdadenews.com.br", "sulbahianews.com.br", "seligaalagoinhas.com.br", "alta-pressao.com",
        "apoonline.com.br", "seabrahoje.com.br", "jornaldachapada.com.br", "valencaagora.com.br",
        "catunoticias.com.br", "itapetingaagora.com.br", "blogdomarcosfrahm.com", "vozdocampo.com.br",
        "pimenta.blog.br", "portalalerta.com.br", "remansonoticias.com.br", "ruybarbosanoticias.com.br"
    ]
    
    print("\n -> Iniciando varredura direcionada em portais parceiros e locais...")
    for dom in dominios_alvo:
        print(f"    Buscando no site: {dom}...")
        # Query unificada por domínio
        q_text = f'("IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano" OR "IFBA" OR "Instituto Federal da Bahia") site:{dom} after:2008-12-29'
        q_encoded = urllib.parse.quote_plus(q_text)
        url_rss = f'https://news.google.com/rss/search?q={q_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        
        try:
            response = requests.get(url_rss, headers=headers, timeout=20)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall('./channel/item')
                print(f"      - Encontrados {len(items)} registros no site {dom}.")
                
                for item in items:
                    link_original = item.find('link').text
                    if link_original in links_conhecidos: continue
                    
                    link_direto = resolver_url_direta(link_original)
                    if link_direto in links_conhecidos: continue
                    
                    titulo_completo = item.find('title').text or 'Sem Título'
                    veiculo = dom
                    source_tag = item.find('source')
                    if source_tag is not None and source_tag.text:
                        veiculo = html.unescape(source_tag.text)
                        if ' - ' in titulo_completo and veiculo in titulo_completo:
                            titulo_completo = titulo_completo.rsplit(' - ', 1)[0]
                        titulo = html.unescape(titulo_completo)
                    else:
                        if ' - ' in titulo_completo:
                            partes = titulo_completo.rsplit(' - ', 1)
                            titulo = html.unescape(partes[0].strip())
                            veiculo = html.unescape(partes[1].strip())
                        else:
                            titulo = html.unescape(titulo_completo)

                    chave_nova = f"{titulo.strip().lower()}|{veiculo.strip().lower()}"
                    if chave_nova in titulos_veiculos_conhecidos: continue

                    data_pub = padronizar_data(item.find('pubDate').text)
                    
                    clipping_coletado.append({
                        'data': data_pub,
                        'assunto': titulo,
                        'veiculo': veiculo,
                        'link': link_direto,
                        'eixo_institucional': classificar_eixo(titulo),
                        'abrangencia': classificar_abrangencia(veiculo),
                        'campus': classificar_campus(titulo, veiculo)
                    })
                    
                    links_conhecidos.add(link_direto)
                    titulos_veiculos_conhecidos.add(chave_nova)
            else:
                print(f"      X Erro HTTP ao buscar site {dom} ({response.status_code})")
            
            time.sleep(0.3)
        except Exception as e:
            print(f"      X Falha ao processar site {dom}: {e}")

    # 5. Consolida e gera os arquivos finais
    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente
    
    if not df_final.empty:
        df_final['assunto'] = df_final['assunto'].astype(str).str.strip()
        df_final['veiculo'] = df_final['veiculo'].astype(str).str.strip()
        
        # Remove duplicatas
        df_final = df_final.drop_duplicates(subset=['link'], keep='first')
        df_final['tmp_key'] = df_final['assunto'].str.lower() + df_final['veiculo'].str.lower()
        df_final = df_final.drop_duplicates(subset=['tmp_key'], keep='first').drop(columns=['tmp_key'])
        
        # Atualiza classificações
        df_final['eixo_institucional'] = df_final['assunto'].apply(classificar_eixo)
        df_final['abrangencia'] = df_final['veiculo'].apply(classificar_abrangencia)
        df_final['campus'] = df_final.apply(lambda row: classificar_campus(row['assunto'], row['veiculo']), axis=1)
        
        # Filtra registros por relevância (remove ruídos e notícias legítimas do IFBA)
        if not df_final.empty:
            df_final['valido'] = df_final.apply(lambda r: e_valido_baiano(r['assunto'], r['campus']), axis=1)
            
            # Identifica e salva novos descartados
            df_descartados = df_final[~df_final['valido']]
            if not df_descartados.empty:
                novos_descartados = df_descartados['link'].dropna().unique().tolist()
                if novos_descartados:
                    try:
                        with open(ARQUIVO_DESCARTADOS, 'a', encoding='utf-8') as f:
                            for l in novos_descartados:
                                f.write(l + '\n')
                    except Exception as e:
                        print(f"Erro ao salvar links descartados: {e}")
                        
            df_final = df_final[df_final['valido']].drop(columns=['valido'])
        
        df_final['data'] = df_final['data'].astype(str)
        df_final['ano_num'] = df_final['data'].apply(lambda x: int(x[:4]) if len(x) >= 4 else 0)

        def definir_arquivo(data_str):
            try:
                ano = int(str(data_str)[:4])
                return 'clipping_ate_2021.csv' if ano <= 2021 else f'clipping_{ano}.csv'
            except: return 'clipping_extra.csv'

        df_final['arquivo_destino'] = df_final['data'].apply(definir_arquivo)
        
        # Stats por Ano e Geral
        stats_por_ano = {}
        contagem_por_ano_real = df_final['ano_num'].value_counts().to_dict()
        
        caminho_geral = os.path.join(DIR_DATA, 'clipping_geral.csv')
        df_final.sort_values(by=['data'], ascending=False).drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho_geral, index=False, encoding='utf-8-sig')

        def gerar_stats_dict(df, key_name):
            ano_ref = datetime.now().year if key_name == 'geral' else (2021 if key_name == 'ate_2021' else int(key_name))
            historico = []
            for a in range(ano_ref, 2011, -1):
                if a in contagem_por_ano_real:
                    historico.append({"ano": a, "total": int(contagem_por_ano_real[a])})
            
            return {
                "total": len(df),
                "eixos": df['eixo_institucional'].value_counts().to_dict(),
                "abrangencia": df['abrangencia'].value_counts().to_dict(),
                "top_veiculos": df['veiculo'].value_counts().head(10).to_dict(),
                "meses": df['data'].str[5:7].value_counts().to_dict(),
                "campuses": df['campus'].value_counts().to_dict(),
                "historico": historico
            }

        # Stats Geral
        stats_por_ano['geral'] = gerar_stats_dict(df_final, 'geral')

        # Stats por arquivo
        for arquivo, df_grupo in df_final.groupby('arquivo_destino'):
            ano_key = arquivo.replace('clipping_', '').replace('.csv', '')
            # Ordena do mais recente para o mais antigo antes de salvar e gerar estatísticas
            df_grupo_sorted = df_grupo.sort_values(by=['data'], ascending=False)
            stats_por_ano[ano_key] = gerar_stats_dict(df_grupo_sorted, ano_key)
            caminho = os.path.join(DIR_DATA, arquivo)
            df_grupo_sorted.drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho, index=False, encoding='utf-8-sig')

        with open(ARQUIVO_STATS, 'w', encoding='utf-8') as f:
            json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)
        
        print(f"\nCarga inicial com RSS concluída com sucesso!")
        print(f"Tamanho final do banco de dados: {len(df_final)} registros.")
        print(f"Novas matérias capturadas e adicionadas: {len(df_novo)} registros.")

if __name__ == "__main__":
    processar_carga_inicial()
