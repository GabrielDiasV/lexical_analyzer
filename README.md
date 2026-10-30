# Analisador Léxico — Simple Script Language

Analisador léxico em Python (sem dependências externas) para a gramática da
disciplina de Compiladores (Prof. Luiz Guedes, IME). Implementa o projeto
descrito na apostila:

- **Enumeração de tokens** com as palavras reservadas em ordem alfabética nos
  primeiros valores, de modo que a posição no vetor de reservadas **é** o token.
- **Busca binária** no vetor de palavras reservadas para distinguir reservada de
  identificador.
- **Tabela de nomes** (hash) que atribui a cada identificador um **token
  secundário** inteiro na ordem de primeira ocorrência. Cada identificador entra
  uma só vez.
- **Tabela de constantes** (união discriminada char / int / string) cuja posição
  é o token secundário de `NUMERAL`, `CHARACTER` e `STRINGVAL`.
- **Autômato finito** com lookahead de um caractere: o léxico está sempre um
  caractere à frente para saber onde o lexema termina sem perder o caractere
  que inicia o próximo token (`a+b`, `x<=y`, `i++`).

## Lexemas reconhecidos

```
letra  = 'a'..'z' + 'A'..'Z'
digito = '0'..'9'
Id     = letra . (letra + digito)*          -> ID        (token secundário: nome)
n      = digito . digito*                   -> NUMERAL   (token secundário: índice na tabela de constantes)
c      = ''' . any . '''                    -> CHARACTER (idem)
s      = '"' . any* . '"'                   -> STRINGVAL (idem)
```

Palavras reservadas: `array boolean break char continue do else false function
if integer of return string struct true type var while`.

`return` não está na gramática da seção 2.1, mas aparece em todos os exemplos
do cap. 7 e é necessário para a geração de código (instrução `RET`).

Literais de caractere aceitam também `'\0'`, `'\n'`, `'\t'` e `'\\'` (a
apostila usa `'\0'` nos exemplos 7.4.2 e 7.4.3). `'\'` sozinho continua sendo
a barra invertida.

Símbolos: `: ; , = [ ] { } ( ) && || < > <= >= != == + ++ - -- * / . !`.

Observação: seguindo a gramática à letra, `_` **não** faz parte de `Id`. Um
`_` no fonte é erro léxico. Separadores (espaço, tab, quebra de linha) são
ignorados.

## Estrutura

```
lexical_analyzer/
├── lexer/
│   ├── tokens.py    enumeração TokenKind, vetor KEYWORDS, tabelas de símbolos, classe Token
│   ├── tables.py    search_keyword (busca binária), NameTable, ConstTable
│   └── lexer.py     classe Lexer: next_token() e o autômato
├── compiler/
│   ├── symbols.py   objetos (fig. 7.11), tabela de símbolos com escopos, CheckTypes
│   ├── errors.py    códigos de erro de escopo/tipo (ERR_*) e CompileError
│   ├── parser.py    descida recursiva + escopo + tipos + geração de código (uma passada)
│   ├── codegen.py   emissor do Assembly: newLabel(), BEGIN_FUNC/END_FUNC, pool de constantes
│   └── vm.py        montador e interpretador da máquina virtual de pilha
├── main.py          CLI do analisador léxico (lista tokens)
├── compile.py       CLI do compilador (gera Assembly e executa)
├── examples/        programas de exemplo (.ssl); examples/codegen/ para o compilador
└── tests/           testes automatizados (unittest)
```

Requer Python 3.10 ou superior. Nenhuma instalação é necessária.

## Como rodar o analisador

Dentro da pasta `lexical_analyzer`:

```bash
# lista os tokens de um arquivo
python3 main.py examples/fatorial.ssl

# lista os tokens e imprime as tabelas de nomes e constantes ao final
python3 main.py examples/tipos.ssl --tables

# lê o programa da entrada padrão
echo 'var x, y: integer; x = y + 10;' | python3 main.py -

# modo tolerante: em vez de parar no 1º erro, emite UNKNOWN e continua
python3 main.py --lenient examples/erro.ssl
```

