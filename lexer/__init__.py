"""Analisador léxico para a Simple Script Language (Guedes, Compiladores).

Exposto para uso externo:
    Lexer            -- o autômato finito que produz tokens
    Token / TokenKind -- o token principal (terminal da gramática)
    LexicalError     -- erro lançado ao encontrar lexema inválido
"""
from .tokens import TokenKind, Token, KEYWORDS
from .tables import NameTable, ConstTable, Const
from .lexer import Lexer, LexicalError

__all__ = [
    "TokenKind", "Token", "KEYWORDS",
    "NameTable", "ConstTable", "Const",
    "Lexer", "LexicalError",
]
