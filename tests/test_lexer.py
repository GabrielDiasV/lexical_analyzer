"""Testes do analisador léxico. Rode com:  python -m unittest -v"""
from __future__ import annotations

import unittest

from lexer import Lexer, LexicalError, TokenKind as T
from lexer.tables import search_keyword
from lexer.tokens import KEYWORDS


def kinds(src: str) -> list[T]:
    return [t.kind for t in Lexer(src).tokens(include_eof=False)]


def pairs(src: str) -> list[tuple[T, int | None]]:
    return [(t.kind, t.secondary) for t in Lexer(src).tokens(include_eof=False)]


class KeywordTableTests(unittest.TestCase):
    def test_vector_is_sorted_and_matches_enum(self):
        self.assertEqual(list(KEYWORDS), sorted(KEYWORDS))
        for i, kw in enumerate(KEYWORDS):
            self.assertEqual(T(i).name.lower(), kw)

    def test_binary_search_returns_position_as_token(self):
        for i, kw in enumerate(KEYWORDS):
            self.assertEqual(search_keyword(kw), T(i))

    def test_binary_search_non_keyword_is_id(self):
        for w in ("x", "whilex", "Integer", "arr", "zzz", "aaa", "structure"):
            self.assertEqual(search_keyword(w), T.ID)


class KeywordsAndIdentifiersTests(unittest.TestCase):
    def test_all_keywords_are_recognized(self):
        src = " ".join(KEYWORDS)
        self.assertEqual(kinds(src), [T(i) for i in range(len(KEYWORDS))])

    def test_keywords_have_no_secondary_token(self):
        for kind, sec in pairs("while if type"):
            self.assertIsNone(sec)

    def test_keywords_are_case_sensitive(self):
        # 'While' não é palavra reservada: vira identificador
        self.assertEqual(pairs("While while"), [(T.ID, 0), (T.WHILE, None)])

    def test_identifier_prefix_of_keyword_is_id(self):
        self.assertEqual(kinds("whilex iff d"), [T.ID, T.ID, T.ID])

    def test_id_regex_letter_then_letters_or_digits(self):
        self.assertEqual(kinds("a1b2 Z9"), [T.ID, T.ID])
        lx = Lexer("a1b2 Z9")
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual([t.lexeme for t in toks], ["a1b2", "Z9"])

    def test_underscore_is_not_part_of_id(self):
        # A gramática define Id = letra.(letra+digito)*; '_' está fora do alfabeto.
        with self.assertRaises(LexicalError):
            kinds("a_b")

    def test_secondary_token_is_order_of_first_appearance(self):
        self.assertEqual(
            pairs("x y x z y"),
            [(T.ID, 0), (T.ID, 1), (T.ID, 0), (T.ID, 2), (T.ID, 1)],
        )

    def test_name_table_stores_each_identifier_once(self):
        lx = Lexer("soma soma total soma")
        list(lx.tokens())
        self.assertEqual(len(lx.names), 2)
        self.assertEqual(lx.names.get_name(0), "soma")
        self.assertEqual(lx.names.get_name(1), "total")


