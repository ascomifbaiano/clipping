import os
import time
import glob
import html
import urllib.parse
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import urllib3
from datetime import datetime
from clipping_utils import (
    DIR_DATA, padronizar_data, classificar_eixo, 
    classificar_abrangencia, classificar_campus, resolver_url_direta, salvar_e_gerar_stats, validar_noticia
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def processar_carga_inicial():
    print("Iniciando Carga Inicial Avançada (Ponytail Mode) via RSS Brackets (2008 - Hoje)...")
    os.makedirs(DIR_DATA, exist_ok=True)

    links_conhecidos = set()
    titulos_veiculos_conhecidos = set() 
    dfs_existentes = []

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

    anos = list(range(2008, datetime.now().year + 1))
    brackets = []
    for a in anos:
        start_date = '2008-12-29' if a == 2008 else f'{a}-01-01'
        end_date = f'{a}-12-31' if a < datetime.now().year else datetime.now().strftime('%Y-%m-%d')
        brackets.append((start_date, end_date))

    query_templates = [
        '("IF Baiano" OR "IFBAIANO" OR "IF-Baiano" OR "Instituto Federal Baiano") after:{start} before:{end}',
        '("IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano") site:edu.br after:{start} before:{end}',
        '(("IFBA" OR "Instituto Federal da Bahia") AND ("Alagoinhas" OR "Bom Jesus da Lapa" OR "Catu" OR "Governador Mangabeira" OR "Guanambi" OR "Itaberaba" OR "Itapetinga" OR "Santa Inês" OR "Senhor do Bonfim" OR "Serrinha" OR "Teixeira de Freitas" OR "Uruçuca" OR "Xique-Xique" OR "Santo Estêvão" OR "Ribeira do Pombal" OR "Remanso" OR "Ruy Barbosa")) after:{start} before:{end}'
    ]

    clipping_coletado = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}

    for start, end in brackets:
        print(f"\n -> Escaneando período: {start} até {end}...")
        for q_tpl in query_templates:
            q_text = q_tpl.format(start=start, end=end)
            q_encoded = urllib.parse.quote_plus(q_text)
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

                        # Ignorar notícias vindas do próprio portal do IF Baiano (evitar auto-clipping)
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
                        if chave_nova in titulos_veiculos_conhecidos: continue

                        # Validar se a notícia é realmente sobre o IF Baiano (ou confusão válida com o IFBA)
                        if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=True):
                            continue

                        data_pub = padronizar_data(item.find('pubDate').text)
                        clipping_coletado.append({
                            'data': data_pub, 'assunto': titulo, 'veiculo': veiculo, 'link': link_direto,
                            'eixo_institucional': classificar_eixo(titulo), 'abrangencia': classificar_abrangencia(veiculo),
                            'campus': classificar_campus(titulo, veiculo)
                        })
                        links_conhecidos.add(link_direto)
                        titulos_veiculos_conhecidos.add(chave_nova)
                        time.sleep(0.5)
            except Exception as e:
                print(f"    X Falha ao processar RSS: {e}")

    dominios_alvo = [
        "mec.gov.br", "portal.mec.gov.br", "gov.br", "planalto.gov.br", "conif.org.br",
        "ufba.br", "ifba.edu.br", "uneb.br", "uesb.br", "ufrb.edu.br", "ufob.edu.br", 
        "univasf.edu.br", "ifsc.edu.br", "ifsp.edu.br", "ifsertao-pe.edu.br", "ifpe.edu.br",
        "atarde.com.br", "correio24horas.com.br", "bnews.com.br", "bahianoticias.com.br", "ibahia.com",
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
        q_text = f'("IF Baiano" OR "IFBAIANO" OR "Instituto Federal Baiano" OR "IFBA" OR "Instituto Federal da Bahia") site:{dom} after:2008-12-29'
        q_encoded = urllib.parse.quote_plus(q_text)
        url_rss = f'https://news.google.com/rss/search?q={q_encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419'
        try:
            response = requests.get(url_rss, headers=headers, timeout=20)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for item in root.findall('./channel/item'):
                    link_original = item.find('link').text
                    if link_original in links_conhecidos: continue
                    link_direto = resolver_url_direta(link_original)
                    if link_direto in links_conhecidos: continue

                    # Ignorar notícias vindas do próprio portal do IF Baiano (evitar auto-clipping)
                    if 'ifbaiano.edu.br' in link_direto:
                        continue

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

                    # Validar se a notícia é realmente sobre o IF Baiano (ou confusão válida com o IFBA)
                    if not validar_noticia(titulo, veiculo, link_direto, puxar_conteudo=True):
                        continue

                    data_pub = padronizar_data(item.find('pubDate').text)
                    clipping_coletado.append({
                        'data': data_pub, 'assunto': titulo, 'veiculo': veiculo, 'link': link_direto,
                        'eixo_institucional': classificar_eixo(titulo), 'abrangencia': classificar_abrangencia(veiculo),
                        'campus': classificar_campus(titulo, veiculo)
                    })
                    links_conhecidos.add(link_direto)
                    titulos_veiculos_conhecidos.add(chave_nova)
                    time.sleep(0.3)
        except Exception as e:
            print(f"      X Falha ao processar site {dom}: {e}")

    df_novo = pd.DataFrame(clipping_coletado)
    df_final = pd.concat([df_novo, df_existente], ignore_index=True) if not df_novo.empty else df_existente

    salvar_e_gerar_stats(df_final)
    print(f"\nCarga inicial concluída com sucesso! Total: {len(df_final)} registros.")

if __name__ == "__main__":
    processar_carga_inicial()
