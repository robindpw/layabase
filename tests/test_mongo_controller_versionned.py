import enum

import flask
import flask_restplus
import pytest
from layaberr import ValidationFailed, ModelCouldNotBeFound

import layabase
import layabase.mongo


class EnumTest(enum.Enum):
    Value1 = 1
    Value2 = 2


@pytest.fixture
def controller():
    class TestCollection:
        __collection_name__ = "test"

        key = layabase.mongo.Column(is_primary_key=True)
        dict_field = layabase.mongo.DictColumn(
            fields={
                "first_key": layabase.mongo.Column(EnumTest, is_nullable=False),
                "second_key": layabase.mongo.Column(int, is_nullable=False),
            },
            is_required=True,
        )

    controller = layabase.CRUDController(TestCollection, history=True)
    layabase.load("mongomock", [controller])
    return controller


@pytest.fixture
def app(controller: layabase.CRUDController):
    application = flask.Flask(__name__)
    application.testing = True
    api = flask_restplus.Api(application)
    namespace = api.namespace("Test", path="/")

    controller.namespace(namespace)

    @namespace.route("/test")
    class TestResource(flask_restplus.Resource):
        @namespace.expect(controller.query_get_parser)
        @namespace.marshal_with(controller.get_response_model)
        def get(self):
            return []

        @namespace.expect(controller.json_post_model)
        def post(self):
            return []

        @namespace.expect(controller.json_put_model)
        def put(self):
            return []

        @namespace.expect(controller.query_delete_parser)
        def delete(self):
            return []

    @namespace.route("/test/history")
    class TestHistoryResource(flask_restplus.Resource):
        @namespace.expect(controller.query_get_history_parser)
        @namespace.marshal_with(controller.get_history_response_model)
        def get(self):
            return []

    @namespace.route("/test_rollback_parser")
    class TestRollbackParserResource(flask_restplus.Resource):
        @namespace.expect(controller.query_rollback_parser)
        def get(self):
            return controller.query_rollback_parser.parse_args()

    return application


def test_get_url_with_primary_key_in_document_and_many_documents(
    controller: layabase.CRUDController,
):
    documents = [
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        },
        {
            "key": "second",
            "dict_field": {"first_key": "Value2", "second_key": 2},
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        },
    ]
    assert controller.get_url("/test", *documents) == "/test?key=first&key=second"


def test_get_url_with_primary_key_in_document_and_a_single_document(
    controller: layabase.CRUDController,
):
    document = {
        "key": "first",
        "dict_field": {"first_key": "Value1", "second_key": 1},
        "valid_since_revision": 1,
        "valid_until_revision": -1,
    }
    assert controller.get_url("/test", document) == "/test?key=first"


def test_get_url_with_primary_key_in_document_and_no_document(
    controller: layabase.CRUDController,
):
    assert controller.get_url("/test") == "/test"


def test_post_versioning_is_valid(controller: layabase.CRUDController):
    assert controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    ) == {
        "key": "first",
        "dict_field": {"first_key": "Value1", "second_key": 1},
        "valid_since_revision": 1,
        "valid_until_revision": -1,
    }
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        }
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        }
    ]


def test_post_without_providing_required_nullable_dict_column_is_valid(
    controller: layabase.CRUDController,
):
    assert controller.post({"key": "first"}) == {
        "dict_field": {"first_key": None, "second_key": None},
        "key": "first",
        "valid_since_revision": 1,
        "valid_until_revision": -1,
    }


def test_put_many_without_previous(controller: layabase.CRUDController):
    controller.post({"key": "first"})
    with pytest.raises(ModelCouldNotBeFound) as exception_info:
        controller.put_many([{"key": "unknown"}])
    assert exception_info.value.requested_data == {
        "key": "unknown",
        "valid_until_revision": -1,
    }


def test_rollback_invalid_query(controller: layabase.CRUDController):
    controller.post({"key": "first"})
    with pytest.raises(ValidationFailed) as exception_info:
        controller.rollback_to({"revision": 0, "dict_field.second_key": "invalid"})
    assert exception_info.value.errors == {
        "dict_field.second_key": ["Not a valid int."]
    }
    assert exception_info.value.received_data == {"dict_field.second_key": "invalid"}


