"""Compilador da Simple Script Language: análise sintática, de escopo, de
tipos e geração de código para a máquina virtual de pilha (caps. 3 a 7).

Exposto para uso externo:
    compile_source  -- compila o fonte e devolve CompileResult (asm + erros)
    CompileError    -- erro léxico/sintático, que interrompe a compilação
    SemanticError   -- erro de escopo/tipo (acumulado em CompileResult.errors)
    assemble / run  -- montador e interpretador da máquina virtual
"""
from .errors import CompileError, ErrorCode, SemanticError
from .parser import CompileResult, Parser, compile_source
from .vm import Program, VMError, assemble, format_value, run

__all__ = [
    "compile_source", "CompileResult", "Parser",
    "CompileError", "SemanticError", "ErrorCode",
    "assemble", "run", "Program", "VMError", "format_value",
]
