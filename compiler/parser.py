"""Tradução dirigida pela sintaxe: análise sintática, de escopo, de tipos e
geração de código numa única passada (caps. 3 a 7 da apostila).

O analisador é descendente por descida recursiva (seção 3.4). As regras com
recursão à esquerda da gramática (LDE, LS, E, L, R, Y, LV, LP, LI, DC, LE)
viram laços, o que preserva a associatividade à esquerda. As regras de
atributos das figuras 5.8, 6.x e 7.12–7.29 são executadas no ponto da
derivação em que a apostila as coloca; os marcadores semânticos (NB, NF, MF,
MT, ME, MW, MC) aparecem como comentários no código.

Extensões em relação à gramática da seção 2.1, todas exigidas pelos exemplos
do cap. 7 ou pela máquina virtual:
  - `return E ;` (gera ||E|| RET), usado em todos os exemplos da seção 7.4;
  - expressões como comando (`i++;`, `f(x);`), seguidas de POP (seção 7.3);
  - lista de parâmetros, lista de argumentos, LDV e LS podem ser vazias;
  - `;` opcional após uma declaração de tipo e após o último campo de struct;
  - indexação de string `s[i]` com CHAR_AT / SET_CHAR (figs. 7.9 e 7.29).
Variáveis globais não existem: o endereçamento da máquina é relativo ao BP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from lexer import Lexer, LexicalError, Token, TokenKind as T

from .codegen import CodeEmitter
from .errors import CompileError, ErrorCode as E, SemanticError
from .symbols import (P_BOOL, P_CHAR, P_INTEGER, P_STRING, P_UNIVERSAL, TYPE_KINDS,
                      Kind, Object, SymbolTable, check_types, is_scalar, resolve)

# Primeiros símbolos de E que não são identificadores (comando-expressão).
_EXPR_FIRST = {T.PLUS_PLUS, T.MINUS_MINUS, T.LEFT_PARENTHESIS, T.MINUS, T.NOT,
               T.TRUE, T.FALSE, T.CHARACTER, T.STRINGVAL, T.NUMERAL}

_REL_OPS = {T.LESS_THAN: "LT", T.GREATER_THAN: "GT", T.LESS_OR_EQUAL: "LE",
            T.GREATER_OR_EQUAL: "GE", T.EQUAL_EQUAL: "EQ", T.NOT_EQUAL: "NEQ"}

_SCALAR_TYPES = {T.INTEGER: P_INTEGER, T.CHAR: P_CHAR, T.BOOLEAN: P_BOOL, T.STRING: P_STRING}

_DESCR = {T.SEMI_COLON: "';'", T.COLON: "':'", T.COMMA: "','", T.EQUALS: "'='",
          T.LEFT_SQUARE: "'['", T.RIGHT_SQUARE: "']'", T.LEFT_BRACES: "'{'",
          T.RIGHT_BRACES: "'}'", T.LEFT_PARENTHESIS: "'('", T.RIGHT_PARENTHESIS: "')'",
          T.ID: "identificador", T.NUMERAL: "número", T.EOF: "fim de arquivo"}


@dataclass
class LValue:
    """Atributos sintetizados de LV.

    kind    -- "ref": endereço (deslocamento a partir do BP) no topo da pilha;
               "char": caractere de uma string, s[E] (índice já na pilha)
    type    -- LV.type
    var     -- variável/parâmetro base
    pending -- LV é um identificador simples cujo LOAD_REF ainda não foi
               emitido: permite usar LOAD_VAR/STORE_VAR (fig. 7.9) em vez de
               LOAD_REF + DE_REF/STORE_REF (fig. 7.8) quando o tamanho é 1
    """
    kind: str
    type: Object
    var: Optional[Object] = None
    pending: bool = False


@dataclass
class Loop:
    """Destinos de break/continue do comando de repetição corrente."""
    cont: Optional[int]
    cont_backward: bool
    brk: Optional[int]


@dataclass
class CompileResult:
    asm: Optional[str]                          # None se houve erro semântico
    errors: list[SemanticError]
    functions: list[Object] = field(default_factory=list)


class Parser:
    def __init__(self, source: str, simple_vars: bool = True) -> None:
        """simple_vars -- usa LOAD_VAR/STORE_VAR para variáveis escalares
        simples (fig. 7.9); False gera sempre a forma geral com LOAD_REF."""
        self.lexer = Lexer(source)
        self.scope = SymbolTable()
        self.code = CodeEmitter()
        self.errors: list[SemanticError] = []
        self.functions: list[Object] = []
        self.simple_vars = simple_vars
        self.cur_function: Optional[Object] = None
        self.loops: list[Loop] = []
        self.tok: Token = self._next()

    # ================================================================ apoio
    def _next(self) -> Token:
        try:
            return self.lexer.next_token()
        except LexicalError as err:
            raise CompileError(f"erro léxico: {err.args[0].split(': ', 1)[-1]}",
                               err.line, err.col) from None

    def _advance(self) -> Token:
        tok = self.tok
        self.tok = self._next()
        return tok

    def _syntax_error(self, expected: str) -> CompileError:
        found = self.tok.lexeme or _DESCR.get(self.tok.kind, self.tok.kind.name)
        return CompileError(f"erro sintático: esperado {expected}, encontrado '{found}'",
                            self.tok.line, self.tok.col)

    def _expect(self, kind: T) -> Token:
        if self.tok.kind != kind:
            raise self._syntax_error(_DESCR.get(kind, f"'{kind.name.lower()}'"))
        return self._advance()

    def _accept(self, kind: T) -> bool:
        if self.tok.kind == kind:
            self._advance()
            return True
        return False

    def _error(self, code: E, tok: Token, arg: object = "") -> None:
        self.errors.append(SemanticError(code, tok.line, tok.col, str(arg)))

    # ======================================================= identificadores
    def _idd(self) -> Object:
        """IDD (fig. 5.8): declaração. Em redeclaração devolve um objeto avulso,
        fora da tabela, para não corromper o objeto original."""
        tok = self._expect(T.ID)
        if self.scope.search(tok.secondary) is not None:
            self._error(E.ERR_REDECL, tok, tok.lexeme)
            return Object(tok.secondary, text=tok.lexeme)
        return self.scope.define(tok.secondary, tok.lexeme)

    def _idu(self) -> tuple[Object, Token]:
        """IDU (fig. 5.8): uso. Não declarado é definido como Universal para
        evitar mensagens repetidas."""
        tok = self._expect(T.ID)
        obj = self.scope.find(tok.secondary)
        if obj is None:
            self._error(E.ERR_NOT_DECL, tok, tok.lexeme)
            obj = self.scope.define(tok.secondary, tok.lexeme)
            obj.kind, obj.type = Kind.UNIVERSAL, P_UNIVERSAL
        return obj, tok

    # =================================================================== P
    def parse_program(self) -> CompileResult:
        """P -> LDE ;  LDE -> LDE DE | DE ;  DE -> DF | DT"""
        while self.tok.kind != T.EOF:
            if self.tok.kind == T.FUNCTION:
                self._function_decl()
            elif self.tok.kind == T.TYPE:
                self._type_decl()
            elif self.tok.kind == T.VAR:
                raise CompileError("variáveis globais não são suportadas pela máquina "
                                   "virtual: declare-as dentro de uma função",
                                   self.tok.line, self.tok.col)
            else:
                raise self._syntax_error("'function' ou 'type'")
        asm = None if self.errors else self.code.text(self.lexer.consts)
        return CompileResult(asm, self.errors, self.functions)

    # ============================================================ tipos (T)
    def _type(self) -> Object:
        """T -> 'integer' | 'char' | 'boolean' | 'string' | IDU   (fig. 7.12)"""
        if self.tok.kind in _SCALAR_TYPES:
            return _SCALAR_TYPES[self._advance().kind]
        if self.tok.kind != T.ID:
            raise self._syntax_error("tipo")
        p, tok = self._idu()
        if p.kind in TYPE_KINDS:
            return p
        if p.kind != Kind.UNIVERSAL:
            self._error(E.ERR_TYPE_EXPECTED, tok, tok.lexeme)
        return P_UNIVERSAL

    def _type_decl(self) -> None:
        """DT (figs. 7.13, 7.14, 7.16)"""
        self._expect(T.TYPE)
        p = self._idd()
        self._expect(T.EQUALS)
        if self._accept(T.ARRAY):
            # DT -> 'type' IDD '=' 'array' '[' NUM ']' 'of' T
            self._expect(T.LEFT_SQUARE)
            num = self._expect(T.NUMERAL)
            n = self.lexer.consts.get_int_const(num.secondary)
            self._expect(T.RIGHT_SQUARE)
            self._expect(T.OF)
            t = self._type()
            if n <= 0:
                self._error(E.ERR_ARRAY_SIZE, num)
            p.kind = Kind.ARRAY_TYPE
            p.num_elems, p.elem_type, p.size = n, t, n * t.size
        elif self._accept(T.STRUCT):
            # DT -> 'type' IDD '=' 'struct' NB '{' DC '}'
            self.scope.new_block()                                   # NB
            self._expect(T.LEFT_BRACES)
            fields, size = self._field_decls()
            self._expect(T.RIGHT_BRACES)
            p.kind = Kind.STRUCT_TYPE
            p.fields, p.size = fields, size
            self.scope.end_block()
        else:
            # DT -> 'type' IDD '=' T
            t = self._type()
            p.kind = Kind.ALIAS_TYPE
            p.base_type, p.size = t, t.size
        self._accept(T.SEMI_COLON)

    def _field_decls(self) -> tuple[list[Object], int]:
        """DC -> DC ';' LI ':' T | LI ':' T   (fig. 7.15)"""
        fields: list[Object] = []
        n = 0
        while True:
            ids = self._id_list()
            self._expect(T.COLON)
            t = self._type()
            for p in ids:
                p.kind, p.type, p.index, p.size = Kind.FIELD, t, n, t.size
                n += t.size
            fields += ids
            if not self._accept(T.SEMI_COLON) or self.tok.kind == T.RIGHT_BRACES:
                return fields, n

    def _id_list(self) -> list[Object]:
        """LI -> LI ',' IDD | IDD"""
        ids = [self._idd()]
        while self._accept(T.COMMA):
            ids.append(self._idd())
        return ids

    # ============================================================== funções
    def _function_decl(self) -> None:
        """DF -> 'function' IDD NF '(' LP ')' ':' T MF B   (fig. 7.18)"""
        self._expect(T.FUNCTION)
        f = self._idd()
        # NF: a numeração de parâmetros e variáveis começa em 0
        f.kind = Kind.FUNCTION
        f.index = len(self.functions)
        self.functions.append(f)
        self.scope.new_block()
        self._expect(T.LEFT_PARENTHESIS)
        params, size = self._param_list()
        self._expect(T.RIGHT_PARENTHESIS)
        self._expect(T.COLON)
        t = self._type()
        # MF: completa o objeto da função e grava o cabeçalho com v provisório
        f.ret_type, f.params, f.n_params, f.n_vars = t, params, size, size
        self.cur_function = f
        offset = self.code.begin_func(f.index, f.n_params, f.text)
        # B: o corpo compartilha o nível dos parâmetros
        self._block(new_scope=False)
        self.code.end_func(offset, f.index, f.n_params, f.n_vars, f.text)
        self.scope.end_block()
        self.cur_function = None

    def _param_list(self) -> tuple[list[Object], int]:
        """LP -> LP ',' IDD ':' T | IDD ':' T | ε   (fig. 7.17)"""
        params: list[Object] = []
        n = 0
        if self.tok.kind == T.RIGHT_PARENTHESIS:
            return params, n
        while True:
            p = self._idd()
            self._expect(T.COLON)
            t = self._type()
            p.kind, p.type, p.index, p.size = Kind.PARAM, t, n, t.size
            n += t.size
            params.append(p)
            if not self._accept(T.COMMA):
                return params, n

    def _block(self, new_scope: bool) -> None:
        """B -> '{' LDV LS '}'"""
        self._expect(T.LEFT_BRACES)
        if new_scope:
            self.scope.new_block()
        while self.tok.kind == T.VAR:
            self._var_decl()
        while self.tok.kind != T.RIGHT_BRACES:
            self._statement()
        self._expect(T.RIGHT_BRACES)
        if new_scope:
            self.scope.end_block()

    def _var_decl(self) -> None:
        """DV -> 'var' LI ':' T ';'   (fig. 7.19)

        Todas as variáveis de uma função compartilham a numeração, mesmo em
        blocos internos: o índice continua de curFunction.nVars."""
        self._expect(T.VAR)
        ids = self._id_list()
        self._expect(T.COLON)
        t = self._type()
        self._expect(T.SEMI_COLON)
        n = self.cur_function.n_vars
        for p in ids:
            p.kind, p.type, p.index, p.size = Kind.VAR, t, n, t.size
            n += t.size
        self.cur_function.n_vars = n

    # ============================================================ comandos
    def _statement(self) -> None:
        k = self.tok.kind
        if k == T.IF:
            self._if()
        elif k == T.WHILE:
            self._while()
        elif k == T.DO:
            self._do_while()
        elif k == T.LEFT_BRACES:
            self._block(new_scope=True)
        elif k in (T.BREAK, T.CONTINUE):
            self._break_continue()
        elif k == T.RETURN:
            self._return()
        elif k == T.ID:
            self._id_statement()
        elif k in _EXPR_FIRST:
            t = self._expr()
            self._expect(T.SEMI_COLON)
            self._pop(t)
        else:
            raise self._syntax_error("comando")

    def _check_bool(self, t: Object, tok: Token) -> None:
        if not check_types(t, P_BOOL):
            self._error(E.ERR_BOOL_TYPE_EXPECTED, tok)

    def _if(self) -> None:
        """S -> 'if' '(' E ')' MT S | 'if' '(' E ')' MT S 'else' ME S   (fig. 7.21)"""
        self._expect(T.IF)
        self._expect(T.LEFT_PARENTHESIS)
        tok = self.tok
        t = self._expr()
        self._expect(T.RIGHT_PARENTHESIS)
        self._check_bool(t, tok)
        l1 = self.code.new_label()                                   # MT
        self.code.emit("TJMP_FW", f"L{l1}")
        self._statement()
        if self._accept(T.ELSE):
            l2 = self.code.new_label()                               # ME
            self.code.emit("JMP_FW", f"L{l2}")
            self.code.label(l1)
            self._statement()
            self.code.label(l2)
        else:
            self.code.label(l1)

    def _while(self) -> None:
        """S -> 'while' MW '(' E ')' MT S   (fig. 7.22)"""
        self._expect(T.WHILE)
        l1 = self.code.new_label()                                   # MW
        self.code.label(l1)
        self._expect(T.LEFT_PARENTHESIS)
        tok = self.tok
        t = self._expr()
        self._expect(T.RIGHT_PARENTHESIS)
        self._check_bool(t, tok)
        l2 = self.code.new_label()                                   # MT
        self.code.emit("TJMP_FW", f"L{l2}")
        self.loops.append(Loop(cont=l1, cont_backward=True, brk=l2))
        self._statement()
        self.loops.pop()
        self.code.emit("JMP_BW", f"L{l1}")
        self.code.label(l2)

    def _do_while(self) -> None:
        """S -> 'do' MW S 'while' '(' E ')' ';'   (fig. 7.22)

        Os rótulos de continue (antes de ||E||) e de break (após o laço) só
        são criados se algum desses comandos aparecer no corpo."""
        self._expect(T.DO)
        l1 = self.code.new_label()                                   # MW
        self.code.label(l1)
        loop = Loop(cont=None, cont_backward=False, brk=None)
        self.loops.append(loop)
        self._statement()
        self.loops.pop()
        self._expect(T.WHILE)
        self._expect(T.LEFT_PARENTHESIS)
        if loop.cont is not None:
            self.code.label(loop.cont)
        tok = self.tok
        t = self._expr()
        self._expect(T.RIGHT_PARENTHESIS)
        self._expect(T.SEMI_COLON)
        self._check_bool(t, tok)
        self.code.emit("NOT")
        self.code.emit("TJMP_BW", f"L{l1}")
        if loop.brk is not None:
            self.code.label(loop.brk)

    def _break_continue(self) -> None:
        """S -> 'break' ';' (JMP_FW L)  |  'continue' ';' (JMP_BW L / JMP_FW L)"""
        tok = self._advance()
        self._expect(T.SEMI_COLON)
        if not self.loops:
            self._error(E.ERR_BREAK_OUTSIDE_LOOP, tok, tok.lexeme)
            return
        loop = self.loops[-1]
        if tok.kind == T.BREAK:
            if loop.brk is None:
                loop.brk = self.code.new_label()
            self.code.emit("JMP_FW", f"L{loop.brk}")
        else:
            if loop.cont is None:
                loop.cont = self.code.new_label()
            self.code.emit("JMP_BW" if loop.cont_backward else "JMP_FW", f"L{loop.cont}")

    def _return(self) -> None:
        """S -> 'return' E ';'   gera ||E|| RET"""
        self._expect(T.RETURN)
        tok = self.tok
        t = self._expr()
        self._expect(T.SEMI_COLON)
        if not check_types(self.cur_function.ret_type, t):
            self._error(E.ERR_RETURN_TYPE, tok)
        self.code.emit("RET")

    def _id_statement(self) -> None:
        """S -> LV '=' E ';'  |  E ';'  (comando iniciado por identificador)"""
        obj, tok = self._idu()
        if self.tok.kind == T.LEFT_PARENTHESIS:
            prefix: Union[LValue, Object] = self._call(obj, tok)
        else:
            prefix = self._lvalue(obj, tok)
            if self.tok.kind == T.EQUALS:
                self._assignment(prefix)
                return
        t = self._expr(prefix)
        self._expect(T.SEMI_COLON)
        self._pop(t)

    def _pop(self, t: Object) -> None:
        """Expressão como comando: descarta o valor (todas as suas células)."""
        for _ in range(resolve(t).size):
            self.code.emit("POP")

    def _assignment(self, lv: LValue) -> None:
        """S -> LV '=' E ';'  (figs. 7.8 e 7.23)  |  IDU '[' E1 ']' '=' E2 (SET_CHAR)"""
        eq = self._expect(T.EQUALS)
        if lv.kind == "char":
            t = self._expr()
            self._expect(T.SEMI_COLON)
            if not check_types(t, P_CHAR):
                self._error(E.ERR_TYPE_MISMATCH, eq)
            self.code.emit("SET_CHAR", lv.var.index)
            return
        simple = lv.pending and resolve(lv.type).size == 1
        if not simple:
            self._materialize(lv)            # o endereço deve preceder ||E||
        t = self._expr()
        self._expect(T.SEMI_COLON)
        if not check_types(lv.type, t):
            self._error(E.ERR_TYPE_MISMATCH, eq)
        if simple:
            self.code.emit("STORE_VAR", lv.var.index)
        else:
            self.code.emit("STORE_REF", resolve(lv.type).size)

    # ========================================================== left-values
    def _materialize(self, lv: LValue) -> None:
        """Emite o LOAD_REF adiado de um identificador simples."""
        if lv.pending:
            self.code.emit("LOAD_REF", lv.var.index)
            lv.pending = False

    def _lvalue(self, obj: Object, tok: Token) -> LValue:
        """LV -> LV '.' ID | LV '[' E ']' | IDU   (fig. 7.27)"""
        if obj.kind not in (Kind.VAR, Kind.PARAM):
            if obj.kind != Kind.UNIVERSAL:
                self._error(E.ERR_KIND_NOT_VAR, tok, tok.lexeme)
            lv = LValue("ref", P_UNIVERSAL)
        elif resolve(obj.type) is P_STRING and self.tok.kind == T.LEFT_SQUARE:
            # IDU '[' E ']' sobre string: acesso a caractere (fig. 7.29)
            self._advance()
            itok = self.tok
            t = self._expr()
            self._expect(T.RIGHT_SQUARE)
            if not check_types(t, P_INTEGER):
                self._error(E.ERR_INVALID_INDEX_TYPE, itok)
            return LValue("char", P_CHAR, obj)
        else:
            lv = LValue("ref", obj.type, obj, pending=True)
            if not self.simple_vars:
                self._materialize(lv)

        while self.tok.kind in (T.DOT, T.LEFT_SQUARE):
            self._materialize(lv)
            t = resolve(lv.type)
            if self._accept(T.DOT):
                ftok = self._expect(T.ID)
                if t.kind != Kind.STRUCT_TYPE:
                    if t.kind != Kind.UNIVERSAL:
                        self._error(E.ERR_KIND_NOT_STRUCT, ftok, tok.lexeme)
                    lv.type = P_UNIVERSAL
                    continue
                fld = next((p for p in t.fields if p.name == ftok.secondary), None)
                if fld is None:
                    self._error(E.ERR_FIELD_NOT_DECL, ftok, ftok.lexeme)
                    lv.type = P_UNIVERSAL
                else:
                    self.code.emit("ADD", fld.index)
                    lv.type = fld.type
            else:
                self._advance()
                itok = self.tok
                ti = self._expr()
                self._expect(T.RIGHT_SQUARE)
                if t.kind != Kind.ARRAY_TYPE:
                    if t.kind != Kind.UNIVERSAL:
                        self._error(E.ERR_KIND_NOT_ARRAY, itok, tok.lexeme)
                    lv.type = P_UNIVERSAL
                else:
                    self.code.emit("MUL", resolve(t.elem_type).size)
                    self.code.emit("ADD")
                    lv.type = t.elem_type
                if not check_types(ti, P_INTEGER):
                    self._error(E.ERR_INVALID_INDEX_TYPE, itok)
        return lv

    def _lv_value(self, lv: LValue) -> Object:
        """F -> LV | LV '++' | LV '--'  (left-value usado como right-value)"""
        if self.tok.kind in (T.PLUS_PLUS, T.MINUS_MINUS):
            op = self._advance()
            return self._inc_dec(lv, op, prefix=False)
        if lv.kind == "char":
            self.code.emit("CHAR_AT", lv.var.index)
            return P_CHAR
        size = resolve(lv.type).size
        if lv.pending and size == 1:
            self.code.emit("LOAD_VAR", lv.var.index)
        else:
            self._materialize(lv)
            self.code.emit("DE_REF", size)
        return lv.type

    def _inc_dec(self, lv: LValue, op: Token, prefix: bool) -> Object:
        """'++' LV | '--' LV | LV '++' | LV '--'   (figs. 7.8 e 7.9)"""
        if lv.kind == "char" or not check_types(lv.type, P_INTEGER):
            self._error(E.ERR_INVALID_TYPE, op, "char" if lv.kind == "char"
                        else resolve(lv.type).text)
            return P_UNIVERSAL
        step, undo = ("INC", "DEC") if op.kind == T.PLUS_PLUS else ("DEC", "INC")
        c = self.code
        if lv.pending:
            n = lv.var.index
            c.emit("LOAD_VAR", n)
            if prefix:
                c.emit(step)
                c.emit("DUP")
            else:
                c.emit("DUP")
                c.emit(step)
            c.emit("STORE_VAR", n)
        else:
            c.emit("DUP")
            c.emit("DUP")
            c.emit("DE_REF", 1)
            c.emit(step)
            c.emit("STORE_REF", 1)
            c.emit("DE_REF", 1)
            if not prefix:
                c.emit(undo)
        return P_INTEGER

    # =========================================================== expressões
    # Cada nível aceita um `prefix`: o 1º operando já reconhecido (um LV ou o
    # tipo de uma chamada), usado quando o comando começa por identificador.
    def _expr(self, prefix: Union[LValue, Object, None] = None) -> Object:
        """E -> E '&&' L | E '||' L | L   (fig. 7.23)"""
        t = self._relational(prefix)
        while self.tok.kind in (T.AND, T.OR):
            op = self._advance()
            t2 = self._relational()
            self._check_bool(t, op)
            self._check_bool(t2, op)
            self.code.emit("AND" if op.kind == T.AND else "OR")
            t = P_BOOL
        return t

    def _relational(self, prefix=None) -> Object:
        """L -> L relop R | R   (fig. 7.24)"""
        t = self._arith(prefix)
        while self.tok.kind in _REL_OPS:
            op = self._advance()
            t2 = self._arith()
            if not check_types(t, t2):
                self._error(E.ERR_TYPE_MISMATCH, op)
            elif not (is_scalar(t) and is_scalar(t2)):
                self._error(E.ERR_INVALID_TYPE, op, resolve(t).text)
            self.code.emit(_REL_OPS[op.kind])
            t = P_BOOL
        return t

    def _arith(self, prefix=None) -> Object:
        """R -> R '+' Y | R '-' Y | Y   (fig. 7.25)"""
        t = self._term(prefix)
        while self.tok.kind in (T.PLUS, T.MINUS):
            op = self._advance()
            t2 = self._term()
            if not check_types(t, t2):
                self._error(E.ERR_TYPE_MISMATCH, op)
            elif not (check_types(t, P_INTEGER) or
                      (op.kind == T.PLUS and check_types(t, P_STRING))):
                self._error(E.ERR_INVALID_TYPE, op, resolve(t).text)
            self.code.emit("ADD" if op.kind == T.PLUS else "SUB")
        return t

    def _term(self, prefix=None) -> Object:
        """Y -> Y '*' F | Y '/' F | F   (fig. 7.25)"""
        t = self._factor(prefix)
        while self.tok.kind in (T.TIMES, T.DIVIDE):
            op = self._advance()
            t2 = self._factor()
            if not check_types(t, t2):
                self._error(E.ERR_TYPE_MISMATCH, op)
            elif not check_types(t, P_INTEGER):
                self._error(E.ERR_INVALID_TYPE, op, resolve(t).text)
            self.code.emit("MUL" if op.kind == T.TIMES else "DIV")
        return t

    def _factor(self, prefix=None) -> Object:
        """F (figs. 7.7, 7.8, 7.10, 7.26)"""
        if isinstance(prefix, LValue):
            return self._lv_value(prefix)
        if prefix is not None:
            return prefix
        k = self.tok.kind
        c = self.code
        if k in (T.PLUS_PLUS, T.MINUS_MINUS):
            op = self._advance()
            obj, tok = self._idu()
            return self._inc_dec(self._lvalue(obj, tok), op, prefix=True)
        if k == T.LEFT_PARENTHESIS:
            self._advance()
            t = self._expr()
            self._expect(T.RIGHT_PARENTHESIS)
            return t
        if k == T.MINUS:
            op = self._advance()
            t = self._factor()
            if not check_types(t, P_INTEGER):
                self._error(E.ERR_INVALID_TYPE, op, resolve(t).text)
            c.emit("NEG")
            return P_INTEGER
        if k == T.NOT:
            op = self._advance()
            t = self._factor()
            if not check_types(t, P_BOOL):
                self._error(E.ERR_INVALID_TYPE, op, resolve(t).text)
            c.emit("NOT")
            return P_BOOL
        if k == T.TRUE:
            self._advance()
            c.emit("LOAD_TRUE")
            return P_BOOL
        if k == T.FALSE:
            self._advance()
            c.emit("LOAD_FALSE")
            return P_BOOL
        if k in (T.CHARACTER, T.STRINGVAL, T.NUMERAL):
            tok = self._advance()
            c.emit("LOAD_CONST", tok.secondary)
            return {T.CHARACTER: P_CHAR, T.STRINGVAL: P_STRING, T.NUMERAL: P_INTEGER}[k]
        if k == T.ID:
            obj, tok = self._idu()
            if self.tok.kind == T.LEFT_PARENTHESIS:
                return self._call(obj, tok)
            return self._lv_value(self._lvalue(obj, tok))
        raise self._syntax_error("expressão")

    def _call(self, f: Object, tok: Token) -> Object:
        """F -> IDU MC '(' LE ')'   (figs. 6.23 e 7.28)

        Os argumentos são empilhados pelo próprio código das expressões; só
        resta emitir o CALL com o índice da função no pool de funções."""
        # MC
        err = f.kind != Kind.FUNCTION
        if err:
            if f.kind != Kind.UNIVERSAL:
                self._error(E.ERR_KIND_NOT_FUNC, tok, tok.lexeme)
            ret, params = P_UNIVERSAL, []
        else:
            ret, params = f.ret_type, f.params
        self._expect(T.LEFT_PARENTHESIS)
        n = 0
        if self.tok.kind != T.RIGHT_PARENTHESIS:
            while True:                                              # LE
                atok = self.tok
                t = self._expr()
                n += 1
                if not err:
                    if n > len(params):
                        self._error(E.ERR_TOO_MANY_ARGS, atok, tok.lexeme)
                        err = True
                    elif not check_types(params[n - 1].type, t):
                        self._error(E.ERR_PARAM_TYPE, atok, n)
                if not self._accept(T.COMMA):
                    break
        self._expect(T.RIGHT_PARENTHESIS)
        if not err and n < len(params):
            self._error(E.ERR_TOO_FEW_ARGS, tok, tok.lexeme)
        self.code.emit("CALL", f.index if f.kind == Kind.FUNCTION else 0)
        return ret


def compile_source(source: str, simple_vars: bool = True) -> CompileResult:
    """Compila um programa. Lança CompileError em erro léxico ou sintático;
    erros semânticos voltam em CompileResult.errors (e asm fica None)."""
    return Parser(source, simple_vars=simple_vars).parse_program()
