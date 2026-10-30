"""Erros de compilação.

Erros sintáticos interrompem a compilação (CompileError). Erros semânticos
(escopo e tipos) são acumulados para que vários sejam relatados de uma vez; a
existência de qualquer um deles faz o papel do ERROR_FLAG da apostila e impede
que o código gerado seja entregue.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(Enum):
    # cap. 5 – análise de escopo
    ERR_REDECL = "identificador '{0}' já declarado neste escopo"
    ERR_NOT_DECL = "identificador '{0}' não declarado"
    # cap. 6 – análise de tipos
    ERR_TYPE_EXPECTED = "'{0}' não é um tipo"
    ERR_BOOL_TYPE_EXPECTED = "esperada expressão do tipo boolean"
    ERR_TYPE_MISMATCH = "tipos incompatíveis"
    ERR_INVALID_TYPE = "operação inválida para o tipo {0}"
    ERR_KIND_NOT_STRUCT = "'{0}' não é uma struct"
    ERR_FIELD_NOT_DECL = "campo '{0}' não declarado na struct"
    ERR_KIND_NOT_ARRAY = "'{0}' não é um array"
    ERR_INVALID_INDEX_TYPE = "índice deve ser do tipo integer"
    ERR_KIND_NOT_VAR = "'{0}' não é uma variável nem um parâmetro"
    ERR_KIND_NOT_FUNC = "'{0}' não é uma função"
    ERR_TOO_MANY_ARGS = "argumentos demais na chamada de '{0}'"
    ERR_TOO_FEW_ARGS = "argumentos de menos na chamada de '{0}'"
    ERR_PARAM_TYPE = "tipo do argumento {0} incompatível com o parâmetro"
    ERR_NOT_STRING = "'{0}' não é uma string"
    # extensões necessárias à geração de código (break/continue/return)
    ERR_BREAK_OUTSIDE_LOOP = "'{0}' fora de um comando de repetição"
    ERR_RETURN_TYPE = "tipo do valor retornado incompatível com o tipo da função"
    ERR_ARRAY_SIZE = "tamanho do array deve ser maior que zero"


@dataclass(frozen=True)
class SemanticError:
    code: ErrorCode
    line: int
    col: int
    arg: str = ""

    @property
    def message(self) -> str:
        return self.code.value.format(self.arg)

    def __str__(self) -> str:
        return f"linha {self.line}, coluna {self.col}: {self.code.name}: {self.message}"


class CompileError(Exception):
    """Erro que interrompe a compilação (léxico ou sintático)."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"linha {line}, coluna {col}: {message}")
        self.line = line
        self.col = col
