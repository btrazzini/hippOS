# hippOS

*Read in English: [README.md](README.md)*

Assistentes pessoais de IA com memória: um assistente por área da sua vida (trabalho, saúde, finanças, um hobby e o que vier depois), e uma memória que é sua, em Markdown simples no seu Google Drive, consolidada pelo `/sleep` do jeito que o cérebro consolida a memória durante a noite. O nome vem do hipocampo (*hippocampus*), a parte do cérebro que consolida a memória durante o sono, que é o que o `/sleep` faz. Funciona no Claude (chat, celular, Claude Code) e no Codex.

O sistema é todo em inglês (regras, código, comandos e nomes de arquivo), e a estrutura da memória também (títulos, frontmatter, marcadores e campos do BOARD, como em `templates/`). Só o conteúdo fica no seu idioma, e o assistente responde no idioma que você escolher no seu perfil, inclusive português.

Este repositório guarda só o **sistema**: protocolo, skills, validador e moldes. A **memória** de cada pessoa fica numa pasta `hippOS/` no Google Drive dela. Nada pessoal entra aqui.

## Como funciona

```
GitHub (sua cópia do hippOS)      Google Drive: hippOS/
  system/protocol.md                core/         quem você é, preferências, princípios, visão geral
  skills/assistant/  ──lê───────▶   areas/<area>  memória curada de cada área
                     ──grava────▶   inbox/<area>  capturas brutas de cada conversa
  skills/sleep/      ──lê o inbox, grava areas/ e core/, esvazia o inbox
  tools/memory.py    validador, STATE, abertura, fidelidade (sem rede)
  tools/lookup.py    o GitHub da área, pelo gh, na hora
```

A configuração é guiada: o **`/configure`** faz uma pergunta por vez e monta a memória (veja "Começar").

1. **`/assistant <area>`** abre uma conversa como o assistente daquela área. Ele lê o núcleo (`core/`), as regras da área e o `STATE.md`, levanta sozinho nas fontes da área o que espera por você (GitHub, pelo `tools/lookup.py`), responde "o que eu devo?" e, durante a conversa, grava no `inbox/` um arquivo pequeno por captura (decisão, mudança de estado, pendência, preferência). Nunca altera a memória curada.
   - **A abertura** conta o que outras sessões acabaram de anotar (já é memória, mesmo antes do sono) e numera cada item, para você responder "1 feito, 3 na sexta". Começa pelo que o sono concluiu que precisa da sua **atenção** (o que as datas sozinhas não mostram, como duas coisas que se atropelam ou um prazo que depende de alguém parado). Depois mostra o que está atrasado, os próximos prazos, o que **cobrar** (o que você espera dos outros, atrasado ou parado há uma semana), o que espera por você, três itens **sem data** (a cada dia outros, para nada depender de você lembrar de perguntar) e uma linha **Também** com a contagem do resto que espera (perguntas, itens estacionados, decisões a revisar, iniciativas sem conferência). Com o conector de calendário, as reuniões do dia vêm com o que cada lado deve.
   - **`/assistant`** sem área dá o resumo de todas as áreas de uma vez; às segundas, a abertura oferece a **revisão semanal** (`memory.py review`). Antes de você falar com alguém, o `memory.py person` traz tudo o que está aberto com a pessoa.
2. **`/sleep`**, sem área, acha sozinho o que precisa de sono (`memory.py pending`: capturas no inbox, estado velho ou de versão anterior, erro ou arrumação apontada pelo validador) e processa área por área, núcleo por último. Com uma área (`/sleep <area>`), fica só nela. Em cada área: consolida na memória curada (fase 1), fiscaliza com o validador, a conferência de fidelidade e um revisor independente (fase 2), gera os `STATE.md` e o `MAP.md`, registra o que mudou no `CHANGELOG.md` e esvazia o inbox. Pendências fechadas ficam no `LOG.md`, e o que é mais antigo vai para `log/<AAAA-MM>.md` em vez de ser apagado, para "eu já mandei aquilo?" ter resposta.

Modos da conversa: normal (captura), "só discutindo" (não grava nada), "esquece isso" (o sono remove).

## Onde rodar cada coisa

