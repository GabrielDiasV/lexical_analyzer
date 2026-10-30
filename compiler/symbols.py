"""Tabela de símbolos, objetos e compatibilidade de tipos.

Corresponde à estrutura `object` estendida da apostila (fig. 7.11): cada
identificador declarado vira um Object com um kind e os atributos daquele kind.
Para a geração de código, tipos guardam o seu tamanho (nSize) em número de
valores escalares e variáveis/parâmetros/campos guardam o seu endereço (nIndex)
e tamanho.

As funções de escopo seguem o cap. 5: NewBlock/EndBlock empilham/desempilham
níveis, Define insere no nível corrente, Search procura só no nível corrente
(para IDD) e Find procura em todos os níveis visíveis (para IDU).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class Kind(Enum):
    NO_KIND_DEF = auto()
    VAR = auto()
    PARAM = auto()
    FUNCTION = auto()
    FIELD = auto()
    ARRAY_TYPE = auto()
    STRUCT_TYPE = auto()
    ALIAS_TYPE = auto()
    SCALAR_TYPE = auto()
    UNIVERSAL = auto()


TYPE_KINDS = (Kind.ARRAY_TYPE, Kind.STRUCT_TYPE, Kind.ALIAS_TYPE, Kind.SCALAR_TYPE)


@dataclass(eq=False)
class Object:
    """Um identificador declarado. Os campos usados dependem do kind.

    VAR / PARAM / FIELD : type, index (endereço), size
    FUNCTION            : ret_type, params, index (posição no pool), n_params, n_vars
    ARRAY_TYPE          : size, elem_type, num_elems
    STRUCT_TYPE         : size, fields
    ALIAS_TYPE          : size, base_type
    SCALAR_TYPE         : size (tipos pré-definidos integer, char, boolean, string)
    """
    name: int                                # token secundário do identificador
    kind: Kind = Kind.NO_KIND_DEF
    text: str = ""                           # lexema, só para mensagens
    type: Optional["Object"] = None
    index: int = 0
    size: int = 0
    ret_type: Optional["Object"] = None
    params: list["Object"] = field(default_factory=list)
    n_params: int = 0
    n_vars: int = 0
    elem_type: Optional["Object"] = None
    num_elems: int = 0
    fields: list["Object"] = field(default_factory=list)
    base_type: Optional["Object"] = None

    def __repr__(self) -> str:
        return f"<{self.kind.name} {self.text or self.name}>"


# Tipos pré-definidos (pInteger, pChar, pBool, pString) e o tipo Universal,
# compatível com qualquer outro, usado para não propagar mensagens de erro.
P_INTEGER = Object(-1, Kind.SCALAR_TYPE, "integer", size=1)
P_CHAR = Object(-2, Kind.SCALAR_TYPE, "char", size=1)
P_BOOL = Object(-3, Kind.SCALAR_TYPE, "boolean", size=1)
P_STRING = Object(-4, Kind.SCALAR_TYPE, "string", size=1)
P_UNIVERSAL = Object(-5, Kind.UNIVERSAL, "universal", size=0)


def resolve(t: Object) -> Object:
    """Segue os tipos sinônimos (alias) até o tipo base."""
    while t.kind == Kind.ALIAS_TYPE:
        t = t.base_type
    return t


def check_types(t1: Object, t2: Object) -> bool:
    """Compatibilidade estrutural de tipos (fig. 6.17).

    Diferenças em relação à figura: os aliases são resolvidos antes da
    comparação (um `type nome = string` é compatível com `string`), e o laço
    dos campos de struct avança nas duas listas.
    """
    t1, t2 = resolve(t1), resolve(t2)
    if t1 is t2:
        return True
    if t1.kind == Kind.UNIVERSAL or t2.kind == Kind.UNIVERSAL:
        return True
    if t1.kind != t2.kind:
        return False
    if t1.kind == Kind.ARRAY_TYPE:
        return t1.num_elems == t2.num_elems and check_types(t1.elem_type, t2.elem_type)
    if t1.kind == Kind.STRUCT_TYPE:
        return len(t1.fields) == len(t2.fields) and all(
            check_types(f1.type, f2.type) for f1, f2 in zip(t1.fields, t2.fields))
    return False


def is_scalar(t: Object) -> bool:
    t = resolve(t)
    return t.kind in (Kind.SCALAR_TYPE, Kind.UNIVERSAL)


class SymbolTable:
    """Pilha de níveis de escopo; cada nível é um hash nome -> Object."""

    def __init__(self) -> None:
        self._levels: list[dict[int, Object]] = [{}]

    def new_block(self) -> int:
        self._levels.append({})
        return len(self._levels) - 1

    def end_block(self) -> int:
        self._levels.pop()
        return len(self._levels) - 1

    def define(self, name: int, text: str = "") -> Object:
        obj = Object(name, text=text)
        self._levels[-1][name] = obj
        return obj

    def search(self, name: int) -> Optional[Object]:
        """Procura apenas no nível corrente (declarações)."""
        return self._levels[-1].get(name)

    def find(self, name: int) -> Optional[Object]:
        """Procura do nível mais interno para o mais externo (usos)."""
        for level in reversed(self._levels):
            if name in level:
                return level[name]
        return None
