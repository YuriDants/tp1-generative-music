```markdown
# Geração Musical Simbólica Baseada em Gramáticas Probabilísticas Inspirada na Décima Espinela e no Repente Nordestino

Este repositório contém a implementação final, o código-fonte e os artefatos experimentais do **Trabalho Prático 1 (TP1)** da disciplina **DCC831 — IA Generativa para Música**, ministrada na Universidade Federal de Minas Gerais (UFMG).

O projeto investiga o uso de **gramáticas generativas probabilísticas para composição musical simbólica**, utilizando a *décima espinela* como referência poética formal e a *cantoria de viola / repente nordestino* como inspiração musical e cultural.

> **Nota metodológica:** A estrutura poética é adotada como uma **abstração computacional de design** para conferir coesão estrutural às peças, não se tratando de uma reconstrução etnomusicológica ou de um modelo empírico da prática tradicional do repente.

---

## 📌 Sistema Final — V2.5

A versão final do sistema é a **V2.5**.

O sistema gera quatro famílias melódicas independentes a partir de uma gramática probabilística compartilhada e as atribui a papéis estruturais recorrentes segundo uma estrutura inspirada no esquema de rimas da décima espinela:

```text
Esquema poético:  A  B  B  A  A  C  C  D  D  C
                  ↓  ↓  ↓  ↓  ↓  ↓  ↓  ↓  ↓  ↓
Papéis musicais:  R1 R2 R2 R1 R1 R3 R3 R4 R4 R3
```

- **Estrutura simbólica:** cada frase contém exatamente 8 eventos simbólicos, em uma abstração computacional das oito sílabas de cada verso octossilábico.
- **Controle de variação:** a microvariação de alturas (*pitch*) é controlada pelo hiperparâmetro \(p_{\mathrm{var}}\).
- **Arranjo e percussão:** ritmo, atribuição de timbres e uma gramática auxiliar de percussão introduzem camadas estocásticas adicionais.
- **Formatos de saída:** o sistema gera arquivos **MIDI** e renderiza áudios **WAV** utilizando o MuseScore.

---

## 🎧 Realizações Utilizadas no Artigo

Para a avaliação quantitativa apresentada no artigo final, foram geradas três realizações controladas na versão V2.5:

| Realização | *Random Seed* | \(p_{\mathrm{var}}\) | Função Experimental |
| ---------- | ------------- | -------------------- | ------------------- |
| **M1** | `101` | `0.20` | Realização de referência. |
| **M2** | `202` | `0.20` | Seed diferente com o mesmo \(p_{\mathrm{var}}\), para observar diversidade entre realizações da mesma configuração. |
| **M3** | `101` | `0.70` | Mesma seed de M1 com \(p_{\mathrm{var}}\) elevado, para isolar o efeito da microvariação. |

Somente os resultados da **V2.5** são utilizados nas análises quantitativas reportadas no artigo.

### Exemplos Suplementares da V2.5

Além das três realizações utilizadas na análise do artigo, foram geradas **sete realizações suplementares** com a mesma implementação V2.5, com o objetivo de disponibilizar uma amostra maior de músicas para audição e inspeção do comportamento do gerador.

| Realização | Seed | `p_var` | BPM |
| ---------- | ---: | ------: | --: |
| **M4** | `303` | `0.20` | `96` |
| **M5** | `404` | `0.20` | `96` |
| **M6** | `505` | `0.20` | `96` |
| **M7** | `606` | `0.20` | `120` |
| **M8** | `707` | `0.20` | `120` |
| **M9** | `808` | `0.20` | `144` |
| **M10** | `909` | `0.20` | `144` |

Os respectivos arquivos MIDI, WAV e JSON estão disponíveis em [`supplementary_outputs_v25/`](supplementary_outputs_v25/).

> **Observação:** M4–M10 são exemplos suplementares da implementação V2.5 e não integram o desenho experimental nem os resultados quantitativos apresentados no artigo. O manuscrito já estava finalizado no limite de três páginas do TP1 quando esses exemplos adicionais foram produzidos. M1, M2 e M3 permanecem como as únicas realizações utilizadas nas análises reportadas no artigo.

As realizações suplementares foram produzidas diretamente pela implementação V2.5, sem seleção estética posterior. M4–M6 mantêm o BPM utilizado no experimento principal, enquanto M7–M8 e M9–M10 permitem também ouvir o mesmo sistema em velocidades maiores.

### Artefatos de Áudio e Saídas Simbólicas

- **M1:** [MIDI](outputs_v25/m1.mid) | [WAV](outputs_v25/m1.wav) | [Metadata/JSON](outputs_v25/m1.json)
- **M2:** [MIDI](outputs_v25/m2.mid) | [WAV](outputs_v25/m2.wav) | [Metadata/JSON](outputs_v25/m2.json)
- **M3:** [MIDI](outputs_v25/m3.mid) | [WAV](outputs_v25/m3.wav) | [Metadata/JSON](outputs_v25/m3.json)

---

## 📂 Estrutura do Repositório

```text
.
├── README.md                           # Este documento
├── requirements.txt                    # Dependências Python
├── generate_v25.py                     # Script principal da versão V2.5
│
├── outputs_v25/                        # Saídas finais utilizadas no artigo
│   ├── m1.mid
│   ├── m1.wav
│   ├── m1.json
│   ├── m2.mid
│   ├── m2.wav
│   ├── m2.json
│   ├── m3.mid
│   ├── m3.wav
│   ├── m3.json
│   └── experiment_validation.json      # Validação cruzada automatizada M1 × M3
│
├── development_history/                # Artefatos de versões anteriores
│   ├── v1/
│   ├── v2/
│   ├── v2_1/
│   ├── v2_2/
│   ├── v2_3/
│   └── v2_4/
│
└── paper/                              # Artigo e arquivos-fonte em LaTeX
    ├── TP1_ISMIR_2026_Paper.pdf
    ├── TP1_ISMIR_2026_Paper.tex
    └── TP1_ISMIR2026.bib
