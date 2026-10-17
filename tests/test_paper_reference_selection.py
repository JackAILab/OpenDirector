from tools.prepare_paper_reference_review import select


def test_selection_is_order_invariant_deduplicated_and_reports_shortfall():
    rows=[{'item':str(i),'sha256':str(i),'duration':t} for i,t in enumerate([10,10,20,30,45,60,70,100])]
    duplicate={**rows[0],'item':'other_source'}
    one,coverage=select(rows+[duplicate],per_bin=3)
    two,_=select(list(reversed(rows+[duplicate])),per_bin=3)
    assert one==two and len(one)==8
    assert coverage=={'under_15':2,'15_to_30':2,'30_to_60':2,'over_60':2}
    assert len({r['sha256'] for r in one})==8