Saída para `echo 'var x, y: integer; x = y + 10;' | python3 main.py - --tables`:

```
LINHA  COL  TOKEN                 SEC  LEXEMA
------------------------------------------------------------
    1    1  VAR                        var
    1    5  ID                      0  x
    1    6  COMMA                      ,
    1    8  ID                      1  y
    1    9  COLON                      :
    1   11  INTEGER                    integer
    1   18  SEMI_COLON                 ;
    1   20  ID                      0  x
    1   22  EQUALS                     =
    1   24  ID                      1  y
    1   26  PLUS                       +
    1   28  NUMERAL                 0  10
    1   30  SEMI_COLON                 ;
    2    1  EOF

TABELA DE NOMES (token secundário -> identificador)
     0  x
     1  y

TABELA DE CONSTANTES (token secundário -> tipo, valor)
     0  int    10
```

Repare que o segundo `x` recebe o mesmo token secundário `0` do primeiro: é
o mesmo nome. A coluna `SEC` fica vazia em palavras reservadas e símbolos,
que não precisam de token secundário.

O programa termina com código de saída `0` se não houve erro léxico e `1` se
houve (útil em scripts).

## Como rodar os testes

Dentro da pasta `lexical_analyzer`:

```bash
python3 -m unittest -v
```

Ou apenas um grupo:

```bash
python3 -m unittest tests.test_lexer.SymbolsTests -v
python3 -m unittest tests.test_lexer.ConstantsTests.test_numeral -v
```

Se tiver `pytest` instalado, `pytest -v` também funciona.

O que os testes cobrem:

| Grupo | O que verifica |
|---|---|
| `KeywordTableTests` | vetor de reservadas ordenado e alinhado com a enumeração; busca binária devolve a posição como token |
| `KeywordsAndIdentifiersTests` | todas as reservadas; `While` e `whilex` são ID; token secundário segue a ordem de primeira ocorrência; cada nome entra uma vez na tabela |
| `ConstantsTests` | numerais, strings (inclusive vazias e contendo reservadas), caracteres; numeração única na tabela de constantes; erros de string/char malformados |
| `SymbolsTests` | todos os símbolos de 1 e 2 caracteres; o lookahead separa `a+b`, `a++b`, `a+++b`, `x<=y`, `x=-1`; `&` e `|` isolados são erro |
| `WhitespaceAndPositionTests` | separadores ignorados; entrada vazia gera só EOF; linha e coluna corretas |
| `ErrorHandlingTests` | caractere inválido lança `LexicalError` com posição; modo tolerante emite `UNKNOWN` |
| `ProgramTests` | declarações, cabeçalho de função, tipos, expressão com todos os níveis de operador; os arquivos de `examples/` tokenizam sem erro |

## Escrevendo seus próprios testes

Crie um arquivo `.ssl` e rode `python3 main.py seu_arquivo.ssl --tables`. Para
um teste automatizado, adicione um método em `tests/test_lexer.py` usando os
auxiliares já existentes:

```python
def test_meu_caso(self):
    self.assertEqual(kinds("x++;"), [T.ID, T.PLUS_PLUS, T.SEMI_COLON])
    self.assertEqual(pairs("a b a"), [(T.ID, 0), (T.ID, 1), (T.ID, 0)])
```

`kinds(src)` devolve só os tokens principais; `pairs(src)` devolve pares
(token principal, token secundário).

## Uso como biblioteca

```python
from lexer import Lexer, TokenKind

lx = Lexer("var x: integer; x = 'a';")
for tok in lx.tokens(include_eof=False):
    print(tok.kind.name, tok.secondary, tok.lexeme)

print(lx.names.get_name(0))         # 'x'
print(lx.consts.get_char_const(0))  # 'a'
```

Um analisador sintático consome os tokens chamando `lx.next_token()`
repetidamente, exatamente como `nextToken()` na apostila. Após cada chamada,
`lx.token` e `lx.token_secundario` guardam o último token principal e
secundário devolvidos.

## Geração de código

