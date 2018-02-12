import logging

import pycommon_database.database_mongo as database_mongo
import pycommon_database.database_sqlalchemy as database_sqlalchemy

logger = logging.getLogger(__name__)


def _is_mongo(database_connection_url: str):
    return database_connection_url and database_connection_url.startswith('mongo')


def load(database_connection_url: str, create_models_func: callable, **kwargs):
    """
    Create all necessary tables and perform the link between models and underlying database connection.

    :param database_connection_url: URL formatted as a standard database connection string (Mandatory).
    :param create_models_func: Function that will be called to create models and return them (instances of CRUDModel) (Mandatory).
    :param kwargs: Additional custom parameters.
    """
    if _is_mongo(database_connection_url):
        return database_mongo.load(database_connection_url, create_models_func)
    return database_sqlalchemy.load(database_connection_url, create_models_func, **kwargs)


def reset(base):
    """
    If the database was already created, then drop all tables and recreate them all.
    """
    # TODO check type of base
    if _is_mongo(base.connection_url):
        database_mongo.reset(base)
    else:
        database_sqlalchemy.reset(base)


class ControllerModelNotSet(Exception):
    def __init__(self, controller_class):
        Exception.__init__(self,
                           f'Model was not attached to {controller_class.__name__}. Call {controller_class.model}.')


def _ignore_read_only_fields(model_properties: dict, input_dictionnaries):
    read_only_fields = [item[0] for item in model_properties.items() if item[1].get('readOnly', None)]
    if isinstance(input_dictionnaries, list):
        return [{k: v for k, v in d.items() if k not in read_only_fields} for d in input_dictionnaries]
    else:
        return {k: v for k, v in input_dictionnaries.items() if k not in read_only_fields}


class CRUDController:
    """
    Class providing methods to interact with a CRUDModel.
    """
    _model = None
    _audit_model = None

    # CRUD request parsers
    query_get_parser = None
    query_delete_parser = None
    query_get_audit_parser = None

    # CRUD model definition (instead of request parsers)
    json_post_model = None
    json_put_model = None

    # CRUD response marshallers
    get_response_model = None
    get_audit_response_model = None
    get_model_description_response_model = None

    # The response that is always sent for the Model Description
    _model_description_dictionary = None

    @classmethod
    def model(cls, value, audit: bool = False):
        """
        Initialize related model (should extends CRUDModel).

        :param value: CRUDModel and SQLAlchemy model.
        :param audit: True to add an extra model representing the audit table. No audit by default.
        """
        cls._model = value
        if not cls._model:
            raise ControllerModelNotSet(cls)
        cls.query_get_parser = cls._model.query_get_parser()
        cls.query_delete_parser = cls._model.query_delete_parser()
        if audit:
            # TODO Ensure this method handle mongo ?
            cls._audit_model = audit.create_from(cls._model)
            # TODO Ensure it works fine thanks to inheritance
            cls.query_get_audit_parser = cls._audit_model.query_get_parser()
        else:
            cls._audit_model = None
            cls.query_get_audit_parser = None
        cls._model_description_dictionary = cls._model.description_dictionary()

    @classmethod
    def namespace(cls, namespace):
        """
        Create Flask RestPlus models that can be used to marshall results (and document service).
        This method should always be called AFTER cls.model()

        :param namespace: Flask RestPlus API.
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        cls.json_post_model = namespace.model(cls._model.__name__, cls._model.flask_restplus_fields())
        cls.json_put_model = namespace.model(cls._model.__name__, cls._model.flask_restplus_fields())
        cls.get_response_model = namespace.model(cls._model.__name__, cls._model.flask_restplus_fields())
        if cls._audit_model:
            # TODO Ensure it works fine thanks to inheritance
            cls.get_audit_response_model = namespace.model('Audit' + cls._model.__name__, cls._audit_model.flask_restplus_fields())
        else:
            cls.get_audit_response_model = None
        cls.get_model_description_response_model = namespace.model(''.join([cls._model.__name__, 'Description']), cls._model.flask_restplus_description_fields())


    @classmethod
    def get(cls, request_arguments: dict):
        """
        Return all models formatted as a list of dictionaries.
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        return cls._model.get_all(**request_arguments)

    @classmethod
    def post(cls, new_sample_dictionary: dict):
        """
        Add a model formatted as a dictionary.
        :raises ValidationFailed in case Marshmallow validation fail.
        :returns The inserted model formatted as a dictionary.
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        if hasattr(cls.json_post_model, '_schema'):
            new_sample_dictionary = _ignore_read_only_fields(cls.json_post_model._schema.get('properties', None),
                                                             new_sample_dictionary)
        new_sample_model = cls._model.add(new_sample_dictionary)
        if cls._audit_model:
            # TODO Add session at the same time instead of on each request
            cls._audit_model._session = cls._model._session
            cls._audit_model.audit_add(new_sample_model)
        return new_sample_model

    @classmethod
    def post_many(cls, new_sample_dictionaries_list: list):
        """
        Add models formatted as a list of dictionaries.
        :raises ValidationFailed in case Marshmallow validation fail.
        :returns The inserted models formatted as a list of dictionaries.
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        if hasattr(cls.json_post_model, '_schema'):
            new_sample_dictionaries_list = _ignore_read_only_fields(cls.json_post_model._schema.get('properties', None),
                                                                    new_sample_dictionaries_list)
        new_sample_models = cls._model.add_all(new_sample_dictionaries_list)
        if cls._audit_model:
            # TODO Add session at the same time instead of on each request
            cls._audit_model._session = cls._model._session
            for new_sample_model in new_sample_models:
                cls._audit_model.audit_add(new_sample_model)
        return new_sample_models

    @classmethod
    def put(cls, updated_sample_dictionary: dict):
        """
        Update a model formatted as a dictionary.
        :raises ValidationFailed in case Marshmallow validation fail.
        :returns A tuple containing previous model formatted as a dictionary (first item)
        and new model formatted as a dictionary (second item).
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        updated_sample_model = cls._model.update(updated_sample_dictionary)
        if cls._audit_model:
            # TODO Add session at the same time instead of on each request
            cls._audit_model._session = cls._model._session
            cls._audit_model.audit_update(updated_sample_model[1])
        return updated_sample_model

    @classmethod
    def delete(cls, request_arguments: dict):
        """
        Remove the model(s) matching those criterion.
        :returns Number of removed rows.
        """
        if not cls._model:
            raise ControllerModelNotSet(cls)
        if cls._audit_model:
            # TODO Add session at the same time instead of on each request
            cls._audit_model._session = cls._model._session
            cls._audit_model.audit_remove(**request_arguments)
        return cls._model.remove(**request_arguments)

    @classmethod
    def get_audit(cls, request_arguments: dict):
        """
        Return all audit models formatted as a list of dictionaries.
        """
        if not cls._audit_model:
            return []
        # TODO Add session at the same time instead of on each request
        cls._audit_model._session = cls._model._session
        return cls._audit_model.get_all(**request_arguments)

    @classmethod
    def get_model_description(cls):
        if not cls._model_description_dictionary:
            raise ControllerModelNotSet(cls)
        return cls._model_description_dictionary
