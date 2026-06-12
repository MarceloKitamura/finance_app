"""
Testes do parcelamento na importação de fatura.

Cobrem:
- o parser de parcela (parse_installment) — casos positivos e negativos;
- o fluxo completo: importar uma linha "NETFLIX 03/12" gera a parcela do mês
  + as parcelas futuras, e REIMPORTAR não duplica.

Rodam com um banco SQLite temporário (DATA_DIR aponta para uma pasta tmp).
Sem pytest: dá para rodar direto com `python -m tests.test_installment_import`.
"""

import os
import tempfile


def _fresh_app(tmpdir):
    """Importa o app com um DATA_DIR isolado (banco limpo a cada execução)."""
    os.environ["DATA_DIR"] = tmpdir
    # Importa só depois de setar DATA_DIR para o config apontar para o tmp.
    from app.database import initialize_database
    initialize_database()


def test_parse_installment():
    from app.utils.import_parsers import parse_installment

    # Positivos.
    r = parse_installment("NETFLIX.COM 03/12")
    assert r == {"base": "NETFLIX.COM", "installment_no": 3, "installments_total": 12}, r

    r = parse_installment("MAGALU PARC 02/10")
    assert r["installment_no"] == 2 and r["installments_total"] == 10, r
    assert "magalu" in r["base"].lower() and "parc" not in r["base"].lower(), r

    r = parse_installment("LOJA X PARCELA 3 DE 12")
    assert r["installment_no"] == 3 and r["installments_total"] == 12, r

    # Negativos (não deve detectar parcela).
    assert parse_installment("UBER * TRIP") is None
    assert parse_installment("PAGAMENTO RECEBIDO") is None
    # Data no meio, sem palavra-chave nem fim de linha: não é parcela.
    assert parse_installment("COMPRA 12/2025 LOJA") is None
    # "à vista" não tem N/M.
    assert parse_installment("PADARIA DO ZE") is None
    print("OK parse_installment")


def test_import_installments_flow(tmpdir):
    _fresh_app(tmpdir)
    from app.services.ai_service import AIService
    from app.services.import_service import ImportService
    from app.services.transaction_service import TransactionService

    # use_llm=False = só palavras-chave (offline), sem chamar API nos testes.
    svc = ImportService(ai_service=AIService(use_llm=False))

    # CSV de fatura: 1 compra parcelada (3/12) + 1 à vista, no cartão "Nubank".
    csv_text = "data;valor;descricao\n2026-06-10;-100,00;NETFLIX 03/12\n2026-06-11;-50,00;PADARIA\n"
    mapping = {"date": 0, "amount": 1, "description": 2, "card": "Nubank"}

    prev = svc.preview("csv", csv_text, mapping)
    items = prev["items"]
    assert len(items) == 2, items
    parc = next(i for i in items if "NETFLIX" in i["description"])
    assert parc["installments_total"] == 12 and parc["installment_no"] == 3, parc
    assert parc["base_description"] == "NETFLIX", parc
    avista = next(i for i in items if "PADARIA" in i["description"])
    assert avista["installments_total"] == 1, avista

    # Grava.
    res = svc.import_transactions(items)
    # Parcela 3/12 importada + futuras 4..12 (9) = 10 da compra parcelada
    # + 1 à vista = 11 transações gravadas.
    assert res["imported"] == 11, res

    ts = TransactionService()
    todas = ts.list_all()
    netflix = [t for t in todas if t.purchase_group]
    assert len(netflix) == 10, [t.description for t in netflix]
    nums = sorted(t.installment_no for t in netflix)
    assert nums == list(range(3, 13)), nums
    # Cada parcela cai num mês diferente, ancorada no dia 10.
    datas = sorted(t.date for t in netflix)
    assert datas[0] == "2026-06-10", datas[0]   # parcela 3 = junho/2026
    assert datas[-1] == "2027-03-10", datas[-1]  # parcela 12 = março/2027

    # REIMPORTAR a mesma fatura não deve duplicar nada. Refaz a prévia (é o que
    # o usuário faria): a linha à vista vira duplicata e a parcelada é
    # deduplicada pelo purchase_group no service.
    prev2 = svc.preview("csv", csv_text, mapping)
    res2 = svc.import_transactions(prev2["items"])
    assert res2["imported"] == 0, res2
    total_apos = len(TransactionService().list_all())
    assert total_apos == 11, total_apos
    print("OK import_installments_flow")


