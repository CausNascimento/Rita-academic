# Rita Academic

Servidor [MCP](https://modelcontextprotocol.io) acadêmico pessoal, em Python. Dá a qualquer
assistente de IA (Claude Desktop, ChatGPT Desktop, Claude Code, Cursor etc.) acesso a uma
biblioteca de textos **no seu computador**, para quatro coisas:

1. **Organizar** pastas locais onde você deposita PDFs, EPUBs, Markdown e áudios.
2. **Fichar** textos, aproveitando os **destaques feitos no PDF** em qualquer leitor comum.
3. **Pesquisar** o acervo (texto completo, destaques, fichamentos, transcrições) com **citação
   pronta** com página, para alimentar a escrita de artigos.
4. **Transcrever leituras gravadas** de livros físicos, interpretando **comandos de voz em
   português** ("destaque isso… fim do destaque", "nota:…", "página 42") e gerando o fichamento.

O servidor **não chama nenhuma API de IA**. Ele só expõe dados e ferramentas; quem resume,
interpreta e redige é o assistente conectado. Por isso funciona igual com qualquer modelo.
A transcrição é feita localmente com [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(sem chave, sem envio do áudio para fora).

## Requisitos

- Python 3.11+ e [uv](https://docs.astral.sh/uv/) (ou pip).
- `ffmpeg` no PATH (para normalizar áudios). macOS: `brew install ffmpeg`; Debian/Ubuntu:
  `sudo apt install ffmpeg`; Windows: `winget install ffmpeg`.
- Na primeira transcrição, o modelo Whisper é baixado (modelo `small` ≈ 500 MB).

## Instalação

```bash
git clone https://github.com/CausNascimento/Rita-academic.git
cd Rita-academic
uv venv && uv pip install -e .
cp .env.example .env   # edite RITA_LIBRARY_ROOT
```

Teste rápido:

```bash
RITA_LIBRARY_ROOT=~/Biblioteca uv run rita-academic --transport stdio
# ou, com interface visual:
npx @modelcontextprotocol/inspector uv run rita-academic --transport stdio
```

## Estrutura da biblioteca

```
~/Biblioteca/
  _inbox/                 # jogue aqui o que chegar; a IA organiza depois
  _notes/                 # fichamentos (Markdown + frontmatter YAML)
  Artigos e livros/<Autor>/<Ano> - <Título>.pdf
  Textos/                 # .md e .txt
  Leituras gravadas/      # áudios de leitura em voz alta
  .rita/                  # índice SQLite (FTS5) e cache; pode apagar e reindexar
```

O padrão de pastas é configurável (`RITA_ORGANIZE_TEMPLATE`). Os documentos são identificados
por um hash do conteúdo, então mover ou renomear arquivos não quebra fichamentos nem citações.

## Configuração nos clientes

### Claude Desktop (stdio)

Edite `claude_desktop_config.json` (Configurações → Desenvolvedor → Editar configuração):

```json
{
  "mcpServers": {
    "rita-academic": {
      "command": "uv",
      "args": ["--directory", "/CAMINHO/para/Rita-academic", "run", "rita-academic", "--transport", "stdio"],
      "env": {
        "RITA_LIBRARY_ROOT": "/CAMINHO/para/Biblioteca",
        "RITA_WHISPER_MODEL": "small"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add rita-academic -e RITA_LIBRARY_ROOT=/CAMINHO/para/Biblioteca -- \
  uv --directory /CAMINHO/para/Rita-academic run rita-academic --transport stdio
```

### ChatGPT Desktop e outros clientes só-HTTP

O ChatGPT aceita apenas servidores MCP **remotos** (HTTP/SSE), não processos locais via stdio.
Suba o servidor em HTTP e exponha-o por HTTPS:

```bash
RITA_LIBRARY_ROOT=~/Biblioteca uv run rita-academic --transport streamable-http --port 8765
# em outro terminal, um túnel HTTPS, por exemplo:
ngrok http 8765          # ou: cloudflared tunnel --url http://localhost:8765
```

Depois, no ChatGPT: *Settings → Apps/Connectors → Advanced → Developer mode → Create*, URL
`https://<seu-tunel>/mcp`, autenticação "none". Use `--stateless` se o cliente reconectar a cada
chamada. **Atenção:** um túnel público expõe sua biblioteca a quem tiver a URL; use túneis com
autenticação ou restrinja o acesso quando terminar.

## Variáveis de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `RITA_LIBRARY_ROOT` | (obrigatória) | pasta raiz da biblioteca |
| `RITA_INBOX_DIR` | `<root>/_inbox` | caixa de entrada |
| `RITA_NOTES_DIR` | `<root>/_notes` | onde ficam os fichamentos |
| `RITA_NOTES_MODE` | `notes_dir` | `next_to_source` grava o `.md` ao lado do PDF |
| `RITA_ORGANIZE_TEMPLATE` | `{type}/{author_sort}/{year} - {title}{ext}` | padrão de pastas |
| `RITA_WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3` |
| `RITA_WHISPER_DEVICE` / `RITA_WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | use `cuda` / `float16` com GPU |
| `RITA_LANGUAGE` | `pt` | idioma da transcrição |
| `RITA_COMMAND_KEYWORDS` | — | YAML com palavras-chave de voz personalizadas |
| `RITA_HTTP_HOST` / `RITA_HTTP_PORT` | `127.0.0.1` / `8765` | transporte HTTP |

## Ferramentas, recursos e prompts

**Biblioteca:** `scan_library`, `list_documents`, `get_document`, `search_metadata`,
`extract_metadata`, `update_metadata`, `add_tags`, `remove_tags`, `propose_organization`,
`organize_documents` (só move com `apply=true`, nunca para fora da biblioteca).

**Fichamento:** `extract_pdf_annotations` (highlight, underline, strikeout, squiggly e notas
adesivas, com página e cor), `annotations_to_markdown`, `get_fichamento`, `write_fichamento`,
`append_to_fichamento`, `list_notes`. Seções padrão do fichamento: *Referência, Resumo,
Destaques, Notas, Citações para uso*.

**Pesquisa para escrita:** `search` (FTS5, ignora acentos, busca por prefixo; filtra por tipo
de fonte, documento ou tag), `get_passage` (texto + citação autor-data e ABNT com `p. N`),
`export_references` (ABNT ou BibTeX). Esta é a camada que uma skill de escrita de artigos
deve consumir.

**Leitura gravada:** `transcribe_audio`, `get_job`, `list_jobs`, `cancel_job`, `get_transcript`,
`parse_reading_commands`, `reading_session_to_fichamento`, `audio_to_fichamento` (pipeline
completo em segundo plano).

**Recursos:** `rita://library/summary`, `rita://doc/{id}`, `rita://doc/{id}/page/{n}`,
`rita://doc/{id}/fichamento`, `rita://job/{id}`, `rita://config/keywords`.

**Prompts (em português):** `fichamento`, `fichamento_de_leitura_gravada`, `organizar_biblioteca`.

## Comandos de voz na leitura gravada

Grave a leitura com o celular ou gravador e entregue o arquivo ao assistente
("transcreva `~/Downloads/leitura.m4a` e fiche no livro X"). Durante a leitura, diga:

| Dizer | Efeito |
|---|---|
| "**página** quarenta e dois" / "página 42" | define a página corrente (por extenso ou numeral) |
| "**capítulo** três" / "capítulo IV" · "**seção** dois" | define capítulo/seção correntes |
| "**destaque isso**" … "**fim do destaque**" | o que vier entre os dois vira citação direta |
| "**nota**:" … "**fim da nota**" | observação sua (também fecha com uma pausa de ~4 s) |
| "**cancela**" / "apaga isso" | descarta o destaque/nota em andamento ou o último |

Tudo o que não for comando vira "trecho não interpretado" e fica disponível para a IA usar nas
notas. As palavras-chave podem ser trocadas num YAML (`RITA_COMMAND_KEYWORDS`):

```yaml
highlight_start: ["grifa", "destaque isso"]
highlight_end: ["chega", "fim do destaque"]
note_gap_seconds: 6
```

## Fluxos de uso

- **Fichar um PDF destacado:** "Rode o prompt *fichamento* para o doc `<id>`". O assistente
  extrai os destaques, lê páginas quando precisar, redige e grava com `write_fichamento`.
- **Organizar a caixa de entrada:** prompt *organizar_biblioteca*; o assistente completa
  metadados, propõe de→para e só move após confirmação.
- **Escrever um artigo:** "Busque no acervo sobre *autonomia docente* e me traga as passagens
  com citação". `search` → `get_passage` → referências com `export_references`.
- **Livro físico:** `audio_to_fichamento(path, target_doc_id)` em segundo plano; acompanhe com
  `get_job`; ao terminar, os destaques entram na seção *Destaques* do fichamento do livro.

## Desenvolvimento

```bash
uv pip install -e ".[dev]"
uv run pytest -q
uv run ruff check src tests
```

Os testes usam um PDF gerado com anotações, um WAV de 1 s e um transcritor falso; a transcrição
real com faster-whisper não roda na suíte.
