"""Montador e interpretador da máquina virtual de pilha (seção 7.1).

Arquitetura:
  - Pool de Constantes : valores escalares polimórficos (linhas CONST);
  - Pool de Funções    : para cada função, tamanho dos parâmetros, tamanho das
                         variáveis (que engloba os parâmetros) e índice da 1ª
                         instrução no Array de Código (BEGIN_FUNC);
  - Array de Código    : instruções de todas as funções; o montador resolve os
                         rótulos Ln para índices nesse array;
  - Pilha de Valores   : polimórfica (integer, char, boolean, string). Os
                         parâmetros e variáveis de uma chamada ocupam
                         st[bp .. bp+v-1]; endereços são deslocamentos a partir
                         de bp;
  - Pilha Operacional  : guarda (&ret, bp) da função chamadora.

Convenção de chamada: o chamador empilha os argumentos (p células) e executa
CALL n; a função recebe bp = sp-p+1 e as v-p células das variáveis locais são
reservadas. Em RET, as células acima de bp+v (o valor de retorno, que pode
ocupar várias células, como um array) substituem o registro de ativação.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

_JUMPS = {"JMP_FW", "JMP_BW", "TJMP_FW", "TJMP_BW"}


class VMError(Exception):
    pass


@dataclass(frozen=True)
class Function:
    index: int
    n_params: int
    n_vars: int
    ip: int
    name: str


@dataclass
class Program:
    consts: dict[int, object]
    functions: dict[int, Function]
    code: list[tuple[str, tuple]]

    def function(self, entry: Optional[str | int] = None) -> Function:
        """Função de entrada: por índice, por nome, `main` ou a última declarada."""
        if isinstance(entry, int) or (isinstance(entry, str) and entry.isdigit()):
            idx = int(entry)
            if idx not in self.functions:
                raise VMError(f"função {idx} não existe")
            return self.functions[idx]
        name = entry or "main"
        for f in self.functions.values():
            if f.name == name:
                return f
        if entry is None and self.functions:
            return self.functions[max(self.functions)]
        raise VMError(f"função '{name}' não encontrada")


def assemble(text: str) -> Program:
    """Traduz o Assembly textual para o programa carregado na máquina."""
    consts: dict[int, object] = {}
    functions: dict[int, Function] = {}
    code: list[tuple[str, tuple]] = []
    labels: dict[str, int] = {}

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("CONST "):
            _, idx, ctype, value = line.split(" ", 3)
            consts[int(idx)] = int(value) if ctype == "int" else json.loads(value)
            continue
        line, _, comment = line.partition(";")
        line = line.strip()
        if line.endswith(":"):
            labels[line[:-1]] = len(code)
            continue
        op, *args = line.replace(",", " ").split()
        if op == "BEGIN_FUNC":
            f, p, v = map(int, args)
            functions[f] = Function(f, p, v, len(code), comment.strip())
            continue
        parsed = tuple(a if op in _JUMPS else int(a) for a in args)
        code.append((op, parsed))

    for i, (op, args) in enumerate(code):
        if op in _JUMPS:
            if args[0] not in labels:
                raise VMError(f"rótulo {args[0]} não definido")
            code[i] = (op, (labels[args[0]],))
    return Program(consts, functions, code)


def run(program: Program, entry: Optional[str | int] = None, args: Sequence = (),
        max_steps: int = 10_000_000,
        trace: Optional[Callable[[str], None]] = None) -> list:
    """Executa a função de entrada com os argumentos dados (um por célula) e
    devolve as células do valor retornado."""
    func = program.function(entry)
    if len(args) != func.n_params:
        raise VMError(f"'{func.name}' espera {func.n_params} célula(s) de argumentos, "
                      f"recebeu {len(args)}")
    code, consts, functions = program.code, program.consts, program.functions
    st: list = list(args) + [0] * (func.n_vars - func.n_params)
    ops: list[tuple[int, int, Function]] = []          # pilha operacional
    bp, ip, cur = 0, func.ip, func

    for _ in range(max_steps):
        op, a = code[ip]
        if trace:
            trace(f"{ip:5}  {cur.name:<10} {op:<10} {' '.join(map(str, a)):<6} "
                  f"bp={bp:<3} {st}")
        ip += 1
        try:
            if op == "LOAD_CONST":
                st.append(consts[a[0]])
            elif op == "LOAD_VAR":
                st.append(st[bp + a[0]])
            elif op == "STORE_VAR":
                st[bp + a[0]] = st.pop()
            elif op == "LOAD_REF":
                st.append(a[0])
            elif op == "DE_REF":
                addr = bp + st.pop()
                cells = st[addr:addr + a[0]]
                if len(cells) != a[0]:
                    raise VMError("acesso fora do registro de ativação")
                st.extend(cells)
            elif op == "STORE_REF":
                n = a[0]
                cells = st[len(st) - n:]
                addr = bp + st[-n - 1]
                del st[-n - 1:]
                if addr + n > len(st):
                    raise VMError("acesso fora do registro de ativação")
                st[addr:addr + n] = cells
            elif op == "LOAD_TRUE":
                st.append(True)
            elif op == "LOAD_FALSE":
                st.append(False)
            elif op == "ADD":
                if a:
                    st[-1] += a[0]
                else:
                    y = st.pop()
                    st[-1] += y
            elif op == "SUB":
                y = st.pop()
                st[-1] -= y
            elif op == "MUL":
                if a:
                    st[-1] *= a[0]
                else:
                    y = st.pop()
                    st[-1] *= y
            elif op == "DIV":
                y = st.pop()
                if y == 0:
                    raise VMError("divisão por zero")
                x = st[-1]
                st[-1] = abs(x) // abs(y) * (1 if (x >= 0) == (y >= 0) else -1)
            elif op == "INC":
                st[-1] += 1
            elif op == "DEC":
                st[-1] -= 1
            elif op == "NEG":
                st[-1] = -st[-1]
            elif op == "AND":
                y = st.pop()
                st[-1] = bool(st[-1]) and bool(y)
            elif op == "OR":
                y = st.pop()
                st[-1] = bool(st[-1]) or bool(y)
            elif op == "NOT":
                st[-1] = not st[-1]
            elif op in ("EQ", "NEQ", "NE", "LT", "LE", "GT", "GE"):
                y = st.pop()
                x = st[-1]
                st[-1] = {"EQ": x == y, "NEQ": x != y, "NE": x != y, "LT": x < y,
                          "LE": x <= y, "GT": x > y, "GE": x >= y}[op]
            elif op in ("JMP_FW", "JMP_BW"):
                ip = a[0]
            elif op in ("TJMP_FW", "TJMP_BW"):
                if not st.pop():
                    ip = a[0]
            elif op == "DUP":
                st.append(st[-1])
            elif op == "POP":
                st.pop()
            elif op == "CHAR_AT":
                i = st.pop()
                s = st[bp + a[0]]
                st.append(_char_at(s, i))
            elif op == "SET_CHAR":
                c = st.pop()
                i = st.pop()
                s = st[bp + a[0]]
                if not 0 <= i <= len(s):
                    raise VMError(f"índice {i} fora da string {s!r}")
                st[bp + a[0]] = s[:i] + c + s[i + 1:]
            elif op == "CALL":
                f = functions[a[0]]
                ops.append((ip, bp, cur))
                bp = len(st) - f.n_params
                st.extend([0] * (f.n_vars - f.n_params))
                ip, cur = f.ip, f
            elif op == "RET":
                ret = st[bp + cur.n_vars:]
                del st[bp:]
                st.extend(ret)
                if not ops:
                    return ret
                ip, bp, cur = ops.pop()
            elif op == "END_FUNC":
                raise VMError(f"a função '{cur.name}' terminou sem executar return")
            else:
                raise VMError(f"instrução não suportada: {op}")
        except (TypeError, IndexError) as err:
            raise VMError(f"erro de execução em {op} (ip={ip - 1}, "
                          f"função '{cur.name}'): {err}") from None
    raise VMError(f"limite de {max_steps} instruções excedido")


def _char_at(s: str, i: int) -> str:
    if 0 <= i < len(s):
        return s[i]
    if i == len(s):
        return "\0"                    # terminador, como em C
    raise VMError(f"índice {i} fora da string {s!r}")


def format_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False) if len(v) != 1 else repr(v)
    return str(v)
