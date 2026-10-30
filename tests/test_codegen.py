"""Testes da geração de código e da máquina virtual. Rode com:  python -m unittest -v"""
from __future__ import annotations

import pathlib
import unittest

from compiler import CompileError, ErrorCode as E, assemble, compile_source, run

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples" / "codegen"


def asm(src: str, **kw) -> str:
    result = compile_source(src, **kw)
    assert not result.errors, [str(e) for e in result.errors]
    return result.asm


def body(src: str, **kw) -> list[str]:
    """Só as instruções e rótulos (sem pool de constantes nem comentários)."""
    return [line.strip() for line in asm(src, **kw).splitlines()
            if line and not line.startswith((";", "CONST"))]


def execute(src: str, entry=None, args=(), **kw):
    ret = run(assemble(asm(src, **kw)), entry, list(args))
    return ret[0] if len(ret) == 1 else ret


def error_codes(src: str) -> list[E]:
    return [e.code for e in compile_source(src).errors]


def fn(stmts: str, decls: str = "", ret: str = "integer") -> str:
    return f"function main(): {ret} {{ {decls} {stmts} }}"


class ApostilaExampleTests(unittest.TestCase):
    def test_fatorial_matches_section_7_4_1(self):
        # Mesmo código do exemplo 7.4.1, com duas correções: a comparação
        # `i <= n` gera LE (a apostila imprime LT por engano) e o tamanho das
        # variáveis em BEGIN_FUNC inclui os parâmetros, como mandam as regras
        # da seção 7.5 (fig. 7.18).
        src = (EXAMPLES / "fatorial.ssl").read_text()
        self.assertEqual(body(src), [
            "BEGIN_FUNC 0 1 3 ; fatorial",
            "LOAD_CONST 0", "STORE_VAR 1", "LOAD_CONST 1", "STORE_VAR 2",
            "L0:", "LOAD_VAR 1", "LOAD_VAR 0", "LE", "TJMP_FW L1",
            "LOAD_VAR 2", "LOAD_VAR 1", "DUP", "INC", "STORE_VAR 1", "MUL", "STORE_VAR 2",
            "JMP_BW L0", "L1:", "LOAD_VAR 2", "RET", "END_FUNC",
            "BEGIN_FUNC 1 1 3 ; somaFat",
            "LOAD_CONST 2", "STORE_VAR 1", "LOAD_CONST 3", "STORE_VAR 2",
            "L2:", "LOAD_VAR 1", "INC", "DUP", "STORE_VAR 1", "LOAD_VAR 0", "LE", "TJMP_FW L3",
            "LOAD_VAR 2", "LOAD_VAR 1", "CALL 0", "ADD", "STORE_VAR 2",
            "JMP_BW L2", "L3:", "LOAD_VAR 2", "RET", "END_FUNC",
        ])

    def test_examples_run_in_both_modes(self):
        cases = [
            ("fatorial.ssl", "fatorial", [6], 720),
            ("fatorial.ssl", "somaFat", [4], 1 + 2 + 6 + 24),
            ("bsort.ssl", None, [], list(range(10))),
            ("strings.ssl", None, [], "serodalipmoc / odnum ,alo"),
            ("structs.ssl", None, [], 97),
        ]
        for refs in (False, True):
            for name, entry, args, expected in cases:
                with self.subTest(example=name, entry=entry, refs=refs):
                    src = (EXAMPLES / name).read_text()
                    self.assertEqual(execute(src, entry, args, simple_vars=not refs), expected)

    def test_constant_pool_uses_secondary_tokens(self):
        text = asm(fn('return 7 + 7;', "var s: string; var c: char;"))
        self.assertIn("CONST 0 int 7\nCONST 1 int 7", text)
        text = asm(fn("s = \"a;b\"; c = '\\0'; return 0;", "var s: string; var c: char;"))
        self.assertIn('CONST 0 string "a;b"', text)
        self.assertIn('CONST 1 char "\\u0000"', text)