def test_put_without_providing_required_nullable_dict_column_is_valid(
    controller: layabase.CRUDController,
):
    controller.post(
        {"key": "first", "dict_field": {"first_key": "Value1", "second_key": 0}}
    )
    assert controller.put({"key": "first"}) == (
        {
            "dict_field": {"first_key": "Value1", "second_key": 0},
            "key": "first",
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 0},
            "key": "first",
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
    )


def test_put_versioning_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    assert controller.put(
        {"key": "first", "dict_field.first_key": EnumTest.Value2}
    ) == (
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": -1,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
    )
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        }
    ]


def test_delete_versioning_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.put({"key": "first", "dict_field.first_key": EnumTest.Value2})
    assert controller.delete({"key": "first"}) == 1
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": 3,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
    ]
    assert controller.get({}) == []


def test_rollback_deleted_versioning_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.put({"key": "first", "dict_field.first_key": EnumTest.Value2})
    before_delete = 2
    controller.delete({"key": "first"})
    assert controller.rollback_to({"revision": before_delete}) == 1
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": 3,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 4,
            "valid_until_revision": -1,
        },
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 4,
            "valid_until_revision": -1,
        }
    ]


def test_rollback_before_update_deleted_versioning_is_valid(
    controller: layabase.CRUDController,
):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    before_update = 1
    controller.put({"key": "first", "dict_field.first_key": EnumTest.Value2})
    controller.delete({"key": "first"})
    assert controller.rollback_to({"revision": before_update}) == 1
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": 3,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 4,
            "valid_until_revision": -1,
        },
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 4,
            "valid_until_revision": -1,
        }
    ]


def test_rollback_already_valid_versioning_is_valid(
    controller: layabase.CRUDController,
):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.put({"key": "first", "dict_field.first_key": EnumTest.Value2})

    assert controller.rollback_to({"revision": 2}) == 0
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        }
    ]


def test_rollback_unknown_criteria_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    before_update = 1
    controller.put({"key": "first", "dict_field.first_key": EnumTest.Value2})

    assert controller.rollback_to({"revision": before_update, "key": "unknown"}) == 0
    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
    ]
    assert controller.get({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        }
    ]


