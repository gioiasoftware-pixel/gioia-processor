from ingest.llm_extract import deduplicate_wines


def test_deduplicate_prefers_stage1_over_stage0_5():
    stage0_5 = {
        "name": "Chianti Classico",
        "winery": "Castello di Ama",
        "qty": 2,
        "source_stage": "stage0_5",
        "region": None
    }
    stage1 = {
        "name": "Chianti Classico",
        "winery": "Castello di Ama",
        "qty": 4,
        "source_stage": "stage1",
        "region": "Toscana",
        "type": "Rosso"
    }

    result = deduplicate_wines([stage0_5, stage1], merge_quantities=True)
    assert len(result) == 1
    wine = result[0]
    assert wine["source_stage"] == "stage1"
    assert wine["region"] == "Toscana"
    # qty aggregata
    assert wine["qty"] == 6


def test_deduplicate_stage3_enriches_without_overwriting():
    stage1 = {
        "name": "Barolo",
        "winery": "Giacomo Conterno",
        "qty": 3,
        "source_stage": "stage1",
        "region": "Piemonte",
        "type": "Rosso"
    }
    stage3 = {
        "name": "Barolo",
        "winery": "Giacomo Conterno",
        "qty": 0,
        "source_stage": "stage3",
        "description": "Nebbiolo di struttura",
        "notes": "Da degustare"
    }

    result = deduplicate_wines([stage1, stage3], merge_quantities=True)
    assert len(result) == 1
    wine = result[0]
    # Stage1 data resta intatta
    assert wine["region"] == "Piemonte"
    assert wine["type"] == "Rosso"
    # Stage3 aggiunge campi accessori
    assert wine["description"] == "Nebbiolo di struttura"
    assert wine["notes"] == "Da degustare"
    assert wine["qty"] == 3