O pacote `compiler` implementa o cap. 7 da apostila. Como a geração de código é
dirigida pela sintaxe, ele inclui as etapas anteriores das quais ela depende:
análise sintática por descida recursiva (seção 3.4), análise de escopo (cap. 5)
e de tipos (cap. 6). Tudo acontece numa única passada: as regras de atributos
das figs. 7.12–7.29 rodam no ponto da derivação em que a apostila as coloca, e
os marcadores semânticos (NB, NF, MF, MT, ME, MW, MC) aparecem comentados no
código.

```bash
# imprime o Assembly gerado
python3 compile.py examples/codegen/fatorial.ssl

# compila e executa na máquina virtual (entrada: main ou a última função)
python3 compile.py examples/codegen/bsort.ssl --run
python3 compile.py examples/codegen/fatorial.ssl --run --entry fatorial --args 6

# grava o Assembly e o executa depois
python3 compile.py examples/codegen/strings.ssl -o strings.asm
python3 compile.py strings.asm --run --trace

# forma geral com LOAD_REF/DE_REF/STORE_REF também para escalares (fig. 7.8)
python3 compile.py examples/codegen/fatorial.ssl --refs
```

Saída para `examples/codegen/fatorial.ssl`: a mesma da seção 7.4.1, instrução
por instrução (os comentários `;` são ignorados pelo montador):

```
; pool de constantes
CONST 0 int 2
CONST 1 int 1
CONST 2 int 0
CONST 3 int 0
; pool de funções / array de código
BEGIN_FUNC 0 1 3 ; fatorial
	LOAD_CONST 0
	STORE_VAR 1
	LOAD_CONST 1
	STORE_VAR 2
L0:
	LOAD_VAR 1
	LOAD_VAR 0
	LE
	TJMP_FW L1
	LOAD_VAR 2
	LOAD_VAR 1
	DUP
	INC
	STORE_VAR 1
	MUL
	STORE_VAR 2
	JMP_BW L0
L1:
	LOAD_VAR 2
	RET
END_FUNC
...
```

### O que é gerado

| Construção | Código | Figura |
|---|---|---|
| `function f(...)` | `BEGIN_FUNC n p v` … `END_FUNC`, com `v` corrigido no fim do bloco | 7.4, 7.18 |
| `if`, `if/else` | `TJMP_FW`, `JMP_FW` e rótulos de `newLabel()` | 7.5, 7.21 |
| `while`, `do/while` | `JMP_BW` / `NOT` + `TJMP_BW` | 7.5, 7.22 |
| `break`, `continue` | `JMP_FW` para a saída / `JMP_BW` ou `JMP_FW` para o teste | 7.5 |
| `&& \|\| < > <= >= == != + - * /` | operandos e depois `AND OR LT GT LE GE EQ NEQ ADD SUB MUL DIV` | 7.6, 7.23–7.25 |
| `- !` unários, literais | `NEG`, `NOT`, `LOAD_TRUE`, `LOAD_FALSE`, `LOAD_CONST n` | 7.7, 7.26 |
| left-values `a.x`, `a[i]` | `LOAD_REF n`, `ADD n` (campo), `MUL n` + `ADD` (elemento) | 7.8, 7.27 |
| left-value como valor | `DE_REF n` (n = tamanho do tipo, em células) | 7.8, 7.26 |
| `LV = E` | `\|\|LV\|\| \|\|E\|\| STORE_REF n` | 7.8, 7.23 |
| `++ --` pré/pós | `DUP DUP DE_REF 1 INC/DEC STORE_REF 1 DE_REF 1 [DEC/INC]` | 7.8, 7.26 |
| variável escalar simples | `LOAD_VAR n`, `STORE_VAR n`, `LOAD_VAR INC DUP STORE_VAR` … | 7.9, 7.29 |
| `s[i]` em string | `CHAR_AT n` / `SET_CHAR n` | 7.9, 7.29 |
| chamada `f(a, b)` | argumentos empilhados pelas expressões + `CALL n` | 7.10, 7.28 |
| `return E;` | `\|\|E\|\| RET` | 7.4 |
| expressão como comando (`i++;`) | `\|\|E\|\|` + `POP` por célula | 7.3 |

