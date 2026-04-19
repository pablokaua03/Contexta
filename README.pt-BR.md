<div align="center">

# Contexta

**Packs de contexto curados para debug, onboarding, review, refactor e handoff entre IAs. O Contexta analisa o projeto primeiro e exporta o contexto mais útil para a tarefa.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Dependências de Runtime](https://img.shields.io/badge/Depend%C3%AAncias%20de%20Runtime-Contexta%201.6-blue)]()
[![Versão](https://img.shields.io/badge/Vers%C3%A3o-1.6.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/Download%20para%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Download%20para%20Linux-E95420?style=for-the-badge&logo=linux&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta-linux.tar.gz)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Todas%20as%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest)

> Portátil no Windows, instalável no Linux e executável a partir do código-fonte com Python.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="Preview da interface do Contexta" src="assets/dark.png">
</picture>

</div>

---

## O que o Contexta exporta

Em vez de despejar arquivos cegamente, o Contexta monta um pack de contexto. Dependendo do pack, do modo e da tarefa, a saída pode incluir:

- resumo do projeto com stack, entry points, propósito provável e módulos centrais
- seção `Read This First` para orientar a leitura
- fluxo principal de execução
- arquivos centrais, arquivos de apoio, testes relacionados e contexto de arquivos alterados
- relationship map, riscos e pontos de impacto
- payload em Markdown pronto para colar no ChatGPT, Claude, Gemini, Copilot ou outra ferramenta

No modo `full`, o código continua presente. A inteligência entra em volta do payload, não no lugar dele.

---

## Principais recursos

| Recurso | Detalhe |
|---|---|
| GUI + CLI | Fluxo desktop para uso diário e CLI para automação |
| Packs de contexto | `custom`, `chatgpt`, `onboarding`, `pr_review`, `risk_review`, `debug`, `backend`, `frontend`, `changes_related` |
| Modos de contexto | `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| Compressão | `full`, `balanced`, `focused`, `signatures`, `lean` |
| Fingerprinting | Detecta stack, framework e tipo de projeto antes de selecionar arquivos — Django, Kotlin Android, Spring Boot, Flutter e mais |
| Proteção contra blobs | Colapsa automaticamente literais base64/binários em todos os modos de compressão |
| Análise syntax-aware | Usa tree-sitter com fallback heurístico para extrair símbolos em várias linguagens |
| Estimativa de tokens | Usa `tiktoken` para estimar melhor o tamanho dos packs |
| Relationship map | Destaca dependências locais e testes provavelmente relacionados |
| Build multiplataforma | Usa Nuitka no Windows e PyInstaller mais bundle instalável no Linux |

---

## Início rápido

### Windows

1. Baixe `contexta.exe` ou `contexta-setup.exe`
2. Execute
3. Escolha a pasta do projeto
4. Selecione pack, modo, tarefa e compressão
5. Gere o pack e cole o Markdown na IA

> O Windows ainda pode alertar sobre executáveis open-source sem assinatura.

### Linux

1. Baixe `contexta-linux.tar.gz`
2. Extraia o pacote
3. Rode `./install.sh` para instalar localmente ou execute o binário `contexta` direto

### Rodando pelo fonte

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
python -m pip install -r requirements.txt
python contexta.py
```

Em algumas distros Linux, o `tkinter` pode vir como pacote separado, como `python3-tk`.

---

## Build a partir do código

```bash
# Windows
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

Importante:

- gere o build do Windows no Windows e o pacote Linux no Linux
- o build do Windows usa Nuitka e exige Visual Studio C++ Build Tools
- o build do Linux gera `dist/contexta` e também `dist/contexta-linux.tar.gz`
- em Debian/Ubuntu, instale `python3-tk` antes do build

Saídas do build:

- Windows: `dist/contexta.exe`
- Instalador do Windows: `dist/contexta-setup.exe` quando o Inno Setup estiver instalado
- Linux / macOS: `dist/contexta`
- Bundle instalável do Linux: `dist/contexta-linux.tar.gz`

---

## Testes

```bash
python -m unittest discover tests/
```

Use esse comando para ver a contagem mais recente da suíte.

---

## Segurança e comportamento

- o Contexta é read-only: não modifica o projeto analisado
- não envia telemetria nem exige rede para funcionar
- limites de scan evitam exports descontrolados
- payloads binários/base64 continuam suprimidos em excerpts focados
- as dependências de runtime são auxiliares locais de análise, não serviços externos

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

Veja [CHANGELOG.md](CHANGELOG.md)

## Licença

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)