class ConstantsTests(unittest.TestCase):
    def test_numeral(self):
        lx = Lexer("0 42 007")
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual([t.kind for t in toks], [T.NUMERAL] * 3)
        self.assertEqual([lx.consts.get_int_const(t.secondary) for t in toks], [0, 42, 7])

    def test_numeral_followed_by_letter_splits_into_two_tokens(self):
        # n = digito.digito*: '12abc' é NUMERAL 12 seguido de ID abc
        self.assertEqual(kinds("12abc"), [T.NUMERAL, T.ID])

    def test_string(self):
        lx = Lexer('"ola, mundo" ""')
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual([t.kind for t in toks], [T.STRINGVAL, T.STRINGVAL])
        self.assertEqual(lx.consts.get_string_const(toks[0].secondary), "ola, mundo")
        self.assertEqual(lx.consts.get_string_const(toks[1].secondary), "")

    def test_string_may_contain_symbols_and_keywords(self):
        lx = Lexer('"while (x <= 3) { y++; }"')
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].kind, T.STRINGVAL)

    def test_character(self):
        lx = Lexer("'a' '+' ' '")
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual([t.kind for t in toks], [T.CHARACTER] * 3)
        self.assertEqual([lx.consts.get_char_const(t.secondary) for t in toks], ["a", "+", " "])

    def test_constants_share_one_numbering(self):
        lx = Lexer("1 'c' \"s\" 2")
        toks = list(lx.tokens(include_eof=False))
        self.assertEqual([t.secondary for t in toks], [0, 1, 2, 3])
        self.assertEqual(lx.consts.get(1).type, "char")
        self.assertEqual(lx.consts.get(2).type, "string")

    def test_unterminated_string_is_error(self):
        with self.assertRaises(LexicalError):
            kinds('"abc')

    def test_char_with_two_characters_is_error(self):
        with self.assertRaises(LexicalError):
            kinds("'ab'")

    def test_true_false_are_keywords_not_constants(self):
        self.assertEqual(pairs("true false"), [(T.TRUE, None), (T.FALSE, None)])


class SymbolsTests(unittest.TestCase):
    def test_single_char_symbols(self):
        self.assertEqual(
            kinds(": ; , [ ] { } ( ) * / ."),
            [T.COLON, T.SEMI_COLON, T.COMMA, T.LEFT_SQUARE, T.RIGHT_SQUARE,
             T.LEFT_BRACES, T.RIGHT_BRACES, T.LEFT_PARENTHESIS, T.RIGHT_PARENTHESIS,
             T.TIMES, T.DIVIDE, T.DOT],
        )

    def test_two_char_symbols(self):
        self.assertEqual(
            kinds("== <= >= != ++ -- && ||"),
            [T.EQUAL_EQUAL, T.LESS_OR_EQUAL, T.GREATER_OR_EQUAL, T.NOT_EQUAL,
             T.PLUS_PLUS, T.MINUS_MINUS, T.AND, T.OR],
        )

    def test_one_char_versions_of_two_char_symbols(self):
        self.assertEqual(
            kinds("= < > ! + -"),
            [T.EQUALS, T.LESS_THAN, T.GREATER_THAN, T.NOT, T.PLUS, T.MINUS],
        )

    def test_lookahead_splits_symbols_without_spaces(self):
        # a+b: ao ler '+', 'a' acabou; o '+' não pode ser descartado.
        self.assertEqual(kinds("a+b"), [T.ID, T.PLUS, T.ID])
        self.assertEqual(kinds("a++b"), [T.ID, T.PLUS_PLUS, T.ID])
        self.assertEqual(kinds("a+++b"), [T.ID, T.PLUS_PLUS, T.PLUS, T.ID])
        self.assertEqual(kinds("x<=y"), [T.ID, T.LESS_OR_EQUAL, T.ID])
        self.assertEqual(kinds("x<y"), [T.ID, T.LESS_THAN, T.ID])
        self.assertEqual(kinds("x==y"), [T.ID, T.EQUAL_EQUAL, T.ID])
        self.assertEqual(kinds("x=y"), [T.ID, T.EQUALS, T.ID])
        self.assertEqual(kinds("x=-1"), [T.ID, T.EQUALS, T.MINUS, T.NUMERAL])

    def test_lone_ampersand_or_pipe_is_error(self):
        with self.assertRaises(LexicalError):
            kinds("a & b")
        with self.assertRaises(LexicalError):
            kinds("a | b")


