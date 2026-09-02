"""Tabelas de apoio do analisador léxico.

- search_keyword: busca BINÁRIA no vetor de palavras reservadas. Se achar,
  a posição É o token. Se não achar, devolve ID.
- NameTable: tabela de identificadores (hash). Devolve o "nome", um inteiro na
  ordem de primeira leitura. Cada identificador entra uma só vez.
- ConstTable: vetor de constantes (union discriminada). A posição é o token
  secundário. Fases posteriores recuperam o valor pela posição.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .tokens import KEYWORDS, TokenKind


def search_keyword(text: str) -> TokenKind:
    """Busca binária em KEYWORDS. Devolve o token da palavra reservada ou ID."""
    lo, hi = 0, len(KEYWORDS) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if KEYWORDS[mid] == text:
            return TokenKind(mid)          # posição no vetor == valor do token
        if KEYWORDS[mid] < text:
            lo = mid + 1
        else:
            hi = mid - 1
    return TokenKind.ID


class NameTable:
    """Tabela de nomes: identificador -> token secundário ("nome")."""

    def __init__(self) -> None:
        self._index: dict[str, int] = {}     # hash: busca/inserção quase O(1)
        self._names: list[str] = []

    def search_name(self, text: str) -> int:
        """Devolve o nome do identificador, inserindo-o se for a 1ª ocorrência."""
        idx = self._index.get(text)
        if idx is None:
            idx = len(self._names)
            self._index[text] = idx
            self._names.append(text)
        return idx

    def get_name(self, idx: int) -> str:
        return self._names[idx]

    def __len__(self) -> int:
        return len(self._names)

    def items(self):
        return list(enumerate(self._names))


@dataclass(frozen=True)
class Const:
    """Equivalente ao t_const da apostila: tipo discriminador + valor."""
    type: str                          # "char" | "int" | "string"
    value: Union[str, int]


class ConstTable:
    """Vetor de constantes. A posição de inserção é o token secundário."""

    def __init__(self) -> None:
        self._consts: list[Const] = []

    def _add(self, c: Const) -> int:
        self._consts.append(c)
        return len(self._consts) - 1

    def add_char_const(self, c: str) -> int:
        return self._add(Const("char", c))

    def add_int_const(self, n: int) -> int:
        return self._add(Const("int", n))

    def add_string_const(self, s: str) -> int:
        return self._add(Const("string", s))

    def get_char_const(self, idx: int) -> str:
        c = self._consts[idx]
        assert c.type == "char"
        return c.value  # type: ignore[return-value]

    def get_int_const(self, idx: int) -> int:
        c = self._consts[idx]
        assert c.type == "int"
        return c.value  # type: ignore[return-value]

    def get_string_const(self, idx: int) -> str:
        c = self._consts[idx]
        assert c.type == "string"
        return c.value  # type: ignore[return-value]

    def get(self, idx: int) -> Const:
        return self._consts[idx]

    def __len__(self) -> int:
        return len(self._consts)

    def items(self):
        return list(enumerate(self._consts))
