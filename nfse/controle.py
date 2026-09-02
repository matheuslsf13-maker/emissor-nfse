# -*- coding: utf-8 -*-
"""Numeração sequencial, antiduplicidade e registro de transmissão.

Guardado em **SQLite** (`dados/controle.db`) -- um arquivo só, sem servidor,
que já vem com o Python. A versão anterior usava um JSON reescrito inteiro a
cada nota; funcionava, mas o custo crescia com o histórico: com 3.000 notas
acumuladas uma emissão de 246 levava 14 segundos, com 12.000 passava de 50.
Em SQLite é uma gravação por nota, independente do tamanho do histórico.

Número de DPS repetido é rejeitado pela prefeitura, e nota duplicada dá
trabalho para cancelar -- em Vila Velha o cancelamento exige processo
administrativo. Por isso cada número é reservado e gravado na hora, dentro de
uma transação: se faltar energia no meio da emissão, o que já saiu está
registrado e não sai de novo.

Chave de antiduplicidade: unidade + lançamento do caixa.

**NÃO APAGUE `dados/controle.db`.** Perder esse arquivo faz a numeração
recomeçar e todas as notas seguintes serem rejeitadas.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime

_TRAVA = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS unidades (
    unidade        TEXT PRIMARY KEY,
    ultimo_numero  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS emitidas (
    chave               TEXT PRIMARY KEY,
    numero              INTEGER,
    arquivo             TEXT,
    descricao           TEXT,
    em                  TEXT,
    documento           TEXT,
    competencia         TEXT,
    valor               TEXT,
    secao               TEXT,
    transmitida         INTEGER NOT NULL DEFAULT 0,
    transmitida_em      TEXT,
    numero_nota         TEXT,
    codigo_verificacao  TEXT,
    chave_acesso        TEXT,
    ambiente            TEXT
);
CREATE INDEX IF NOT EXISTS idx_emitidas_arquivo ON emitidas(arquivo);
CREATE INDEX IF NOT EXISTS idx_emitidas_competencia ON emitidas(competencia);
"""

CAMPOS_REGISTRO = ("numero", "arquivo", "descricao", "em", "documento",
                   "competencia", "valor", "secao", "transmitida",
                   "transmitida_em", "numero_nota", "codigo_verificacao",
                   "chave_acesso", "ambiente")


class ControleIlegivel(Exception):
    """O arquivo de controle existe mas nao e um banco valido.

    Acontece quando o `controle.db` corrompe -- desligamento no meio de uma
    gravacao, disco cheio, antivirus mexendo no arquivo, ou uma copia mal
    feita. E o arquivo mais critico do sistema: perde-lo faz a numeracao
    recomecar e a prefeitura rejeitar tudo.

    Vira excecao propria para o app poder explicar em portugues o que
    aconteceu e mandar restaurar o backup, em vez de mostrar
    `sqlite3.DatabaseError: file is not a database` numa tela 500 -- que na
    recepcao da clinica e um beco sem saida.
    """