def test_versioned_many(controller: layabase.CRUDController):
    controller.post_many(
        [
            {
                "key": "first",
                "dict_field.first_key": EnumTest.Value1,
                "dict_field.second_key": 1,
            },
            {
                "key": "second",
                "dict_field.first_key": EnumTest.Value2,
                "dict_field.second_key": 2,
            },
        ]
    )
    controller.put_many(
        [
            {"key": "first", "dict_field.first_key": EnumTest.Value2},
            {"key": "second", "dict_field.second_key": 3},
        ]
    )

    assert controller.get_history({}) == [
        {
            "key": "first",
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
        {
            "key": "second",
            "dict_field": {"first_key": "Value2", "second_key": 3},
            "valid_since_revision": 2,
            "valid_until_revision": -1,
        },
        {
            "key": "first",
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
        {
            "key": "second",
            "dict_field": {"first_key": "Value2", "second_key": 2},
            "valid_since_revision": 1,
            "valid_until_revision": 2,
        },
    ]


def test_rollback_without_revision_is_invalid(controller: layabase.CRUDController):
    with pytest.raises(ValidationFailed) as exception_info:
        controller.rollback_to({"key": "unknown"})
    assert exception_info.value.errors == {
        "revision": ["Missing data for required field."]
    }
    assert exception_info.value.received_data == {"key": "unknown"}


def test_rollback_with_non_int_revision_is_invalid(controller: layabase.CRUDController):
    with pytest.raises(ValidationFailed) as exception_info:
        controller.rollback_to({"revision": "invalid revision"})
    assert exception_info.value.errors == {"revision": ["Not a valid int."]}
    assert exception_info.value.received_data == {"revision": "invalid revision"}


def test_rollback_with_negative_revision_is_valid(controller: layabase.CRUDController):
    assert controller.rollback_to({"revision": -1}) == 0


def test_rollback_before_existing_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    before_insert = 1
    controller.post(
        {
            "key": "second",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    assert controller.rollback_to({"revision": before_insert}) == 1
    assert controller.get({"key": "second"}) == []


def test_get_revision_is_valid_when_empty(controller: layabase.CRUDController):
    assert controller._model.current_revision() == 0


def test_get_revision_is_valid_when_1(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    assert controller._model.current_revision() == 1


def test_get_revision_is_valid_when_2(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.post(
        {
            "key": "second",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    assert controller._model.current_revision() == 2


def test_rollback_to_0(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "first",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.post(
        {
            "key": "second",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    assert controller.rollback_to({"revision": 0}) == 2
    assert controller.get({}) == []


def test_rollback_multiple_rows_is_valid(controller: layabase.CRUDController):
    controller.post(
        {
            "key": "1",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.post(
        {
            "key": "2",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.put({"key": "1", "dict_field.first_key": EnumTest.Value2})
    controller.delete({"key": "2"})
    controller.post(
        {
            "key": "3",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.post(
        {
            "key": "4",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    before_insert = 6
    controller.post(
        {
            "key": "5",
            "dict_field.first_key": EnumTest.Value1,
            "dict_field.second_key": 1,
        }
    )
    controller.put({"key": "1", "dict_field.second_key": 2})
    # Remove key 5 and Update key 1 (Key 3 and Key 4 unchanged)
    assert controller.rollback_to({"revision": before_insert}) == 2
    assert controller.get({}) == [
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "3",
            "valid_since_revision": 5,
            "valid_until_revision": -1,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "4",
            "valid_since_revision": 6,
            "valid_until_revision": -1,
        },
        {
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "key": "1",
            "valid_since_revision": 9,
            "valid_until_revision": -1,
        },
    ]
    assert controller.get_history({}) == [
        {
            "dict_field": {"first_key": "Value2", "second_key": 2},
            "key": "1",
            "valid_since_revision": 8,
            "valid_until_revision": 9,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "2",
            "valid_since_revision": 2,
            "valid_until_revision": 4,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "1",
            "valid_since_revision": 1,
            "valid_until_revision": 3,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "3",
            "valid_since_revision": 5,
            "valid_until_revision": -1,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "4",
            "valid_since_revision": 6,
            "valid_until_revision": -1,
        },
        {
            "dict_field": {"first_key": "Value1", "second_key": 1},
            "key": "5",
            "valid_since_revision": 7,
            "valid_until_revision": 9,
        },
        {
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "key": "1",
            "valid_since_revision": 3,
            "valid_until_revision": 8,
        },
        {
            "dict_field": {"first_key": "Value2", "second_key": 1},
            "key": "1",
            "valid_since_revision": 9,
            "valid_until_revision": -1,
        },
    ]


def test_open_api_definition(client):
    response = client.get("/swagger.json")
    assert response.json == {
        "swagger": "2.0",
        "basePath": "/",
        "paths": {
            "/test": {
                "post": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "post_test_resource",
                    "parameters": [
                        {
                            "name": "payload",
                            "required": True,
                            "in": "body",
                            "schema": {
                                "$ref": "#/definitions/TestCollection_PostRequestModel"
                            },
                        }
                    ],
                    "tags": ["Test"],
                },
                "put": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "put_test_resource",
                    "parameters": [
                        {
                            "name": "payload",
                            "required": True,
                            "in": "body",
                            "schema": {
                                "$ref": "#/definitions/TestCollection_PutRequestModel"
                            },
                        }
                    ],
                    "tags": ["Test"],
                },
                "delete": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "delete_test_resource",
                    "parameters": [
                        {
                            "name": "key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.first_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.second_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                    ],
                    "tags": ["Test"],
                },
                "get": {
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "$ref": "#/definitions/TestCollection_GetResponseModel"
                            },
                        }
                    },
                    "operationId": "get_test_resource",
                    "parameters": [
                        {
                            "name": "key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.first_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.second_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "type": "integer",
                            "minimum": 0,
                            "exclusiveMinimum": True,
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "type": "integer",
                            "minimum": 0,
                        },
                        {
                            "name": "X-Fields",
                            "in": "header",
                            "type": "string",
                            "format": "mask",
                            "description": "An optional fields mask",
                        },
                    ],
                    "tags": ["Test"],
                },
            },
            "/test/history": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {
                                "$ref": "#/definitions/TestCollection_GetHistoryResponseModel"
                            },
                        }
                    },
                    "operationId": "get_test_history_resource",
                    "parameters": [
                        {
                            "name": "valid_since_revision",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "valid_until_revision",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.first_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.second_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "type": "integer",
                            "minimum": 0,
                            "exclusiveMinimum": True,
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "type": "integer",
                            "minimum": 0,
                        },
                        {
                            "name": "X-Fields",
                            "in": "header",
                            "type": "string",
                            "format": "mask",
                            "description": "An optional fields mask",
                        },
                    ],
                    "tags": ["Test"],
                }
            },
            "/test_rollback_parser": {
                "get": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "get_test_rollback_parser_resource",
                    "parameters": [
                        {
                            "name": "key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.first_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "dict_field.second_key",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                        {
                            "name": "revision",
                            "in": "query",
                            "type": "integer",
                            "minimum": 0,
                            "exclusiveMinimum": True,
                            "required": True,
                        },
                    ],
                    "tags": ["Test"],
                }
            },
        },
        "info": {"title": "API", "version": "1.0"},
        "produces": ["application/json"],
        "consumes": ["application/json"],
        "tags": [{"name": "Test"}],
        "definitions": {
            "TestCollection_PostRequestModel": {
                "required": ["dict_field"],
                "properties": {
                    "dict_field": {
                        "readOnly": False,
                        "default": {"first_key": None, "second_key": None},
                        "example": {"first_key": "Value1", "second_key": 1},
                        "allOf": [{"$ref": "#/definitions/first_key_second_key"}],
                    },
                    "key": {
                        "type": "string",
                        "readOnly": False,
                        "example": "sample key",
                    },
                },
                "type": "object",
            },
            "first_key_second_key": {
                "properties": {
                    "first_key": {
                        "type": "string",
                        "readOnly": False,
                        "example": "Value1",
                        "enum": ["Value1", "Value2"],
                    },
                    "second_key": {"type": "integer", "readOnly": False, "example": 1},
                },
                "type": "object",
            },
            "TestCollection_PutRequestModel": {
                "required": ["dict_field"],
                "properties": {
                    "dict_field": {
                        "readOnly": False,
                        "default": {"first_key": None, "second_key": None},
                        "example": {"first_key": "Value1", "second_key": 1},
                        "allOf": [{"$ref": "#/definitions/first_key_second_key"}],
                    },
                    "key": {
                        "type": "string",
                        "readOnly": False,
                        "example": "sample key",
                    },
                },
                "type": "object",
            },
            "TestCollection_GetResponseModel": {
                "required": ["dict_field"],
                "properties": {
                    "dict_field": {
                        "readOnly": False,
                        "default": {"first_key": None, "second_key": None},
                        "example": {"first_key": "Value1", "second_key": 1},
                        "allOf": [{"$ref": "#/definitions/first_key_second_key"}],
                    },
                    "key": {
                        "type": "string",
                        "readOnly": False,
                        "example": "sample key",
                    },
                },
                "type": "object",
            },
            "TestCollection_GetHistoryResponseModel": {
                "required": ["dict_field"],
                "properties": {
                    "dict_field": {
                        "readOnly": False,
                        "default": {"first_key": None, "second_key": None},
                        "example": {"first_key": "Value1", "second_key": 1},
                        "allOf": [{"$ref": "#/definitions/first_key_second_key"}],
                    },
                    "key": {
                        "type": "string",
                        "readOnly": False,
                        "example": "sample key",
                    },
                    "valid_since_revision": {
                        "type": "integer",
                        "description": "Record is valid since this revision (included).",
                        "readOnly": False,
                        "example": 1,
                    },
                    "valid_until_revision": {
                        "type": "integer",
                        "description": "Record is valid until this revision (excluded).",
                        "readOnly": False,
                        "example": 1,
                    },
                },
                "type": "object",
            },
        },
        "responses": {
            "ParseError": {"description": "When a mask can't be parsed"},
            "MaskError": {"description": "When any error occurs on mask"},
        },
    }


def test_query_rollback_parser(client):
    response = client.get(
        "/test_rollback_parser?dict_field.first_key=4&dict_field.second_key=3&key=test&revision=2"
    )
    assert response.json == {
        "dict_field.first_key": ["4"],
        "dict_field.second_key": [3],
        "key": ["test"],
        "revision": 2,
    }