| | Assistente (`/assistant`) | Sono (`/sleep`) |
|---|---|---|
| Claude Code no computador | Sim, o mais rápido (lê a pasta do Drive direto do disco) | **Sim, o lugar principal** |
| Claude Code na nuvem (claude.ai/code, navegador ou app do celular) | Sim | **Sim: é como rodar o sono longe do computador** |
| Codex no computador | Sim | Sim, escolhendo o modelo na mão (o Codex ignora `model` e `effort` da skill) |
| Chat do Claude (computador ou celular) | Sim | **Não** |
| Codex na nuvem | Não (sem acesso ao Drive) | Não |
| Agentes de fora (ex.: o Dot, da OpenAI) | Sim, pelo conector do Drive, com o `EXTERNAL-AGENTS.md` colado nas instruções deles | Não |

**Por que o sono não roda no chat:** ele precisa ler a memória inteira, rodar o validador em Python e regravar arquivos. No chat, cada arquivo passa pela conversa, um a um (são dezenas); o validador só roda se a execução de código estiver ligada e precisa ser copiado para dentro a cada vez; e, como o conector do Drive não edita arquivo, cada alteração vira "criar um novo e mandar o antigo para a lixeira", o que perde o histórico de versões do Drive. O Claude Code (no computador ou na nuvem) tem o repositório, um terminal e fixa o modelo e o esforço do sono (`model: opus`, `effort: medium`).

**Regra prática:** chat e celular servem para conversar com o assistente e gerar capturas; o sono roda no Claude Code. Longe do computador, abra uma sessão em claude.ai/code com a sua cópia do repositório e digite `/sleep`. Um sono por vez: a trava `SLEEP-IN-PROGRESS.md`, na raiz, impede dois ao mesmo tempo.

**Modelo recomendado:** o assistente no dia a dia com Sonnet, esforço médio; Opus, esforço alto, para decisões difíceis (dá para trocar no meio da conversa). O sono já fixa o Opus sozinho no Claude Code.

## Começar

Testado no Mac; no Windows, ainda não (veja "Limites conhecidos").

1. **Clone e ligue as skills**, no seu computador:
   ```
   git clone https://github.com/btrazzini/hippOS ~/hippOS
   cd ~/hippOS
   ./install.sh
   ```
   O `install.sh` liga as skills no Claude Code e no Codex (`~/.claude/skills`, `~/.agents/skills` e `~/.codex/skills`).
2. **`/configure`**, no Claude Code aberto nessa pasta. Ele faz uma pergunta por vez e monta tudo: a pasta `hippOS/` direto em "Meu Drive" (o nome é fixo: é por ele que o assistente a acha), o seu perfil (nome, idioma, fuso horário), as primeiras áreas e os arquivos `STATE.md` e `MAP.md`, e oferece agendar o `/sleep` toda noite. Para respostas em português, escolha `pt-BR` como idioma.
3. **Sua cópia privada.** O `/configure` também oferece criá-la: o Claude Code na nuvem só abre repositórios da sua conta, e um fork de repositório público não pode ser privado. A sua cópia pode ter qualquer nome; o hippOS fica como `upstream`, e você atualiza com `git pull upstream main` e `git push`. Os seus ajustes (hooks no `.claude/settings.json`, skills suas) ficam só na sua cópia, em arquivos que o hippOS não tem, e nunca dão conflito.
4. **Proteções** (opcional): o `/protect` pergunta o que o assistente de cada área nunca pode fazer (deploy, gravar num banco, derrubar um ambiente compartilhado, editar uma pasta de código) e grava isso no `AREA.md` da área. No seu computador, ele também liga o guarda, um hook em `tools/guard.py` que bloqueia esses comandos, endereços e edições nas sessões abertas nesta pasta. Fora daí, são regras que o assistente segue.
5. **Nuvem e chat:** ligue o conector do Google Drive na sua conta do Claude, com a conta Google onde a pasta `hippOS/` está. Na nuvem, as sessões abrem a sua cópia privada; no chat, um projeto que sincroniza a sua cópia, ou a skill `assistant` instalada na sua conta com o zip de `tools/package.sh` (reinstale a cada versão). O Codex na nuvem não é suportado: o ambiente dele não tem as ferramentas do Google Drive.

Sem computador? Importe o hippOS como repositório privado na sua conta do GitHub, abra uma sessão em claude.ai/code nele e rode o `/configure`: ele monta a memória pelo conector do Drive.

## Adicionar uma área

Rode o `/configure` de novo e escolha adicionar uma área. À mão: `python3 tools/memory.py area <root> <area>` a cria a partir de `templates/area/`; preencha o `AREA.md` (missão, papel, limites, fontes) e rode o `/sleep`, que gera o `STATE.md` dela e atualiza o `MAP.md`.

