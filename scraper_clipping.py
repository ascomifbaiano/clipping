import requests
import pandas as pd
import os
import html
import urllib3
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CONFIGURAÇÕES E HEURÍSTICA
# ==========================================
ARQUIVO_CLIPPING = 'data/clipping.csv'

def padronizar_data(data_str, ano_referencia=str(datetime.now().year)):
    d_str = str(data_str).strip().lower()
    
    meses = {'janeiro':'01','fevereiro':'02','março':'03','marco':'03','abril':'04','maio':'05','junho':'06',
             'julho':'07','agosto':'08','setembro':'09','outubro':'10','novembro':'11','dezembro':'12'}
    for pt, num in meses.items():
        d_str = d_str.replace(pt, num)
        
    # Tenta YYYY-MM-DD
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', d_str)
    if match: return match.group(0)

    # Tenta DD/MM/YYYY ou DD-MM-YYYY
    match = re.search(r'(\d{2})[-/](\d{2})[-/](\d{2,4})', d_str)
    if match:
        d, m, y = match.groups()
        if len(y) == 2: y = '20' + y
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    # Tenta "DD de Mes de YYYY"
    match = re.search(r'(\d{1,2})\s+(?:de\s+)?(\d{2})\s+(?:de\s+)?(\d{4})', d_str)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

    # Tenta MM/YYYY
    match = re.search(r'(\d{2})[-/](\d{4})', d_str)
    if match:
        m, y = match.groups()
        return f"{y}-{m.zfill(2)}-01"

    # Tenta DD/MM (assume ano de referência ou atual)
    match = re.search(r'(\d{2})[-/](\d{2})', d_str)
    if match:
        d, m = match.groups()
        return f"{ano_referencia}-{m.zfill(2)}-{d.zfill(2)}"

    return f"{ano_referencia}-01-01"

def classificar_eixo(titulo):
    t = str(titulo).lower()
    if any(w in t for w in ['sisu', 'prosel', 'vaga', 'curso', 'graduação', 'especialização', 'técnico', 'matrícula', 'ensino', 'aluno', 'estudante', 'aula', 'partiu if']): return 'Ensino'
    if any(w in t for w in ['pesquisa', 'ciência', 'tecnologia', 'inovação', 'patente', 'cnpq', 'artigo', 'fapesb', 'científica', 'pesquisador', 'desenvolve', 'biofilme']): return 'Pesquisa'
    if any(w in t for w in ['extensão', 'comunidade', 'projeto', 'feira', 'evento', 'seminário', 'agricultura familiar', 'mulheres mil', 'oficina', 'tenda', 'jornada']): return 'Extensão'
    return 'Institucional'

def classificar_abrangencia(veiculo):
    v = str(veiculo).lower()
    if any(w in v for w in ['g1', 'cnn', 'r7', 'terra', 'estadao', 'msn', 'uol', 'record', 'band', 'catraca livre', 'o tempo']): return 'Imprensa (Nacional)'
    if any(w in v for w in ['a tarde', 'correio', 'bnews', 'aratu', 'ibahia', 'tribuna da bahia', 'bahia notícias', 'farol da bahia', 'bahia.ba', 'bahia já']): return 'Imprensa Regional (Bahia)'
    if any(w in v for w in ['prefeitura', 'gov.br', 'conif', 'mec', 'if baiano', 'ufba', 'uesb', 'ifba', 'adab', 'codevasf', 'embrapa']): return 'Institucional / Governamental'
    if any(w in v for w in ['concurso', 'pci', 'qconcursos', 'ache', 'direção', 'estrategia', 'educação', 'agro', 'rural', 'defesa', 'tecnologia', 'focus', 'gran', 'vestibular']): return 'Especializados (Nichos)'
    return 'Imprensa Local'

# ==========================================
# 2. MOTOR DE CLIPPING (Google + Bing + Base Manual)
# ==========================================
def processar_clipping():
    print("Iniciando Motor de Clipping Externo...")
    links_conhecidos = set()
    df_existente = pd.DataFrame()

    # 1. Carrega e retro-alimenta a base manual
    if os.path.exists(ARQUIVO_CLIPPING):
        try:
            df_existente = pd.read_csv(ARQUIVO_CLIPPING, on_bad_lines='skip')
            print(f"Base histórica encontrada com {len(df_existente)} registros. Aplicando lavagem de dados...")
            
            if 'data' in df_existente.columns:
                df_existente['data'] = df_existente['data'].apply(lambda x: padronizar_data(x))
            if 'eixo_institucional' not in df_existente.columns:
                df_existente['eixo_institucional'] = df_existente['assunto'].apply(classificar_eixo)
            if 'abrangencia' not in df_existente.columns:
                df_existente['abrangencia'] = df_existente['veiculo'].apply(classificar_abrangencia)
                
            links_conhecidos = set(df_existente['link'].dropna().tolist())
        except Exception as e:
            print(f"Aviso: Erro ao ler CSV. {e}")

    # 2. Caça novas notícias
    clipping_coletado = []
    fontes_pesquisa = [
        ("Google News", 'https://news.google.com/rss/search?q="IF+Baiano"&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
        ("Bing News", 'https://www.bing.com/news/search?q="IF+Baiano"&format=rss')
    ]
    
    for nome_motor, url_rss in fontes_pesquisa:
        print(f" -> Varrendo {nome_motor}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
            response = requests.get(url_rss, headers=headers, timeout=30)
            root = ET.fromstring(response.content)
            
            for item in root.findall('./channel/item'):
                link = item.find('link').text
                if link in links_conhecidos: continue 
                
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

                data_pub = padronizar_data(item.find('pubDate').text)
                
                clipping_coletado.append({
                    'data': data_pub,
                    'assunto': titulo,
                    'veiculo': veiculo,
                    'link': link,
                    'eixo_institucional': classificar_eixo(titulo),
                    'abrangencia': classificar_abrangencia(veiculo)
                })
                links_conhecidos.add(link) 
        except Exception as e:
            print(f"   X Erro ao buscar no {nome_motor}: {e}")

    # 3. Consolidação
    df_novo = pd.DataFrame(clipping_coletado)
    if not df_novo.empty:
        print(f"Encontradas {len(df_novo)} novas publicações na mídia!")
        df_final = pd.concat([df_novo, df_existente], ignore_index=True)
    else:
        print("Nenhuma notícia nova na mídia hoje.")
        df_final = df_existente
    
    if not df_final.empty:
        os.makedirs(os.path.dirname(ARQUIVO_CLIPPING), exist_ok=True)
        # Limpeza final de duplicatas e ordenação
        df_final = df_final.drop_duplicates(subset=['link'], keep='first')
        df_final.sort_values(by=['data'], ascending=[False]).to_csv(ARQUIVO_CLIPPING, index=False, encoding='utf-8')
        print(f"Acervo de Clipping Consolidado: {len(df_final)} registros totais.")

if __name__ == "__main__":
    processar_clipping()
