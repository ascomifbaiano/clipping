import requests
import pandas as pd
import os
import html
import urllib3
import xml.etree.ElementTree as ET
import re
import time
import json
from datetime import datetime
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CONFIGURAÇÕES E HEURÍSTICA
# ==========================================
DIR_DATA = 'data'
ARQUIVO_ANTIGO = os.path.join(DIR_DATA, 'clipping.csv')
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
    
    # Heurística para portais locais das cidades do IF Baiano e portais de notícias conhecidos
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

# ==========================================
# 2. MOTOR DE CLIPPING
# ==========================================
def processar_clipping():
    print("Iniciando Motor de Clipping Inteligente...")
    os.makedirs(DIR_DATA, exist_ok=True)
    
    links_conhecidos = set()
    titulos_veiculos_conhecidos = set() 
    dfs_existentes = []

    import glob
    arquivos_historicos = glob.glob(os.path.join(DIR_DATA, 'clipping_*.csv'))
    if os.path.exists(ARQUIVO_ANTIGO):
        arquivos_historicos.append(ARQUIVO_ANTIGO)

    for arq in arquivos_historicos:
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

    import urllib.parse
    
    # 1. Termos principais e variações do IF Baiano (inclusive variações comuns de gênero/grafia)
    termos_principais = [
        '"IF Baiano"',
        '"IFBAIANO"',
        '"IF-Baiano"',
        '"IF.Baiano"',
        '"IF_Baiano"',
        '"Instituto Federal Baiano"',
        '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
        '"Instituto Federal de Educação Ciência e Tecnologia Baiano"',
        '"IFBaiana"',
        '"IF Baiana"',
        '"Instituto Federal Baiana"',
        '"Federal Baiano"'
    ]
    query_principal = " OR ".join(termos_principais)

    # 2. Menções errôneas (IFBA ou Instituto Federal da Bahia) nas cidades do IF Baiano (evitando falsos positivos)
    # Valença foi removida desta lista específica pois possui campi de ambas as instituições.
    cidades_exclusivas = [
        "Alagoinhas", "Bom Jesus da Lapa", "Catu", "Governador Mangabeira", 
        "Guanambi", "Itaberaba", "Itapetinga", "Santa Inês", "Senhor do Bonfim", 
        "Serrinha", "Teixeira de Freitas", "Uruçuca", "Xique-Xique", 
        "Santo Estêvão", "Ribeira do Pombal", "Remanso", "Ruy Barbosa"
    ]
    termos_erro = [
        '"IFBA"',
        '"Instituto Federal da Bahia"'
    ]
    cidades_quoted = [f'"{c}"' for c in cidades_exclusivas]
    query_erro = f"({' OR '.join(termos_erro)}) AND ({' OR '.join(cidades_quoted)})"

    queries = [query_principal, query_erro]
    
    clipping_coletado = []
    fontes_pesquisa = []
    
    for q_text in queries:
        q_encoded = urllib.parse.quote_plus(q_text)
        fontes_pesquisa.append(("Google News", f'https://news.google.com/rss/search?q={q_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419'))
        fontes_pesquisa.append(("Bing News", f'https://www.bing.com/news/search?q={q_encoded}&format=rss'))

    # Adiciona varredura direta nos portais oficiais e parceiros chave diariamente
    dominios_alvo = [
        "mec.gov.br", "portal.mec.gov.br", "gov.br", "planalto.gov.br", "conif.org.br",
        "portallapaoeste.com.br", "bomjesusdalapanoticias.com.br", "centraldalapa.com",
        "agenciasertao.com", "iguanambi.com.br", "blogdoeloiltoncajuhy.com.br",
        "nettomaravilha.com.br", "teixeiranews.com.br", "bahiaextremosul.com.br",
        "liberdadenews.com.br", "sulbahianews.com.br", "seligaalagoinhas.com.br",
        "alta-pressao.com", "valencaagora.com.br", "catunoticias.com.br",
        "itapetingaagora.com.br", "blogdomarcosfrahm.com", "portalalerta.com.br",
        "remansonoticias.com.br", "ruybarbosanoticias.com.br"
    ]
    for dom in dominios_alvo:
        q_text_dom = f'("IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano" OR "IFBA" OR "Instituto Federal da Bahia") site:{dom}'
        q_encoded_dom = urllib.parse.quote_plus(q_text_dom)
        fontes_pesquisa.append((f"Site {dom}", f'https://news.google.com/rss/search?q={q_encoded_dom}&hl=pt-BR&gl=BR&ceid=BR:pt-419'))
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    
    for nome_motor, url_rss in fontes_pesquisa:
        print(f" -> Varrendo {nome_motor}...")
        try:
            response = requests.get(url_rss, headers=headers, timeout=30)
            root = ET.fromstring(response.content)
            for item in root.findall('./channel/item'):
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
                    'data': data_pub, 'assunto': titulo, 'veiculo': veiculo, 'link': link_direto,
                    'eixo_institucional': classificar_eixo(titulo), 'abrangencia': classificar_abrangencia(veiculo)
                })
                links_conhecidos.add(link_direto)
                titulos_veiculos_conhecidos.add(chave_nova)
                time.sleep(0.5) 
        except Exception as e:
            print(f"   X Erro no motor {nome_motor}: {e}")

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente
    
    if not df_final.empty:
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
        
        # Stats por Ano e Geral
        stats_por_ano = {}
        contagem_por_ano_real = df_final['ano_num'].value_counts().to_dict()
        
        # Otimização: Salvar um CSV "Geral" para carregamento sob demanda
        caminho_geral = os.path.join(DIR_DATA, 'clipping_geral.csv')
        df_final.sort_values(by=['data'], ascending=False).drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho_geral, index=False, encoding='utf-8-sig')

        # Função auxiliar para gerar dict de stats
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
            stats_por_ano[ano_key] = gerar_stats_dict(df_grupo, ano_key)
            caminho = os.path.join(DIR_DATA, arquivo)
            df_grupo.drop(columns=['arquivo_destino', 'ano_num']).to_csv(caminho, index=False, encoding='utf-8-sig')

        with open(ARQUIVO_STATS, 'w', encoding='utf-8') as f:
            json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)
        
        print(f"Sucesso! Dados limpos, CSV Geral e Stats JSON atualizados em {DIR_DATA}/")
        
        if os.path.exists(ARQUIVO_ANTIGO):
            os.remove(ARQUIVO_ANTIGO)

if __name__ == "__main__":
    processar_clipping()