class CodeShapeTests(unittest.TestCase):
    def test_if_else_labels(self):
        code = body(fn("if (x < 1) x = 1; else x = 2; return x;", "var x: integer;"))
        i = code.index("TJMP_FW L0")
        self.assertEqual(code[i:i + 8], ["TJMP_FW L0", "LOAD_CONST 1", "STORE_VAR 0",
                                         "JMP_FW L1", "L0:", "LOAD_CONST 2", "STORE_VAR 0", "L1:"])

    def test_do_while_uses_not_and_backward_jump(self):
        code = body(fn("do x = x - 1; while (x > 0); return x;", "var x: integer;"))
        self.assertEqual(code[1], "L0:")
        i = code.index("GT")
        self.assertEqual(code[i:i + 3], ["GT", "NOT", "TJMP_BW L0"])

    def test_break_and_continue_targets(self):
        code = body(fn("while (true) { if (x) break; continue; } return 0;", "var x: boolean;"))
        self.assertEqual(code[1:4], ["L0:", "LOAD_TRUE", "TJMP_FW L1"])
        self.assertIn("JMP_FW L1", code)                 # break -> saída do while
        self.assertEqual(code.count("JMP_BW L0"), 2)     # continue + fim do laço
        code = body(fn("do { if (x) continue; break; } while (x); return 0;",
                       "var x: boolean;"))
        self.assertIn("JMP_FW L2", code)                 # continue -> antes de ||E||
        self.assertIn("JMP_FW L3", code)                 # break -> após o laço
        self.assertLess(code.index("L2:"), code.index("NOT"))

    def test_left_value_increments_fig_7_8(self):
        code = body(fn("return x++;", "var x: integer;"), simple_vars=False)
        self.assertEqual(code[1:10], ["LOAD_REF 0", "DUP", "DUP", "DE_REF 1", "INC",
                                      "STORE_REF 1", "DE_REF 1", "DEC", "RET"])
        code = body(fn("return --x;", "var x: integer;"), simple_vars=False)
        self.assertEqual(code[1:9], ["LOAD_REF 0", "DUP", "DUP", "DE_REF 1", "DEC",
                                     "STORE_REF 1", "DE_REF 1", "RET"])

    def test_struct_and_array_access(self):
        src = ("type p = struct { x, y: integer; n: string };"
               "type v = array [3] of p;" + fn("a[k].n = \"z\"; return a[2].y;",
                                               "var k: integer; var a: v;"))
        code = body(src)
        self.assertEqual(code[0], "BEGIN_FUNC 0 0 10 ; main")
        self.assertEqual(code[1:9], ["LOAD_REF 1", "LOAD_VAR 0", "MUL 3", "ADD", "ADD 2",
                                     "LOAD_CONST 1", "STORE_REF 1", "LOAD_REF 1"])
        self.assertEqual(code[9:15], ["LOAD_CONST 2", "MUL 3", "ADD", "ADD 1", "DE_REF 1", "RET"])

    def test_aggregate_assignment_and_args_copy_all_cells(self):
        src = ("type p = struct { x, y: integer };"
               "function f(a: p): p { return a; }" + fn("q = f(r); return 0;", "var q, r: p;"))
        code = body(src)
        self.assertEqual(code[1:4], ["LOAD_REF 0", "DE_REF 2", "RET"])
        i = code.index("BEGIN_FUNC 1 0 4 ; main")
        self.assertEqual(code[i + 1:i + 6], ["LOAD_REF 0", "LOAD_REF 2", "DE_REF 2",
                                             "CALL 0", "STORE_REF 2"])

    def test_vars_of_inner_blocks_share_function_numbering(self):
        code = body("function f(a: integer, b: integer): integer {"
                    " var x: integer; { var y: integer; y = 1; } { var z: integer; z = 2; }"
                    " return x; }")
        self.assertEqual(code[0], "BEGIN_FUNC 0 2 5 ; f")
        self.assertIn("STORE_VAR 3", code)
        self.assertIn("STORE_VAR 4", code)

    def test_expression_statement_pops_value(self):
        code = body("function f(): integer { return 1; }"
                    + fn("x++; f(); return x;", "var x: integer;"))
        self.assertEqual(code.count("POP"), 2)


