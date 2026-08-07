import os
import glob
import time
import html
import urllib.parse
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import urllib3
from clipping_utils import (
    DIR_DATA, padronizar_data, classificar_eixo, 
    classificar_abrangencia, resolver_url_direta, salvar_e_gerar_stats, validar_noticia
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ARQUIVO_ANTIGO = os.path.join(DIR_DATA, 'clipping.csv')

def processar_clipping():
    print("Iniciando Motor de Clipping Inteligente (Ponytail Fast Mode)...", flush=True)
    os.makedirs(DIR_DATA, exist_ok=True)

    links_conhecidos = set()
    titulos_veiculos_conhecidos = set() 
    dfs_existentes = []

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
            print(f"Aviso ao ler {arq}: {e}", flush=True)

    df_existente = pd.concat(dfs_existentes, ignore_index=True) if dfs_existentes else pd.DataFrame()

    termos_principais = [
        '"IF Baiano"', '"IFBAIANO"', '"IF-Baiano"', '"IF.Baiano"', '"IF_Baiano"',
        '"Instituto Federal Baiano"', '"Instituto Federal de Educação, Ciência e Tecnologia Baiano"',
        '"Instituto Federal de Educação Ciência e Tecnologia Baiano"', '"IFBaiana"', '"IF Baiana"',
        '"Instituto Federal Baiana"', '"Federal Baiano"'
    ]
    query_principal = " OR ".join(termos_principais)

    cidades_exclusivas = [
        "Alagoinhas", "Bom Jesus da Lapa", "Catu", "Governador Mangabeira", 
        "Guanambi", "Itaberaba", "Itapetinga", "Santa Inês", "Senhor do Bonfim", 
        "Serrinha", "Teixeira de Freitas", "Uruçuca", "Xique-Xique", 
        "Santo Estêvão", "Ribeira do Pombal", "Remanso", "Ruy Barbosa"
    ]
    termos_erro = ['"IFBA"', '"Instituto Federal da Bahia"']
    cidades_quoted = [f'"{c}"' for c in cidades_exclusivas]
    query_erro = f"({' OR '.join(termos_erro)}) AND ({' OR '.join(cidades_quoted)})"

    # Reforço de busca para qualquer menção em domínios de instituições de ensino (.edu.br) e portais governamentais (.gov.br)
    query_academic = '("IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano") (site:edu.br OR site:gov.br OR site:conif.org.br)'

    fontes_pesquisa = [
        ("Google News Principal", f'https://news.google.com/rss/search?q={urllib.parse.quote_plus(query_principal)}&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
        ("Bing News Principal", f'https://www.bing.com/news/search?q={urllib.parse.quote_plus(query_principal)}&format=rss'),
        ("Google News Erros Mídia", f'https://news.google.com/rss/search?q={urllib.parse.quote_plus(query_erro)}&hl=pt-BR&gl=BR&ceid=BR:pt-419'),
        ("Google News Acadêmico e Gov", f'https://news.google.com/rss/search?q={urllib.parse.quote_plus(query_academic)}&hl=pt-BR&gl=BR&ceid=BR:pt-419')
    ]

    clipping_coletado = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    for nome_motor, url_rss in fontes_pesquisa:
        print(f" -> Varrendo {nome_motor}...", flush=True)
        try:
            response = requests.get(url_rss, headers=headers, timeout=10)
            if response.status_code != 200:
                continue
            root = ET.fromstring(response.content)
            for item in root.findall('./channel/item'):
                link_original = item.find('link').text or ''
                if not link_original or link_original in links_conhecidos:
                    continue 

                link_direto = resolver_url_direta(link_original)
                if link_direto in links_conhecidos:
                    continue

                if 'ifbaiano.edu.br' in link_direto:
                    continue

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
                if chave_nova in titulos_veiculos_conhecidos:
                    continue

                # Valida se a notícia é sobre o IF Baiano (usando scraping profundo apenas em casos ambíguos)
                if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=True):
                    continue

                data_pub = padronizar_data(item.find('pubDate').text)
                clipping_coletado.append({
                    'data': data_pub, 'assunto': titulo, 'veiculo': veiculo, 'link': link_direto,
                    'eixo_institucional': classificar_eixo(titulo), 'abrangencia': classificar_abrangencia(veiculo)
                })
                links_conhecidos.add(link_direto)
                titulos_veiculos_conhecidos.add(chave_nova)
        except Exception as e:
            print(f"   X Erro no motor {nome_motor}: {e}", flush=True)

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    salvar_e_gerar_stats(df_final)
    if os.path.exists(ARQUIVO_ANTIGO):
        os.remove(ARQUIVO_ANTIGO)

if __name__ == "__main__":
    processar_clipping()