## Versões

`system/VERSION`. Se você mudar o protocolo ou uma skill, `tools/version.sh <nova>` sobe a versão em todos os lugares (`VERSION`, cabeçalho do protocolo, título das skills e `memory.py`); sem argumento, só confere. Depois, reinstale no Claude (`tools/package.sh`). Cada versão ganha a tag `vX.Y.Z`, com notas em Releases. Mudança nos dois primeiros números pede um `/sleep` (sem área, ele passa por todas) para converter a memória ao formato novo: nessa passada ele lê todos os registros, não só os que as capturas tocaram.

Notas antigas não precisam de ferramenta à parte: o que o validador aponta, o próximo `/sleep` corrige, mesmo sem versão nova. Um `.md` solto numa área ou fora das pastas do protocolo é tratado como captura: o conteúdo vai para o lugar certo e o arquivo, para a lixeira do Drive. Para guardar um texto que não é memória, deixe-o em `areas/<area>/drafts/`.

## Limites conhecidos

- **Windows não foi testado.** As skills usam links simbólicos do git (ligue o Modo de Desenvolvedor ou rode `git config core.symlinks true` antes de clonar), o `install.sh` precisa de bash (Git Bash ou WSL), as regras chamam `python3` e, para o fuso horário sair certo, é preciso o pacote `tzdata` (`pip install tzdata`).
- **Ids das pastas fora do Mac.** Só o Google Drive para desktop no Mac expõe os ids das pastas, então um `/sleep` local no Windows ou no Linux os deixa fora do `MAP.md`; o assistente no chat e na nuvem depende deles. Um `/sleep` rodado na nuvem (claude.ai/code) os preenche.
- **As proteções só são garantidas no computador.** O guarda bloqueia o que as listas citam nas sessões abertas na pasta do repositório; no chat, na nuvem e em outras pastas, são regras. Os padrões são texto simples, então um comando reescrito de propósito pode escapar; mantenha o que for crítico também atrás de permissões de verdade.
- **O sono só roda sozinho se estiver agendado.** O `/configure` oferece agendar o `/sleep` toda noite: uma tarefa agendada no app do Claude no computador (modo local; só roda com o app aberto, ou na próxima vez que ele abrir) ou uma rotina na nuvem (`/schedule`, na sua cópia privada, pelo conector, mais devagar). Sem isso, você mesmo roda o `/sleep`.

## Créditos e inspiração

O hippOS deve muito ao **[ai-memory](https://github.com/akitaonrails/ai-memory)**, do Fabio Akita (licença MIT): memória de longo prazo para agentes de código, cujo ciclo (captura, consolidação, abertura, passagem de trabalho) espelha o do hippOS (captura, sono, abertura, fio). Duas ideias dele estão no centro do hippOS:

- **Conferir a fidelidade da consolidação sem IA.** Um modelo consolidando anotações costuma perder os literais (datas, valores, números de issue e PR, código, links); um código simples confere se eles chegaram à memória. Aqui: `memory.py fidelity`, na fiscalização do sono.
- **Regras com orçamento.** O que o agente lê a cada sessão tem teto de palavras, e promover uma regra é subtrativo: para entrar uma, outra sai. Aqui: o teto no `tools/version.sh` e a regra no `AGENTS.md`.

O hippOS trouxe ideias do ai-memory, não código. Os dois remontam ao padrão "LLM wiki" de Andrej Karpathy (ingerir, consultar e faxinar, com índice e log). O que trouxemos, o que ficou para depois e o que não serve está em `system/inspirations.md`.

## Contribuir

Issues e pull requests são bem-vindos; quem decide o que entra é o mantenedor. Veja o [CONTRIBUTING.md](CONTRIBUTING.md) (em inglês).

## Licença

[MIT](LICENSE): use, copie, altere e redistribua o hippOS, com fins comerciais ou não, desde que mantenha o aviso da licença, que credita a origem. Se construir algo em cima dele, um link de volta para este repositório é bem-vindo.

Tudo foi pensado para ser auditável: as regras que os agentes seguem são Markdown simples em `system/` e `skills/`, as ferramentas são Python simples, sem dependências, e nada acessa a rede além do `gh`, quando uma área lista fontes do GitHub. A sua memória fica no seu Google Drive; este repositório nunca a guarda.
