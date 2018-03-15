import unittest
import logging
import sqlalchemy
import sys
import datetime
from marshmallow_sqlalchemy.fields import fields as marshmallow_fields
from flask_restplus import fields as flask_rest_plus_fields, inputs
from pycommon_test.flask_restplus_mock import TestAPI
from threading import Thread
import time
import enum
import json

logging.basicConfig(
    format='%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    level=logging.DEBUG)
logging.getLogger('sqlalchemy').setLevel(logging.DEBUG)

from pycommon_database import database, flask_restplus_errors, database_sqlalchemy, database_mongo, versioning_mongo

logger = logging.getLogger(__name__)


def parser_types(flask_parser) -> dict:
    return {arg.name: arg.type for arg in flask_parser.args}


def parser_actions(flask_parser) -> dict:
    return {arg.name: arg.action for arg in flask_parser.args}


class MongoColumnTest(unittest.TestCase):
    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_str_column_cannot_auto_increment(self):
        with self.assertRaises(Exception) as cm:
            database_mongo.Column(should_auto_increment=True)
        self.assertEqual('Only int fields can be auto incremented.', cm.exception.args[0])

    def test_auto_incremented_field_cannot_be_non_nullable(self):
        with self.assertRaises(Exception) as cm:
            database_mongo.Column(int, should_auto_increment=True, is_nullable=False)
        self.assertEqual('A field cannot be mandatory and auto incremented at the same time.', cm.exception.args[0])

    def test_field_with_default_value_cannot_be_non_nullable(self):
        with self.assertRaises(Exception) as cm:
            database_mongo.Column(default_value='test', is_nullable=False)
        self.assertEqual('A field cannot be mandatory and having a default value at the same time.', cm.exception.args[0])


class SQlAlchemyDatabaseTest(unittest.TestCase):
    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        self.maxDiff = None

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_none_connection_string_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load(None, None)
        self.assertEqual('A database connection URL must be provided.', cm.exception.args[0])

    def test_empty_connection_string_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load('', None)
        self.assertEqual('A database connection URL must be provided.', cm.exception.args[0])

    def test_no_create_models_function_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load('sqlite:///:memory:', None)
        self.assertEqual('A method allowing to create related models must be provided.', cm.exception.args[0])

    def test_models_are_added_to_metadata(self):
        def create_models(base):
            class TestModel(base):
                __tablename__ = 'sample_table_name'

                key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)

                @classmethod
                def _post_init(cls, base):
                    pass

            return [TestModel]

        db = database.load('sqlite:///:memory:', create_models)
        self.assertEqual('sqlite:///:memory:', str(db.metadata.bind.engine.url))
        self.assertEqual(['sample_table_name'], [table for table in db.metadata.tables.keys()])

    def test_sybase_url(self):
        self.assertEqual('sybase+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2',
                         database_sqlalchemy._clean_database_url('sybase+pyodbc:///?odbc_connect=TEST=VALUE;TEST2=VALUE2'))

    def test_sybase_does_not_support_offset(self):
        self.assertFalse(database_sqlalchemy._supports_offset('sybase+pyodbc'))

    def test_sybase_does_not_support_retrieving_metadata(self):
        self.assertFalse(database_sqlalchemy._can_retrieve_metadata('sybase+pyodbc'))

    def test_mssql_url(self):
        self.assertEqual('mssql+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2',
                         database_sqlalchemy._clean_database_url('mssql+pyodbc:///?odbc_connect=TEST=VALUE;TEST2=VALUE2'))

    def test_mssql_does_not_support_offset(self):
        self.assertFalse(database_sqlalchemy._supports_offset('mssql+pyodbc'))

    def test_mssql_does_not_support_retrieving_metadata(self):
        self.assertFalse(database_sqlalchemy._can_retrieve_metadata('mssql+pyodbc'))

    def test_sql_lite_support_offset(self):
        self.assertTrue(database_sqlalchemy._supports_offset('sqlite'))

    def test_in_memory_database_is_considered_as_in_memory(self):
        self.assertTrue(database_sqlalchemy._in_memory('sqlite:///:memory:'))

    def test_real_database_is_not_considered_as_in_memory(self):
        self.assertFalse(database_sqlalchemy._in_memory('sybase+pyodbc:///?odbc_connect=TEST%3DVALUE%3BTEST2%3DVALUE2'))


class MongoDatabaseTest(unittest.TestCase):
    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_none_connection_string_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load(None, None)
        self.assertEqual('A database connection URL must be provided.', cm.exception.args[0])

    def test_empty_connection_string_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load('', None)
        self.assertEqual('A database connection URL must be provided.', cm.exception.args[0])

    def test_no_create_models_function_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            database.load('mongomock', None)
        self.assertEqual('A method allowing to create related models must be provided.', cm.exception.args[0])


class SQlAlchemyCRUDModelTest(unittest.TestCase):
    _db = None
    _model = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('sqlite:///:memory:', cls._create_models)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'sample_table_name'

            key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            mandatory = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
            optional = sqlalchemy.Column(sqlalchemy.String)

        class TestModelAutoIncr(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'autoincre_table_name'

            key = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
            mandatory = sqlalchemy.Column(sqlalchemy.String, nullable=False)

        logger.info('Save model class...')
        cls._model = TestModel
        cls._model_autoincr = TestModelAutoIncr
        return [TestModel, TestModelAutoIncr]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_get_all_without_data_returns_empty_list(self):
        self.assertEqual([], self._model.get_all())

    def test_get_without_data_returns_empty_dict(self):
        self.assertEqual({}, self._model.get())

    def test_add_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_add_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_update_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.update(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_update_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.update({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_remove_without_nothing_do_not_fail(self):
        self.assertEqual(0, self._model.remove())
        self.assertEqual({}, self._model.get())

    def test_add_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add({
                'key': 'my_key',
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key'}, cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_add_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add({
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'mandatory': 1}, cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_add_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add({
                'key': 256,
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Not a valid string.']}, cm.exception.errors)
        self.assertEqual({'key': 256, 'mandatory': 1}, cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_update_with_wrong_type_is_invalid(self):
        self._model.add({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self._model.update({
                'key': 'value1',
                'mandatory': 'invalid_value',
            })
        self.assertEqual({'mandatory': ['Not a valid integer.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': 'invalid_value'}, cm.exception.received_data)

    def test_add_all_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add_all(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)

    def test_add_all_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add_all({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_add_all_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add_all([{
                'key': 'my_key',
            },
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                }
            ])
        self.assertEqual({0: {'mandatory': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'key': 'my_key'}, {'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}],
                         cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_add_all_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add_all([{
                'mandatory': 1,
            },
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                }]
            )
        self.assertEqual({0: {'key': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'mandatory': 1}, {'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}],
                         cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_add_all_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.add_all([{
                'key': 256,
                'mandatory': 1,
            },
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                }]
            )
        self.assertEqual({0: {'key': ['Not a valid string.']}}, cm.exception.errors)
        self.assertEqual([{'key': 256, 'mandatory': 1}, {'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}],
                         cm.exception.received_data)
        self.assertEqual({}, self._model.get())

    def test_add_without_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': None},
            self._model.add({
                'key': 'my_key',
                'mandatory': 1,
            })
        )
        self.assertEqual({'key': 'my_key', 'mandatory': 1, 'optional': None}, self._model.get())

    def test_add_with_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self._model.add({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        )
        self.assertEqual({'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}, self._model.get())

    def test_update_unexisting_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self._model.update({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        self.assertEqual({'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}, cm.exception.requested_data)

    def test_add_with_unknown_field_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self._model.add({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            })
        )
        self.assertEqual({'key': 'my_key', 'mandatory': 1, 'optional': 'my_value'}, self._model.get())

    def test_get_without_filter_is_retrieving_the_only_item(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            {
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            },
            self._model.get())

    def test_get_without_filter_is_failing_if_more_than_one_item_exists(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        with self.assertRaises(Exception) as cm:
            self._model.get()
        self.assertEqual({'': ['More than one result: Consider another filtering.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_get_all_without_filter_is_retrieving_everything_after_multiple_posts(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self._model.get_all())

    def test_get_all_without_filter_is_retrieving_everything(self):
        self._model.add_all([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            }
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self._model.get_all())

    def test_get_all_with_filter_is_retrieving_subset_after_multiple_posts(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self._model.get_all(optional='my_value1'))

    def test_get_all_with_filter_is_retrieving_subset(self):
        self._model.add_all([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            }
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self._model.get_all(optional='my_value1'))

    def test_get_all_order_by(self):
        self._model.add_all([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 1,
                'optional': 'my_value2',
            },
            {'key': 'my_key3', 'mandatory': -1, 'optional': 'my_value3'},

        ])
        self.assertEqual(
            [
                {'key': 'my_key3', 'mandatory': -1, 'optional': 'my_value3'},
                {'key': 'my_key2', 'mandatory': 1, 'optional': 'my_value2'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'}
            ],
            self._model.get_all(order_by=[sqlalchemy.asc(self._model.mandatory),
                                                   sqlalchemy.desc(self._model.key)]))

    def test_get_with_filter_is_retrieving_the_proper_row_after_multiple_posts(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual({'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                         self._model.get(optional='my_value1'))

    def test_get_with_filter_is_retrieving_the_proper_row(self):
        self._model.add_all([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            }
        ])
        self.assertEqual({'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                         self._model.get(optional='my_value1'))

    def test_update_is_updating(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            (
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
            ),
            self._model.update({
                'key': 'my_key1',
                'optional': 'my_value',
            })
        )
        self.assertEqual({'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
                         self._model.get(mandatory=1))

    def test_update_is_updating_and_previous_value_cannot_be_used_to_filter(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.update({
            'key': 'my_key1',
            'optional': 'my_value',
        })
        self.assertEqual({}, self._model.get(optional='my_value1'))

    def test_remove_with_filter_is_removing_the_proper_row(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(1, self._model.remove(key='my_key1'))
        self.assertEqual([{'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}],
                         self._model.get_all())

    def test_remove_without_filter_is_removing_everything(self):
        self._model.add({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self._model.add({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(2, self._model.remove())
        self.assertEqual([], self._model.get_all())


class SQLAlchemyCRUDControllerTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    class TestAutoIncrementController(database.CRUDController):
        pass

    class TestDateController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('sqlite:///:memory:', cls._create_models)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'sample_table_name'

            key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            mandatory = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
            optional = sqlalchemy.Column(sqlalchemy.String)

        class TestAutoIncrementModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'auto_increment_table_name'

            key = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
            enum_field = sqlalchemy.Column(sqlalchemy.Enum('Value1', 'Value2'), nullable=False,
                                           doc='Test Documentation')
            optional_with_default = sqlalchemy.Column(sqlalchemy.String, default='Test value')

        class TestDateModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'date_table_name'

            key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            date_str = sqlalchemy.Column(sqlalchemy.Date)
            datetime_str = sqlalchemy.Column(sqlalchemy.DateTime)

        logger.info('Save model class...')
        cls.TestController.model(TestModel)
        cls.TestController.namespace(TestAPI)
        cls.TestAutoIncrementController.model(TestAutoIncrementModel)
        cls.TestAutoIncrementController.namespace(TestAPI)
        cls.TestDateController.model(TestDateModel)
        cls.TestDateController.namespace(TestAPI)
        return [TestModel, TestAutoIncrementModel, TestDateModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_get_all_without_data_returns_empty_list(self):
        self.assertEqual([], self.TestController.get({}))

    def test_post_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_post_list_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_post_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_post_many_with_empty_list_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_put_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_put_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_delete_without_nothing_do_not_fail(self):
        self.assertEqual(0, self.TestController.delete({}))

    def test_post_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 'my_key',
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key'}, cm.exception.received_data)

    def test_post_many_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 'my_key',
            }])
        self.assertEqual({0: {'mandatory': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'key': 'my_key'}], cm.exception.received_data)

    def test_post_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'mandatory': 1}, cm.exception.received_data)

    def test_post_many_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'mandatory': 1}], cm.exception.received_data)

    def test_post_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 256,
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Not a valid string.']}, cm.exception.errors)
        self.assertEqual({'key': 256, 'mandatory': 1}, cm.exception.received_data)

    def test_post_many_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 256,
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Not a valid string.']}}, cm.exception.errors)
        self.assertEqual([{'key': 256, 'mandatory': 1}], cm.exception.received_data)

    def test_put_with_wrong_type_is_invalid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestController.put({
                'key': 'value1',
                'mandatory': 'invalid value',
            })
        self.assertEqual({'mandatory': ['Not a valid integer.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': 'invalid value'}, cm.exception.received_data)

    def test_post_without_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': None},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
            })
        )

    def test_post_many_without_optional_is_valid(self):
        self.assertEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': None},
                {'mandatory': 2, 'key': 'my_key2', 'optional': None},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                }
            ])
        )

    def test_post_with_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        )

    def test_post_many_with_optional_is_valid(self):
        self.assertListEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
                {'mandatory': 2, 'key': 'my_key2', 'optional': 'my_value2'},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                }
            ])
        )

    def test_post_with_unknown_field_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            })
        )

    def test_post_many_with_unknown_field_is_valid(self):
        self.assertListEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
                {'mandatory': 2, 'key': 'my_key2', 'optional': 'my_value2'},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    # This field do not exists in schema
                    'unknown': 'my_value',
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    # This field do not exists in schema
                    'unknown': 'my_value2',
                },
            ])
        )

    def test_post_with_specified_incremented_field_is_ignored_and_valid(self):
        self.assertEqual(
            {'optional_with_default': 'Test value', 'key': 1, 'enum_field': 'Value1'},
            self.TestAutoIncrementController.post({
                'key': 'my_key',
                'enum_field': 'Value1',
            })
        )

    def test_post_many_with_specified_incremented_field_is_ignored_and_valid(self):
        self.assertListEqual(
            [
                {'optional_with_default': 'Test value', 'enum_field': 'Value1', 'key': 1},
                {'optional_with_default': 'Test value', 'enum_field': 'Value2', 'key': 2},
            ],
            self.TestAutoIncrementController.post_many([{
                'key': 'my_key',
                'enum_field': 'Value1',
            }, {
                'key': 'my_key',
                'enum_field': 'Value2',
            }])
        )

    def test_get_without_filter_is_retrieving_the_only_item(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.TestController.get({}))

    def test_get_from_another_thread_than_post(self):
        def save_get_result():
            self.thread_get_result = self.TestController.get({})

        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })

        self.thread_get_result = None
        get_thread = Thread(name='GetInOtherThread', target=save_get_result)
        get_thread.start()
        get_thread.join()

        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.thread_get_result)

    def test_get_without_filter_is_retrieving_everything_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))

    def test_get_without_filter_is_retrieving_everything(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            },
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))

    def test_get_with_filter_is_retrieving_subset_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))

    def test_get_with_filter_is_retrieving_subset(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            },
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))

    def test_put_is_updating(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            (
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
            ),
            self.TestController.put({
                'key': 'my_key1',
                'optional': 'my_value',
            })
        )
        self.assertEqual([{'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'}],
                         self.TestController.get({'mandatory': 1}))

    def test_put_is_updating_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        self.assertEqual(
            (
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59+00:00', 'key': 'my_key1'},
                {'date_str': '2018-06-01', 'datetime_str': '1989-12-31T01:00:00+00:00', 'key': 'my_key1'},
            ),
            self.TestDateController.put({
                'key': 'my_key1',
                'date_str': '2018-06-01',
                'datetime_str': '1989-12-31T01:00:00',
            })
        )
        self.assertEqual([
            {'date_str': '2018-06-01', 'datetime_str': '1989-12-31T01:00:00+00:00', 'key': 'my_key1'}
        ],
            self.TestDateController.get({'date_str': '2018-06-01'}))

    def test_get_date_is_handled_for_valid_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        d = datetime.datetime.strptime('2017-05-15', '%Y-%m-%d').date()
        self.assertEqual(
            [
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59+00:00', 'key': 'my_key1'},
            ],
            self.TestDateController.get({
                'date_str': d,
            })
        )

    def test_get_date_is_handled_for_unused_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        d = datetime.datetime.strptime('2016-09-23', '%Y-%m-%d').date()
        self.assertEqual(
            [],
            self.TestDateController.get({
                'date_str': d,
            })
        )

    def test_get_date_is_handled_for_valid_datetime(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        dt = datetime.datetime.strptime('2016-09-23T23:59:59', '%Y-%m-%dT%H:%M:%S')
        self.assertEqual(
            [
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59+00:00', 'key': 'my_key1'},
            ],
            self.TestDateController.get({
                'datetime_str': dt,
            })
        )

    def test_get_date_is_handled_for_unused_datetime(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        dt = datetime.datetime.strptime('2016-09-24T23:59:59', '%Y-%m-%dT%H:%M:%S')
        self.assertEqual(
            [],
            self.TestDateController.get({
                'datetime_str': dt,
            })
        )

    def test_put_is_updating_and_previous_value_cannot_be_used_to_filter(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'optional': 'my_value',
        })
        self.assertEqual([], self.TestController.get({'optional': 'my_value1'}))

    def test_delete_with_filter_is_removing_the_proper_row(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(1, self.TestController.delete({'key': 'my_key1'}))
        self.assertEqual([{'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}],
                         self.TestController.get({}))

    def test_delete_without_filter_is_removing_everything(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(2, self.TestController.delete({}))
        self.assertEqual([], self.TestController.get({}))

    def test_query_get_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_parser))

    def test_query_delete_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
            },
            parser_types(self.TestController.query_delete_parser))

    def test_json_post_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.json_post_model.name
        )
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_post_model.fields_flask_type
        )

    def test_json_post_model_with_auto_increment_and_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.json_post_model.name
        )
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.json_post_model.fields_flask_type
        )
        self.assertEqual(
            {'enum_field': None, 'key': None, 'optional_with_default': 'Test value'},
            self.TestAutoIncrementController.json_post_model.fields_default
        )

    def test_json_put_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.json_put_model.name
        )
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_put_model.fields_flask_type
        )

    def test_json_put_model_with_auto_increment_and_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.json_put_model.name
        )
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.json_put_model.fields_flask_type
        )

    def test_get_response_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.get_response_model.name)
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type)

    def test_get_response_model_with_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.get_response_model.name)
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.get_response_model.fields_flask_type)
        self.assertEqual(
            {'enum_field': 'Test Documentation', 'key': None, 'optional_with_default': None},
            self.TestAutoIncrementController.get_response_model.fields_description)
        self.assertEqual(
            {'enum_field': ['Value1', 'Value2'], 'key': None, 'optional_with_default': None},
            self.TestAutoIncrementController.get_response_model.fields_enum)

    def test_get_with_limit_2_is_retrieving_subset_of_2_first_elements(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},
            ],
            self.TestController.get({'limit': 2}))

    def test_get_with_offset_1_is_retrieving_subset_of_n_minus_1_first_elements(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},
                {'key': 'my_key3', 'mandatory': 3, 'optional': 'my_value3'},
            ],
            self.TestController.get({'offset': 1}))

    def test_get_with_limit_1_and_offset_1_is_retrieving_middle_element(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},

            ],
            self.TestController.get({'offset': 1, 'limit': 1}))

    def test_get_model_description_returns_description(self):
        self.assertEqual(
            {
                'key': 'key',
                'mandatory': 'mandatory',
                'optional': 'optional',
                'table': 'sample_table_name'
            },
            self.TestController.get_model_description())

    def test_get_model_description_response_model(self):
        self.assertEqual(
            'TestModelDescription',
            self.TestController.get_model_description_response_model.name)
        self.assertEqual(
            {'key': 'String',
             'mandatory': 'String',
             'optional': 'String',
             'table': 'String'},
            self.TestController.get_model_description_response_model.fields_flask_type)


class SQLAlchemyCRUDControllerFailuresTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('sqlite:///:memory:', cls._create_models)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'sample_table_name'

            key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            mandatory = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
            optional = sqlalchemy.Column(sqlalchemy.String)

        logger.info('Save model class...')
        return [TestModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_model_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.model(None)
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_namespace_method_without_setting_model(self):
        class TestNamespace:
            pass

        with self.assertRaises(Exception) as cm:
            self.TestController.namespace(TestNamespace)
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_get_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_post_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_post_many_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_put_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_delete_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.delete({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_audit_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get_audit({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_model_description_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get_model_description()
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")


class SQLAlchemyCRUDControllerAuditTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('sqlite:///:memory:', cls._create_models)
        cls.TestController.namespace(TestAPI)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'sample_table_name'

            key = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            mandatory = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
            optional = sqlalchemy.Column(sqlalchemy.String)

        logger.info('Save model class...')
        TestModel.audit()
        cls.TestController.model(TestModel)
        return [TestModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_get_all_without_data_returns_empty_list(self):
        self.assertEqual([], self.TestController.get({}))
        self._check_audit([])

    def test_get_parser_fields_order(self):
        self.assertEqual(
            [
                'key',
                'mandatory',
                'optional',
                'limit',
                'offset',
            ],
            [arg.name for arg in self.TestController.query_get_parser.args]
        )

    def test_delete_parser_fields_order(self):
        self.assertEqual(
            [
                'key',
                'mandatory',
                'optional',
            ],
            [arg.name for arg in self.TestController.query_delete_parser.args]
        )

    def test_post_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_post_model.fields_flask_type
        )

    def test_put_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_put_model.fields_flask_type
        )

    def test_get_response_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type
        )

    def test_post_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_post_many_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_post_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_post_many_with_empty_list_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_put_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_put_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit([])

    def test_delete_without_nothing_do_not_fail(self):
        self.assertEqual(0, self.TestController.delete({}))
        self._check_audit([])

    def test_post_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 'my_key',
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key'}, cm.exception.received_data)
        self._check_audit([])

    def test_post_many_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 'my_key',
            }])
        self.assertEqual({0: {'mandatory': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'key': 'my_key'}], cm.exception.received_data)
        self._check_audit([])

    def test_post_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'mandatory': 1}, cm.exception.received_data)
        self._check_audit([])

    def test_post_many_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'mandatory': 1}], cm.exception.received_data)
        self._check_audit([])

    def test_post_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 256,
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Not a valid string.']}, cm.exception.errors)
        self.assertEqual({'key': 256, 'mandatory': 1}, cm.exception.received_data)
        self._check_audit([])

    def test_post_many_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 256,
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Not a valid string.']}}, cm.exception.errors)
        self.assertEqual([{'key': 256, 'mandatory': 1}], cm.exception.received_data)
        self._check_audit([])

    def test_put_with_wrong_type_is_invalid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestController.put({
                'key': 'value1',
                'mandatory': 'invalid_value',
            })
        self.assertEqual({'mandatory': ['Not a valid integer.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': 'invalid_value'}, cm.exception.received_data)
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'value1',
                    'mandatory': 1,
                    'optional': None,
                },
            ]
        )

    def test_post_without_optional_is_valid(self):
        self.assertEqual(
            {'optional': None, 'mandatory': 1, 'key': 'my_key'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
            })
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': None,
                },
            ]
        )

    def test_post_many_without_optional_is_valid(self):
        self.assertListEqual(
            [{'optional': None, 'mandatory': 1, 'key': 'my_key'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
            }])
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': None,
                },
            ]
        )

    def _check_audit(self, expected_audit, filter_audit={}):
        audit = self.TestController.get_audit(filter_audit)
        audit = [{key: audit_line[key] for key in sorted(audit_line.keys())} for audit_line in audit]

        if not expected_audit:
            self.assertEqual(audit, expected_audit)
        else:
            self.assertRegex(f'{audit}', f'{expected_audit}'.replace('[', '\\[').replace(']', '\\]').replace('\\\\', '\\'))

    def test_post_with_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                }
            ]
        )

    def test_post_many_with_optional_is_valid(self):
        self.assertListEqual(
            [{'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            }])
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                }
            ]
        )

    def test_post_with_unknown_field_is_valid(self):
        self.assertEqual(
            {'optional': 'my_value', 'mandatory': 1, 'key': 'my_key'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            })
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
            ]
        )

    def test_post_many_with_unknown_field_is_valid(self):
        self.assertListEqual(
            [{'optional': 'my_value', 'mandatory': 1, 'key': 'my_key'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            }])
        )
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
            ]
        )

    def test_get_without_filter_is_retrieving_the_only_item(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.TestController.get({}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
            ]
        )

    def test_get_without_filter_is_retrieving_everything_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
            ]
        )

    def test_get_without_filter_is_retrieving_everything(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            }
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
            ]
        )

    def test_get_with_filter_is_retrieving_subset(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
            ]
        )

    def test_put_is_updating(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            (
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
            ),
            self.TestController.put({
                'key': 'my_key1',
                'optional': 'my_value',
            })
        )
        self.assertEqual([{'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'}],
                         self.TestController.get({'mandatory': 1}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'U',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
            ]
        )

    def test_put_is_updating_and_previous_value_cannot_be_used_to_filter(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'optional': 'my_value',
        })
        self.assertEqual([], self.TestController.get({'optional': 'my_value1'}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'U',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
            ]
        )

    def test_delete_with_filter_is_removing_the_proper_row(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(1, self.TestController.delete({'key': 'my_key1'}))
        self.assertEqual([{'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}],
                         self.TestController.get({}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
                {
                    'audit_action': 'D',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
            ]
        )

    def test_audit_filter_on_model_is_returning_only_selected_data(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 2,
        })
        self.TestController.delete({'key': 'my_key1'})
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'U',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'D',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                },
            ],
            filter_audit={'key': 'my_key1'}
        )

    def test_audit_filter_on_audit_model_is_returning_only_selected_data(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 2,
        })
        time.sleep(1)
        self.TestController.delete({'key': 'my_key1'})
        self._check_audit(
            [
                {
                    'audit_action': 'U',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                },
            ],
            filter_audit={'audit_action': 'U'}
        )

    def test_delete_without_filter_is_removing_everything(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        time.sleep(1)
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(2, self.TestController.delete({}))
        self.assertEqual([], self.TestController.get({}))
        self._check_audit(
            [
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'I',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
                {
                    'audit_action': 'D',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                },
                {
                    'audit_action': 'D',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d\+00:00',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                },
            ]
        )

    def test_query_get_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_parser))
        self._check_audit([])

    def test_query_get_audit_parser(self):
        self.assertEqual(
            {
                'audit_action': str,
                'audit_date_utc': inputs.datetime_from_iso8601,
                'audit_user': str,
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_audit_parser))
        self._check_audit([])

    def test_query_delete_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
            },
            parser_types(self.TestController.query_delete_parser))
        self._check_audit([])

    def test_get_response_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.get_response_model.name)
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type)
        self._check_audit([])

    def test_get_audit_response_model(self):
        self.assertEqual(
            'AuditTestModel',
            self.TestController.get_audit_response_model.name)
        self.assertEqual(
            {'audit_action': 'String',
             'audit_date_utc': 'DateTime',
             'audit_user': 'String',
             'key': 'String',
             'mandatory': 'Integer',
             'optional': 'String'},
            self.TestController.get_audit_response_model.fields_flask_type)
        self._check_audit([])


