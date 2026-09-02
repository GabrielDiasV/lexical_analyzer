#!/usr/bin/env python3
"""Interface de linha de comando do analisador léxico.

Uso:
    python main.py programa.ssl            # lista os tokens
    python main.py programa.ssl --tables   # também mostra as tabelas de nomes e constantes
    python main.py --lenient programa.ssl  # não para no 1º erro; emite UNKNOWN
    echo 'var x: integer;' | python main.py -
"""
from __future__ import annotations

import argparse
import sys

from lexer import Lexer, LexicalError, TokenKind


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisador léxico da Simple Script Language")
    parser.add_argument("source", help="arquivo fonte ('-' para stdin)")
    parser.add_argument("--tables", action="store_true",
                        help="imprime as tabelas de nomes e constantes ao final")
    parser.add_argument("--lenient", action="store_true",
                        help="não interrompe em erro léxico; emite tokens UNKNOWN")
    args = parser.parse_args(argv)

    text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()
    lx = Lexer(text, strict=not args.lenient)

    print(f"{'LINHA':>5} {'COL':>4}  {'TOKEN':<20} {'SEC':>4}  LEXEMA")
    print("-" * 60)
    status = 0
    try:
        for tok in lx.tokens(include_eof=True):
            sec = "" if tok.secondary is None else str(tok.secondary)
            print(f"{tok.line:>5} {tok.col:>4}  {tok.kind.name:<20} {sec:>4}  {tok.lexeme}")
            if tok.kind == TokenKind.UNKNOWN:
                status = 1
    except LexicalError as err:
        print(f"\nERRO LÉXICO: {err}", file=sys.stderr)
        status = 1

    if args.tables:
        print("\nTABELA DE NOMES (token secundário -> identificador)")
        for idx, name in lx.names.items():
            print(f"  {idx:>4}  {name}")
        print("\nTABELA DE CONSTANTES (token secundário -> tipo, valor)")
        for idx, c in lx.consts.items():
            print(f"  {idx:>4}  {c.type:<6} {c.value!r}")
    return status


if __name__ == "__main__":
    sys.exit(main())