def test_edit_parcela_preserva_metadata(tmpdir):
    """Editar o valor de uma parcela mantém id, grupo e N/total (centavos)."""
    _fresh_app(tmpdir)
    from app.services.ai_service import AIService
    from app.services.import_service import ImportService
    from app.services.transaction_service import TransactionService

    svc = ImportService(ai_service=AIService(use_llm=False))
    csv_text = "data;valor;descricao\n2026-06-10;-100,00;NETFLIX 03/12\n"
    mapping = {"date": 0, "amount": 1, "description": 2, "card": "Nubank"}
    svc.import_transactions(svc.preview("csv", csv_text, mapping)["items"])

    ts = TransactionService()
    parcelas = [t for t in ts.list_all() if t.purchase_group]
    ultima = max(parcelas, key=lambda t: t.installment_no)
    upd = ts.update_transaction(ultima.id, amount=100.07)
    assert upd.amount == 100.07 and upd.id == ultima.id, upd
    assert upd.installment_no == 12 and upd.installments_total == 12, upd
    assert upd.purchase_group == ultima.purchase_group, "grupo preservado"
    print("OK edit_parcela_preserva_metadata")


def test_preview_avisa_parcela_projetada(tmpdir):
    """A prévia marca como duplicata uma parcela já projetada de outra fatura."""
    _fresh_app(tmpdir)
    from app.services.ai_service import AIService
    from app.services.import_service import ImportService

    svc = ImportService(ai_service=AIService(use_llm=False))
    mapping = {"date": 0, "amount": 1, "description": 2, "card": "Nubank"}
    # Importa a fatura de junho (parcela 3/12) -> projeta 4..12.
    svc.import_transactions(
        svc.preview("csv", "data;valor;descricao\n2026-06-10;-100,00;NETFLIX 03/12\n", mapping)["items"]
    )
    # Importar a fatura de julho (4/12) deve AVISAR que a parcela já existe.
    prev = svc.preview("csv", "data;valor;descricao\n2026-07-10;-100,00;NETFLIX 04/12\n", mapping)
    it = prev["items"][0]
    assert it["installment_no"] == 4 and it["installments_total"] == 12, it
    assert it["duplicate"] is True and it["include"] is False, it
    print("OK preview_avisa_parcela_projetada")


def test_apply_to_group_spent_by(tmpdir):
    """Editar uma parcela com apply_to_group muda 'quem gastou' em todas,
    preservando valor e data de cada parcela."""
    _fresh_app(tmpdir)
    from app.services.ai_service import AIService
    from app.services.import_service import ImportService
    from app.services.transaction_service import TransactionService

    svc = ImportService(ai_service=AIService(use_llm=False))
    mapping = {"date": 0, "amount": 1, "description": 2, "card": "Nubank"}
    # 100,03 / 12 gera centavo extra na última parcela (valores diferentes).
    svc.import_transactions(
        svc.preview("csv", "data;valor;descricao\n2026-06-10;-100,03;NETFLIX 03/12\n", mapping)["items"]
    )
    ts = TransactionService()
    parcelas = sorted((t for t in ts.list_all() if t.purchase_group), key=lambda t: t.installment_no)
    antes = {t.installment_no: (t.date, t.amount) for t in parcelas}

    ts.update_transaction(parcelas[2].id, spent_by="Namorada", apply_to_group=True)
    depois = sorted((t for t in ts.list_all() if t.purchase_group), key=lambda t: t.installment_no)
    assert {t.spent_by for t in depois} == {"Namorada"}, [t.spent_by for t in depois]
    for t in depois:
        assert (t.date, t.amount) == antes[t.installment_no], ("valor/data mudou", t.installment_no)

    # Sem apply_to_group: muda só a parcela editada.
    ts.update_transaction(depois[0].id, spent_by="Eu", apply_to_group=False)
    final = sorted((t for t in ts.list_all() if t.purchase_group), key=lambda t: t.installment_no)
    assert final[0].spent_by == "Eu", final[0].spent_by
    assert all(t.spent_by == "Namorada" for t in final[1:]), [t.spent_by for t in final]
    print("OK apply_to_group_spent_by")


def test_forecast_sem_salario(tmpdir):
    """Modo sem salário zera o salário a receber e marca included=False."""
    _fresh_app(tmpdir)
    from app.services.forecast_service import ForecastService

    fs = ForecastService()
    com = fs.monthly_forecast(2026, 6, include_salary=True)
    sem = fs.monthly_forecast(2026, 6, include_salary=False)
    assert sem["future_salary"] == 0.0, sem["future_salary"]
    assert com["salary"]["included"] is True, com["salary"]
    assert sem["salary"]["included"] is False, sem["salary"]
    print("OK forecast_sem_salario")


if __name__ == "__main__":
    test_parse_installment()
    # ignore_cleanup_errors: no Windows o SQLite pode segurar o arquivo um
    # instante após fechar; não é falha do teste.
    for fn in (
        test_import_installments_flow,
        test_edit_parcela_preserva_metadata,
        test_preview_avisa_parcela_projetada,
        test_apply_to_group_spent_by,
        test_forecast_sem_salario,
    ):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            fn(d)
    print("TODOS OS TESTES PASSARAM")
