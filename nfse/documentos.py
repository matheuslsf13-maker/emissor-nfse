# -*- coding: utf-8 -*-
"""Validacao e formatacao de CPF/CNPJ.

O TechCare aceita cadastros com CPF invalido (tipicamente terminados em
zeros, ex. 875.560.000-00). Emitir nota com CPF invalido e erro fiscal, nao
apenas rejeicao. Por isso todo documento passa por aqui antes de virar nota.
"""

from __future__ import annotations

from .util import so_digitos


def _dv(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    cpf = so_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    d1 = _dv(cpf[:9], list(range(10, 1, -1)))
    d2 = _dv(cpf[:10], list(range(11, 1, -1)))
    return cpf[9] == d1 and cpf[10] == d2


def cnpj_valido(valor: str) -> bool:
    cnpj = so_digitos(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    return cnpj[12] == _dv(cnpj[:12], p1) and cnpj[13] == _dv(cnpj[:13], p2)


def documento_valido(valor: str) -> bool:
    d = so_digitos(valor)
    if len(d) == 11:
        return cpf_valido(d)
    if len(d) == 14:
        return cnpj_valido(d)
    return False


def formatar_cpf(valor: str) -> str:
    c = so_digitos(valor).zfill(11)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


def formatar_cnpj(valor: str) -> str:
    c = so_digitos(valor).zfill(14)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def formatar_documento(valor: str) -> str:
    d = so_digitos(valor)
    if len(d) == 11:
        return formatar_cpf(d)
    if len(d) == 14:
        return formatar_cnpj(d)
    return valor or ""


def formatar_cep(valor: str) -> str:
    c = so_digitos(valor)
    return f"{c[:5]}-{c[5:]}" if len(c) == 8 else (valor or "")