class ExecutionTests(unittest.TestCase):
    def test_recursion(self):
        src = ("function fib(n: integer): integer {"
               " if (n < 2) return n; return fib(n - 1) + fib(n - 2); }")
        self.assertEqual(execute(src, "fib", [15]), 610)

    def test_pre_and_post_increment_values(self):
        for refs in (False, True):
            src = fn("i = 5; a = i++; b = ++i; c = i--; d = --i; return a*1000 + b*100 + c*10 + d;",
                     "var i, a, b, c, d: integer;")
            self.assertEqual(execute(src, simple_vars=not refs), 5000 + 700 + 70 + 5)

    def test_operators(self):
        self.assertEqual(execute(fn("return -7 / 2 + 10 - 2 * 3;")), -3 + 4)
        self.assertEqual(execute(fn("return !(1 < 2) || 3 >= 3 && 'a' != 'b';", ret="boolean")),
                         True)
        self.assertEqual(execute(fn('return "ab" + "cd" == "abcd";', ret="boolean")), True)

    def test_string_chars(self):
        src = fn("s = \"gato\"; s[0] = 'p'; s[4] = 's'; return s;", "var s: string;", "string")
        self.assertEqual(execute(src), "patos")

    def test_alias_types(self):
        src = "type nome = string; type n = integer;" + fn(
            's = "x"; k = 3; return k + 1;', "var s: nome; var k: n;", "n")
        self.assertEqual(execute(src), 4)

    def test_args_by_value(self):
        src = ("type v = array [2] of integer;"
               "function zera(a: v): integer { a[0] = 0; return 0; }"
               + fn("a[0] = 9; a[1] = 8; z = zera(a); return a[0];", "var a: v; var z: integer;"))
        self.assertEqual(execute(src), 9)


class ErrorTests(unittest.TestCase):
    def test_semantic_errors(self):
        cases = {
            fn("x = 1; return 0;"): [E.ERR_NOT_DECL],
            fn("return 0;", "var x: integer; var x: char;"): [E.ERR_REDECL],
            fn("x = 'a'; return 0;", "var x: integer;"): [E.ERR_TYPE_MISMATCH],
            fn("if (x) x = 1; return 0;", "var x: integer;"): [E.ERR_BOOL_TYPE_EXPECTED],
            fn("return x + true;", "var x: boolean;", "boolean"): [E.ERR_INVALID_TYPE],
            fn("x[0] = 1; return 0;", "var x: integer;"): [E.ERR_KIND_NOT_ARRAY],
            fn("x.a = 1; return 0;", "var x: integer;"): [E.ERR_KIND_NOT_STRUCT],
            fn("break; return 0;"): [E.ERR_BREAK_OUTSIDE_LOOP],
            fn("return 'c';"): [E.ERR_RETURN_TYPE],
            fn("return main(1);"): [E.ERR_TOO_MANY_ARGS],
            fn("return x(1);", "var x: integer;"): [E.ERR_KIND_NOT_FUNC],
            fn("return 0;", "var x: main;"): [E.ERR_TYPE_EXPECTED],
            "function f(a: integer): integer { return a; }" + fn("return f();"):
                [E.ERR_TOO_FEW_ARGS],
            "function f(a: integer): integer { return a; }" + fn("return f(true);"):
                [E.ERR_PARAM_TYPE],
            "type p = struct { a: integer };" + fn("return x.b;", "var x: p;"):
                [E.ERR_FIELD_NOT_DECL],
            fn("return s[true];", "var s: string;", "char"): [E.ERR_INVALID_INDEX_TYPE],
        }
        for src, expected in cases.items():
            with self.subTest(src=src):
                self.assertEqual(error_codes(src), expected)

    def test_no_code_when_errors(self):
        result = compile_source(fn("x = 1; return 0;"))
        self.assertIsNone(result.asm)

    def test_undeclared_reported_once(self):
        self.assertEqual(error_codes(fn("x = 1; x = x + 1; return x;")), [E.ERR_NOT_DECL])

    def test_syntax_and_lexical_errors_stop(self):
        for src in (fn("x = ;", "var x: integer;"), "var x: integer;", fn("return 1 # 2;")):
            with self.subTest(src=src):
                with self.assertRaises(CompileError):
                    compile_source(src)


if __name__ == "__main__":
    unittest.main()
