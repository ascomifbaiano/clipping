import requests
import pandas as pd
import os
import html
import urllib3
import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CONFIGURAÇÕES E HEURÍSTICA
# ==========================================
ARQUIVO_CLIPPING = 'data/clipping.csv'

def padronizar_data(data_str, ano_referencia=str(datetime.now().year)):
    if not data_str: return f"{ano_referencia}-01-01"
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

    # Tenta RFC 2822 (pubDate do RSS)
    try:
        dt = parsedate_to_datetime(data_str)
        return dt.strftime('%Y-%m-%d')
    except: pass

    return f"{ano_referencia}-01-01"

def classificar_eixo(titulo):
    t = str(titulo).lower()
    # Prioridade para Gestão e RH
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
    return 'Imprensa Local'

def resolver_url_direta(url_rss):
    """Tenta extrair a URL real por trás do redirecionamento do Google/Bing"""
    try:
        # User agent para simular navegador e evitar bloqueios
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        # Apenas HEAD para ser rápido
        res = requests.head(url_rss, headers=headers, allow_redirects=True, timeout=5)
        return res.url
    except:
        return url_rss

# ==========================================
# 2. MOTOR DE CLIPPING
# ==========================================
def processar_clipping():
    print("Iniciando Motor de Clipping Inteligente...")
    links_conhecidos = set()
    df_existente = pd.DataFrame()

    # 1. Carrega base e corrige codificação
    if os.path.exists(ARQUIVO_CLIPPING):
        try:
            # Tenta ler com utf-8-sig para lidar com BOM de Excel
            df_existente = pd.read_csv(ARQUIVO_CLIPPING, encoding='utf-8-sig')
            print(f"Base histórica: {len(df_existente)} registros.")
            
            # Limpeza de encoding em colunas existentes (se houver lixo)
            for col in ['assunto', 'veiculo']:
                if col in df_existente.columns:
                    df_existente[col] = df_existente[col].apply(lambda x: str(x).encode('latin1').decode('utf-8') if isinstance(x, str) and 'Ã' in x else x)
            
            links_conhecidos = set(df_existente['link'].dropna().tolist())
        except Exception as e:
            print(f"Aviso ao ler base: {e}")

    # 2. Busca novas notícias
    clipping_coletado = []
    fontes_pesquisa = [
        ("Google News", 'https://news.google.com/rss/search?q="IF+Baiano"&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
        ("Bing News", 'https://www.bing.com/news/search?q="IF+Baiano"&format=rss')
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    
    for nome_motor, url_rss in fontes_pesquisa:
        print(f" -> Varrendo {nome_motor}...")
        try:
            response = requests.get(url_rss, headers=headers, timeout=30)
            root = ET.fromstring(response.content)
            
            for item in root.findall('./channel/item'):
                link_original = item.find('link').text
                
                # Se já temos o link, pula
                if link_original in links_conhecidos: continue 
                
                print(f"    - Resolvendo: {link_original[:50]}...")
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

                data_pub = padronizar_data(item.find('pubDate').text)
                
                clipping_coletado.append({
                    'data': data_pub,
                    'assunto': titulo,
                    'veiculo': veiculo,
                    'link': link_direto,
                    'eixo_institucional': classificar_eixo(titulo),
                    'abrangencia': classificar_abrangencia(veiculo)
                })
                links_conhecidos.add(link_direto)
                time.sleep(0.5) # Pequena pausa para não ser bloqueado ao resolver URLs
                
        except Exception as e:
            print(f"   X Erro no motor {nome_motor}: {e}")

    # 3. Consolidação e Salvamento Seguro
    df_novo = pd.DataFrame(clipping_coletado)
    if not df_novo.empty:
        print(f"Novas notícias: {len(df_novo)}")
        df_final = pd.concat([df_novo, df_existente], ignore_index=True)
    else:
        df_final = df_existente
    
    if not df_final.empty:
        # Re-classificar tudo para garantir consistência com a nova heurística
        df_final['eixo_institucional'] = df_final['assunto'].apply(classificar_eixo)
        df_final['abrangencia'] = df_final['veiculo'].apply(classificar_abrangencia)
        
        # Limpeza Final
        df_final = df_final.drop_duplicates(subset=['link'], keep='first')
        df_final = df_final.sort_values(by=['data'], ascending=False)
        
        os.makedirs(os.path.dirname(ARQUIVO_CLIPPING), exist_ok=True)
        # Salva com encoding UTF-8 real para evitar lixo
        df_final.to_csv(ARQUIVO_CLIPPING, index=False, encoding='utf-8-sig')
        print(f"Sucesso! Total: {len(df_final)} registros.")

if __name__ == "__main__":
    processar_clipping()

if __name__ == "__main__":
    processar_clipping()
