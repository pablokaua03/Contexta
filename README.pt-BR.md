<div align="center">

# Contexta

**Packs de contexto curados para debug, onboarding, review, refactor e handoff entre IAs. O Contexta analisa o projeto primeiro e depois exporta o contexto mais útil para a tarefa.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Plataforma](https://img.shields.io/badge/Plataforma-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Zero Dependências de Runtime](https://img.shields.io/badge/Depend%C3%AAncias%20de%20Runtime-Zero-brightgreen)]()
[![Versão](https://img.shields.io/badge/Vers%C3%A3o-1.5.0-purple)]()

<br>

[<img src="https://img.shields.io/badge/Download%20para%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest/download/contexta.exe)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Todas%20as%20Releases-333?style=for-the-badge&logo=github&logoColor=white" height="42">](https://github.com/pablokaua03/Contexta/releases/latest)

> Sem instalação. É baixar e usar, ou executar pelo código-fonte com Python.

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dark.png">
  <source media="(prefers-color-scheme: light)" srcset="assets/white.png">
  <img alt="Preview da interface do Contexta" src="assets/dark.png">
</picture>

</div>

---

## O que o Contexta exporta

O Contexta não só despeja arquivos. Ele monta um pack de contexto pensado para leitura humana e para uso com IA. Dependendo do pack, do modo e da tarefa, a saída pode incluir:

- resumo do projeto com tecnologias, entry points, propósito provável e módulos centrais
- seção `Read This First` para orientar a leitura
- fluxo principal de execução (`Main Flow`)
- arquivos centrais, arquivos de apoio, testes relacionados e contexto de arquivos alterados
- mapa de relacionamentos e hotspots/riscos
- payload em Markdown pronto para colar no ChatGPT, Claude, Gemini, Copilot ou outra ferramenta

No modo `full`, o código continua presente. A inteligência do Contexta entra em volta do payload, não no lugar dele.

---

## Onde ele ajuda de verdade

Use o Contexta quando você quer:

- explicar um projeto rapidamente para outra pessoa ou outro modelo
- revisar mudanças com contexto próximo
- debugar com arquivos alterados e hotspots já organizados
- fazer onboarding em uma base desconhecida
- passar trabalho de uma IA para outra sem reconstruir contexto do zero

---

## Recursos principais

| Recurso | Detalhe |
|---|---|
| GUI + CLI | Interface desktop para uso diário e linha de comando para script/automação |
| Context Packs | `custom`, `chatgpt`, `onboarding`, `pr_review`, `debug`, `backend`, `frontend`, `changes_related` |
| Context Modes | `full`, `debug`, `feature`, `diff`, `onboarding`, `refactor` |
| Compression Modes | `full`, `balanced`, `focused`, `signatures` |
| Saída orientada por tarefa | Molda o pack para explicação, bug report, code review, refactor, testes, dead code ou AI handoff |
| Relationship Map | Mostra dependências locais e testes provavelmente relacionados |
| Changed Files + Context | Puxa arquivos alterados e expande para o contexto mais relevante |
| Selection reasons | Explica por que cada arquivo entrou |
| Read This First + Main Flow | Facilita leitura rápida por humanos e por modelos |
| Estimativa de tokens | Mostra uma noção aproximada de custo/tamanho |
| Builds com PyInstaller | Gera um executável nativo para a plataforma atual via `build.bat` ou `build.sh` |

---

## Packs, modos e compressão

### Context packs

- `onboarding`: melhor ponto de partida para entender uma base nova
- `pr_review`: enfatiza revisão e mudanças recentes
- `debug`: sobe arquivos suspeitos e alterados
- `backend` / `frontend`: puxam mais contexto para esse lado da aplicação
- `changes_related`: começa no git diff e expande para o entorno
- `custom`: deixa tudo nas suas mãos

### Context modes

- `full`: orientação rápida + payload completo dos arquivos selecionados
- `debug`: prioriza hotspots, mudanças recentes e caminhos de falha
- `feature`: sesga a seleção em torno do `focus`
- `diff`: parte das mudanças do git e do contexto vizinho
- `onboarding`: gera uma leitura mais explicativa
- `refactor`: destaca módulos centrais e arquivos conectados

### Compression modes

- `full`: preserva mais corpo bruto dos arquivos
- `balanced`: mistura narrativa, trechos e payload completo dos mais importantes
- `focused`: corta agressivamente em favor da tarefa atual
- `signatures`: visão estrutural rápida com pouco token

---

## Início rápido

### Opção A: executável do Windows

1. Baixe `contexta.exe`
2. Execute
3. Escolha a pasta do projeto
4. Selecione pack, modo, tarefa e compressão
5. Gere o pack e cole o Markdown na IA

> O Windows pode implicar com executáveis open-source sem assinatura.

### Opção B: rodar pelo código-fonte

```bash
git clone https://github.com/pablokaua03/Contexta.git
cd Contexta
python contexta.py
```

O Contexta em si usa apenas a biblioteca padrão do Python em runtime. Em algumas distros Linux, o `tkinter` pode vir como pacote separado, como `python3-tk`.

---

## Exemplos de CLI

```bash
python contexta.py /caminho/para/projeto
python contexta.py /caminho/para/projeto --pack onboarding
python contexta.py /caminho/para/projeto --mode debug --task bug_report --focus "auth flow"
python contexta.py /caminho/para/projeto --pack pr_review --diff --copy
python contexta.py /caminho/para/projeto --task ai_handoff --compression balanced --focus "theme"
```

### Opções da CLI

| Flag | Descrição |
|---|---|
| `--hidden` | Inclui pastas/arquivos ocultos |
| `--unknown` | Inclui extensões não reconhecidas |
| `--diff` | Prefere contexto baseado em git diff |
| `--staged` | Usa apenas mudanças staged |
| `-p / --prompt` | Adiciona uma instrução ou objetivo customizado |
| `--focus` | Influencia score, ordem, excerpts e contexto relacionado |
| `--mode` | Modo de seleção |
| `--ai` | Perfil de IA alvo |
| `--task` | Perfil de tarefa |
| `--compression` | Estratégia de compressão |
| `--pack` | Pack predefinido |
| `-c / --copy` | Copia a saída para o clipboard |
| `-o / --output` | Caminho de saída customizado |
| `--version` | Exibe a versão |

---

## Dicas de prompting por IA alvo

### Generic LLM
- Geralmente funciona bem: tarefa clara, formato de saída explícito
- Geralmente evite: pedido vago sem definição de pronto

### ChatGPT
- Geralmente funciona bem: instruções curtas mas específicas, resultado esperado claro
- Geralmente evite: misturar análise arquitetural e implementação sem prioridade

### Claude
- Geralmente funciona bem: pedido estruturado, contexto de arquitetura + objetivo claro
- Geralmente evite: prompt amplo demais sem ordenação

### Gemini
- Geralmente funciona bem: contexto mais amplo com prioridades explícitas
- Geralmente evite: assumir que janela grande dispensa estrutura

### Copilot / agentes de código
- Geralmente funciona bem: arquivos, restrições e estado final bem definidos
- Geralmente evite: objetivo aberto sem comportamento-alvo

---

## Guia de tokens

| Tamanho aproximado | Heurística |
|---|---|
| `< 8k` | Normalmente cabe na maioria das sessões de chat/coding |
| `8k - 32k` | Faixa confortável para muitos usos comuns |
| `32k - 128k` | Melhor para sessões com contexto maior |
| `> 128k` | Vale considerar long-context ou um export mais enxuto |

---

## Compilar a partir do código

```bash
# Windows
.\build.bat

# Linux / macOS
chmod +x build.sh && ./build.sh
```

Importante:
- Gere o executável de Windows no Windows e o executável de Linux no Linux. O PyInstaller não faz cross-compile confiável de Windows para Linux.
- Em Debian/Ubuntu, instale `python3-tk` antes do build.

Saídas do build:
- Windows: `dist/contexta.exe`
- Linux / macOS: `dist/contexta`

Se você quiser o binário Linux sem preparar Linux localmente, rode o workflow do GitHub Actions `.github/workflows/build-linux.yml` e baixe o artefato `contexta-linux`.

---

## Rodar os testes

```bash
python -m unittest discover tests/
```

Suite atual: **61 testes automatizados**

---

## Segurança e comportamento

- Somente leitura: não modifica o projeto escaneado
- Sem telemetria e sem necessidade de rede na aplicação
- Limites de scan evitam exportações descontroladas
- Blobs binários/base64 embutidos são omitidos dos excerpts focados

---

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md)

## Changelog

Veja [CHANGELOG.md](CHANGELOG.md)

## Licença

[MIT](LICENSE) © [pablokaua03](https://github.com/pablokaua03)
