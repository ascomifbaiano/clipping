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
    return 'Imprensa Local'

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
