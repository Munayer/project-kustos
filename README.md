# Project Kustos

Um índice pessoal num arquivo só: **pessoas**, **verba** (conceitos e formas),
**fontes** (à maneira do Zotero) e **corpus** (medidas do corpo), todos na
mesma base e ligados entre si.

Python puro, só biblioteca padrão, interface em Tk. Um JSON é a fonte de
verdade; um espelho em Markdown é gerado para ler no Obsidian ou no celular.
Pensado para rodar em mais de uma máquina com a pasta sincronizada (Syncthing,
por exemplo), com fusão automática de conflitos.

> *English:* a single-file personal index (people, concepts/word forms,
> bibliographic sources, body measurements) in pure-stdlib Python with a Tk
> GUI. The UI is in Portuguese.

## Requisitos

- Python 3.10 ou mais novo, com Tkinter (já vem no instalador oficial do
  Windows; no Linux, pode ser preciso instalar `python3-tk`).
- Nada mais.

## Como usar

1. Baixe `_kustos.py` e `_kustos.cmd` para uma pasta vazia.
2. No Windows, dê duplo clique em `_kustos.cmd`. Em outros sistemas:

   ```bash
   python3 _kustos.py
   ```

Na primeira gravação o programa cria `_kustos.json` ao lado do `.py`.
Todos os seus dados ficam nessa pasta; nada sai do seu computador.

## O que tem

- **Quatro acervos** no trilho lateral, cada um com id próprio:
  `p_` pessoa · `c_` conceito · `f_` forma · `s_` fonte · `h_` medida.
- **Ligações tipadas** entre quaisquer registros (`author_of`, `cites`,
  `attested_in`, `defined_in`, `translates`, `measured_in`…). Rótulos fora da
  tabela são aceitos e marcados como "atípicos".
- **Fontes**: tipo livre (livro, artigo, tese, lei, acórdão, página web,
  vídeo…), citação em ABNT, ABNT autor-data, BibTeX e CSL-JSON.
  Importa do Zotero (CSL-JSON ou BibTeX) sem duplicar.
- **Corpus**: medidas com sistema, unidade, faixa de referência e leituras
  datadas; mapa do corpo desenhado no próprio programa e curva de tendência.
  Também gera uma página HTML para abrir no navegador.
- **Busca** com operadores:

  ```
  p: v: f: c:                       só pessoas / verba / fontes / corpus
  ^ab                               nome que começa com "ab"
  tag:x lang:de type:livro sys:renal dom:direito id:c_
  ```

- **Sincronização entre máquinas**: cada máquina escreve o próprio diário
  (`_kustos.log.<máquina>.jsonl`); arquivos `*.sync-conflict-*` são
  fundidos registro a registro ao abrir. O histórico completo de cada
  registro sai dos diários.

## Linha de comando (opcional)

```
python _kustos.py doctor                valida a base, não muda nada
python _kustos.py search <texto>
python _kustos.py cite <id|texto> [abnt|abnt-autor-data|bibtex|csl-json|bruto]
python _kustos.py export [bibtex|csl|abnt] [arquivo]
python _kustos.py import zotero <export.json|.bib>
python _kustos.py mirror | corpus | merge | history <id> | replay
```

## Sincronizando com Syncthing

Sugestão para o `.stignore` da pasta:

```
*.tmp
_kustos.replay.json
_kustos_fontes.*
__pycache__
```

## Licença

MIT. Veja [LICENSE](LICENSE).
