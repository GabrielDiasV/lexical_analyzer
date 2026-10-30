#!/usr/bin/env python3
"""Interface de linha de comando do compilador (geração de código).

Uso:
    python3 compile.py programa.ssl                 # imprime o Assembly gerado
    python3 compile.py programa.ssl -o programa.asm # grava o Assembly em arquivo
    python3 compile.py programa.ssl --refs          # sempre LOAD_REF/DE_REF/STORE_REF
    python3 compile.py programa.ssl --run           # compila e executa na máquina virtual
    python3 compile.py programa.ssl --run --entry fatorial --args 5
    python3 compile.py programa.asm --run           # executa um Assembly já gerado
    echo '...' | python3 compile.py -
"""
from __future__ import annotations

import argparse
import sys

from compiler import CompileError, VMError, assemble, compile_source, format_value, run


def _parse_arg(text: str):
    if text in ("true", "false"):
        return text == "true"
    try:
        return int(text)
    except ValueError:
        return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compilador da Simple Script Language")
    ap.add_argument("source", help="arquivo .ssl ou .asm ('-' para stdin)")
    ap.add_argument("-o", "--output", help="grava o Assembly neste arquivo")
    ap.add_argument("--refs", action="store_true",
                    help="não usa LOAD_VAR/STORE_VAR para variáveis escalares (fig. 7.8)")
    ap.add_argument("--run", action="store_true", help="executa o código na máquina virtual")
    ap.add_argument("--entry", help="função de entrada (nome ou índice; padrão: main ou a última)")
    ap.add_argument("--args", nargs="*", default=[], help="argumentos da função de entrada")
    ap.add_argument("--trace", action="store_true", help="mostra cada instrução executada")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()

    if args.source.endswith(".asm"):
        asm = text
    else:
        try:
            result = compile_source(text, simple_vars=not args.refs)
        except CompileError as err:
            print(f"{args.source}: {err}", file=sys.stderr)
            return 1
        if result.errors:
            for e in result.errors:
                print(f"{args.source}: {e}", file=sys.stderr)
            print(f"{len(result.errors)} erro(s); nenhum código gerado.", file=sys.stderr)
            return 1
        asm = result.asm
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(asm)
        elif not args.run:
            sys.stdout.write(asm)

    if args.run:
        try:
            program = assemble(asm)
            trace = (lambda s: print(s, file=sys.stderr)) if args.trace else None
            ret = run(program, args.entry, [_parse_arg(a) for a in args.args], trace=trace)
        except VMError as err:
            print(f"erro na máquina virtual: {err}", file=sys.stderr)
            return 1
        name = program.function(args.entry).name
        print(f"{name}({', '.join(args.args)}) = "
              + (format_value(ret[0]) if len(ret) == 1
                 else "[" + ", ".join(map(format_value, ret)) + "]"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