class SQLAlchemyFlaskRestPlusModelsTest(unittest.TestCase):
    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_rest_plus_type_for_string_field_is_string(self):
        field = marshmallow_fields.String()
        self.assertEqual(flask_rest_plus_fields.String, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_int_field_is_integer(self):
        field = marshmallow_fields.Integer()
        self.assertEqual(flask_rest_plus_fields.Integer, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_bool_field_is_boolean(self):
        field = marshmallow_fields.Boolean()
        self.assertEqual(flask_rest_plus_fields.Boolean, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_date_field_is_date(self):
        field = marshmallow_fields.Date()
        self.assertEqual(flask_rest_plus_fields.Date, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_datetime_field_is_datetime(self):
        field = marshmallow_fields.DateTime()
        self.assertEqual(flask_rest_plus_fields.DateTime, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_decimal_field_is_fixed(self):
        field = marshmallow_fields.Decimal()
        self.assertEqual(flask_rest_plus_fields.Fixed, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_float_field_is_float(self):
        field = marshmallow_fields.Float()
        self.assertEqual(flask_rest_plus_fields.Float, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_number_field_is_decimal(self):
        field = marshmallow_fields.Number()
        self.assertEqual(flask_rest_plus_fields.Decimal, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_time_field_is_datetime(self):
        field = marshmallow_fields.Time()
        self.assertEqual(flask_rest_plus_fields.DateTime, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_field_field_is_string(self):
        field = marshmallow_fields.Field()
        self.assertEqual(flask_rest_plus_fields.String, database_sqlalchemy._get_rest_plus_type(field))

    def test_rest_plus_type_for_none_field_cannot_be_guessed(self):
        with self.assertRaises(Exception) as cm:
            database_sqlalchemy._get_rest_plus_type(None)
        self.assertEqual('Flask RestPlus field type cannot be guessed for None field.', cm.exception.args[0])

    def test_rest_plus_example_for_string_field(self):
        field = marshmallow_fields.String()
        self.assertEqual('sample_value', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_int_field_is_integer(self):
        field = marshmallow_fields.Integer()
        self.assertEqual('0', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_bool_field_is_true(self):
        field = marshmallow_fields.Boolean()
        self.assertEqual('true', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_date_field_is_YYYY_MM_DD(self):
        field = marshmallow_fields.Date()
        self.assertEqual('2017-09-24', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_datetime_field_is_YYYY_MM_DDTHH_MM_SS(self):
        field = marshmallow_fields.DateTime()
        self.assertEqual('2017-09-24T15:36:09', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_decimal_field_is_decimal(self):
        field = marshmallow_fields.Decimal()
        self.assertEqual('0.0', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_float_field_is_float(self):
        field = marshmallow_fields.Float()
        self.assertEqual('0.0', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_number_field_is_decimal(self):
        field = marshmallow_fields.Number()
        self.assertEqual('0.0', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_time_field_is_HH_MM_SS(self):
        field = marshmallow_fields.Time()
        self.assertEqual('15:36:09', database_sqlalchemy._get_example(field))

    def test_rest_plus_example_for_none_field_is_sample_value(self):
        self.assertEqual('sample_value', database_sqlalchemy._get_example(None))


class SQlAlchemyColumnsTest(unittest.TestCase):
    _model = None

    @classmethod
    def setUpClass(cls):
        database.load('sqlite:///:memory:', cls._create_models)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_sqlalchemy.CRUDModel, base):
            __tablename__ = 'sample_table_name'

            string_column = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
            integer_column = sqlalchemy.Column(sqlalchemy.Integer)
            boolean_column = sqlalchemy.Column(sqlalchemy.Boolean)
            date_column = sqlalchemy.Column(sqlalchemy.Date)
            datetime_column = sqlalchemy.Column(sqlalchemy.DateTime)
            float_column = sqlalchemy.Column(sqlalchemy.Float)

        logger.info('Save model class...')
        cls._model = TestModel
        return [TestModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_field_declaration_order_is_kept_in_schema(self):
        fields = self._model.schema().fields
        self.assertEqual(
            [
                'string_column',
                'integer_column',
                'boolean_column',
                'date_column',
                'datetime_column',
                'float_column',
            ],
            [field_name for field_name in fields]
        )

    def test_python_type_for_sqlalchemy_string_field_is_string(self):
        field = self._model.schema().fields['string_column']
        self.assertEqual(str, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_integer_field_is_integer(self):
        field = self._model.schema().fields['integer_column']
        self.assertEqual(int, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_boolean_field_is_boolean(self):
        field = self._model.schema().fields['boolean_column']
        self.assertEqual(inputs.boolean, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_date_field_is_date(self):
        field = self._model.schema().fields['date_column']
        self.assertEqual(inputs.date_from_iso8601, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_datetime_field_is_datetime(self):
        field = self._model.schema().fields['datetime_column']
        self.assertEqual(inputs.datetime_from_iso8601, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_float_field_is_float(self):
        field = self._model.schema().fields['float_column']
        self.assertEqual(float, database_sqlalchemy._get_python_type(field))

    def test_python_type_for_sqlalchemy_none_field_cannot_be_guessed(self):
        with self.assertRaises(Exception) as cm:
            database_sqlalchemy._get_python_type(None)
        self.assertEqual('Python field type cannot be guessed for None field.', cm.exception.args[0])


class FlaskRestPlusErrorsTest(unittest.TestCase):
    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_handle_exception_failed_validation_on_list_of_items(self):
        class TestAPI:

            @staticmethod
            def model(cls, name):
                pass

            @staticmethod
            def errorhandler(cls):
                pass

            @staticmethod
            def marshal_with(cls, code):
                def wrapper(func):
                    # Mock of the input (List of items)
                    received_data = [{'optional_string_value': 'my_value1', 'mandatory_integer_value': 1,
                                      'optional_enum_value': 'First Enum Value', 'optional_date_value': '2017-10-23',
                                      'optional_date_time_value': '2017-10-24T21:46:57.12458+00:00',
                                      'optional_float_value': 100},
                                     {'optional_string_value': 'my_value2', 'optional_enum_value': 'First Enum Value',
                                      'optional_date_value': '2017-10-23',
                                      'optional_date_time_value': '2017-10-24T21:46:57.12458+00:00',
                                      'optional_float_value': 200}]
                    failed_validation = flask_restplus_errors.ValidationFailed(received_data)
                    errors = {1: {'mandatory_integer_value': ['Missing data for required field.']}}
                    setattr(failed_validation, 'errors', errors)
                    # Call handle_exception method
                    result = func(failed_validation)
                    # Assert output, if NOK will raise Assertion Error
                    assert (result[0] == {'fields': [{'field_name': 'mandatory_integer_value on item number: 1.',
                                                      'messages': ['Missing data for required field.']}]})
                    assert (result[1] == 400)
                    return result

                return wrapper

        # Since TestApi is not completely mocked, add_failed_validation_handler will raise a "NoneType is not iterable
        # exception after the call to handle_exception. Exception is therefore ignored
        try:
            flask_restplus_errors.add_failed_validation_handler(TestAPI)
        except TypeError:
            pass

    def test_handle_exception_failed_validation_a_single_item(self):
        class TestAPI:

            @staticmethod
            def model(cls, name):
                pass

            @staticmethod
            def errorhandler(cls):
                pass

            @staticmethod
            def marshal_with(cls, code):
                def wrapper(func):
                    # Mock of the input (Single item)
                    received_data = {'optional_string_value': 'my_value1', 'mandatory_integer_value': 1,
                                     'optional_enum_value': 'First Enum Value', 'optional_date_value': '2017-10-23',
                                     'optional_date_time_value': '2017-10-24T21:46:57.12458+00:00',
                                     'optional_float_value': 100}, {'optional_string_value': 'my_value2',
                                                                    'optional_enum_value': 'First Enum Value',
                                                                    'optional_date_value': '2017-10-23',
                                                                    'optional_date_time_value': '2017-10-24T21:46:57.12458+00:00',
                                                                    'optional_float_value': 200}
                    failed_validation = flask_restplus_errors.ValidationFailed(received_data)
                    errors = {'mandatory_integer_value': ['Missing data for required field.']}
                    setattr(failed_validation, 'errors', errors)
                    # Call handle_exception method
                    result = func(failed_validation)
                    # Assert output, if NOK will raise Assertion Error
                    assert (result[0] == {'fields': [
                        {'field_name': 'mandatory_integer_value', 'messages': ['Missing data for required field.']}]})
                    assert (result[1] == 400)
                    return result

                return wrapper

        # Since TestApi is not completely mocked, add_failed_validation_handler will raise a "NoneType is not iterable
        # exception after the call to handle_exception. Exception is therefore ignored
        try:
            flask_restplus_errors.add_failed_validation_handler(TestAPI)
        except TypeError:
            pass


class EnumTest(enum.Enum):
    Value1 = 1
    Value2 = 2


class MongoCRUDControllerTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    class TestAutoIncrementController(database.CRUDController):
        pass

    class TestDateController(database.CRUDController):
        pass

    class TestDictController(database.CRUDController):
        pass

    class TestOptionalDictController(database.CRUDController):
        pass

    class TestIndexController(database.CRUDController):
        pass

    class TestDefaultPrimaryKeyController(database.CRUDController):
        pass

    class TestListController(database.CRUDController):
        pass

    class TestIdController(database.CRUDController):
        pass

    class TestUnvalidatedListAndDictController(database.CRUDController):
        pass

    class TestVersionedController(database.CRUDController):
        pass

    class TestVersionedUniqueNonPrimaryController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('mongomock', cls._create_models)
        cls.TestController.namespace(TestAPI)
        cls.TestAutoIncrementController.namespace(TestAPI)
        cls.TestDateController.namespace(TestAPI)
        cls.TestDictController.namespace(TestAPI)
        cls.TestOptionalDictController.namespace(TestAPI)
        cls.TestIndexController.namespace(TestAPI)
        cls.TestDefaultPrimaryKeyController.namespace(TestAPI)
        cls.TestListController.namespace(TestAPI)
        cls.TestIdController.namespace(TestAPI)
        cls.TestUnvalidatedListAndDictController.namespace(TestAPI)
        cls.TestVersionedController.namespace(TestAPI)
        cls.TestVersionedUniqueNonPrimaryController.namespace(TestAPI)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_mongo.CRUDModel, base=base, table_name='sample_table_name'):
            key = database_mongo.Column(str, is_primary_key=True)
            mandatory = database_mongo.Column(int, is_nullable=False)
            optional = database_mongo.Column(str)

        class TestAutoIncrementModel(database_mongo.CRUDModel, base=base, table_name='auto_increment_table_name'):
            key = database_mongo.Column(int, is_primary_key=True, should_auto_increment=True)
            enum_field = database_mongo.Column(EnumTest, is_nullable=False, description='Test Documentation')
            optional_with_default = database_mongo.Column(str, default_value='Test value')

        class TestDateModel(database_mongo.CRUDModel, base=base, table_name='date_table_name'):
            key = database_mongo.Column(str, is_primary_key=True)
            date_str = database_mongo.Column(datetime.date)
            datetime_str = database_mongo.Column(datetime.datetime)

        class TestDictModel(database_mongo.CRUDModel, base=base, table_name='dict_table_name'):
            key = database_mongo.Column(str, is_primary_key=True)
            dict_col = database_mongo.DictColumn(
                {
                    'first_key': database_mongo.Column(EnumTest, is_nullable=False),
                    'second_key': database_mongo.Column(int, is_nullable=False),
                },
                is_nullable=False)

        class TestOptionalDictModel(database_mongo.CRUDModel, base=base, table_name='optional_dict_table_name'):
            key = database_mongo.Column(str, is_primary_key=True)
            dict_col = database_mongo.DictColumn(
                lambda model_as_dict: {
                    'first_key': database_mongo.Column(EnumTest, is_nullable=False),
                    'second_key': database_mongo.Column(int, is_nullable=False),
                }
            )

        class TestIndexModel(database_mongo.CRUDModel, base=base, table_name='index_table_name'):
            unique_key = database_mongo.Column(str, is_primary_key=True, index_type=database_mongo.IndexType.Unique)
            non_unique_key = database_mongo.Column(datetime.date, index_type=database_mongo.IndexType.Other)

        class TestDefaultPrimaryKeyModel(database_mongo.CRUDModel, base=base, table_name='default_primary_table_name'):
            key = database_mongo.Column(is_primary_key=True, default_value='test')
            optional = database_mongo.Column()

        class TestListModel(database_mongo.CRUDModel, base=base, table_name='list_table_name'):
            key = database_mongo.Column(is_primary_key=True)
            list_field = database_mongo.ListColumn(database_mongo.DictColumn({
                        'first_key': database_mongo.Column(EnumTest, is_nullable=False),
                        'second_key': database_mongo.Column(int, is_nullable=False),
                    }))
            bool_field = database_mongo.Column(bool)

        class TestUnvalidatedListAndDictModel(database_mongo.CRUDModel, base=base, table_name='list_and_dict_table_name'):
            float_key = database_mongo.Column(float, is_primary_key=True)
            float_with_default = database_mongo.Column(float, default_value=34)
            dict_field = database_mongo.Column(dict, is_required=True)
            list_field = database_mongo.Column(list, is_required=True)

        class TestIdModel(database_mongo.CRUDModel, base=base, table_name='id_table_name'):
            _id = database_mongo.Column(is_primary_key=True)

        class TestVersionedModel(versioning_mongo.VersionedCRUDModel, base=base, table_name='versioned_table_name'):
            key = database_mongo.Column(is_primary_key=True, index_type=database_mongo.IndexType.Unique)
            dict_field = database_mongo.DictColumn({
                'first_key': database_mongo.Column(EnumTest, is_nullable=False),
                'second_key': database_mongo.Column(int, is_nullable=False),
            }, is_required=True)

        class TestVersionedUniqueNonPrimaryModel(versioning_mongo.VersionedCRUDModel, base=base, table_name='versioned_uni_table_name'):
            key = database_mongo.Column(int, is_primary_key=True, should_auto_increment=True)
            unique = database_mongo.Column(int, index_type=database_mongo.IndexType.Unique)

        logger.info('Save model class...')
        cls.TestController.model(TestModel)
        cls.TestAutoIncrementController.model(TestAutoIncrementModel)
        cls.TestDateController.model(TestDateModel)
        cls.TestDictController.model(TestDictModel)
        cls.TestOptionalDictController.model(TestOptionalDictModel)
        cls.TestIndexController.model(TestIndexModel)
        cls.TestDefaultPrimaryKeyController.model(TestDefaultPrimaryKeyModel)
        cls.TestListController.model(TestListModel)
        cls.TestIdController.model(TestIdModel)
        cls.TestUnvalidatedListAndDictController.model(TestUnvalidatedListAndDictModel)
        cls.TestVersionedController.model(TestVersionedModel)
        cls.TestVersionedUniqueNonPrimaryController.model(TestVersionedUniqueNonPrimaryModel)
        return [TestModel, TestAutoIncrementModel, TestDateModel, TestDictModel, TestOptionalDictModel, TestIndexModel,
                TestDefaultPrimaryKeyModel, TestListModel, TestIdModel, TestUnvalidatedListAndDictModel,
                TestVersionedModel, TestVersionedUniqueNonPrimaryModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_get_all_without_data_returns_empty_list(self):
        self.assertEqual([], self.TestController.get({}))

    def test_post_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual(None, cm.exception.received_data)

    def test_post_list_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual([], cm.exception.received_data)

    def test_post_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_post_many_with_empty_list_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual([], cm.exception.received_data)

    def test_put_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_put_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_delete_without_nothing_do_not_fail(self):
        self.assertEqual(0, self.TestController.delete({}))

    def test_post_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 'my_key',
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key'}, cm.exception.received_data)

    def test_post_many_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 'my_key',
            }])
        self.assertEqual({0: {'mandatory': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'key': 'my_key'}], cm.exception.received_data)

    def test_post_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'mandatory': 1}, cm.exception.received_data)

    def test_post_many_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'mandatory': 1}], cm.exception.received_data)

    def test_post_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 256,
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Not a valid str.']}, cm.exception.errors)
        self.assertEqual({'key': 256, 'mandatory': 1}, cm.exception.received_data)

    def test_post_twice_with_unique_index_is_invalid(self):
        self.assertEqual(
            {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            self.TestIndexController.post({
                'unique_key': 'test',
                'non_unique_key': '2017-01-01',
            })
        )
        with self.assertRaises(Exception) as cm:
            self.TestIndexController.post({
                'unique_key': 'test',
                'non_unique_key': '2017-01-02',
            })
        self.assertEqual({'': ['This item already exists.']}, cm.exception.errors)
        self.assertEqual({'non_unique_key': '2017-01-02', 'unique_key': 'test'}, cm.exception.received_data)

    def test_get_all_without_primary_key_is_valid(self):
        self.assertEqual(
            {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            self.TestIndexController.post({
                'unique_key': 'test',
                'non_unique_key': '2017-01-01',
            })
        )
        self.assertEqual(
            [
                {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            ],
            self.TestIndexController.get({})
        )

    def test_get_one_and_multiple_results_is_invalid(self):
        self.TestIndexController.post({
            'unique_key': 'test',
            'non_unique_key': '2017-01-01',
        })
        self.TestIndexController.post({
            'unique_key': 'test2',
            'non_unique_key': '2017-01-01',
        })
        with self.assertRaises(Exception) as cm:
            self.TestIndexController.get_one({})
        self.assertEqual({'': ['More than one result: Consider another filtering.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)

    def test_get_one_is_valid(self):
        self.TestIndexController.post({
            'unique_key': 'test',
            'non_unique_key': '2017-01-01',
        })
        self.TestIndexController.post({
            'unique_key': 'test2',
            'non_unique_key': '2017-01-01',
        })
        self.assertEqual(
            {
                'unique_key': 'test2',
                'non_unique_key': '2017-01-01',
            },
            self.TestIndexController.get_one({'unique_key': 'test2'})
        )

    def test_get_one_without_result_is_valid(self):
        self.TestIndexController.post({
            'unique_key': 'test',
            'non_unique_key': '2017-01-01',
        })
        self.TestIndexController.post({
            'unique_key': 'test2',
            'non_unique_key': '2017-01-01',
        })
        self.assertEqual(
            {},
            self.TestIndexController.get_one({'unique_key': 'test3'})
        )

    def _assert_regex(self, expected, actual):
        self.assertRegex(f'{actual}',
                         f'{expected}'.replace('[', '\\[').replace(']', '\\]').replace('\\\\', '\\'))

    def test_post_versioning_is_valid(self):
        self.assertEqual(
            {
                'key': 'first',
                'dict_field': {'first_key': 'Value1', 'second_key': 1},
                'valid_since_revision': 1,
                'valid_until_revision': None
            },
            self.TestVersionedController.post({
                'key': 'first',
                'dict_field.first_key': EnumTest.Value1,
                'dict_field.second_key': 1,
            })
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': None
                }
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': None
                }
            ],
            self.TestVersionedController.get({})
        )

    def test_revison_is_shared(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedUniqueNonPrimaryController.post({
            'unique': 1,
        })
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.second_key': 2,
        })
        self.TestVersionedController.delete({
            'key': 'first',
        })
        self.TestVersionedController.rollback_to({
            'revision': 2,
        })
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 2},
                    'valid_since_revision': 3,
                    'valid_until_revision': 4
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 3
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 5,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 1,
                    'unique': 1,
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedUniqueNonPrimaryController.get_history({})
        )

    def test_put_versioning_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.assertEqual(
            (
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': None
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                }
            ),
            self.TestVersionedController.put({
                'key': 'first',
                'dict_field.first_key': EnumTest.Value2,
            })
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get({})
        )

    def test_delete_versioning_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value2,
        })
        self.assertEqual(
            1,
            self.TestVersionedController.delete({
                'key': 'first',
            })
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': 3
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [],
            self.TestVersionedController.get({})
        )

    def test_rollback_deleted_versioning_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value2,
        })
        before_delete = 2
        self.TestVersionedController.delete({
            'key': 'first',
        })
        self.assertEqual(
            1,
            self.TestVersionedController.rollback_to({'revision': before_delete})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': 3
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 4,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 4,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get({})
        )

    def test_rollback_before_update_deleted_versioning_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        before_update = 1
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value2,
        })
        self.TestVersionedController.delete({
            'key': 'first',
        })
        self.assertEqual(
            1,
            self.TestVersionedController.rollback_to({'revision': before_update})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': 3
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 4,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 4,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get({})
        )

    def test_rollback_already_valid_versioning_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value2,
        })

        self.assertEqual(
            0,
            self.TestVersionedController.rollback_to({'revision': 2})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                }
            ],
            self.TestVersionedController.get({})
        )

    def test_rollback_unknown_criteria_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        before_update = 1
        self.TestVersionedController.put({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value2,
        })

        self.assertEqual(
            0,
            self.TestVersionedController.rollback_to({'revision': before_update, 'key': 'unknown'})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'valid_since_revision': 1,
                    'valid_until_revision': 2
                },
            ],
            self.TestVersionedController.get_history({})
        )
        self.assertEqual(
            [
                {
                    'key': 'first',
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'valid_since_revision': 2,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get({})
        )

    def test_rollback_without_revision_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestVersionedController.rollback_to({'key': 'unknown'})
        self.assertEqual({'revision': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'unknown'}, cm.exception.received_data)

    def test_rollback_with_non_int_revision_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestVersionedController.rollback_to({'revision': 'invalid revision'})
        self.assertEqual({'revision': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'revision': 'invalid revision'}, cm.exception.received_data)

    def test_rollback_without_versioning_is_valid(self):
        self.assertEqual(0, self.TestController.rollback_to({'revision': 'invalid revision'}))

    def test_rollback_with_negative_revision_is_valid(self):
        self.assertEqual(0, self.TestVersionedController.rollback_to({'revision': -1}))

    def test_rollback_before_existing_is_valid(self):
        self.TestVersionedController.post({
            'key': 'first',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        before_insert = 1
        self.TestVersionedController.post({
            'key': 'second',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.assertEqual(
            1,
            self.TestVersionedController.rollback_to({'revision': before_insert})
        )
        self.assertEqual(
            [
            ],
            self.TestVersionedController.get({'key': 'second'})
        )

    def test_rollback_multiple_rows_is_valid(self):
        self.TestVersionedController.post({
            'key': '1',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.post({
            'key': '2',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.put({
            'key': '1',
            'dict_field.first_key': EnumTest.Value2,
        })
        self.TestVersionedController.delete({
            'key': '2',
        })
        self.TestVersionedController.post({
            'key': '3',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.post({
            'key': '4',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        before_insert = 6
        self.TestVersionedController.post({
            'key': '5',
            'dict_field.first_key': EnumTest.Value1,
            'dict_field.second_key': 1,
        })
        self.TestVersionedController.put({
            'key': '1',
            'dict_field.second_key': 2,
        })
        self.assertEqual(
            2,  # Remove key 5 and Update key 1 (Key 3 and Key 4 unchanged)
            self.TestVersionedController.rollback_to({'revision': before_insert})
        )
        self.assertEqual(
            [
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '3',
                    'valid_since_revision': 5,
                    'valid_until_revision': None
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '4',
                    'valid_since_revision': 6,
                    'valid_until_revision': None
                },
                {
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'key': '1',
                    'valid_since_revision': 9,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get({})
        )
        self.maxDiff = None
        self.assertEqual(
            [
                {
                    'dict_field': {'first_key': 'Value2', 'second_key': 2},
                    'key': '1',
                    'valid_since_revision': 8,
                    'valid_until_revision': 9
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '2',
                    'valid_since_revision': 2,
                    'valid_until_revision': 4
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '1',
                    'valid_since_revision': 1,
                    'valid_until_revision': 3
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '3',
                    'valid_since_revision': 5,
                    'valid_until_revision': None
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '4',
                    'valid_since_revision': 6,
                    'valid_until_revision': None
                },
                {
                    'dict_field': {'first_key': 'Value1', 'second_key': 1},
                    'key': '5',
                    'valid_since_revision': 7,
                    'valid_until_revision': 9
                },
                {
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'key': '1',
                    'valid_since_revision': 3,
                    'valid_until_revision': 8
                },
                {
                    'dict_field': {'first_key': 'Value2', 'second_key': 1},
                    'key': '1',
                    'valid_since_revision': 9,
                    'valid_until_revision': None
                },
            ],
            self.TestVersionedController.get_history({})
        )

    def test_versioning_handles_unique_non_primary(self):
        self.TestVersionedUniqueNonPrimaryController.post({
            'unique': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestVersionedUniqueNonPrimaryController.post({
                'unique': 1,
            })
        self.assertEqual({'': ['This item already exists.']}, cm.exception.errors)
        self.assertEqual({'key': 2, 'unique': 1, 'valid_since_revision': 2, 'valid_until_revision': None}, cm.exception.received_data)

    def test_post_id_is_valid(self):
        self.assertEqual(
            {'_id': '123456789abcdef012345678'},
            self.TestIdController.post({
                '_id': '123456789ABCDEF012345678',
            })
        )

    def test_invalid_id_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestIdController.post({
                '_id': 'invalid value',
            })
        self.assertEqual({'_id': ["'invalid value' is not a valid ObjectId, it must be a 12-byte input or a 24-character hex string"]}, cm.exception.errors)
        self.assertEqual({'_id': 'invalid value'}, cm.exception.received_data)

    def test_get_all_with_none_primary_key_is_valid(self):
        self.assertEqual(
            {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            self.TestIndexController.post({
                'unique_key': 'test',
                'non_unique_key': '2017-01-01',
            })
        )
        self.assertEqual(
            [
                {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            ],
            self.TestIndexController.get({'unique_key': None})
        )

    def test_post_many_with_same_unique_index_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestIndexController.post_many([
                {
                    'unique_key': 'test',
                    'non_unique_key': '2017-01-01',
                },
                {
                    'unique_key': 'test',
                    'non_unique_key': '2017-01-01',
                }
            ])
        self.assertEqual({'': ['batch op errors occurred']}, cm.exception.errors)
        self.assertEqual([
                {
                    'unique_key': 'test',
                    'non_unique_key': '2017-01-01',
                },
                {
                    'unique_key': 'test',
                    'non_unique_key': '2017-01-01',
                }
            ],
            cm.exception.received_data)

    def test_post_without_primary_key_but_default_value_is_valid(self):
        self.assertEqual(
            {'key': 'test', 'optional': 'test2'},
            self.TestDefaultPrimaryKeyController.post({
                'optional': 'test2',
            })
        )

    def test_put_without_primary_key_but_default_value_is_valid(self):
        self.assertEqual(
            {'key': 'test', 'optional': 'test2'},
            self.TestDefaultPrimaryKeyController.post({
                'optional': 'test2',
            })
        )
        self.assertEqual(
            ({'key': 'test', 'optional': 'test2'}, {'key': 'test', 'optional': 'test3'}),
            self.TestDefaultPrimaryKeyController.put({
                'optional': 'test3',
            })
        )

    def test_post_different_unique_index_is_valid(self):
        self.assertEqual(
            {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
            self.TestIndexController.post({
                'unique_key': 'test',
                'non_unique_key': '2017-01-01',
            })
        )
        self.assertEqual(
            {'non_unique_key': '2017-01-01', 'unique_key': 'test2'},
            self.TestIndexController.post({
                'unique_key': 'test2',
                'non_unique_key': '2017-01-01',
            })
        )
        self.assertEqual(
            [
                {'non_unique_key': '2017-01-01', 'unique_key': 'test'},
                {'non_unique_key': '2017-01-01', 'unique_key': 'test2'},
            ],
            self.TestIndexController.get({})
        )

    def test_post_many_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 256,
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Not a valid str.']}}, cm.exception.errors)
        self.assertEqual([{'key': 256, 'mandatory': 1}], cm.exception.received_data)

    def test_json_post_model_versioned(self):
        self.assertEqual(
            'TestVersionedModel_Versioned',
            self.TestVersionedController.json_post_model.name)
        self.assertEqual(
            {
                'dict_field': (
                    'Nested',
                    {
                        'first_key': 'String',
                        'second_key': 'Integer'
                    }
                ),
                'key': 'String'
            },
            self.TestVersionedController.json_post_model.fields_flask_type)
        self.assertEqual(
            {
                'dict_field': (
                    None,
                    {
                        'first_key': None,
                        'second_key': None
                    }
                ),
                'key': None
            },
            self.TestVersionedController.json_post_model.fields_description)
        self.assertEqual(
            {
                'dict_field': (
                    None,
                    {
                        'first_key': ['Value1', 'Value2'],
                        'second_key': None
                    }
                ),
                'key': None
            },
            self.TestVersionedController.json_post_model.fields_enum)
        self.assertEqual(
            {
                'dict_field': (
                    {'first_key': 'Value1', 'second_key': 1},
                    {
                        'first_key': 'Value1',
                        'second_key': 1
                    }
                ),
                'key': 'sample key'
            },
            self.TestVersionedController.json_post_model.fields_example)
        self.assertEqual(
            {
                'dict_field': (
                    {'first_key': None, 'second_key': None},
                    {
                        'first_key': None,
                        'second_key': None
                    }
                ),
                'key': None
            },
            self.TestVersionedController.json_post_model.fields_default)
        self.assertEqual(
            {
                'dict_field': (
                    True,
                    {
                        'first_key': False,
                        'second_key': False
                    }
                ),
                'key': False
            },
            self.TestVersionedController.json_post_model.fields_required)
        self.assertEqual(
            {
                'dict_field': (
                    False,
                    {
                        'first_key': False,
                        'second_key': False
                    }
                ),
                'key': False
            },
            self.TestVersionedController.json_post_model.fields_readonly)

    def test_json_post_model_with_list_of_dict(self):
        self.assertEqual(
            'TestListModel',
            self.TestListController.json_post_model.name)
        self.assertEqual(
            {
                'bool_field': 'Boolean',
                'key': 'String',
                'list_field': (
                    'List',
                    {'list_field_inner': (
                        'Nested',
                        {
                            'first_key': 'String',
                            'second_key': 'Integer'
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_flask_type)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_description)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': ['Value1', 'Value2'],
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_enum)
        self.assertEqual(
            {
                'bool_field': True,
                'key': 'sample key',
                'list_field': (
                    [{'first_key': 'Value1', 'second_key': 1}],
                    {'list_field_inner': (
                        {'first_key': 'Value1', 'second_key': 1},
                        {
                            'first_key': 'Value1',
                            'second_key': 1
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_example)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        {'first_key': None, 'second_key': None},
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_default)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_required)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.json_post_model.fields_readonly)

    def test_json_put_model_with_list_of_dict(self):
        self.assertEqual(
            'TestListModel',
            self.TestListController.json_put_model.name)
        self.assertEqual(
            {
                'bool_field': 'Boolean',
                'key': 'String',
                'list_field': (
                    'List',
                    {'list_field_inner': (
                        'Nested',
                        {
                            'first_key': 'String',
                            'second_key': 'Integer'
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_flask_type)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_description)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': ['Value1', 'Value2'],
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_enum)
        self.assertEqual(
            {
                'bool_field': True,
                'key': 'sample key',
                'list_field': (
                    [{'first_key': 'Value1', 'second_key': 1}],
                    {'list_field_inner': (
                        {'first_key': 'Value1', 'second_key': 1},
                        {
                            'first_key': 'Value1',
                            'second_key': 1
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_example)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        {'first_key': None, 'second_key': None},
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_default)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_required)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.json_put_model.fields_readonly)

    def test_put_with_wrong_type_is_invalid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestController.put({
                'key': 'value1',
                'mandatory': 'invalid value',
            })
        self.assertEqual({'mandatory': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': 'invalid value'}, cm.exception.received_data)

    def test_put_with_optional_as_None_is_valid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        self.TestController.put({
            'key': 'value1',
            'mandatory': 1,
            'optional': None,
        })
        self.assertEqual(
            [{'mandatory': 1, 'key': 'value1', 'optional': None}],
            self.TestController.get({})
        )

    def test_put_with_non_nullable_as_None_is_invalid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestController.put({
                'key': 'value1',
                'mandatory': None,
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': None}, cm.exception.received_data)

    def test_post_without_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': None},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
            })
        )

    def test_get_with_non_nullable_None_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': None},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
            })
        )
        self.assertEqual(
            [{'mandatory': 1, 'key': 'my_key', 'optional': None}],
            self.TestController.get({
                'key': 'my_key',
                'mandatory': None,
            })
        )

    def test_post_many_without_optional_is_valid(self):
        self.assertEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': None},
                {'mandatory': 2, 'key': 'my_key2', 'optional': None},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                }
            ])
        )

    def test_post_with_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        )

    def test_post_list_of_dict_is_valid(self):
        self.assertEqual(
            {
                'bool_field': False,
                'key': 'my_key',
                'list_field': [
                    {'first_key': 'Value1', 'second_key': 1},
                    {'first_key': 'Value2', 'second_key': 2},
                ],
            },
            self.TestListController.post({
                'key': 'my_key',
                'list_field': [
                    {'first_key': EnumTest.Value1, 'second_key': 1},
                    {'first_key': EnumTest.Value2, 'second_key': 2}
                ],
                'bool_field': False,
            })
        )

    def test_post_optional_missing_list_of_dict_is_valid(self):
        self.assertEqual(
            {
                'bool_field': False,
                'key': 'my_key',
                'list_field': [],
            },
            self.TestListController.post({
                'key': 'my_key',
                'bool_field': False,
            })
        )

    def test_post_optional_list_of_dict_as_None_is_valid(self):
        self.assertEqual(
            {
                'bool_field': False,
                'key': 'my_key',
                'list_field': [],
            },
            self.TestListController.post({
                'key': 'my_key',
                'bool_field': False,
                'list_field': None,
            })
        )

    def test_get_list_of_dict_is_valid(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            [
                {
                    'bool_field': False,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value1', 'second_key': 1},
                        {'first_key': 'Value2', 'second_key': 2},
                    ],
                }
            ],
            self.TestListController.get({
                'list_field': [
                    {'first_key': EnumTest.Value1, 'second_key': 1},
                    {'first_key': 'Value2', 'second_key': 2},
                ],
            })
        )

    def test_get_optional_list_of_dict_as_None_is_skipped(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            [
                {
                    'bool_field': False,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value1', 'second_key': 1},
                        {'first_key': 'Value2', 'second_key': 2},
                    ],
                }
            ],
            self.TestListController.get({
                'list_field': None,
            })
        )

    def test_delete_list_of_dict_is_valid(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            1,
            self.TestListController.delete({
                'list_field': [
                    {'first_key': EnumTest.Value1, 'second_key': 1},
                    {'first_key': 'Value2', 'second_key': 2},
                ],
            })
        )

    def test_delete_optional_list_of_dict_as_None_is_valid(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            1,
            self.TestListController.delete({
                'list_field': None,
            })
        )

    def test_put_list_of_dict_is_valid(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            (
                {
                    'bool_field': False,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value1', 'second_key': 1},
                        {'first_key': 'Value2', 'second_key': 2},
                    ],
                },
                {
                    'bool_field': True,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value2', 'second_key': 10},
                        {'first_key': 'Value1', 'second_key': 2},
                    ],
                },
            ),
            self.TestListController.put({
                'key': 'my_key',
                'list_field': [
                    {'first_key': EnumTest.Value2, 'second_key': 10},
                    {'first_key': EnumTest.Value1, 'second_key': 2}
                ],
                'bool_field': True,
            })
        )

    def test_put_without_optional_list_of_dict_is_valid(self):
        self.TestListController.post({
            'key': 'my_key',
            'list_field': [
                {'first_key': EnumTest.Value1, 'second_key': 1},
                {'first_key': EnumTest.Value2, 'second_key': 2}
            ],
            'bool_field': False,
        })
        self.assertEqual(
            (
                {
                    'bool_field': False,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value1', 'second_key': 1},
                        {'first_key': 'Value2', 'second_key': 2},
                    ],
                },
                {
                    'bool_field': True,
                    'key': 'my_key',
                    'list_field': [
                        {'first_key': 'Value1', 'second_key': 1},
                        {'first_key': 'Value2', 'second_key': 2},
                    ],
                },
            ),
            self.TestListController.put({
                'key': 'my_key',
                'bool_field': True,
            })
        )

    def test_post_dict_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )

    def test_post_missing_optional_dict_is_valid(self):
        self.assertEqual(
            {
                'dict_col': {
                    'first_key': None,
                    'second_key': None
                },
                'key': 'my_key'
            },
            self.TestOptionalDictController.post({
                'key': 'my_key',
            })
        )

    def test_post_optional_dict_as_None_is_valid(self):
        self.assertEqual(
            {
                'dict_col': {
                    'first_key': None,
                    'second_key': None
                },
                'key': 'my_key'
            },
            self.TestOptionalDictController.post({
                'key': 'my_key',
                'dict_col': None,
            })
        )

    def test_put_missing_optional_dict_is_valid(self):
        self.TestOptionalDictController.post({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value1',
                'second_key': 3,
            },
        })
        self.assertEqual(
            (
                {
                    'key': 'my_key',
                    'dict_col': {
                        'first_key': 'Value1',
                        'second_key': 3,
                    },
                },
                {
                    'key': 'my_key',
                    'dict_col': {
                        'first_key': 'Value1',
                        'second_key': 3,
                    },
                }
            ),
            self.TestOptionalDictController.put({
                'key': 'my_key',
            })
        )

    def test_put_optional_dict_as_None_is_valid(self):
        self.TestOptionalDictController.post({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value1',
                'second_key': 3,
            },
        })
        self.assertEqual(
            (
                {
                    'key': 'my_key',
                    'dict_col': {
                        'first_key': 'Value1',
                        'second_key': 3,
                    },
                },
                {
                    'key': 'my_key',
                    'dict_col': {
                        'first_key': 'Value1',
                        'second_key': 3,
                    },
                }
            ),
            self.TestOptionalDictController.put({
                'key': 'my_key',
                'dict_col': None,
            })
        )

    def test_get_optional_dict_as_None_is_valid(self):
        self.TestOptionalDictController.post({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value1',
                'second_key': 3,
            },
        })
        self.assertEqual(
            [
                {
                    'key': 'my_key',
                    'dict_col': {
                        'first_key': 'Value1',
                        'second_key': 3,
                    },
                }
            ],
            self.TestOptionalDictController.get({
                'dict_col': None,
            })
        )

    def test_delete_optional_dict_as_None_is_valid(self):
        self.TestOptionalDictController.post({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value1',
                'second_key': 3,
            },
        })
        self.assertEqual(
            1,
            self.TestOptionalDictController.delete({
                'dict_col': None,
            })
        )

    def test_get_with_dot_notation_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': EnumTest.Value1,
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            [
                {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            ],
            self.TestDictController.get({
                'dict_col.first_key': EnumTest.Value1,
            })
        )

    def test_update_with_dot_notation_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            (
                {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
                {'dict_col': {'first_key': 'Value1', 'second_key': 4}, 'key': 'my_key'}
            ),
            self.TestDictController.put({
                'key': 'my_key',
                'dict_col.second_key': 4,
            })
        )

    def test_update_with_dot_notation_invalid_value_is_invalid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        with self.assertRaises(Exception) as cm:
            self.TestDictController.put({
                'key': 'my_key',
                'dict_col.second_key': 'invalid integer',
            })
        self.assertEqual({'dict_col.second_key': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key', 'dict_col.second_key': 'invalid integer'}, cm.exception.received_data)

    def test_delete_with_dot_notation_invalid_value_is_invalid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        with self.assertRaises(Exception) as cm:
            self.TestDictController.delete({
                'dict_col.second_key': 'invalid integer',
            })
        self.assertEqual({'dict_col.second_key': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'dict_col.second_key': 'invalid integer'}, cm.exception.received_data)

    def test_delete_with_dot_notation_valid_value_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(1, self.TestDictController.delete({
                'dict_col.second_key': 3,
            }))

    def test_delete_with_dot_notation_enum_value_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(1, self.TestDictController.delete({
                'dict_col.first_key': EnumTest.Value1,
            }))

    def test_post_with_dot_notation_invalid_value_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col.first_key': 'Value1',
                'dict_col.second_key': 'invalid integer',
            })
        self.assertEqual({'dict_col.second_key': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key', 'dict_col.first_key': 'Value1', 'dict_col.second_key': 'invalid integer'}, cm.exception.received_data)

    def test_post_with_dot_notation_valid_value_is_valid(self):
        self.assertEqual({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value2',
                'second_key': 1,
            }
        },
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col.first_key': 'Value2',
                'dict_col.second_key': 1,
            })
        )

    def test_get_with_unmatching_dot_notation_is_empty(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            [],
            self.TestDictController.get({
                'dict_col.first_key': 'Value2',
            })
        )

    def test_get_with_unknown_dot_notation_returns_everything(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            [
                {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'}
            ],
            self.TestDictController.get({
                'dict_col.unknown': 'Value1',
            })
        )

    def test_delete_with_dot_notation_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            1,
            self.TestDictController.delete({
                'dict_col.first_key': 'Value1',
            })
        )
        self.assertEqual(
            [],
            self.TestDictController.get({})
        )

    def test_delete_with_unmatching_dot_notation_is_empty(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            0,
            self.TestDictController.delete({
                'dict_col.first_key': 'Value2',
            })
        )
        self.assertEqual(
            [
                {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            ],
            self.TestDictController.get({})
        )

    def test_delete_with_unknown_dot_notation_deletes_everything(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            1,
            self.TestDictController.delete({
                'dict_col.unknown': 'Value2',
            })
        )
        self.assertEqual(
            [],
            self.TestDictController.get({})
        )

    def test_put_without_primary_key_is_invalid(self):
        self.TestDictController.post({
            'key': 'my_key',
            'dict_col': {
                'first_key': 'Value1',
                'second_key': 3,
            },
        })
        with self.assertRaises(Exception) as cm:
            self.TestDictController.put({
                'dict_col': {
                    'first_key': 'Value2',
                    'second_key': 4,
                },
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({
                'dict_col': {
                    'first_key': 'Value2',
                    'second_key': 4,
                },
            }, cm.exception.received_data)

    def test_post_dict_with_dot_notation_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col.first_key': 'Value1',
                'dict_col.second_key': 3,
            })
        )

    def test_put_dict_with_dot_notation_is_valid(self):
        self.assertEqual(
            {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                    'second_key': 3,
                },
            })
        )
        self.assertEqual(
            (
                {'dict_col': {'first_key': 'Value1', 'second_key': 3}, 'key': 'my_key'},
                {'dict_col': {'first_key': 'Value2', 'second_key': 3}, 'key': 'my_key'}
            ),
            self.TestDictController.put({
                'key': 'my_key',
                'dict_col.first_key': EnumTest.Value2,
            })
        )

    def test_post_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDictController.post({
                'key': 'my_key',
                'dict_col': {
                    'first_key': 'Value1',
                },
            })
        self.assertEqual({'dict_col.second_key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key', 'dict_col': {'first_key': 'Value1'}}, cm.exception.received_data)

    def test_post_many_with_optional_is_valid(self):
        self.assertListEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
                {'mandatory': 2, 'key': 'my_key2', 'optional': 'my_value2'},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                }
            ])
        )

    def test_post_with_unknown_field_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            })
        )

    def test_post_many_with_unknown_field_is_valid(self):
        self.assertListEqual(
            [
                {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
                {'mandatory': 2, 'key': 'my_key2', 'optional': 'my_value2'},
            ],
            self.TestController.post_many([
                {
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    # This field do not exists in schema
                    'unknown': 'my_value',
                },
                {
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    # This field do not exists in schema
                    'unknown': 'my_value2',
                },
            ])
        )

    def test_post_with_specified_incremented_field_is_ignored_and_valid(self):
        self.assertEqual(
            {'optional_with_default': 'Test value', 'key': 1, 'enum_field': 'Value1'},
            self.TestAutoIncrementController.post({
                'key': 'my_key',
                'enum_field': 'Value1',
            })
        )

    def test_post_with_enum_is_valid(self):
        self.assertEqual(
            {'optional_with_default': 'Test value', 'key': 1, 'enum_field': 'Value1'},
            self.TestAutoIncrementController.post({
                'key': 'my_key',
                'enum_field': EnumTest.Value1,
            })
        )

    def test_post_with_invalid_enum_choice_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestAutoIncrementController.post({
                'key': 'my_key',
                'enum_field': 'InvalidValue',
            })
        self.assertEqual({'enum_field': ['Value "InvalidValue" is not within [\'Value1\', \'Value2\'].']}, cm.exception.errors)
        self.assertEqual({'enum_field': 'InvalidValue'}, cm.exception.received_data)

    def test_post_many_with_specified_incremented_field_is_ignored_and_valid(self):
        self.assertListEqual(
            [
                {'optional_with_default': 'Test value', 'enum_field': 'Value1', 'key': 1},
                {'optional_with_default': 'Test value', 'enum_field': 'Value2', 'key': 2},
            ],
            self.TestAutoIncrementController.post_many([{
                'key': 'my_key',
                'enum_field': 'Value1',
            }, {
                'key': 'my_key',
                'enum_field': 'Value2',
            }])
        )

    def test_get_without_filter_is_retrieving_the_only_item(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.TestController.get({}))

    def test_get_from_another_thread_than_post(self):
        def save_get_result():
            self.thread_get_result = self.TestController.get({})

        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })

        self.thread_get_result = None
        get_thread = Thread(name='GetInOtherThread', target=save_get_result)
        get_thread.start()
        get_thread.join()

        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.thread_get_result)

    def test_get_without_filter_is_retrieving_everything_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))

    def test_get_without_filter_is_retrieving_everything(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            },
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))

    def test_get_with_filter_is_retrieving_subset_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))

    def test_get_with_filter_is_retrieving_subset(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            },
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))

    def test_put_is_updating(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            (
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
            ),
            self.TestController.put({
                'key': 'my_key1',
                'optional': 'my_value',
            })
        )
        self.assertEqual([{'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'}],
                         self.TestController.get({'mandatory': 1}))

    def test_put_is_updating_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        self.assertEqual(
            (
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59', 'key': 'my_key1'},
                {'date_str': '2018-06-01', 'datetime_str': '1989-12-31T01:00:00', 'key': 'my_key1'},
            ),
            self.TestDateController.put({
                'key': 'my_key1',
                'date_str': '2018-06-01',
                'datetime_str': '1989-12-31T01:00:00',
            })
        )
        self.assertEqual([
            {'date_str': '2018-06-01', 'datetime_str': '1989-12-31T01:00:00', 'key': 'my_key1'}
        ],
            self.TestDateController.get({'date_str': '2018-06-01'}))

    def test_get_date_is_handled_for_valid_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        d = datetime.datetime.strptime('2017-05-15', '%Y-%m-%d').date()
        self.assertEqual(
            [
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59', 'key': 'my_key1'},
            ],
            self.TestDateController.get({
                'date_str': d,
            })
        )

    def test_post_invalid_date_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDateController.post({
                'key': 'my_key1',
                'date_str': 'this is not a date',
                'datetime_str': '2016-09-23T23:59:59',
            })
        self.assertEqual({'date_str': ['Not a valid date.']}, cm.exception.errors)
        self.assertEqual({
                'key': 'my_key1',
                'date_str': 'this is not a date',
                'datetime_str': '2016-09-23T23:59:59',
            },
            cm.exception.received_data)

    def test_get_invalid_date_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDateController.get({
                'date_str': 'this is not a date',
            })
        self.assertEqual({'date_str': ['Not a valid date.']}, cm.exception.errors)
        self.assertEqual({
                'date_str': 'this is not a date',
            },
            cm.exception.received_data)

    def test_delete_invalid_date_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDateController.delete({
                'date_str': 'this is not a date',
            })
        self.assertEqual({'date_str': ['Not a valid date.']}, cm.exception.errors)
        self.assertEqual({
                'date_str': 'this is not a date',
            },
            cm.exception.received_data)

    def test_get_with_unknown_fields_is_valid(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2018-12-30',
            'datetime_str': '2016-09-23T23:59:59',
        })
        self.assertEqual(
            [{
                'key': 'my_key1',
                'date_str': '2018-12-30',
                'datetime_str': '2016-09-23T23:59:59',
            }],
            self.TestDateController.get({
                'date_str': '2018-12-30',
                'unknown_field': 'value',
            })
        )

    def test_put_with_unknown_fields_is_valid(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2018-12-30',
            'datetime_str': '2016-09-23T23:59:59',
        })
        self.assertEqual(
            (
                {
                    'key': 'my_key1',
                    'date_str': '2018-12-30',
                    'datetime_str': '2016-09-23T23:59:59',
                },
                {
                    'key': 'my_key1',
                    'date_str': '2018-12-31',
                    'datetime_str': '2016-09-23T23:59:59',
                }
            ),
            self.TestDateController.put({
                'key': 'my_key1',
                'date_str': '2018-12-31',
                'unknown_field': 'value',
            })
        )
        self.assertEqual(
            [{
                'key': 'my_key1',
                'date_str': '2018-12-31',
                'datetime_str': '2016-09-23T23:59:59',
            }],
            self.TestDateController.get({
                'date_str': '2018-12-31',
            })
        )
        self.assertEqual(
            [],
            self.TestDateController.get({
                'date_str': '2018-12-30',
            })
        )

    def test_put_unexisting_is_invalid(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2018-12-30',
            'datetime_str': '2016-09-23T23:59:59',
        })
        with self.assertRaises(Exception) as cm:
            self.TestDateController.put({
                'key': 'my_key2',
            })
        self.assertEqual({
                'key': 'my_key2',
            },
            cm.exception.requested_data)

    def test_post_invalid_datetime_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestDateController.post({
                'key': 'my_key1',
                'date_str': '2016-09-23',
                'datetime_str': 'This is not a valid datetime',
            })
        self.assertEqual({'datetime_str': ['Not a valid datetime.']}, cm.exception.errors)
        self.assertEqual({
                'key': 'my_key1',
                'date_str': '2016-09-23',
                'datetime_str': 'This is not a valid datetime',
            },
            cm.exception.received_data)

    def test_post_datetime_for_a_date_is_valid(self):
        self.assertEqual(
            {
                'key': 'my_key1',
                'date_str': '2017-05-01',
                'datetime_str': '2017-05-30T01:05:45',
            },
            self.TestDateController.post({
                'key': 'my_key1',
                'date_str': datetime.datetime.strptime('2017-05-01T01:05:45', '%Y-%m-%dT%H:%M:%S'),
                'datetime_str': '2017-05-30T01:05:45',
            })
        )

    def test_get_date_is_handled_for_unused_date(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        d = datetime.datetime.strptime('2016-09-23', '%Y-%m-%d').date()
        self.assertEqual(
            [],
            self.TestDateController.get({
                'date_str': d,
            })
        )

    def test_get_date_is_handled_for_valid_datetime(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        dt = datetime.datetime.strptime('2016-09-23T23:59:59', '%Y-%m-%dT%H:%M:%S')
        self.assertEqual(
            [
                {'date_str': '2017-05-15', 'datetime_str': '2016-09-23T23:59:59', 'key': 'my_key1'},
            ],
            self.TestDateController.get({
                'datetime_str': dt,
            })
        )

    def test_get_date_is_handled_for_unused_datetime(self):
        self.TestDateController.post({
            'key': 'my_key1',
            'date_str': '2017-05-15',
            'datetime_str': '2016-09-23T23:59:59',
        })
        dt = datetime.datetime.strptime('2016-09-24T23:59:59', '%Y-%m-%dT%H:%M:%S')
        self.assertEqual(
            [],
            self.TestDateController.get({
                'datetime_str': dt,
            })
        )

    def test_put_is_updating_and_previous_value_cannot_be_used_to_filter(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'optional': 'my_value',
        })
        self.assertEqual([], self.TestController.get({'optional': 'my_value1'}))

    def test_delete_with_filter_is_removing_the_proper_row(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(1, self.TestController.delete({'key': 'my_key1'}))
        self.assertEqual([{'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}],
                         self.TestController.get({}))

    def test_delete_without_filter_is_removing_everything(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(2, self.TestController.delete({}))
        self.assertEqual([], self.TestController.get({}))

    def test_query_get_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_parser))

    def test_query_get_parser_with_list_of_dict(self):
        self.assertEqual(
            {
                'bool_field': inputs.boolean,
                'key': str,
                'list_field': json.loads,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestListController.query_get_parser))
        self.assertEqual(
            {
                'bool_field': 'store',
                'key': 'store',
                'list_field': 'append',
                'limit': 'store',
                'offset': 'store',
            },
            parser_actions(self.TestListController.query_get_parser))

    def test_query_get_parser_with_dict(self):
        self.assertEqual(
            {
                'dict_col.first_key': str,
                'dict_col.second_key': int,
                'key': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestDictController.query_get_parser))
        self.assertEqual(
            {
                'dict_col.first_key': 'store',
                'dict_col.second_key': 'store',
                'key': 'store',
                'limit': 'store',
                'offset': 'store',
            },
            parser_actions(self.TestDictController.query_get_parser))

    def test_query_delete_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
            },
            parser_types(self.TestController.query_delete_parser))

    def test_query_delete_parser_with_list_of_dict(self):
        self.assertEqual(
            {
                'bool_field': inputs.boolean,
                'key': str,
                'list_field': json.loads,
            },
            parser_types(self.TestListController.query_delete_parser))
        self.assertEqual(
            {
                'bool_field': 'store',
                'key': 'store',
                'list_field': 'append',
            },
            parser_actions(self.TestListController.query_delete_parser))

    def test_query_rollback_parser(self):
        self.assertEqual(
            {
                'dict_field.first_key': str,
                'dict_field.second_key': int,
                'key': str,
                'revision': inputs.positive
             },
            parser_types(self.TestVersionedController.query_rollback_parser))
        self.assertEqual(
            {
                'dict_field.first_key': 'store',
                'dict_field.second_key': 'store',
                'key': 'store',
                'revision': 'store'
            },
            parser_actions(self.TestVersionedController.query_rollback_parser))

    def test_query_delete_parser_with_dict(self):
        self.assertEqual(
            {
                'dict_col.first_key': str,
                'dict_col.second_key': int,
                'key': str,
            },
            parser_types(self.TestDictController.query_delete_parser))
        self.assertEqual(
            {
                'dict_col.first_key': 'store',
                'dict_col.second_key': 'store',
                'key': 'store',
            },
            parser_actions(self.TestDictController.query_delete_parser))

    def test_json_post_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.json_post_model.name
        )
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_post_model.fields_flask_type
        )

    def test_json_post_model_with_auto_increment_and_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.json_post_model.name
        )
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.json_post_model.fields_flask_type
        )
        self.assertEqual(
            {'enum_field': None, 'key': None, 'optional_with_default': 'Test value'},
            self.TestAutoIncrementController.json_post_model.fields_default
        )

    def test_json_put_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.json_put_model.name
        )
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_put_model.fields_flask_type
        )

    def test_json_put_model_with_auto_increment_and_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.json_put_model.name
        )
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.json_put_model.fields_flask_type
        )

    def test_get_response_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.get_response_model.name)
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type)

    def test_get_response_model_with_enum(self):
        self.assertEqual(
            'TestAutoIncrementModel',
            self.TestAutoIncrementController.get_response_model.name)
        self.assertEqual(
            {'enum_field': 'String', 'key': 'Integer', 'optional_with_default': 'String'},
            self.TestAutoIncrementController.get_response_model.fields_flask_type)
        self.assertEqual(
            {'enum_field': 'Test Documentation', 'key': None, 'optional_with_default': None},
            self.TestAutoIncrementController.get_response_model.fields_description)
        self.assertEqual(
            {'enum_field': ['Value1', 'Value2'], 'key': None, 'optional_with_default': None},
            self.TestAutoIncrementController.get_response_model.fields_enum)

    def test_get_response_model_with_list_of_dict(self):
        self.assertEqual(
            'TestListModel',
            self.TestListController.get_response_model.name)
        self.assertEqual(
            {
                'bool_field': 'Boolean',
                'key': 'String',
                'list_field': (
                    'List',
                    {'list_field_inner': (
                        'Nested',
                        {
                            'first_key': 'String',
                            'second_key': 'Integer'
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_flask_type)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_description)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        None,
                        {
                            'first_key': ['Value1', 'Value2'],
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_enum)
        self.assertEqual(
            {
                'bool_field': True,
                'key': 'sample key',
                'list_field': (
                    [{'first_key': 'Value1', 'second_key': 1}],
                    {'list_field_inner': (
                        {'first_key': 'Value1', 'second_key': 1},
                        {
                            'first_key': 'Value1',
                            'second_key': 1
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_example)
        self.assertEqual(
            {
                'bool_field': None,
                'key': None,
                'list_field': (
                    None,
                    {'list_field_inner': (
                        {'first_key': None, 'second_key': None},
                        {
                            'first_key': None,
                            'second_key': None
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_default)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_required)
        self.assertEqual(
            {
                'bool_field': False,
                'key': False,
                'list_field': (
                    False,
                    {'list_field_inner': (
                        False,
                        {
                            'first_key': False,
                            'second_key': False
                        })
                    }
                )
            },
            self.TestListController.get_response_model.fields_readonly)

    def test_get_response_model_with_date(self):
        self.assertEqual(
            'TestDateModel',
            self.TestDateController.get_response_model.name)
        self.assertEqual(
            {'date_str': 'Date', 'datetime_str': 'DateTime', 'key': 'String'},
            self.TestDateController.get_response_model.fields_flask_type)
        self.assertEqual(
            {'date_str': None, 'datetime_str': None, 'key': None},
            self.TestDateController.get_response_model.fields_description)
        self.assertEqual(
            {'date_str': None, 'datetime_str': None, 'key': None},
            self.TestDateController.get_response_model.fields_enum)
        self.assertEqual(
            {'date_str': '2017-09-24', 'datetime_str': '2017-09-24T15:36:09', 'key': 'sample key'},
            self.TestDateController.get_response_model.fields_example)
        self.assertEqual(
            {'date_str': None, 'datetime_str': None, 'key': None},
            self.TestDateController.get_response_model.fields_default)
        self.assertEqual(
            {'date_str': False, 'datetime_str': False, 'key': False},
            self.TestDateController.get_response_model.fields_required)
        self.assertEqual(
            {'date_str': False, 'datetime_str': False, 'key': False},
            self.TestDateController.get_response_model.fields_readonly)

    def test_get_response_model_with_float_and_unvalidated_list_and_dict(self):
        self.assertEqual(
            'TestUnvalidatedListAndDictModel',
            self.TestUnvalidatedListAndDictController.get_response_model.name)
        self.assertEqual(
            {
                'dict_field': 'Raw',
                'float_key': 'Float',
                'float_with_default': 'Float',
                'list_field': (
                    'List',
                    {
                        'list_field_inner': 'String'
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_flask_type)
        self.assertEqual(
            {
                'dict_field': None,
                'float_key': None,
                'float_with_default': None,
                'list_field': (
                    None,
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_description)
        self.assertEqual(
            {
                'dict_field': None,
                'float_key': None,
                'float_with_default': None,
                'list_field': (
                    None,
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_enum)
        self.assertEqual(
            {
                'dict_field': {
                    '1st dict_field key': '1st dict_field sample',
                    '2nd dict_field key': '2nd dict_field sample',
                },
                'float_key': 1.4,
                'float_with_default': 34,
                'list_field': (
                    [
                        '1st list_field sample',
                        '2nd list_field sample',
                    ],
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_example)
        self.assertEqual(
            {
                'dict_field': None,
                'float_key': None,
                'float_with_default': 34,
                'list_field': (
                    None,
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_default)
        self.assertEqual(
            {
                'dict_field': True,
                'float_key': False,
                'float_with_default': False,
                'list_field': (
                    True,
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_required)
        self.assertEqual(
            {
                'dict_field': False,
                'float_key': False,
                'float_with_default': False,
                'list_field': (
                    False,
                    {
                        'list_field_inner': None
                    }
                )
            },
            self.TestUnvalidatedListAndDictController.get_response_model.fields_readonly)

    def test_get_with_limit_2_is_retrieving_subset_of_2_first_elements(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},
            ],
            self.TestController.get({'limit': 2}))

    def test_get_with_offset_1_is_retrieving_subset_of_n_minus_1_first_elements(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},
                {'key': 'my_key3', 'mandatory': 3, 'optional': 'my_value3'},
            ],
            self.TestController.get({'offset': 1}))

    def test_get_with_limit_1_and_offset_1_is_retrieving_middle_element(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.TestController.post({
            'key': 'my_key3',
            'mandatory': 3,
            'optional': 'my_value3',
        })
        self.assertEqual(
            [
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'},

            ],
            self.TestController.get({'offset': 1, 'limit': 1}))

    def test_get_model_description_returns_description(self):
        self.assertEqual(
            {
                'key': 'key',
                'mandatory': 'mandatory',
                'optional': 'optional',
                'collection': 'sample_table_name'
            },
            self.TestController.get_model_description())

    def test_get_model_description_response_model(self):
        self.assertEqual(
            'TestModelDescription',
            self.TestController.get_model_description_response_model.name)
        self.assertEqual(
            {'collection': 'String',
             'key': 'String',
             'mandatory': 'String',
             'optional': 'String'},
            self.TestController.get_model_description_response_model.fields_flask_type)


class MongoCRUDControllerFailuresTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('mongomock', cls._create_models)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_mongo.CRUDModel, base=base, table_name='sample_table_name'):
            key = database_mongo.Column(str, is_primary_key=True)
            mandatory = database_mongo.Column(int, is_nullable=False)
            optional = database_mongo.Column(str)

        logger.info('Save model class...')
        return [TestModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_model_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.model(None)
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_namespace_method_without_setting_model(self):
        class TestNamespace:
            pass

        with self.assertRaises(Exception) as cm:
            self.TestController.namespace(TestNamespace)
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_get_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_post_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_post_many_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_put_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_delete_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.delete({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_audit_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get_audit({})
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")

    def test_model_description_method_without_setting_model(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.get_model_description()
        self.assertRegex(
            cm.exception.args[0],
            "Model was not attached to TestController. "
            "Call <bound method CRUDController.model of <class '.*CRUDControllerFailuresTest.TestController'>>.")


class MongoCRUDControllerAuditTest(unittest.TestCase):
    class TestController(database.CRUDController):
        pass

    class TestEnumController(database.CRUDController):
        pass

    class TestVersionedController(database.CRUDController):
        pass

    _db = None

    @classmethod
    def setUpClass(cls):
        cls._db = database.load('mongomock', cls._create_models)
        cls.TestController.namespace(TestAPI)
        cls.TestEnumController.namespace(TestAPI)
        cls.TestVersionedController.namespace(TestAPI)

    @classmethod
    def tearDownClass(cls):
        database.reset(cls._db)

    @classmethod
    def _create_models(cls, base):
        logger.info('Declare model class...')

        class TestModel(database_mongo.CRUDModel, base=base, table_name='sample_table_name', audit=True):
            key = database_mongo.Column(str, is_primary_key=True, index_type=database_mongo.IndexType.Unique)
            mandatory = database_mongo.Column(int, is_nullable=False)
            optional = database_mongo.Column(str)

        class TestEnumModel(database_mongo.CRUDModel, base=base, table_name='enum_table_name', audit=True):
            key = database_mongo.Column(str, is_primary_key=True, index_type=database_mongo.IndexType.Unique)
            enum_fld = database_mongo.Column(EnumTest)

        class TestVersionedModel(versioning_mongo.VersionedCRUDModel, base=base, table_name='versioned_table_name', audit=True):
            key = database_mongo.Column(str, is_primary_key=True, index_type=database_mongo.IndexType.Unique)
            enum_fld = database_mongo.Column(EnumTest)

        logger.info('Save model class...')
        cls.TestController.model(TestModel)
        cls.TestEnumController.model(TestEnumModel)
        cls.TestVersionedController.model(TestVersionedModel)
        return [TestModel, TestEnumModel, TestVersionedModel]

    def setUp(self):
        logger.info(f'-------------------------------')
        logger.info(f'Start of {self._testMethodName}')
        database.reset(self._db)

    def tearDown(self):
        logger.info(f'End of {self._testMethodName}')
        logger.info(f'-------------------------------')

    def test_get_all_without_data_returns_empty_list(self):
        self.assertEqual([], self.TestController.get({}))
        self._check_audit(self.TestController, [])

    def test_get_parser_fields_order(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_parser)
        )

    def test_get_versioned_audit_parser_fields(self):
        self.assertEqual(
            {
                'audit_action': str,
                'audit_date_utc': inputs.datetime_from_iso8601,
                'audit_user': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
                'revision': int,
            },
            parser_types(self.TestVersionedController.query_get_audit_parser)
        )

    def test_delete_parser_fields_order(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
            },
            parser_types(self.TestController.query_delete_parser)
        )

    def test_post_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_post_model.fields_flask_type
        )

    def test_versioned_audit_get_response_model_fields(self):
        self.assertEqual(
            {'audit_action': 'String',
             'audit_date_utc': 'DateTime',
             'audit_user': 'String',
             'revision': 'Integer'},
            self.TestVersionedController.get_audit_response_model.fields_flask_type
        )

    def test_put_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.json_put_model.fields_flask_type
        )

    def test_get_response_model_fields_order(self):
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type
        )

    def test_post_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual(None, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_many_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual([], cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_many_with_empty_list_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([])
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual([], cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_put_with_nothing_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put(None)
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_put_with_empty_dict_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.put({})
        self.assertEqual({'': ['No data provided.']}, cm.exception.errors)
        self.assertEqual({}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_delete_without_nothing_do_not_fail(self):
        self.assertEqual(0, self.TestController.delete({}))
        self._check_audit(self.TestController, [])

    def test_post_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 'my_key',
            })
        self.assertEqual({'mandatory': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'key': 'my_key'}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_many_without_mandatory_field_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 'my_key',
            }])
        self.assertEqual({0: {'mandatory': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'key': 'my_key'}], cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Missing data for required field.']}, cm.exception.errors)
        self.assertEqual({'mandatory': 1}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_many_without_key_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Missing data for required field.']}}, cm.exception.errors)
        self.assertEqual([{'mandatory': 1}], cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post({
                'key': 256,
                'mandatory': 1,
            })
        self.assertEqual({'key': ['Not a valid str.']}, cm.exception.errors)
        self.assertEqual({'key': 256, 'mandatory': 1}, cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_post_many_with_wrong_type_is_invalid(self):
        with self.assertRaises(Exception) as cm:
            self.TestController.post_many([{
                'key': 256,
                'mandatory': 1,
            }])
        self.assertEqual({0: {'key': ['Not a valid str.']}}, cm.exception.errors)
        self.assertEqual([{'key': 256, 'mandatory': 1}], cm.exception.received_data)
        self._check_audit(self.TestController, [])

    def test_put_with_wrong_type_is_invalid(self):
        self.TestController.post({
            'key': 'value1',
            'mandatory': 1,
        })
        with self.assertRaises(Exception) as cm:
            self.TestController.put({
                'key': 'value1',
                'mandatory': 'invalid_value',
            })
        self.assertEqual({'mandatory': ['Not a valid int.']}, cm.exception.errors)
        self.assertEqual({'key': 'value1', 'mandatory': 'invalid_value'}, cm.exception.received_data)
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'value1',
                    'mandatory': 1,
                    'optional': None,
                    'revision': 1,
                },
            ]
        )

    def test_post_without_optional_is_valid(self):
        self.assertEqual(
            {'optional': None, 'mandatory': 1, 'key': 'my_key'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
            })
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': None,
                    'revision': 1,
                },
            ]
        )

    def test_post_with_enum_is_valid(self):
        self.assertEqual(
            {'enum_fld': 'Value1', 'key': 'my_key'},
            self.TestEnumController.post({
                'key': 'my_key',
                'enum_fld': EnumTest.Value1,
            })
        )
        self._check_audit(self.TestEnumController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'enum_fld': 'Value1',
                    'key': 'my_key',
                    'revision': 1,
                },
            ]
        )

    def test_put_with_enum_is_valid(self):
        self.assertEqual(
            {'enum_fld': 'Value1', 'key': 'my_key'},
            self.TestEnumController.post({
                'key': 'my_key',
                'enum_fld': EnumTest.Value1,
            })
        )
        self.assertEqual(
            (
                {'enum_fld': 'Value1', 'key': 'my_key'},
                {'enum_fld': 'Value2', 'key': 'my_key'},
            ),
            self.TestEnumController.put({
                'key': 'my_key',
                'enum_fld': EnumTest.Value2,
            })
        )
        self._check_audit(self.TestEnumController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'enum_fld': 'Value1',
                    'key': 'my_key',
                    'revision': 1,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'enum_fld': 'Value2',
                    'key': 'my_key',
                    'revision': 2,
                },
            ]
        )

    def test_versioned_audit_after_post_put_delete_rollback(self):
        self.TestVersionedController.post({
            'key': 'my_key',
            'enum_fld': EnumTest.Value1,
        })
        self.TestVersionedController.put({
            'key': 'my_key',
            'enum_fld': EnumTest.Value2,
        })
        self.TestVersionedController.delete({
            'key': 'my_key',
        })
        self.TestVersionedController.rollback_to({
            'revision': 1
        })
        self._check_audit(self.TestVersionedController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'revision': 1,
                    'table_name': 'versioned_table_name',
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'revision': 2,
                    'table_name': 'versioned_table_name',
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'revision': 3,
                    'table_name': 'versioned_table_name',
                },
                {
                    'audit_action': 'Rollback',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'revision': 4,
                    'table_name': 'versioned_table_name',
                },
            ]
        )

    def test_delete_with_enum_is_valid(self):
        self.assertEqual(
            {'enum_fld': 'Value1', 'key': 'my_key'},
            self.TestEnumController.post({
                'key': 'my_key',
                'enum_fld': EnumTest.Value1,
            })
        )
        self.assertEqual(1,
            self.TestEnumController.delete({
                'enum_fld': EnumTest.Value1,
            })
        )
        self._check_audit(self.TestEnumController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'enum_fld': 'Value1',
                    'key': 'my_key',
                    'revision': 1,
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'enum_fld': 'Value1',
                    'key': 'my_key',
                    'revision': 2,
                },
            ]
        )

    def test_post_many_without_optional_is_valid(self):
        self.assertListEqual(
            [{'optional': None, 'mandatory': 1, 'key': 'my_key'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
            }])
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': None,
                    'revision': 1,
                },
            ]
        )

    def _check_audit(self, controller, expected_audit, filter_audit={}):
        audit = controller.get_audit(filter_audit)
        audit = [{key: audit_line[key] for key in sorted(audit_line.keys())} for audit_line in audit]

        if not expected_audit:
            self.assertEqual(audit, expected_audit)
        else:
            self.assertRegex(f'{audit}', f'{expected_audit}'.replace('[', '\\[').replace(']', '\\]').replace('\\\\', '\\'))

    def test_post_with_optional_is_valid(self):
        self.assertEqual(
            {'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            })
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 1,
                }
            ]
        )

    def test_post_many_with_optional_is_valid(self):
        self.assertListEqual(
            [{'mandatory': 1, 'key': 'my_key', 'optional': 'my_value'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
            }])
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 1,
                }
            ]
        )

    def test_post_with_unknown_field_is_valid(self):
        self.assertEqual(
            {'optional': 'my_value', 'mandatory': 1, 'key': 'my_key'},
            self.TestController.post({
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            })
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 1,
                },
            ]
        )

    def test_post_many_with_unknown_field_is_valid(self):
        self.assertListEqual(
            [{'optional': 'my_value', 'mandatory': 1, 'key': 'my_key'}],
            self.TestController.post_many([{
                'key': 'my_key',
                'mandatory': 1,
                'optional': 'my_value',
                # This field do not exists in schema
                'unknown': 'my_value',
            }])
        )
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 1,
                },
            ]
        )

    def test_get_without_filter_is_retrieving_the_only_item(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            [{
                'mandatory': 1,
                'optional': 'my_value1',
                'key': 'my_key1'
            }],
            self.TestController.get({}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
            ]
        )

    def test_get_without_filter_is_retrieving_everything_with_multiple_posts(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 2,
                },
            ]
        )

    def test_get_without_filter_is_retrieving_everything(self):
        self.TestController.post_many([
            {
                'key': 'my_key1',
                'mandatory': 1,
                'optional': 'my_value1',
            },
            {
                'key': 'my_key2',
                'mandatory': 2,
                'optional': 'my_value2',
            }
        ])
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}
            ],
            self.TestController.get({}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 2,
                },
            ]
        )

    def test_get_with_filter_is_retrieving_subset(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(
            [
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
            ],
            self.TestController.get({'optional': 'my_value1'}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 2,
                },
            ]
        )

    def test_put_is_updating(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.assertEqual(
            (
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value1'},
                {'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'},
            ),
            self.TestController.put({
                'key': 'my_key1',
                'optional': 'my_value',
            })
        )
        self.assertEqual([{'key': 'my_key1', 'mandatory': 1, 'optional': 'my_value'}],
                         self.TestController.get({'mandatory': 1}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 2,
                },
            ]
        )

    def test_put_is_updating_and_previous_value_cannot_be_used_to_filter(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'optional': 'my_value',
        })
        self.assertEqual([], self.TestController.get({'optional': 'my_value1'}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value',
                    'revision': 2,
                },
            ]
        )

    def test_delete_with_filter_is_removing_the_proper_row(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(1, self.TestController.delete({'key': 'my_key1'}))
        self.assertEqual([{'key': 'my_key2', 'mandatory': 2, 'optional': 'my_value2'}],
                         self.TestController.get({}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 2,
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 3,
                },
            ]
        )

    def test_audit_filter_on_model_is_returning_only_selected_data(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 2,
        })
        self.TestController.delete({'key': 'my_key1'})
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                    'revision': 2,
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                    'revision': 3,
                },
            ],
            filter_audit={'key': 'my_key1'}
        )

    def test_audit_filter_on_audit_model_is_returning_only_selected_data(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 2,
        })
        self.TestController.delete({'key': 'my_key1'})
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                    'revision': 2,
                },
            ],
            filter_audit={'audit_action': 'Update'}
        )

    def test_value_can_be_updated_to_previous_value(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 2,
        })
        self.TestController.put({
            'key': 'my_key1',
            'mandatory': 1,  # Put back initial value
        })
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 2,
                    'optional': 'my_value1',
                    'revision': 2,
                },
                {
                    'audit_action': 'Update',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 3,
                },
            ]
        )

    def test_delete_without_filter_is_removing_everything(self):
        self.TestController.post({
            'key': 'my_key1',
            'mandatory': 1,
            'optional': 'my_value1',
        })
        self.TestController.post({
            'key': 'my_key2',
            'mandatory': 2,
            'optional': 'my_value2',
        })
        self.assertEqual(2, self.TestController.delete({}))
        self.assertEqual([], self.TestController.get({}))
        self._check_audit(self.TestController,
            [
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 1,
                },
                {
                    'audit_action': 'Insert',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 2,
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key1',
                    'mandatory': 1,
                    'optional': 'my_value1',
                    'revision': 3,
                },
                {
                    'audit_action': 'Delete',
                    'audit_date_utc': '\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d.\d\d\d\d\d\d',
                    'audit_user': '',
                    'key': 'my_key2',
                    'mandatory': 2,
                    'optional': 'my_value2',
                    'revision': 4,
                },
            ]
        )

    def test_query_get_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
            },
            parser_types(self.TestController.query_get_parser))
        self._check_audit(self.TestController, [])

    def test_query_get_audit_parser(self):
        self.assertEqual(
            {
                'audit_action': str,
                'audit_date_utc': inputs.datetime_from_iso8601,
                'audit_user': str,
                'key': str,
                'mandatory': int,
                'optional': str,
                'limit': inputs.positive,
                'offset': inputs.natural,
                'revision': int,
            },
            parser_types(self.TestController.query_get_audit_parser))
        self._check_audit(self.TestController, [])

    def test_query_delete_parser(self):
        self.assertEqual(
            {
                'key': str,
                'mandatory': int,
                'optional': str,
            },
            parser_types(self.TestController.query_delete_parser))
        self._check_audit(self.TestController, [])

    def test_get_response_model(self):
        self.assertEqual(
            'TestModel',
            self.TestController.get_response_model.name)
        self.assertEqual(
            {'key': 'String', 'mandatory': 'Integer', 'optional': 'String'},
            self.TestController.get_response_model.fields_flask_type)
        self._check_audit(self.TestController, [])

    def test_get_audit_response_model(self):
        self.assertEqual(
            'AuditTestModel',
            self.TestController.get_audit_response_model.name)
        self.assertEqual(
            {'audit_action': 'String',
             'audit_date_utc': 'DateTime',
             'audit_user': 'String',
             'key': 'String',
             'mandatory': 'Integer',
             'optional': 'String',
             'revision': 'Integer'},
            self.TestController.get_audit_response_model.fields_flask_type)
        self._check_audit(self.TestController, [])


if __name__ == '__main__':
    unittest.main()
