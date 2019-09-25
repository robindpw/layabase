import pytest
import sqlalchemy
import flask
import flask_restplus
from layaberr import ValidationFailed

from layabase import database, database_sqlalchemy


class TestRequiredController(database.CRUDController):
    pass


def _create_models(base):
    class TestRequiredModel(database_sqlalchemy.CRUDModel, base):
        __tablename__ = "required_table_name"

        key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
        mandatory = sqlalchemy.Column(
            sqlalchemy.Integer,
            nullable=False,
            info={"marshmallow": {"required_on_query": True}},
        )

    TestRequiredController.model(TestRequiredModel)
    return [TestRequiredModel]


@pytest.fixture
def db():
    _db = database.load("sqlite:///:memory:", _create_models)
    yield _db
    database.reset(_db)


@pytest.fixture
def app(db):
    application = flask.Flask(__name__)
    application.testing = True
    api = flask_restplus.Api(application)
    namespace = api.namespace("Test", path="/")

    TestRequiredController.namespace(namespace)

    @namespace.route("/test")
    class TestResource(flask_restplus.Resource):
        @namespace.expect(TestRequiredController.query_get_parser)
        @namespace.marshal_with(TestRequiredController.get_response_model)
        def get(self):
            return []

        @namespace.expect(TestRequiredController.json_post_model)
        def post(self):
            return []

        @namespace.expect(TestRequiredController.json_put_model)
        def put(self):
            return []

        @namespace.expect(TestRequiredController.query_delete_parser)
        def delete(self):
            return []

    @namespace.route("/test_parsers")
    class TestParsersResource(flask_restplus.Resource):
        def get(self):
            return TestRequiredController.query_get_parser.parse_args()

        def delete(self):
            return TestRequiredController.query_delete_parser.parse_args()

    return application


def test_query_get_parser_without_required_field(client):
    response = client.get("/test_parsers")
    assert response.status_code == 400
    assert response.json == {
        "errors": {"mandatory": "Missing required parameter in the query string"},
        "message": "Input payload validation failed",
    }


def test_get_without_required_field(client):
    with pytest.raises(ValidationFailed) as exception_info:
        TestRequiredController.get({})
    assert exception_info.value.received_data == {}
    assert exception_info.value.errors == {
        "mandatory": ["Missing data for required field."]
    }


def test_get_with_required_field(client):
    assert TestRequiredController.get({"mandatory": 1}) == []


def test_get_one_without_required_field(client):
    with pytest.raises(ValidationFailed) as exception_info:
        TestRequiredController.get_one({})
    assert exception_info.value.received_data == {}
    assert exception_info.value.errors == {
        "mandatory": ["Missing data for required field."]
    }


def test_get_one_with_required_field(client):
    assert TestRequiredController.get_one({"mandatory": 1}) == {}


def test_delete_without_required_field(client):
    with pytest.raises(ValidationFailed) as exception_info:
        TestRequiredController.delete({})
    assert exception_info.value.received_data == {}
    assert exception_info.value.errors == {
        "mandatory": ["Missing data for required field."]
    }


def test_delete_with_required_field(client):
    assert TestRequiredController.delete({"mandatory": 1}) == 0


def test_query_get_parser_with_required_field(client):
    response = client.get("/test_parsers?mandatory=1")
    assert response.json == {
        "key": None,
        "limit": None,
        "mandatory": [1],
        "offset": None,
        "order_by": None,
    }


def test_query_delete_parser_without_required_field(client):
    response = client.delete("/test_parsers")
    assert response.status_code == 400
    assert response.json == {
        "errors": {"mandatory": "Missing required parameter in the query string"},
        "message": "Input payload validation failed",
    }


def test_query_delete_parser_with_required_field(client):
    response = client.delete("/test_parsers?mandatory=1")
    assert response.json == {"key": None, "mandatory": [1]}


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
                            "schema": {"$ref": "#/definitions/TestRequiredModel"},
                        }
                    ],
                    "tags": ["Test"],
                },
                "get": {
                    "responses": {
                        "200": {
                            "description": "Success",
                            "schema": {"$ref": "#/definitions/TestRequiredModel"},
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
                            "name": "mandatory",
                            "in": "query",
                            "type": "array",
                            "required": True,
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
                            "name": "order_by",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
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
                "put": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "put_test_resource",
                    "parameters": [
                        {
                            "name": "payload",
                            "required": True,
                            "in": "body",
                            "schema": {"$ref": "#/definitions/TestRequiredModel"},
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
                            "name": "mandatory",
                            "in": "query",
                            "type": "array",
                            "required": True,
                            "items": {"type": "integer"},
                            "collectionFormat": "multi",
                        },
                    ],
                    "tags": ["Test"],
                },
            },
            "/test_parsers": {
                "get": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "get_test_parsers_resource",
                    "tags": ["Test"],
                },
                "delete": {
                    "responses": {"200": {"description": "Success"}},
                    "operationId": "delete_test_parsers_resource",
                    "tags": ["Test"],
                },
            },
        },
        "info": {"title": "API", "version": "1.0"},
        "produces": ["application/json"],
        "consumes": ["application/json"],
        "tags": [{"name": "Test"}],
        "definitions": {
            "TestRequiredModel": {
                "required": ["key", "mandatory"],
                "properties": {
                    "key": {"type": "string", "example": "sample_value"},
                    "mandatory": {"type": "integer", "example": "0"},
                },
                "type": "object",
            }
        },
        "responses": {
            "ParseError": {"description": "When a mask can't be parsed"},
            "MaskError": {"description": "When any error occurs on mask"},
        },
    }