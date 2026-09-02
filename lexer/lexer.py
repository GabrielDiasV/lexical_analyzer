"""O autômato finito do analisador léxico.

Implementa next_token() como na apostila: o léxico está sempre UM CARACTERE À
FRENTE (self._next_char). Ao concluir que o caractere lido não pertence ao
lexema corrente, esse caractere é guardado, pois pode iniciar o próximo token.

Expressões regulares reconhecidas (da gramática):
    letra  = 'a'..'z' + 'A'..'Z'
    digito = '0'..'9'
    Id     = letra . (letra + digito)*
    n      = digito . digito*
    c      = ''' . any . '''
    s      = '"' . any* . '"'
"""
from __future__ import annotations

from typing import Iterator, Optional

from .tables import ConstTable, NameTable, search_keyword
from .tokens import SINGLE_CHAR_SYMBOLS, TWO_CHAR_SYMBOLS, Token, TokenKind

_EOF = ""  # sentinela de fim de arquivo devolvida por _read_char()


class LexicalError(Exception):
    """Lexema inválido (caractere fora do alfabeto, string/char malformado)."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"linha {line}, coluna {col}: {message}")
        self.line = line
        self.col = col


class Lexer:
    def __init__(
        self,
        source: str,
        names: Optional[NameTable] = None,
        consts: Optional[ConstTable] = None,
        strict: bool = True,
    ) -> None:
        """
        source -- texto do programa fonte
        names  -- tabela de nomes compartilhada (criada se omitida)
        consts -- tabela de constantes compartilhada (criada se omitida)
        strict -- True: lança LexicalError em lexema inválido
                  False: devolve token UNKNOWN e continua (modo tolerante)
        """
        self._src = source
        self._pos = 0
        self._line = 1
        self._col = 0
        self.names = names if names is not None else NameTable()
        self.consts = consts if consts is not None else ConstTable()
        self.strict = strict

        # Lookahead: começa com um espaço para que a 1ª chamada a next_token()
        # caia no laço de separadores e leia o 1º caractere real.
        self._next_char = " "
        self._next_line = 1
        self._next_col = 0

        # Últimos valores devolvidos (espelham as globais `token`/`tokenSecundario`).
        self.token: TokenKind = TokenKind.UNKNOWN
        self.token_secundario: Optional[int] = None

    # ------------------------------------------------------------------ leitura
    def _read_char(self) -> str:
        """Lê o próximo caractere do fonte e avança a posição. '' no fim."""
        if self._pos >= len(self._src):
            self._next_line, self._next_col = self._line, self._col + 1
            return _EOF
        ch = self._src[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 0
        else:
            self._col += 1
        self._next_line, self._next_col = self._line, self._col
        return ch

    def _advance(self) -> str:
        """Consome o lookahead atual e carrega o próximo."""
        ch = self._next_char
        self._next_char = self._read_char()
        return ch

    def _error(self, msg: str, line: int, col: int) -> Token:
        if self.strict:
            raise LexicalError(msg, line, col)
        return Token(TokenKind.UNKNOWN, None, msg, line, col)

    # --------------------------------------------------------------- autômato
    def next_token(self) -> Token:
        # Estado inicial: laço que pula os separadores.
        while self._next_char != _EOF and self._next_char.isspace():
            self._advance()

        line, col = self._next_line, self._next_col
        ch = self._next_char

        if ch == _EOF:
            return self._emit(TokenKind.EOF, None, "", line, col)

        # ---- Id = letra . (letra + digito)*  |  palavra reservada
        if _is_letter(ch):
            text = []
            while _is_letter(self._next_char) or _is_digit(self._next_char):
                text.append(self._advance())
            lexeme = "".join(text)
            kind = search_keyword(lexeme)          # busca binária
            secondary = self.names.search_name(lexeme) if kind == TokenKind.ID else None
            return self._emit(kind, secondary, lexeme, line, col)

        # ---- n = digito . digito*
        if _is_digit(ch):
            digits = []
            while _is_digit(self._next_char):
                digits.append(self._advance())
            lexeme = "".join(digits)
            return self._emit(TokenKind.NUMERAL, self.consts.add_int_const(int(lexeme)),
                              lexeme, line, col)

        # ---- s = '"' . any* . '"'
        if ch == '"':
            self._advance()                        # abre aspas
            chars = []
            while self._next_char != '"':
                if self._next_char == _EOF:
                    return self._error("string não terminada", line, col)
                chars.append(self._advance())
            self._advance()                        # fecha aspas
            value = "".join(chars)
            return self._emit(TokenKind.STRINGVAL, self.consts.add_string_const(value),
                              f'"{value}"', line, col)

        # ---- c = ''' . any . '''
        if ch == "'":
            self._advance()                        # abre aspa
            if self._next_char == _EOF:
                return self._error("caractere não terminado", line, col)
            value = self._advance()                # exatamente UM caractere (any)
            if self._next_char != "'":
                return self._error("esperado ' para fechar o caractere", line, col)
            self._advance()                        # fecha aspa
            return self._emit(TokenKind.CHARACTER, self.consts.add_char_const(value),
                              f"'{value}'", line, col)

        # ---- símbolos cujo 2º caractere decide (=, ==, <, <=, +, ++, &&, ...)
        if ch in TWO_CHAR_SYMBOLS:
            single, second, double = TWO_CHAR_SYMBOLS[ch]
            self._advance()
            if self._next_char == second:
                self._advance()
                return self._emit(double, None, ch + second, line, col)
            if single is None:                     # '&' ou '|' isolados não existem
                return self._error(f"símbolo inválido '{ch}' (esperado '{ch}{second}')",
                                   line, col)
            return self._emit(single, None, ch, line, col)

        # ---- símbolos de um caractere
        if ch in SINGLE_CHAR_SYMBOLS:
            self._advance()
            return self._emit(SINGLE_CHAR_SYMBOLS[ch], None, ch, line, col)

        # ---- qualquer outra coisa: fora do alfabeto
        self._advance()
        return self._error(f"caractere inválido {ch!r}", line, col)

    def _emit(self, kind: TokenKind, secondary: Optional[int], lexeme: str,
              line: int, col: int) -> Token:
        self.token = kind
        self.token_secundario = secondary
        return Token(kind, secondary, lexeme, line, col)

    # ------------------------------------------------------------ utilidades
    def tokens(self, include_eof: bool = True) -> Iterator[Token]:
        """Itera sobre todos os tokens do fonte."""
        while True:
            tok = self.next_token()
            if tok.kind == TokenKind.EOF:
                if include_eof:
                    yield tok
                return
            yield tok

    def __iter__(self) -> Iterator[Token]:
        return self.tokens()


def _is_letter(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"
