import os
import glob
import json
import pandas as pd
from datetime import datetime

DIR_DATA = 'data'
ARQUIVO_STATS = os.path.join(DIR_DATA, 'stats.json')

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
    t = str(titulo).lower() if pd.notna(titulo) else ""
    c = str(campus) if pd.notna(campus) else "Geral / Não Especificado"

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

def limpar_e_reconstruir():
    print("Iniciando Limpeza Retroativa da Base de Dados...")
    os.makedirs(DIR_DATA, exist_ok=True)

    arquivos = glob.glob(os.path.join(DIR_DATA, 'clipping_*.csv'))
    dfs_limpos = []

    for arq in arquivos:
        nome_base = os.path.basename(arq)
        if nome_base == 'clipping_geral.csv': continue

        print(f"  Processando {nome_base}...")
        try:
            df = pd.read_csv(arq, encoding='utf-8-sig')
            if df.empty: continue

            # Filtra registros válidos
            df['valido'] = df.apply(lambda r: e_valido_baiano(r['assunto'], r['campus']), axis=1)
            df_valido = df[df['valido']].drop(columns=['valido'])

            print(f"    - Original: {len(df)} | Limpo: {len(df_valido)} (Descartados: {len(df) - len(df_valido)})")

            if not df_valido.empty:
                # Salva o arquivo limpo sobrescrevendo o original
                df_valido.to_csv(arq, index=False, encoding='utf-8-sig')
                dfs_limpos.append(df_valido)
            else:
                # Se ficou vazio, removemos o arquivo
                print(f"    - Removendo {nome_base} pois não restaram registros válidos.")
                os.remove(arq)
        except Exception as e:
            print(f"    X Erro ao processar {nome_base}: {e}")

    if not dfs_limpos:
        print("Nenhum registro restou após a limpeza!")
        return

    df_geral = pd.concat(dfs_limpos, ignore_index=True)
    df_geral['data'] = df_geral['data'].astype(str)
    df_geral['ano_num'] = df_geral['data'].apply(lambda x: int(x[:4]) if len(x) >= 4 else 0)

    # Salva o geral consolidadado
    caminho_geral = os.path.join(DIR_DATA, 'clipping_geral.csv')
    df_geral_sorted = df_geral.sort_values(by=['data'], ascending=False)
    df_geral_sorted.drop(columns=['ano_num']).to_csv(caminho_geral, index=False, encoding='utf-8-sig')

    # Estatísticas por Ano e Geral
    stats_por_ano = {}
    contagem_por_ano_real = df_geral['ano_num'].value_counts().to_dict()

    def gerar_stats_dict(df_grupo, key_name):
        ano_ref = datetime.now().year if key_name == 'geral' else (2021 if key_name == 'ate_2021' else int(key_name))
        historico = []
        for a in range(ano_ref, 2011, -1):
            if a in contagem_por_ano_real:
                historico.append({"ano": a, "total": int(contagem_por_ano_real[a])})

        return {
            "total": len(df_grupo),
            "eixos": df_grupo['eixo_institucional'].value_counts().to_dict(),
            "abrangencia": df_grupo['abrangencia'].value_counts().to_dict(),
            "top_veiculos": df_grupo['veiculo'].value_counts().head(10).to_dict(),
            "meses": df_grupo['data'].str[5:7].value_counts().to_dict(),
            "campuses": df_grupo['campus'].value_counts().to_dict(),
            "historico": historico
        }

    # Stats Geral
    stats_por_ano['geral'] = gerar_stats_dict(df_geral_sorted, 'geral')

    # Stats individuais por ano
    for arq in arquivos:
        nome_base = os.path.basename(arq)
        if nome_base == 'clipping_geral.csv': continue
        if not os.path.exists(arq): continue

        df_grupo = pd.read_csv(arq, encoding='utf-8-sig')
        df_grupo_sorted = df_grupo.sort_values(by=['data'], ascending=False)
        ano_key = nome_base.replace('clipping_', '').replace('.csv', '')
        stats_por_ano[ano_key] = gerar_stats_dict(df_grupo_sorted, ano_key)

    with open(ARQUIVO_STATS, 'w', encoding='utf-8') as f:
        json.dump(stats_por_ano, f, ensure_ascii=False, indent=2)

    print(f"\nLimpeza completa! CSV Geral e stats.json atualizados.")
    print(f"Total final da base: {len(df_geral_sorted)} registros (redução significativa de ruído).")

if __name__ == "__main__":
    limpar_e_reconstruir()
