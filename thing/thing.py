#coding=utf-8
import time
import logging
import json
import sys
import redis
from sqlalchemy import Table, MetaData, create_engine
from sqlalchemy.sql import select, func, and_
from sqlalchemy.sql.expression import label
from functools import partial

class AttributeDict(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

class ThingException(Exception):
    pass

class Thing(object):

    # change this if your pk is not id
    # current doesn't support multi pk
    _primary_key = 'id'

    # if leave it as None, lower classname will be used
    _tablename = None

    # record tables schema infomation
    _table_schemas = {} 

    # _has_many = {'posts': {'model': post.Post(), 'foreign_key': 'user_id'}}
    # then u can use like this: current_user.posts.findall()
    _has_many = {}

    # _belongs_to = {'post': {'model': post.Post(), 'foreign_key': 'post_id'}}
    # then u can use like this: comment.post.title
    _belongs_to = {}

    # when a list of rows are ready to be delete, put it here
    # so cache can clear these records
    __tobe_deleted_rows = []

    __tobe_updated_rows = []

    __logger = None

    @staticmethod
    def config(config):
        """
        config is like this:

        config = {
            'db': {
                'master': {
                    'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
                    'echo': False,
                    },
                'slave': {
                    'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
                    'echo': False,
                },
            }, 
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
            }
            'thing':
                'debug': True,
        }

        there must have at least master and slave section in db section
        """
        Thing._config = config
        Thing._db_conn = {}
        Thing._redis_conn = redis.StrictRedis(host=config['redis']['host'], port=config['redis']['port'], db=config['redis']['db'])

    def debug(self, message):
        if Thing._config['thing'].get('debug'):
            if not Thing.__logger:
                Thing.__logger = logging.getLogger(__name__)
                Thing.__logger.setLevel(logging.DEBUG)
                formatter = logging.Formatter('DEBUG - %(message)s')
                handler_stream = logging.StreamHandler(sys.stdout)
                handler_stream.setFormatter(formatter)
                handler_stream.setLevel(logging.DEBUG)
                Thing.__logger.addHandler(handler_stream)
            Thing.__logger.debug(message)

    def compile_query(self, query):
        # TODO format query with values
        return query

    @staticmethod
    def _get_conn(table_name, is_read):
        """
        if this is read operation and table_name.slave exists in config['db'], then this section is used
        else slave section will be used

        if this is write operation and table_name.master exists in config['db'], then this section is used
        else master section will be used
        """
        section = '%s.%s' % (table_name, 'slave' if is_read else 'master')
        if not section in Thing._config['db']:
            # make sure there is 'slave' and 'master' section in config['db']
            section = 'slave' if is_read else 'master'

        # do not connect multi times
        conn = Thing._db_conn.setdefault(section, None)
        if not Thing._db_conn.get(section):
            url = Thing._config['db'][section]['url']
            kwargs = {k:v for k, v in Thing._config['db'][section].items() if k != 'url'}
            Thing._db_conn[section]= create_engine(url, **kwargs).connect().execution_options(autocommit=True)

        if Thing._db_conn[section].closed:
            Thing._db_conn[section].connect()
        return Thing._db_conn[section]

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

    def execute(self, query_str, is_read = True):
        """
        execute raw sql
        """
        db = Thing._get_conn(self._tablename, is_read)
        return db.execute(query_str)

    def __delattr__(self, key):
        if key in self._current_item:
            del self._current_item[key]
        elif key in self._unsaved_items:
            del self._unsaved_items[key]

    def  __getattr__(self, key):

        def _import(name):
            mod = __import__(name)
            components = name.split('.')
            for comp in components[1:]:
                mod = getattr(mod, comp)
            return mod

        if key in self._unsaved_items:
            return self._unsaved_items[key]
        elif key in self._current_item:
            # value = getattr(self._current_item, key)
            value = self._current_item[key]
            return '' if value is None else value
        elif key[:8] == 'find_by_':
            if key.find('_and_') == -1:
                self._find_fields.append(key[8:])
            else:
                self._find_fields = key[8:].split('_and_')
            return self
        elif key[:11] == 'findall_by_':
            if key.find('_and_') == -1:
                self._findall_fields.append(key[11:])
            else:
                self._findall_fields = key[11:].split('_and_')
            return self
        elif key[:11] == 'findall_in_':
            self._findall_in_field = key[11:]
            return self
        elif key[:9] == 'count_by_':
            if key.find('_and_') == -1:
                self._count_by_fields.append(key[9:])
            else:
                self._count_by_fields = key[9:].split('_and_')
            return self
        elif key in self._has_many:
            model_name = self._has_many[key]['model']
            if model_name.find('.') != -1:
                sections = model_name.split('.')
                # __import__ only import first section
                model = getattr(_import('.'.join(sections[:-1])), sections[-1])()
            else:
                model = locals()[model_name]()
            model.where(self._has_many[key]['foreign_key'], '=', getattr(self, self._primary_key))
            return model
        elif key in self._belongs_to:
            model_name = self._belongs_to[key]['model']
            if model_name.find('.') != -1:
                sections = model_name.split('.')
                __import__('.'.join(sections[:-1]))
                model = getattr(sys.modules['.'.join(sections[:-1])], sections[-1])()
            else:
                model = locals()[model_name]()
            model.find(getattr(self, self._belongs_to[key]['foreign_key']))
            return model

        raise ThingException('key:{key} not found'.format(key = key))

    def __call__(self, *args, **kwargs):
        if self._find_fields:
            for i, val in enumerate(self._find_fields):
                self.where(val, '=', args[i])
            self._find_fields = []
            result = self.find()
            return result
        if self._findall_fields:
            for i, val in enumerate(self._findall_fields):
                self.where(val, '=', args[i])
            self._findall_fields = []
            result = self.findall(**kwargs)
            return result
        if self._count_by_fields:
            for i, val in enumerate(self._count_by_fields):
                self.where(val, '=', args[i])
            self._count_by_fields = []
            result = self.count()
            return result
        if self._findall_in_field:
            self.where(self._findall_in_field, 'in', args[0])
            self._findall_in_field = None
            result = self.findall()
            return result
        return self

    def __setattr__(self, key, val):
        if key[0] != '_':
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
        Thing._redis_conn.set('thing.%s:%s' % (self.__class__.__name__, self._current_item[self._primary_key]),
                json.dumps(self.to_dict()))

    def _after_update(self):
        if self.__tobe_updated_rows:
            for row in self.__tobe_updated_rows:
                Thing._redis_conn.delete('thing.%s:%s' % (self.__class__.__name__, row[self._primary_key]))
        elif self._current_item:
            self._after_insert()

    def _before_delete(self):
        if self._primary_key in self._current_item.keys():
            Thing._redis_conn.delete('thing.%s:%s' % (self.__class__.__name__, self._current_item[self._primary_key]))
        elif self.__tobe_deleted_rows:
            for row in self.__tobe_deleted_rows:
                Thing._redis_conn.delete('thing.%s:%s' % (self.__class__.__name__, row[self._primary_key]))

    def _after_delete(self):
        pass

    def _before_find(self, val):
        key_name = 'thing.%s:%s' % (self.__class__.__name__, val)
        result = Thing._redis_conn.get(key_name)
        if result:
            result = json.loads(result)
            self.debug('Cache Read: %s' % key_name)
        return result

    def _after_find(self, val):
        if not val:
            if not self._current_item:
                return
            else:
                val = getattr(self,_current_item, self._primary_key)

        key_name = 'thing.%s:%s' % (self.__class__.__name__, val)
        result = Thing._redis_conn.get(key_name)
        if not result:
            Thing._redis_conn.set(key_name, json.dumps(self.to_dict()))

    def _before_findall(self):
        pass

    def save(self):
        db = Thing._get_conn(self._tablename, False)

        # fill the _unsaved_items with _current_item if not empty
        if self._current_item:
            for key, val in self._current_item.items():
                if not key in self._unsaved_items:
                    self._unsaved_items[key] = val

        if self._primary_key in self._unsaved_items.keys():
            primary_key_val = self._unsaved_items.pop(self._primary_key)
            query = (self.table.update()
                    .where(getattr(self.table.c, self._primary_key) == primary_key_val)
                    .values(**self._unsaved_items))
            self._before_update()
            start_time = time.time()
            db.execute(query)
            self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))

            query = self.table.select().where(getattr(self.table.c, self._primary_key) == primary_key_val)
            self._current_item = db.execute(query).first()
            self._after_update()
        else:
            self._before_insert()
            query = self.table.insert().values(**self._unsaved_items)
            primary_key_val = db.execute(query).inserted_primary_key[0]

            query = self.table.select().where(getattr(self.table.c, self._primary_key) == primary_key_val)
            start_time = time.time()
            self._current_item = db.execute(query).first()
            self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))
            self._after_insert()

        self._unsaved_items = {}
        return primary_key_val

    def delete(self):
        db = Thing._get_conn(self._tablename, False)

        if self._primary_key in self._current_item.keys():
            self._before_delete()
            pk = self._primary_key
            query = self.table.delete().where(getattr(self.table.c, pk) == self._current_item[pk])
            start_time = time.time()
            rowcount = db.execute(query).rowcount
            self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))
        else:
            self.__tobe_deleted_rows = self.table.select([self._primary_key]).query(and_(*self._filters)).findall()
            self._before_delete()
            query = self.table.delete(and_(*self._filters))
            self.__tobe_deleted_rows = []
            start_time = time.time()
            rowcount = db.execute(query).rowcount
            self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))

        self._after_delete()

        return rowcount

    @property
    def table(self):
        """
        get current table info
        """
        if Thing._table_schemas.get(self._tablename, None) is None:
            conn = Thing._get_conn(self._tablename, True)
            Thing._table_schemas[self._tablename] = Table(self._tablename, MetaData(), autoload = True, autoload_with = conn)
        return Thing._table_schemas[self._tablename]

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
        db = Thing._get_conn(self._tablename, True)
        if val:
            result = self._before_find(val)
            if result:
                self._current_item = result
                return self
            query = self.table.select().where(getattr(self.table.c, self._primary_key) == val)
        else:
            query = select(self._selected_fields, and_(*self._filters))

        start_time = time.time()
        result = db.execute(query).first()
        self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))

        self._after_find(val)

        self._current_item = {} if not result else result
        # empty current filter
        self._filters = []
        self._selected_fields = [self.table]
        return self

    def findall(self, limit = -1, offset = 0):
        db = Thing._get_conn(self._tablename, True)

        query = partial(select, self._selected_fields)
        query = query(and_(*self._filters)) if self._filters else query()

        if limit == -1:
            query = query.order_by(self._order_by).offset(offset)
        else:
            query = query.order_by(self._order_by).limit(limit).offset(offset)

        result = self._before_findall()
        if result:
            self._results = result
            return self

        start_time = time.time()
        self._results = db.execute(query).fetchall()
        self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))

        # empty current filter
        self._filters = []
        self._selected_fields = [self.table]
        return self

    def updateall(self, **fields):
        db = Thing._get_conn(self._tablename, False)

        _query = partial(select, [self._primary_key])
        _query = _query(and_(*self._filters)) if self._filters else _query()
        self.__tobe_updated_rows = db.execute(_query).fetchall()
        self._after_update()
        self.__tobe_updated_rows = []

        update = self.table.update()
        if self._filters:
            for _filter in self._filters:
                update = update.where(_filter)
        query = update.values(**fields)


        start_time = time.time()
        rowcount = db.execute(query).rowcount
        self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))

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
        if self._current_item:
            return repr(self._current_item)
        if self._results:
            return repr(self._results)
        return '<%s.%s object at %s>' % (
            self.__class__.__module__,
            self.__class__.__name__,
            hex(id(self))
        )

    def count(self):
        """
        get current query's count
        """
        db = Thing._get_conn(self._tablename, True)
        query = select([func.count(getattr(self.table.c, self._primary_key))], and_(*self._filters))
        start_time = time.time()
        result = db.execute(query).scalar()
        self.debug('[cost:%.4f] - %s' % (time.time() - start_time, query))
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
