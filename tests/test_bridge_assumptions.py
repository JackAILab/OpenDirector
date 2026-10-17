import pytest
from harness.research.bridge_assumptions import validate_assumptions

def test_separates_direct_fact_from_physical_bridge():
    visible={'facts':{'leak':'inverted 30 seconds'}}
    rows=[{'fact_id':'leak','source_condition':'static inversion','target_condition':'static horizontal placement',
      'bridge_assumption':'orientation equivalence','basis':'same container not enough','status':'supported','bridge_status':'reasonable_with_assumption'}]
    result=validate_assumptions(rows,visible)
    assert result[0]['bridge_status']=='reasonable_with_assumption'
    rows[0]['fact_id']='hidden'
    with pytest.raises(ValueError,match='undisclosed_bridge_fact'):validate_assumptions(rows,visible)

def test_unknown_fact_can_be_unknown_but_not_supported():
    row={'fact_id':'hidden','source_condition':'x','target_condition':'y','bridge_assumption':'z','basis':'missing','status':'unknown','bridge_status':'unsupported_leap'}
    assert validate_assumptions([row],{'facts':{}})[0]['status']=='unknown'
    row['status']='supported'
    with pytest.raises(ValueError,match='undisclosed_bridge_fact'):validate_assumptions([row],{'facts':{}})
