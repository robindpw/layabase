import pytest
from layaberr import ValidationFailed

import layabase
import layabase.database_mongo
import layabase.testing


@pytest.fixture
def controller():
    class TestController(layabase.CRUDController):
        class TestNullableAutoSetModel:
            __tablename__ = "nullable_auto_set_table_name"

            prim_def_inc = layabase.database_mongo.Column(
                int, is_primary_key=True, default_value=1, should_auto_increment=True
            )
            prim_def = layabase.database_mongo.Column(
                int, is_primary_key=True, default_value=1
            )
            prim_inc = layabase.database_mongo.Column(
                int, is_primary_key=True, should_auto_increment=True
            )

        model = TestNullableAutoSetModel

    _db = layabase.load("mongomock", [TestController])
    yield TestController
    layabase.testing.reset(_db)


def test_put_without_primary_and_incremented_field(controller):
    controller.post({"prim_def": 1})
    with pytest.raises(ValidationFailed) as exception_info:
        controller.put({"prim_def": 1})
    assert exception_info.value.errors == {
        "prim_inc": ["Missing data for required field."]
    }
    assert exception_info.value.received_data == {"prim_def": 1}
