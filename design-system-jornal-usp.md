# Design System - Referência Jornal da USP

Este documento detalha a estrutura de design, padrões visuais e componentes aplicados no portal **Jornal da USP** (https://jornal.usp.br/). Este guia é focado em layouts de formato editorial/jornalístico, caracterizado pelo alto volume de informações, foco em leitura prolongada e arquitetura de notícias.

## 1. Identidade Visual e Cores

O portal prioriza o conteúdo e a leitura, adotando um fundo predominantemente claro (Clean Design) com categorização feita por meio de cores de apoio.

### Cores Base (Tema)
*   **Branco Puro:** `#FFFFFF` (Fundo principal do site).
*   **Cinza Muito Claro:** `#F7F7F7` ou `#F2F2F2` (Fundos de seções secundárias ou de destaque e sidebars).
*   **Preto Editorial:** `#1A1A1A` ou `#222222` (Utilizado em títulos principais e corpo de texto, evitando o preto puro `#000000` para reduzir fadiga visual).

### Cores Institucionais e de Apoio
*   **Azul USP (Tradicional):** `#005A9C` ou variações próximas para botões, links de destaque e elementos institucionais.
*   **Cores de Categorias (Tags):** O jornalismo acadêmico frequentemente usa color-coding para áreas do conhecimento (Ex: Verde para Ciências/Sustentabilidade, Laranja/Amarelo para Cultura, Azul para Institucional).

## 2. Tipografia Editorial

A tipografia de um portal de notícias busca equilibrar a objetividade nas chamadas com o conforto na leitura de textos longos.

*   **Fonte UI / Títulos (Sans-serif):** Famílias como `Roboto`, `Open Sans` ou `Montserrat`.
*   *Uso:* Menus de navegação, subtítulos (H2, H3), tags de categoria, rodapé e pequenos blocos de informação.
*   **Fonte de Corpo de Texto (Serifada):** Famílias como `Merriweather`, `Lora` ou `Georgia`.
*   *Uso:* Corpo da notícia (P). As serifas ajudam a guiar o olhar em parágrafos densos.
*   **Escala Tipográfica (Desktop):**
*   **H1 (Títulos de Matérias):** 36px a 44px, negrito, altura de linha (line-height) apertada (1.2).
*   **H2/H3 (Chamadas na Home):** 20px a 28px.
*   **Corpo da Matéria (P):** 18px a 20px, com altura de linha folgada (1.6 a 1.8) para conforto.
*   **Metadados (Data, Autor, Tags):** 12px a 14px, caixa alta (uppercase) opcional, em cinza médio (`#666666`).

## 3. Estrutura de Layout e Grid

*   **Grid Base:** Sistema clássico de 12 colunas, comum em sites editoriais (ex: Bootstrap).
*   **Largura (Container):** Limite máximo em torno de `1140px` a `1200px` centralizado.
*   **Composição de Página (Home):**
*   O topo geralmente usa colunas mescladas para a manchete principal (ex: 8 colunas para a notícia de destaque, 4 colunas para lista de mais lidas).
*   **Composição de Página (Artigo Interno):**
*   Coluna central de leitura mais estreita (geralmente equivalente a 6 ou 8 colunas, máx. 700px de largura) para evitar que as linhas de texto fiquem muito longas, ladeada por barras laterais (sidebars) com widgets ou notícias relacionadas.

## 4. Componentes Principais

### 4.1. Cabeçalho (Header) e Navegação
*   **Top Bar (Linha Fina):** Faixa estreita no topo com links rápidos (Portal da USP, Fale Conosco, Redes Sociais, Busca).
*   **Marca (Logotipo):** Centralizada ou alinhada à esquerda com grande peso visual. A tipografia da marca "JORNAL DA USP" impõe autoridade e tradição.
*   **Menu Principal (Navbar):** Menu horizontal "sticky" (fixo ao rolar a página). Categorias amplas: *Atualidades, Ciências, Cultura, Diversidade, Institucional, Universidade*. O hover (passar o mouse) revela mega-menus com subcategorias.

### 4.2. Cards de Notícia
A unidade fundamental da página inicial.
*   **Estrutura:**
1.  **Imagem (Thumbnail):** Proporção padronizada (geralmente 16:9 ou 3:2).
2.  **Tag/Chapéu:** Palavra curta indicando a editoria (ex: "CIÊNCIA"), colorida ou em negrito.
3.  **Título:** Fonte sans-serif grande.
4.  **Linha Fina (Resumo):** Texto opcional com um resumo de 1 ou 2 linhas.
*   **Estilo:** Bordas invisíveis ou muito sutis; o alinhamento das imagens e margens é o que delimita o espaço de cada card.

### 4.3. Player e Multimídia (Rádio e TV)
*   **Integração:** Componentes dedicados para a *Rádio USP* e *Podcasts*. Módulos escuros (dark mode) ou coloridos destacam-se do grid branco de notícias em texto, com botões de "Play" evidentes.

### 4.4. Rodapé (Footer)
*   **Estilo:** Fundo escuro (Preto ou Cinza Chumbo) com textos em branco.
*   **Conteúdo:** 
*   Logo institucional da Universidade de São Paulo (USP).
*   Links institucionais e editorias.
*   Informações de contato e expediente (quem faz o jornal).
*   Licenciamento de conteúdo (Creative Commons).

## 5. Práticas de Leiturabilidade
*   **White Space (Respiro):** Áreas generosas de espaço em branco entre seções de notícias (blocos de destaques vs. colunistas) para evitar poluição visual.
*   **Divisores:** Uso de linhas horizontais finas (1px, `#E0E0E0`) para separar manchetes secundárias sem carregar o design.
