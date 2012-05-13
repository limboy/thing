#coding=utf-8
__title__ = 'thing'
__version__ = '0.2.1'
__author__ = 'lzyy'
__license__ = 'BSD'

import logging
import time
import formencode
from sqlalchemy import Table, MetaData, create_engine
from sqlalchemy.sql import select, func, and_, compiler
from sqlalchemy.sql.expression import label
from functools import partial
from blinker import signal

class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

class ThingException(Exception):
    pass

class ThingError(object):
    """
    a descriptor for Thing's errors
    """

    def __init__(self):
        self._errors = {}

    def __get__(self, instance, type = None):
        errors = {}
        for key, val in self._errors.items():
            errors[key] = val.msg
        return errors

    def __set__(self, instance, error):
        self._errors = {}
        for key, val in error.items():
            if isinstance(val, basestring):
                val = formencode.api.Invalid(val, value = None, state = None)
            self._errors[key] = val

class Thing(formencode.Schema):

    # change this if your pk is not id
    # current doesn't support multi pk
    _primary_key = 'id'

    # if leave it as None, lower classname will be used
    _tablename = None

    # collect sql execution
    _sql_stats = {'total_time':0, 'query_count':0, 'detail':[]}

    # indicate if profile is enabled
    _profile = False

    # like find_by_user_id / findall_by_status
    _dynamic_query = None 

    # record tables schema infomation
    _table_schemas = {} 

    # descriptor
    errors = ThingError()

    # used for formencode.Schema
    allow_extra_fields = True

    def compile_query(self, query):
        """
        used when profiling
        """
        #TODO add query data, not only sql placeholder
        return str(query)

    @staticmethod
    def db_config(db_config):
        """
        db_config is like this:

        db_config = {
            'master': {
                'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
                'echo': False,
                },
            'slave': {
                'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
                'echo': False,
                },
        }

        there must have at least master and slave section in db_config
        """
        Thing._db_config = db_config
        Thing._db_conn = {}

    @staticmethod
    def enable_profile():
        Thing._profile = True

    @staticmethod
    def _get_conn(table_name, is_read, sharding = None):
        """
        if this is read operation and table_name.slave exists in db_config, then this section is used
        else slave section will be used

        if this is write operation and table_name.master exists in db_config, then this section is used
        else master section will be used
        """
        section = '%s.%s%s'%(table_name, 'slave' if is_read else 'write', '.'+sharding if sharding else '')
        if not section in Thing._db_config:
            # make sure there is 'slave' and 'master' section in db_config
            section = 'slave' if is_read else 'master'

        # do not connect multi times
        conn = Thing._db_conn.setdefault(section, None)
        if not Thing._db_conn.get(section):
            url = Thing._db_config[section]['url']
            kwargs = {k:v for k, v in Thing._db_config[section].items() if k != 'url'}
            Thing._db_conn[section]= create_engine(url, **kwargs).connect().execution_options(autocommit=True)

        if Thing._db_conn[section].closed:
            Thing._db_conn[section].connect()
        return Thing._db_conn[section]

    def sharding_strategy(self):
        """
        override this method to implenment your sharding strategy
        if there is `user.master.sharding1` in db_config, and you
        want to use it, return sharding1
        """
        pass

    def __init__(self, **fields):
        """
        set fields' init value is allowed
        """
        self._init_env()
        for field_name, field_value in fields.items():
            self._unsaved_items[field_name] = field_value

    def _init_env(self):
        self._unsaved_items = {}
        self._current_item = {}
        self._filters = []
        self._results = []
        self._current_index = -1
        self.errors = {}
        self._find_fields = []
        self._findall_fields = []
        self._count_by_fields = []
        self._findall_in_field = None
        self._tablename = self._tablename or self.__class__.__name__.lower()
        self._selected_fields = [self.table]
        self._order_by = getattr(self.table.c, self._primary_key).desc()

    @property
    def saved(self):
        return not bool(self._unsaved_items)

    def query(self, query_str):
        """
        execute raw sql
        """
        db = Thing._get_conn(self._tablename, True, self.sharding_strategy())
        return db.execute(query_str)

    def add_error(self, **error_dict):
        """
        manually add an error
        """
        errors = self.errors
        errors.update(error_dict)
        self.errors = errors

    def __delattr__(self, key):
        if key in self._current_item:
            del self._current_item[key]
        elif key in self._unsaved_items:
            del self._unsaved_items[key]

    def  __getattr__(self, key):
        if key in self._unsaved_items:
            return self._unsaved_items[key]
        elif key in self._current_item:
            value = getattr(self._current_item, key)
            return '' if value is None else value
        elif key[:8] == 'find_by_':
            if key.find('_and_') == -1:
                self._find_fields.append(key[8:])
            else:
                self._find_fields = key[8:].split('_and_')
            Thing._dynamic_query = key
            return self
        elif key[:11] == 'findall_by_':
            if key.find('_and_') == -1:
                self._findall_fields.append(key[11:])
            else:
                self._findall_fields = key[11:].split('_and_')
            Thing._dynamic_query = key
            return self
        elif key[:11] == 'findall_in_':
            self._findall_in_field = key[11:]
            Thing._dynamic_query = key
            return self
        elif key[:9] == 'count_by_':
            if key.find('_and_') == -1:
                self._count_by_fields.append(key[9:])
            else:
                self._count_by_fields = key[9:].split('_and_')
            Thing._dynamic_query = key
            return self
        raise ThingException('key:{key} not found'.format(key = key))

    def __call__(self, *args, **kwargs):
        if self._find_fields:
            for i, val in enumerate(self._find_fields):
                self.where(val, '=', args[i])
            self._find_fields = []
            result = self.find()
            Thing._dynamic_query = None
            return result
        if self._findall_fields:
            for i, val in enumerate(self._findall_fields):
                self.where(val, '=', args[i])
            self._findall_fields = []
            result = self.findall(**kwargs)
            Thing._dynamic_query = None
            return result
        if self._count_by_fields:
            for i, val in enumerate(self._count_by_fields):
                self.where(val, '=', args[i])
            self._count_by_fields = []
            result = self.count()
            Thing._dynamic_query = None
            return result
        if self._findall_in_field:
            self.where(self._findall_in_field, 'in', args[0])
            self._findall_in_field = None
            result = self.findall()
            Thing._dynamic_query = None
            return result
        return self

    def __setattr__(self, key, val):
        if key[0] != '_' and key != 'errors':
            self._unsaved_items[key] = val
        else:
            object.__setattr__(self, key, val)

    def __len__(self):
        if self._results:
            return len(self._results)
        elif self._current_item:
            return 1
        return 0

    def _before_insert(self):
        pass

    def _before_update(self):
        pass

    def _after_insert(self):
        pass

    def _after_update(self):
        pass

    def _before_delete(self):
        pass

    def _after_delete(self):
        pass

    def _before_find(self, val):
        pass

    def _before_findall(self):
        pass

    @staticmethod
    def get_sql_stats():
        return Thing._sql_stats

    @staticmethod
    def clear_sql_stats():
        Thing._sql_stats = {'total_time':0, 'query_count':0, 'detail':[]}

    def save(self, validate = True):
        db = Thing._get_conn(self._tablename, False, self.sharding_strategy())

        # fill the _unsaved_items with _current_item if not empty
        if self._current_item:
            for key, val in self._current_item.items():
                if not key in self._unsaved_items:
                    self._unsaved_items[key] = val

        classname = self.__class__.__name__.lower()

        if validate:
            # before validation
            signal('{0}.before_validation'.format(classname)).send(self)
            if self.errors:
                return self

            # validation
            if not self.validate():
                return self

            # after validation
            signal('{0}.after_validation'.format(classname)).send(self)
            if self.errors:
                return self

        if self._primary_key in self._unsaved_items.keys():
            # before update
            signal('{0}.before_update'.format(classname)).send(self)

            primary_key_val = self._unsaved_items.pop(self._primary_key)
            query = (self.table.update()
                    .where(getattr(self.table.c, self._primary_key) == primary_key_val)
                    .values(**self._unsaved_items))
            self._before_update()
            db.execute(query)

            query = self.table.select().where(getattr(self.table.c, self._primary_key) == primary_key_val)
            self._current_item = db.execute(query).first()
            self._after_update()
            # after update
            signal('{0}.after_update'.format(classname)).send(self)
        else:
            # before insert
            signal('{0}.before_insert'.format(classname)).send(self)

            self._before_insert()
            query = self.table.insert().values(**self._unsaved_items)
            primary_key_val = db.execute(query).inserted_primary_key[0]

            query = self.table.select().where(getattr(self.table.c, self._primary_key) == primary_key_val)
            self._current_item = db.execute(query).first()
            self._after_insert()
            # after insert
            signal('{0}.after_insert'.format(classname)).send(self)

        self._unsaved_items = {}
        return primary_key_val

    def delete(self):
        db = Thing._get_conn(self._tablename, False, self.sharding_strategy())
        classname = self.__class__.__name__.lower()

        self._before_delete()
        signal('{0}.before_delete'.format(classname)).send(self)

        if self._primary_key in self._current_item.keys():
            pk = self._primary_key
            query = self.table.delete().where(getattr(self.table.c, pk) == self._current_item[pk])
            rowcount = db.execute(query).rowcount
        else:
            query = self.table.delete(and_(*self._filters))
            rowcount = db.execute(query).rowcount

        self._after_delete()
        signal('{0}.after_delete'.format(classname)).send(self)

        return rowcount

    @property
    def table(self):
        """
        get current table info
        """
        if Thing._table_schemas.get(self._tablename, None) is None:
            conn = Thing._get_conn(self._tablename, True, self.sharding_strategy())
            Thing._table_schemas[self._tablename] = Table(self._tablename, MetaData(), autoload = True, autoload_with = conn)
        return Thing._table_schemas[self._tablename]

    def validate(self, fields = None):
        current_fields = self.__class__.fields
        saved_fields = {}
        if fields:
            for key, val in current_fields.items():
                if key not in fields:
                    saved_fields[key] = current_fields.pop(key)
        try:
            self.to_python(self._unsaved_items)
        except formencode.Invalid, e:
            self.errors = e.error_dict
        for key, val in saved_fields.items():
            current_fields[key] = val
        if self.errors:
            return False
        return True

    def where(self, field, operation, val):
        # check if field has function in it
        field_obj = None
        if field.find('(') != -1:
            sql_func = getattr(func, field[:field.find('(')])
            field = field[field.find('(')+1: -1]
            field_obj = sql_func(getattr(self.table.c, field))
        else:
            field_obj = getattr(self.table.c, field)

        op_dict = {'=': '__eq__',
                   '>': '__gt__',
                   '>=': '__ge__',
                   '<': '__lt__',
                   '<=': '__le__',
                   '!=': '__ne__',
                   'in': 'in_',
                   }

        for op, op_method in op_dict.items():
            if op == operation:
                operation = op_method
                break

        self._filters.append(getattr(field_obj, operation)(val))
        return self

    def order_by(self, order_by):
        """
        order_by (string): if start with '-' means desc
        """
        if order_by[0] == '-':
            self._order_by = getattr(self.table.c, order_by[1:]).desc()
        else:
            self._order_by = getattr(self.table.c, order_by)
        return self

    def select(self, fields):
        self._selected_fields = []
        for field in fields:
            field_obj = None
            if field.find('(') != -1:
                sql_func = getattr(func, field[:field.find('(')])
                if field.find(' as ') == -1:
                    field = field[field.find('(')+1: -1]
                    field_obj = sql_func(getattr(self.table.c, field))
                else:
                    field, as_label = field.split(' as ')
                    field = field[field.find('(')+1: -1]
                    field_obj = sql_func(getattr(self.table.c, field)).label(as_label)
            else:
                field_obj = getattr(self.table.c, field)
            self._selected_fields.append(field_obj)
        return self

    def find(self, val = None):
        db = Thing._get_conn(self._tablename, True, self.sharding_strategy())
        if val:
            result = self._before_find(val)
            if result:
                self._current_item = result
                return self
            query = self.table.select().where(getattr(self.table.c, self._primary_key) == val)
        else:
            query = select(self._selected_fields, and_(*self._filters))

        if self._profile:
            start_time = time.time()
        result = db.execute(query).first()
        if self._profile:
            passed_time = '%.4f' % (time.time() - start_time)
            Thing._sql_stats['total_time'] += float(passed_time)
            Thing._sql_stats['query_count'] += 1
            Thing._sql_stats['detail'].append([self.compile_query(query), passed_time, Thing._dynamic_query])

        self._current_item = {} if not result else result
        # empty current filter
        self._filters = []
        self._selected_fields = [self.table]
        return self

    def findall(self, limit = 20, offset = 0):
        db = Thing._get_conn(self._tablename, True, self.sharding_strategy())

        query = partial(select, self._selected_fields)
        query = query(and_(*self._filters)) if self._filters else query()

        query = query.order_by(self._order_by).limit(limit).offset(offset)

        result = self._before_findall()
        if result:
            self._results = result
            return self

        if self._profile:
            start_time = time.time()
        self._results = db.execute(query).fetchall()
        if self._profile:
            passed_time = '%.4f' % (time.time() - start_time)
            Thing._sql_stats['total_time'] += float(passed_time)
            Thing._sql_stats['query_count'] += 1
            Thing._sql_stats['detail'].append([self.compile_query(query), passed_time, Thing._dynamic_query])

        # empty current filter
        self._filters = []
        self._selected_fields = [self.table]
        return self

    def updateall(self, **fields):
        db = Thing._get_conn(self._tablename, False, self.sharding_strategy())
        update = self.table.update()
        if self._filters:
            for _filter in self._filters:
                update = update.where(_filter)
        query = update.values(**fields)
        if self._profile:
            start_time = time.time()
        rowcount = db.execute().rowcount
        if self._profile:
            passed_time = '%.4f' % (time.time() - start_time)
            Thing._sql_stats['total_time'] += float(passed_time)
            Thing._sql_stats['query_count'] += 1
            Thing._sql_stats['detail'].append([self.compile_query(query), passed_time])
        return rowcount

    def get_field(self, field):
        """
        after findall(), you can call get_field to fetch certain field into a list
        """
        field_content = []
        for result in self._results:
            field_content.append(getattr(result, field))
        return field_content

    def to_dict(self):
        """
        make current find() result into dict
        """
        d = {}
        for column_name in self.table.columns.keys():
            if hasattr(self._current_item, column_name):
                d[column_name] = getattr(self._current_item, column_name)
        return AttributeDict(d)
        
    def to_list(self):
        """
        make current findall() result into list
        """
        results = []
        for result in self._results:
            results.append(result)
        return results

    def __repr__(self):
        if self._results:
            return repr(self._results)
        if self._current_item:
            return repr(self._current_item)
        return repr(self.__class__)

    def count(self):
        """
        get current query's count
        """
        db = Thing._get_conn(self._tablename, True, self.sharding_strategy())
        query = select([func.count(getattr(self.table.c, self._primary_key))], and_(*self._filters))

        if self._profile:
            start_time = time.time()
        result = db.execute(query).scalar()
        if self._profile:
            passed_time = '%.4f' % (time.time() - start_time)
            Thing._sql_stats['total_time'] += float(passed_time)
            Thing._sql_stats['query_count'] += 1
            Thing._sql_stats['detail'].append([self.compile_query(query), passed_time, Thing._dynamic_query])
        return result

    def reset(self):
        self._init_env()
        return self

    def __iter__(self):
        return self

    def next(self):
        if self._current_index < len(self._results) - 1:
            self._current_index += 1
            self._current_item = self._results[self._current_index]
            return self
        else:
            raise StopIteration
