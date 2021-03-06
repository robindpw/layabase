import sqlalchemy
import layabase._database_sqlalchemy

# Those test cases are here to unit test features not testable using in-memory SQLite


def test_sybase_url():
    assert (
        "sybase+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2"
        == layabase._database_sqlalchemy._clean_database_url(
            "sybase+pyodbc:///?odbc_connect=TEST=VALUE;TEST2=VALUE2"
        )
    )


def test_sybase_does_not_support_offset():
    """This unit test case assert the remaining part of test_open_api_definition_without_offset_support"""
    assert not layabase._database_sqlalchemy._supports_offset("sybase+pyodbc")


def test_sybase_does_not_support_retrieving_metadata():
    assert not layabase._database_sqlalchemy._can_retrieve_metadata("sybase+pyodbc")


def test_sybase_prepare_engine(monkeypatch):
    class TestTable:
        __tablename__ = "test"

        key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)

    controller = layabase.CRUDController(TestTable)
    base = layabase.load("sqlite:///:memory:", [controller])
    monkeypatch.setattr(base.metadata.bind.url, "drivername", "sybase")
    layabase._database_sqlalchemy._prepare_engine(base.metadata.bind)
    assert base.metadata.bind.dialect.identifier_preparer.initial_quote == "["
    assert base.metadata.bind.dialect.identifier_preparer.final_quote == "]"


def test_mssql_url():
    assert (
        "mssql+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2"
        == layabase._database_sqlalchemy._clean_database_url(
            "mssql+pyodbc:///?odbc_connect=TEST=VALUE;TEST2=VALUE2"
        )
    )


def test_mssql_does_not_support_offset():
    """This unit test case assert the remaining part of test_open_api_definition_without_offset_support"""
    assert not layabase._database_sqlalchemy._supports_offset("mssql+pyodbc")


def test_mssql_does_not_support_retrieving_metadata():
    assert not layabase._database_sqlalchemy._can_retrieve_metadata("mssql+pyodbc")


def test_sql_lite_support_offset():
    assert layabase._database_sqlalchemy._supports_offset("sqlite")


def test_in_memory_database_is_considered_as_in_memory():
    assert layabase._database_sqlalchemy._in_memory("sqlite:///:memory:")


def test_real_database_is_not_considered_as_in_memory():
    assert not layabase._database_sqlalchemy._in_memory(
        "sybase+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2"
    )
