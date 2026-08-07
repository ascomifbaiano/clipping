import os
import sys
import glob
import pandas as pd

# Adiciona o diretório atual do script ao path do sistema de forma portátil
DIR_CLIPPING = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
sys.path.append(DIR_CLIPPING)

from clipping_utils import validar_noticia, salvar_e_gerar_stats, DIR_DATA

def limpar_banco_clipping():
    path_data = os.path.join(DIR_CLIPPING, DIR_DATA)
    print(f"Buscando arquivos CSV em: {path_data}")

    arquivos_csv = glob.glob(os.path.join(path_data, 'clipping_*.csv'))
    if not arquivos_csv:
        print("Nenhum arquivo CSV localizado.")
        return

    df_geral_filtrado = []
    total_removidos_geral = 0

    for arq in arquivos_csv:
        nome_arq = os.path.basename(arq)
        if nome_arq == 'clipping_geral.csv':
            continue  # O geral será reconstruído a partir dos parciais

        try:
            df = pd.read_csv(arq, encoding='utf-8-sig')
            total_antes = len(df)

            if total_antes == 0:
                continue

            # Aplica o filtro de validação de notícia passando o link
            mascara_validas = df.apply(lambda row: validar_noticia(row['assunto'], row['veiculo'], row.get('link')), axis=1)
            df_limpo = df[mascara_validas].copy()
            total_depois = len(df_limpo)
            removidos = total_antes - total_depois
            total_removidos_geral += removidos

            print(f" -> {nome_arq}: {total_antes} registros -> {total_depois} registros ({removidos} registros inválidos removidos)")

            if total_depois > 0:
                df_geral_filtrado.append(df_limpo)
                df_limpo.to_csv(arq, index=False, encoding='utf-8-sig')
            else:
                df_limpo.to_csv(arq, index=False, encoding='utf-8-sig')

        except Exception as e:
            print(f"Erro ao processar {nome_arq}: {e}")

    # Regenera o clipping_geral.csv e as estatísticas do stats.json
    if df_geral_filtrado:
        df_final = pd.concat(df_geral_filtrado, ignore_index=True)
        print(f"\nRegenerando acervo geral com {len(df_final)} registros totais...")
        salvar_e_gerar_stats(df_final, dir_data=path_data)
        print(f"Saneamento concluído de forma bem-sucedida. Total removido: {total_removidos_geral}")
    else:
        print("\nNenhum registro restante nos arquivos parciais.")

if __name__ == '__main__':
    limpar_banco_clipping()