│
├── generate_supplementary_v25.py       # Geração dos exemplos suplementares M4–M10
│
├── supplementary_outputs_v25/          # Exemplos suplementares da V2.5
│   ├── m4.mid / m4.wav / m4.json
│   ├── m5.mid / m5.wav / m5.json
│   ├── m6.mid / m6.wav / m6.json
│   ├── m7.mid / m7.wav / m7.json
│   ├── m8.mid / m8.wav / m8.json
│   ├── m9.mid / m9.wav / m9.json
│   └── m10.mid / m10.wav / m10.json
```

A pasta `development_history/` contém artefatos selecionados em MIDI, WAV e JSON de versões anteriores do sistema. Esses arquivos são disponibilizados para permitir a observação da evolução do projeto durante o desenvolvimento.

Eles **não fazem parte dos experimentos ou resultados quantitativos reportados no artigo final**, que utiliza exclusivamente a versão V2.5.

---

## 🚀 Histórico de Evolução do Sistema

O projeto passou por várias iterações até alcançar a arquitetura final:

| Versão | Alteração Principal |
| ------ | ------------------- |
| **V1** | Motivos melódicos fixos com variação estocástica local. |
| **V2** | Expansão das decisões estocásticas e experimentos iniciais de arranjo. |
| **V2.1** | Evolução do baseline probabilístico e maior separação entre aleatoriedade estrutural e microvariação. |
| **V2.2** | Derivação melódica procedimental a partir de regras probabilísticas compartilhadas. |
| **V2.3** | Separação explícita entre famílias melódicas, papéis estruturais e atribuição de instrumentos. |
| **V2.4** | Geração independente das quatro famílias melódicas a partir da mesma gramática probabilística. |
| **V2.5** | **Arquitetura final:** preservação da geração melódica da V2.4, adição de percussão probabilística e validações experimentais. |

---

## 🛠️ Requisitos e Instalação

### 1. Ambiente Python

Recomenda-se o **Python 3.10 ou superior**.

Crie e ative um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

A principal biblioteca Python utilizada para construção, escrita e inspeção dos arquivos MIDI é a `pretty_midi`.

### 2. Renderização de Áudio — MuseScore

Para converter automaticamente os arquivos MIDI gerados para WAV, o script utiliza o **MuseScore**.

O sistema procura pelas seguintes formas de execução:

- `org.musescore.MuseScore` via Flatpak;
- `musescore`;
- `mscore`;
- `MuseScore4`.

Em sistemas Linux com Flatpak, o MuseScore pode ser instalado com:

```bash
flatpak install flathub org.musescore.MuseScore
```

Os arquivos MIDI constituem a saída simbólica do sistema. Os arquivos WAV são renderizações destinadas à audição e podem apresentar pequenas diferenças dependendo da versão do MuseScore e da biblioteca de timbres disponível no ambiente.

---

## 🔄 Como Executar e Reproduzir os Experimentos

Para gerar novamente as três realizações finais, executar as validações e renderizar os respectivos áudios, execute na raiz do repositório:

```bash
python generate_v25.py
```

O script utiliza automaticamente as três configurações experimentais:

```text
M1: seed = 101, p_var = 0.20
M2: seed = 202, p_var = 0.20
M3: seed = 101, p_var = 0.70
```

As saídas são gravadas em:

```text
outputs_v25/
```

Para cada realização são produzidos:

```text
.mid   saída musical simbólica em MIDI
.wav   renderização de áudio realizada pelo MuseScore
.json  configuração, decisões gerativas, validações e métricas
```

O script também gera:

```text
outputs_v25/experiment_validation.json
```

contendo as verificações utilizadas na comparação controlada entre M1 e M3.

### Gerar os exemplos suplementares

Com `outputs_v25/` já existente e preservado:

```bash
python generate_supplementary_v25.py

---

## 🔬 Reprodutibilidade e Controle Experimental

O sistema utiliza seeds explícitas e fluxos pseudoaleatórios separados e determinísticos para diferentes componentes da geração, incluindo:

- famílias melódicas;
- ritmo;
- associação entre famílias e papéis estruturais;
- atribuição de instrumentos;
- microvariação;
- percussão.

A comparação **M1 × M2** mantém \(p_{\mathrm{var}}=0.20\) e altera a seed, permitindo observar diversidade entre duas realizações da mesma configuração.

