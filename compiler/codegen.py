"""Emissor do código Assembly da máquina virtual de pilha (cap. 7).

Faz o papel do arquivo `f` em que a apostila grava com fprintf: as regras de
atributos do analisador chamam emit()/label() na ordem em que as instruções
devem aparecer. O código fica num buffer de linhas, o que torna trivial o
"fseek" da fig. 7.18: o BEGIN_FUNC é gravado com tamanho de variáveis 0 e
corrigido no fim do bloco da função, quando ele já é conhecido.

Formato gerado:

    CONST n tipo valor        pool de constantes (índice = token secundário)
    BEGIN_FUNC f p v ; nome   início da função f, p células de parâmetros,
                              v células de parâmetros + variáveis
        INSTRUÇÃO arg         instruções (indentadas com tab)
    Ln:                       rótulos, resolvidos pelo montador
    END_FUNC
"""
from __future__ import annotations

import json

from lexer.tables import ConstTable


def format_const(idx: int, ctype: str, value) -> str:
    text = str(value) if ctype == "int" else json.dumps(value, ensure_ascii=False)
    return f"CONST {idx} {ctype} {text}"


class CodeEmitter:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self._label_no = 0

    def new_label(self) -> int:
        """newLabel() da fig. 7.20: números únicos em todo o arquivo."""
        n = self._label_no
        self._label_no += 1
        return n

    def emit(self, op: str, *args: object) -> None:
        self.lines.append("\t" + " ".join([op, *map(str, args)]))

    def label(self, n: int) -> None:
        self.lines.append(f"L{n}:")

    def begin_func(self, index: int, n_params: int, name: str) -> int:
        """Grava o cabeçalho com v = 0 e devolve o 'offset' para correção (MF.offset)."""
        self.lines.append(f"BEGIN_FUNC {index} {n_params} 0 ; {name}")
        return len(self.lines) - 1

    def end_func(self, offset: int, index: int, n_params: int, n_vars: int, name: str) -> None:
        self.lines.append("END_FUNC")
        self.lines[offset] = f"BEGIN_FUNC {index} {n_params} {n_vars} ; {name}"

    def text(self, consts: ConstTable) -> str:
        out = ["; Simple Script Language -- código gerado",
               "; pool de constantes"]
        out += [format_const(i, c.type, c.value) for i, c in consts.items()]
        out.append("; pool de funções / array de código")
        out += self.lines
        return "\n".join(out) + "\n"