class Controle:
    def __init__(self, caminho: str):
        # Aceita o caminho antigo (.json) para não quebrar quem chama assim.
        if caminho.endswith(".json"):
            self.caminho_json = caminho
            caminho = caminho[:-5] + ".db"
        else:
            self.caminho_json = caminho[:-3] + ".json"
        self.caminho = caminho
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        try:
            self._conexao = sqlite3.connect(caminho, check_same_thread=False)
            self._conexao.row_factory = sqlite3.Row
            self._conexao.executescript(ESQUEMA)
            self._conexao.commit()
        except sqlite3.DatabaseError as erro:
            try:
                self._conexao.close()
            except Exception:
                pass
            self._conexao = None
            raise ControleIlegivel(
                "O arquivo de controle da numeração (%s) não pôde ser lido: "
                "%s. É ele que guarda o último número usado e quais notas já "
                "saíram. NÃO apague nem gere notas antes de resolver: "
                "restaure o backup mais recente por cima deste arquivo. Se "
                "não houver backup, confira no portal da prefeitura qual foi "
                "a última nota emitida e use 'Ajustar numeração'."
                % (caminho, erro)
            )
        self._migrar_do_json()

    # -- migração ----------------------------------------------------------
    def _migrar_do_json(self) -> None:
        """Traz o conteúdo do controle.json antigo, uma vez só."""
        if not os.path.exists(self.caminho_json):
            return
        with open(self.caminho_json, encoding="utf-8") as fh:
            try:
                bruto = json.load(fh)
            except ValueError:
                return
        with _TRAVA, self._conexao:
            for unidade, dados in (bruto.get("unidades") or {}).items():
                self._conexao.execute(
                    "INSERT OR REPLACE INTO unidades VALUES (?, ?)",
                    (unidade, int(dados.get("ultimo_numero", 0))),
                )
            for chave, registro in (bruto.get("emitidas") or {}).items():
                valores = [registro.get(c) for c in CAMPOS_REGISTRO]
                valores[CAMPOS_REGISTRO.index("transmitida")] = int(
                    bool(registro.get("transmitida"))
                )
                self._conexao.execute(
                    "INSERT OR IGNORE INTO emitidas (chave, %s) VALUES (%s)"
                    % (", ".join(CAMPOS_REGISTRO),
                       ", ".join("?" * (len(CAMPOS_REGISTRO) + 1))),
                    [chave] + valores,
                )
        os.replace(self.caminho_json, self.caminho_json + ".migrado")

    # -- numeração ---------------------------------------------------------
    def ultimo_numero(self, unidade: str) -> int:
        linha = self._conexao.execute(
            "SELECT ultimo_numero FROM unidades WHERE unidade = ?", (unidade,)
        ).fetchone()
        return int(linha["ultimo_numero"]) if linha else 0

    def proximo_numero(self, unidade: str) -> int:
        """Reserva o próximo número e grava. Só o modo valendo chama isto."""
        with _TRAVA, self._conexao:
            self._conexao.execute(
                "INSERT INTO unidades (unidade, ultimo_numero) VALUES (?, 1) "
                "ON CONFLICT(unidade) DO UPDATE SET "
                "ultimo_numero = ultimo_numero + 1",
                (unidade,),
            )
            return int(self._conexao.execute(
                "SELECT ultimo_numero FROM unidades WHERE unidade = ?",
                (unidade,),
            ).fetchone()["ultimo_numero"])

    def ajustar_numeracao(self, unidade: str, ultimo: int) -> None:
        """Usado quando a clínica já emitiu notas por fora do sistema."""
        with _TRAVA, self._conexao:
            self._conexao.execute(
                "INSERT INTO unidades (unidade, ultimo_numero) VALUES (?, ?) "
                "ON CONFLICT(unidade) DO UPDATE SET ultimo_numero = excluded.ultimo_numero",
                (unidade, int(ultimo)),
            )

    # -- antiduplicidade ---------------------------------------------------
    @staticmethod
    def chave(unidade: str, lancamento: str) -> str:
        """Identidade de um atendimento: unidade + lançamento do caixa.

        Não é CPF + competência + valor: o mesmo paciente paga o mesmo valor
        várias vezes no mês -- quatro parcelas de R$ 70,00 no mesmo dia são
        quatro atendimentos, não uma nota repetida. Uma chave por valor
        engoliria 30 das 246 notas de agosto/2026 sem ninguém perceber.

        O número do lançamento é estável entre reexportações do relatório,
        então rodar de novo o mesmo período continua sendo seguro.
        """
        return "%s|%s" % (unidade, lancamento)

    def ja_emitida(self, chave: str):
        linha = self._conexao.execute(
            "SELECT * FROM emitidas WHERE chave = ?", (chave,)
        ).fetchone()
        return dict(linha) if linha else None

    def registrar(self, chave: str, numero: int, arquivo: str,
                  descricao: str = "", **contexto) -> None:
        registro = {
            "numero": numero,
            "arquivo": arquivo,
            "descricao": descricao,
            "em": datetime.now().isoformat(timespec="seconds"),
        }
        registro.update({k: v for k, v in contexto.items()
                         if k in CAMPOS_REGISTRO})
        colunas = ["chave"] + list(registro)
        with _TRAVA, self._conexao:
            self._conexao.execute(
                "INSERT OR REPLACE INTO emitidas (%s) VALUES (%s)"
                % (", ".join(colunas), ", ".join("?" * len(colunas))),
                [chave] + list(registro.values()),
            )

    def registrar_transmissao(self, chave: str, numero_nota: str = "",
                              codigo_verificacao: str = "",
                              chave_acesso: str = "",
                              ambiente: str = "") -> None:
        """Marca a nota como aceita pela prefeitura e guarda o que ela devolveu.

        É o número devolvido aqui -- não o nosso número de DPS -- que o
        paciente vê no DANFSe.
        """
        with _TRAVA, self._conexao:
            self._conexao.execute(
                "UPDATE emitidas SET transmitida = 1, transmitida_em = ?, "
                "numero_nota = ?, codigo_verificacao = ?, chave_acesso = ?, "
                "ambiente = ? WHERE chave = ?",
                (datetime.now().isoformat(timespec="seconds"), numero_nota,
                 codigo_verificacao, chave_acesso, ambiente, chave),
            )

    def esquecer(self, chave: str) -> None:
        with _TRAVA, self._conexao:
            self._conexao.execute("DELETE FROM emitidas WHERE chave = ?", (chave,))

    def descartar_lote(self, arquivos) -> dict:
        """Esquece notas GERADAS mas nunca transmitidas, para poder refazer.

        Serve para o erro mais comum de numeracao: gerar um lote inteiro com
        numeros que a prefeitura ja usou. Sem isto, o operador fica preso --
        os XMLs sao recusados por duplicidade e a antiduplicidade do proprio
        sistema impede gerar de novo, porque aqueles lancamentos constam como
        ja emitidos.

        **Nota transmitida nunca e esquecida.** Ela existe do lado da
        prefeitura; apagar o registro aqui criaria uma segunda nota para o
        mesmo atendimento, e em Vila Velha cancelar exige processo
        administrativo. Essas sao contadas e devolvidas separadamente.
        """
        nomes = list(arquivos)
        if not nomes:
            return {"descartadas": 0, "protegidas": 0, "numeros": []}

        marcas = ",".join("?" * len(nomes))
        linhas = self._conexao.execute(
            "SELECT chave, numero, arquivo, transmitida FROM emitidas "
            "WHERE arquivo IN (%s)" % marcas, nomes).fetchall()

        podem = [l for l in linhas if not l["transmitida"]]
        protegidas = [l for l in linhas if l["transmitida"]]
        with _TRAVA, self._conexao:
            for linha in podem:
                self._conexao.execute("DELETE FROM emitidas WHERE chave = ?",
                                      (linha["chave"],))
        return {
            "descartadas": len(podem),
            "protegidas": len(protegidas),
            "numeros": sorted(l["numero"] for l in podem if l["numero"]),
        }

    # -- consultas ---------------------------------------------------------
    def por_arquivo(self) -> dict:
        """arquivo -> (chave, registro). Usado pela transmissão."""
        return {
            linha["arquivo"]: (linha["chave"], dict(linha))
            for linha in self._conexao.execute(
                "SELECT * FROM emitidas WHERE arquivo IS NOT NULL")
        }

    def transmitidas(self, limite: int = 15) -> list:
        """As ultimas notas aceitas pela prefeitura, para a tela de consulta."""
        linhas = self._conexao.execute(
            "SELECT numero, numero_nota, chave_acesso, ambiente, transmitida_em,"
            " descricao, valor, documento FROM emitidas WHERE transmitida = 1"
            " ORDER BY transmitida_em DESC LIMIT ?", (int(limite),)
        ).fetchall()
        return [dict(linha) for linha in linhas]

    def resumo(self) -> dict:
        unidades = {
            linha["unidade"]: int(linha["ultimo_numero"])
            for linha in self._conexao.execute("SELECT * FROM unidades")
        }
        totais = self._conexao.execute(
            "SELECT COUNT(*) AS emitidas, "
            "COALESCE(SUM(transmitida), 0) AS transmitidas FROM emitidas"
        ).fetchone()
        return {
            "unidades": unidades,
            "emitidas": int(totais["emitidas"]),
            "transmitidas": int(totais["transmitidas"]),
        }

    def fechar(self) -> None:
        try:
            self._conexao.close()
        except Exception:
            pass

    # Fechar importa no Windows: com a conexao aberta, o arquivo nao pode ser
    # movido nem apagado -- o que atrapalha backup e restauracao.
    def __enter__(self):
        return self

    def __exit__(self, *erro):
        self.fechar()
        return False

    def __del__(self):
        self.fechar()