A comparação **M1 × M3** utiliza a mesma seed e altera somente:

```text
p_var: 0.20 → 0.70
```

Dessa forma, famílias melódicas, ritmos, associação entre famílias e papéis, instrumentos, percussão e fluxo pseudoaleatório da microvariação permanecem controlados, permitindo analisar especificamente o efeito do hiperparâmetro.

O próprio script realiza verificações estruturais e validações dos arquivos MIDI antes de concluir a execução.

---

## 📄 Artigo Científico

O artigo final de três páginas está disponível neste repositório:

- 📖 [PDF compilado](paper/TP1_ISMIR_2026_Paper.pdf)
- 📝 [Fonte LaTeX](paper/TP1_ISMIR_2026_Paper.tex)
- 📚 [Referências BibTeX](paper/TP1_ISMIR2026.bib)

**Título do artigo:**

*Probabilistic Grammar-Based Symbolic Music Generation Inspired by the Décima Espinela and Northeastern Brazilian Repente*

---

## 🤖 Declaração de Uso de Ferramentas de IA Generativa

Em conformidade com as diretrizes do TP1 da disciplina **DCC831 — IA Generativa para Música**, ferramentas de IA generativa foram utilizadas como **apoio ao processo de desenvolvimento e escrita**, com seus objetivos e respectivas conversas documentados abaixo.

O enunciado da atividade permite o uso de ferramentas de IA como apoio à implementação e à escrita do resumo, desde que esse uso seja declarado. A implementação integral do método de geração musical e o resumo não foram produzidos automaticamente de uma única vez por uma ferramenta de IA.

### ChatGPT — OpenAI

O ChatGPT foi utilizado como ferramenta de apoio em diferentes etapas do trabalho:

- discussão inicial do escopo e da arquitetura do projeto;
- avaliação de alternativas para representar a décima espinela por meio de uma gramática probabilística;
- apoio iterativo à implementação, incluindo discussão de alternativas, geração e revisão de trechos auxiliares de código, depuração e interpretação de erros;
- revisão da lógica de funções e das decisões relacionadas a seeds, fluxos pseudoaleatórios, microvariação, famílias melódicas, papéis estruturais, instrumentação e percussão;
- apoio na definição e revisão das validações, métricas e comparações experimentais;
- análise dos outputs produzidos localmente pelo programa;
- auxílio na organização da redação e revisão do manuscrito;
- apoio na preparação da documentação e estrutura do repositório.

O processo de implementação foi **iterativo**: diferentes versões do sistema foram executadas e testadas localmente, seus resultados foram analisados e novas decisões foram tomadas a partir desses testes.

A versão V2.5 é resultado desse processo de desenvolvimento, execução, análise e refinamento. O uso do ChatGPT ocorreu como **ferramenta de apoio**, e não como geração automática integral, em uma única etapa, da implementação do método.

### NotebookLM — Google

O NotebookLM foi utilizado principalmente como ferramenta de **auditoria baseada nas fontes bibliográficas fornecidas**, com o objetivo de verificar se as afirmações poéticas e musicológicas presentes no manuscrito permaneciam dentro do escopo sustentado pelas referências utilizadas.

Foram verificadas, entre outras, afirmações relativas a:

- décima espinela;
- repente nordestino e cantoria de viola;
- toadas;
- relação entre forma poética e estrutura musical;
- limites entre propriedades documentadas na literatura e abstrações computacionais introduzidas pelo projeto.

O NotebookLM foi utilizado para checagem e auditoria do texto, e não para gerar a implementação musical.

> **Transparência do processo:** a geração das composições apresentadas no trabalho é realizada pelo algoritmo de gramáticas probabilísticas implementado em `generate_v25.py`. Nenhum modelo de linguagem, modelo neural de composição, sistema *text-to-MIDI* ou *text-to-audio* é utilizado para gerar as músicas submetidas.

### Links das Conversas e Ferramentas de Suporte

- **Planejamento e definição da arquitetura:** [ChatGPT — resumo do processo de planejamento](https://chatgpt.com/s/t_6ac2b4a48dcc8191ad023a040127f255)
- **Apoio à implementação e evolução do sistema até a V2.5:** [ChatGPT — resumo do processo de implementação](https://chatgpt.com/s/t_6ac2b3ff24bc81919f99818d1686d2c1)
- **Experimentos, validação e análise dos resultados:** [https://chatgpt.com/share/6ac2b52a-9660-83e9-a564-03e01d86e876)
- **Apoio a redação, organização e auditoria do artigo:** [ChatGPT — Chat Produção - IaMusica](https://chatgpt.com/share/6ac2bc8d-9cf8-83e9-9228-118dd08300e9)
- **Auditoria musicológica baseada nas fontes:** [NotebookLM — notebook de auditoria](https://notebook.google.com/notebook/9991b36b-f149-4b05-ba53-28d545763e2e)

---

## 👤 Autor

**Yuri Siqueira Dantas**  
Universidade Federal de Minas Gerais (UFMG)  
*DCC831 — IA Generativa para Música (2026/2)*
```