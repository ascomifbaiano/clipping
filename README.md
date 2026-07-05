# 📰 Motor de Clipping Inteligente & Dashboard Analytics | IF Baiano

Sistema automatizado de busca, classificação, mineração e monitoramento de menções na imprensa para o **Instituto Federal de Educação, Ciência e Tecnologia Baiano (IF Baiano)**, acompanhado de um dashboard interativo em HTML5/JS com estatísticas históricas.

---

## 📌 Sobre a Aplicação
O Motor de Clipping Inteligente monitora diariamente matérias veiculadas na grande imprensa (Google News, Bing News), portais governamentais (MEC, CONIF, Planalto) e mídias regionais/locais de todas as cidades onde o IF Baiano possui *campus*. O sistema classifica as matérias automaticamente por eixos institucionais, abrangência de mídia e campus associado.

## ✨ Funcionalidades Principais
- 🔍 **Varredura Multi-Motor**: Coleta contínua de notícias via Google News RSS, Bing News RSS e raspagem direcionada em dezenas de portais parceiros da Bahia.
- 🏷️ **Classificação Heurística Automática**:
  - **Eixos Institucionais**: Gestão e RH, Ensino, Pesquisa, Extensão e Institucional.
  - **Abrangência**: Nacional, Regional (Bahia), Governamental, Especializada e Imprensa Local.
  - **Identificação de Campus**: Mapeamento inteligente por cidade ou unidade.
  - **Detecção de Erros da Imprensa (*Somos IF Baiano*)**: Algoritmo para identificar matérias que atribuem ao IFBA ações realizadas pelo IF Baiano em cidades exclusivas.
- 📊 **Dashboard Analytics Interativo**: Painel em HTML5/JS com estatísticas em tempo real, filtros dinâmicos por ano/campus, gráficos e exportação instantânea para CSV.
- 🎨 **Identidade Visual Oficial**: Interface estilizada rigorosamente nas cores institucionais do IF Baiano (Verde `#3E9A2D` e Vermelho `#C80710`).

## 🛠️ Tecnologias Utilizadas
- **Scraper & Processamento**: Python 3.x, Pandas, Requests, ElementTree, Unicodedata.
- **Dashboard Frontend**: HTML5 Semântico, Vanilla CSS3 (Custom Properties), JavaScript ES6+, Chart.js, PapaParse.

## 📁 Estrutura do Projeto
- `clipping_utils.py`: Módulo central de heurísticas, normalização de strings, padronização de datas e geração de estatísticas.
- `scraper_clipping.py`: Motor diário de captura incremental de notícias.
- `scraper_carga_inicial.py`: Robô para reconstrução histórica de acervo (brackets de 2008 a 2026).
- `index.html`: Dashboard analytics para visualização, busca e geração de relatórios.
- `data/`: Diretório contendo os bancos de dados históricos em CSV e estatísticas em `stats.json`.

---

## 📜 Log de Atualizações (Changelog)

### 📅 05/07/2026 - Categorização de Mídia Expandida & Busca Acadêmica
- 🏷️ **Segregação de Abrangência**: Dividida a antiga categoria `'Institucional / Governamental'` em duas categorias distintas: `'Governamental'` (para portais federais, prefeituras e órgãos públicos) e `'Outras Instituições de Ensino'` (para universidades federais como UFBA, e outros Institutos Federais como IFSC, IFSP, IF Sertão PE, etc.).
- 🎨 **Badges e Gráficos do Dashboard**: Adicionado o badge CSS `.badge-abrangencia-edu` no visualizador e na rotina de impressão em [index.html](file:///G:/Meu%20Drive/app/2.%20Projetos%20e%20Aplica%C3%A7%C3%B5es/2.2%20Aplica%C3%A7%C3%B5es%20e%20C%C3%B3digos%20(GitHub)/IF%20Baiano%20APPs/clipping-completo/index.html) e atualizada a paleta de cores do gráfico de abrangência do Chart.js para suportar as 6 categorias de mídia.
- 🎓 **Busca Acadêmica Expandida (.edu.br)**: Adicionado suporte à varredura dirigida a menções do IF Baiano sob qualquer domínio educacional brasileiro no Google News RSS em [scraper_clipping.py](file:///G:/Meu%20Drive/app/2.%20Projetos%20e%20Aplica%C3%A7%C3%B5es/2.2%20Aplica%C3%A7%C3%B5es%20e%20C%C3%B3digos%20(GitHub)/IF%20Baiano%20APPs/clipping-completo/scraper_clipping.py) e [scraper_carga_inicial.py](file:///G:/Meu%20Drive/app/2.%20Projetos%20e%20Aplica%C3%A7%C3%B5es/2.2%20Aplica%C3%A7%C3%B5es%20e%20C%C3%B3digos%20(GitHub)/IF%20Baiano%20APPs/clipping-completo/scraper_carga_inicial.py).
- 🚫 **Filtro de Auto-Clipping**: Implementado filtro no processamento de links do scraper que descarta matérias originadas no domínio `ifbaiano.edu.br` para evitar registro redundante de notícias institucionais próprias como menções externas na imprensa.
- ⚙️ **Refatoração de Regras de Classificação**: Atualizada a biblioteca [clipping_utils.py](file:///G:/Meu%20Drive/app/2.%20Projetos%20e%20Aplica%C3%A7%C3%B5es/2.2%20Aplica%C3%A7%C3%B5es%20e%20C%C3%B3digos%20(GitHub)/IF%20Baiano%20APPs/clipping-completo/clipping_utils.py) para classificar adequadamente os novos termos identificadores de outras instituições federais e estaduais de ensino superior e técnico.

### 📅 27/06/2026 - Otimização Ponytail & Arquitetura Modular
- ♿ **Acessibilidade Universal (WCAG / A11y)**: Suporte a alternância de **Alto Contraste** e atalhos para ajuste de escala de fonte.
- ⚡ **Criação do Módulo Central (`clipping_utils.py`)**: Centralização das funções de classificação e exportação, reduzindo mais de **350 linhas de código duplicado** nos scrapers.
- 🔤 **Normalização Unicodedata (Degrau 3)**: Implementação de remoção nativa de acentos em Python e JS, simplificando os dicionários de busca e aumentando a precisão das heurísticas.
- 🎨 **Harmonização da Marca IF Baiano**: Atualização completa das variáveis CSS de cor no `index.html` para as tonalidades oficiais (`#3E9A2D` e `#C80710`).
- 📱 **Garantia de Responsividade**: Ajuste fluido para exibição em dispositivos móveis e celulares na vertical (portrait mode).
- 📚 **Atualização da Documentação**: Reformulação do arquivo `README.md` com detalhes arquiteturais e histórico de alterações.