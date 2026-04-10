<div align="center">

# ⚡ mdcodebrief

**Escaneia qualquer projeto e gera um único arquivo `.md` com contexto completo de código, pronto para colar em interfaces de IA. Zero dependências, GUI + CLI.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Zero Dependências](https://img.shields.io/badge/Dependências-Zero-brightgreen)]()
[![Version](https://img.shields.io/badge/Versão-1.3.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/⬇%20Download%20para%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/mdcodebrief/releases/latest/download/mdcodebrief.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Todas%20as%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/mdcodebrief/releases/latest)

> Sem instalação. Só baixar e executar.

<br>

![mdcodebrief screenshot](assets/screenshot.png)

</div>

---

## O que é?

`mdcodebrief` é uma ferramenta desktop leve que varre recursivamente uma pasta de projeto e gera um único arquivo Markdown bem estruturado contendo:

- **Árvore visual de diretórios** do projeto inteiro
- Cada **arquivo-fonte** com blocos de código com syntax highlighting
- Caminhos relativos, tamanhos de arquivo e truncagem automática

A saída foi projetada para ser **colada diretamente em interfaces de chat de IA** (ChatGPT, Claude, Gemini, etc.) para que o modelo tenha contexto completo do seu projeto — sem precisar copiar arquivos um a um.

---

## Recursos

| Recurso | Detalhe |
|---|---|
| 🖥️ **Interface visual** | Interface limpa com toggle de tema dark/light |
| ⌨️ **Modo CLI** | Execute sem interface para scripts ou CI |
| 🌳 **Árvore de diretórios** | Visualização ASCII no topo de cada arquivo gerado |
| 🎨 **Syntax highlighting** | 50+ extensões mapeadas |
| 🔒 **Filtragem inteligente** | Ignora `node_modules`, `__pycache__`, `.git`, build dirs, lock files, binários |
| 📋 **Suporte nativo ao `.gitignore`** | Lê e respeita as regras do `.gitignore` automaticamente |
| 📋 **Copiar para clipboard** | Um clique na GUI ou flag `--copy` na CLI |
| 🧮 **Estimativa de tokens** | Mostra `~Xk tokens` com recomendações de modelos |
| 🔀 **Modo Git diff** | `--diff` — varre apenas arquivos alterados |
| 🤖 **Injeção de instrução para IA** | Adiciona um prompt customizado no topo do output |
| 🌗 **Tema Dark / Light** | Toggle no header — troca instantaneamente |
| 📏 **Limites de segurança** | Arquivos truncados em 1 000 linhas; scan para em 2 000 arquivos |
| 🌍 **Multiplataforma** | Windows, macOS, Linux |
| 📦 **Zero dependências** | Apenas biblioteca padrão do Python |

---

## Início rápido

### Opção A — Baixar o executável (sem Python)

1. Baixe o `mdcodebrief.exe` pelo botão acima
2. Dê duplo clique para executar

> ⚠️ **Aviso do Windows SmartScreen:** Clique em **"Mais informações"** → **"Executar mesmo assim"**. Isso é normal para ferramentas open source sem certificado de assinatura pago. Você também pode executar direto pelo código com `python mdcodebrief.py`.

### Opção B — Executar pelo código fonte

```bash
git clone https://github.com/pablokaua03/mdcodebrief.git
cd mdcodebrief
python mdcodebrief.py
```

### Modo CLI

```bash
python mdcodebrief.py /caminho/para/projeto
python mdcodebrief.py /caminho/para/projeto -p "Encontre o memory leak"
python mdcodebrief.py /caminho/para/projeto --diff --copy
python mdcodebrief.py /caminho/para/projeto --diff --copy -p "Revise este PR"
```

---

## Opções CLI

| Flag | Descrição |
|---|---|
| `--hidden` | Incluir pastas/arquivos ocultos |
| `--unknown` | Incluir extensões não reconhecidas |
| `--diff` | Modo Git diff — apenas arquivos alterados |
| `--staged` | Apenas arquivos staged (`git diff --cached`) |
| `-p / --prompt` | Injeta instrução de IA no topo |
| `-c / --copy` | Copia output para clipboard |
| `-o / --output` | Caminho de saída personalizado |
| `--version` | Exibe a versão |

---

## Guia de estimativa de tokens

| Tokens | Modelos recomendados |
|---|---|
| < 8k | Maioria dos modelos |
| 8k – 32k | GPT-4o · Claude Sonnet · Gemini Flash |
| 32k – 128k | Claude 200k · Gemini 1.5 Pro |
| > 128k | Gemini 1.5 Pro 1M |

---

## Compilar executável

```bash
# Windows
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

---

## Segurança

- **Somente leitura** — nunca modifica os arquivos do projeto
- Sem acesso à rede, sem telemetria, sem dependências externas
- Limites rígidos evitam scans infinitos

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Changelog

Veja [CHANGELOG.md](CHANGELOG.md)

---

## Licença

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)