class WhitespaceAndPositionTests(unittest.TestCase):
    def test_separators_are_skipped(self):
        self.assertEqual(kinds("  \t var\n\n  x \r\n:integer ;  "),
                         [T.VAR, T.ID, T.COLON, T.INTEGER, T.SEMI_COLON])

    def test_empty_input_gives_only_eof(self):
        self.assertEqual([t.kind for t in Lexer("").tokens()], [T.EOF])
        self.assertEqual([t.kind for t in Lexer("   \n\t ").tokens()], [T.EOF])

    def test_line_and_column(self):
        toks = list(Lexer("var x;\n  y = 10;").tokens(include_eof=False))
        self.assertEqual([(t.lexeme, t.line, t.col) for t in toks], [
            ("var", 1, 1), ("x", 1, 5), (";", 1, 6),
            ("y", 2, 3), ("=", 2, 5), ("10", 2, 7), (";", 2, 9),
        ])


class ErrorHandlingTests(unittest.TestCase):
    def test_invalid_character_raises_with_position(self):
        with self.assertRaises(LexicalError) as cm:
            kinds("x = 3 # 4;")
        self.assertEqual((cm.exception.line, cm.exception.col), (1, 7))

    def test_lenient_mode_emits_unknown_and_continues(self):
        toks = list(Lexer("x # y", strict=False).tokens(include_eof=False))
        self.assertEqual([t.kind for t in toks], [T.ID, T.UNKNOWN, T.ID])


class ProgramTests(unittest.TestCase):
    def test_full_declaration(self):
        src = "var a, b: integer;"
        self.assertEqual(pairs(src), [
            (T.VAR, None), (T.ID, 0), (T.COMMA, None), (T.ID, 1),
            (T.COLON, None), (T.INTEGER, None), (T.SEMI_COLON, None),
        ])

    def test_function_header(self):
        src = "function f(a: integer, b: char): boolean {"
        self.assertEqual(kinds(src), [
            T.FUNCTION, T.ID, T.LEFT_PARENTHESIS, T.ID, T.COLON, T.INTEGER, T.COMMA,
            T.ID, T.COLON, T.CHAR, T.RIGHT_PARENTHESIS, T.COLON, T.BOOLEAN, T.LEFT_BRACES,
        ])

    def test_type_declarations(self):
        src = "type v = array [ 10 ] of integer; type p = struct { x: integer };"
        self.assertEqual(kinds(src), [
            T.TYPE, T.ID, T.EQUALS, T.ARRAY, T.LEFT_SQUARE, T.NUMERAL, T.RIGHT_SQUARE,
            T.OF, T.INTEGER, T.SEMI_COLON,
            T.TYPE, T.ID, T.EQUALS, T.STRUCT, T.LEFT_BRACES, T.ID, T.COLON, T.INTEGER,
            T.RIGHT_BRACES, T.SEMI_COLON,
        ])

    def test_expression_with_all_operator_levels(self):
        src = "ok = (p.x != 21) || !(p.y >= 0) && v[i] * 2 / 1 - -3;"
        self.assertEqual(kinds(src), [
            T.ID, T.EQUALS, T.LEFT_PARENTHESIS, T.ID, T.DOT, T.ID, T.NOT_EQUAL, T.NUMERAL,
            T.RIGHT_PARENTHESIS, T.OR, T.NOT, T.LEFT_PARENTHESIS, T.ID, T.DOT, T.ID,
            T.GREATER_OR_EQUAL, T.NUMERAL, T.RIGHT_PARENTHESIS, T.AND, T.ID, T.LEFT_SQUARE,
            T.ID, T.RIGHT_SQUARE, T.TIMES, T.NUMERAL, T.DIVIDE, T.NUMERAL, T.MINUS, T.MINUS,
            T.NUMERAL, T.SEMI_COLON,
        ])

    def test_example_files_tokenize_without_error(self):
        import pathlib
        here = pathlib.Path(__file__).resolve().parent.parent / "examples"
        for name in ("fatorial.ssl", "tipos.ssl"):
            toks = list(Lexer((here / name).read_text()).tokens())
            self.assertEqual(toks[-1].kind, T.EOF, name)
            self.assertNotIn(T.UNKNOWN, [t.kind for t in toks], name)


if __name__ == "__main__":
    unittest.main()