Endereçamento (seção 7.5): tamanhos são contados em valores escalares (células
da pilha). Parâmetros começam no endereço 0 e as variáveis continuam a mesma
numeração, inclusive as de blocos internos. O pool de constantes é a própria
tabela de constantes do léxico: o argumento de `LOAD_CONST` é o token
secundário.

Por padrão, um identificador escalar sem `.` ou `[ ]` usa
`LOAD_VAR`/`STORE_VAR` (fig. 7.9), que é o que os exemplos 7.4.1–7.4.3
mostram, e qualquer outro left-value usa a forma geral da fig. 7.8. Com
`--refs` a forma geral é usada sempre. As duas formas executam de forma
idêntica (há testes para isso).

### Máquina virtual

`compiler/vm.py` monta o Assembly (resolve os rótulos, monta os pools de
constantes e de funções) e o interpreta conforme a seção 7.1: a Pilha de
Valores é polimórfica e guarda parâmetros e variáveis em `st[bp+n]`, e a Pilha
Operacional guarda `(&ret, bp)` de quem chamou. Num `RET`, as células acima das
variáveis da função (o valor de retorno, que pode ser um array inteiro) tomam
o lugar do registro de ativação. A linguagem não tem E/S, então a CLI imprime o
valor retornado pela função de entrada.

### Erros

Erros léxicos e sintáticos interrompem a compilação. Erros semânticos são
acumulados e relatados com linha e coluna, com os códigos da apostila
(`ERR_REDECL`, `ERR_NOT_DECL`, `ERR_TYPE_MISMATCH`, `ERR_BOOL_TYPE_EXPECTED`,
`ERR_KIND_NOT_VAR`, `ERR_TOO_FEW_ARGS`, ...). Se houver qualquer erro, nenhum
código é entregue, como o `ERROR_FLAG` da seção 7.6. Identificadores não
declarados recebem o tipo Universal para não repetir mensagens.

```
$ python3 compile.py examples/fatorial.ssl
examples/fatorial.ssl: linha 13, coluna 3: ERR_NOT_DECL: identificador 'resultado' não declarado
1 erro(s); nenhum código gerado.
```

### Decisões e diferenças em relação à apostila

- **Correções de erros de digitação da apostila**: `i <= n` gera `LE` (o
  exemplo 7.4.1 imprime `LT`). O rótulo do `ME`/`MW` tem `:`. `LOAD_REF` recebe
  o endereço da variável, e não o tamanho do tipo (fig. 7.27). `NEQ` segue a
  tabela de instruções (fig. 7.2); a máquina aceita também `NE`.
- **`v` em `BEGIN_FUNC` inclui os parâmetros**, como mandam as regras da seção
  7.5 ("o tamanho calculado para as variáveis engloba o espaço ocupado pelos
  parâmetros"). Alguns exemplos da seção 7.4 mostram só as variáveis locais.
- **`true`/`false`** geram `LOAD_TRUE`/`LOAD_FALSE` (fig. 7.7), já que o léxico
  não atribui token secundário a palavras reservadas.
- **Compatibilidade de tipos** é estrutural (fig. 6.17), mas os aliases são
  resolvidos antes da comparação, então `type nome = string` é compatível com
  `string`. O laço dos campos de struct da figura também foi corrigido para
  avançar nas duas listas.
- **Relacionais só valem para escalares**: `EQ` compara uma célula, então
  comparar arrays/structs é `ERR_INVALID_TYPE`.
- **Extensões de gramática**: `return E;`, expressões como comando, listas de
  parâmetros/argumentos/declarações/comandos vazias, `;` opcional após `type` e
  após o último campo de struct.
- **Não suportado**: variáveis globais (a máquina só endereça relativo ao BP,
  então o compilador dá um erro claro), indexar uma string que esteja dentro
  de struct/array (`CHAR_AT`/`SET_CHAR` endereçam só variáveis), `CALL_LIB`
  (a apostila não define bibliotecas) e comentários no fonte (a gramática não
  os prevê).
- O exemplo 7.4.2 retorna `s1[i] - s2[i]`, que as próprias regras de tipo
  rejeitam (`-` só vale para integer). `examples/codegen/strings.ssl` usa
  comparações no lugar.
