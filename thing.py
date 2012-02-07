import logging
import formencode
from sqlalchemy import Table, MetaData
from sqlalchemy.sql import select, func, and_
from functools import partial
from blinker import signal

class ThingException(Exception):
    pass

class Thing(formencode.Schema):
    allow_extra_fields = True
    _primary_key = 'id'
    _tablename = None

    def __init__(self, engines):
        """
        Args:
            engines (dict): {'master': master_engine, 'slave': slave_engine}
        """
        self._engines = engines
        self._dbs = {}
        for key, engine in self._engines.items():
            self._dbs[key] = engine.connect()
        self._default_engine = self._engines[self._engines.keys()[0]]
        self._default_db = self._dbs[self._dbs.keys()[0]]
        self._init_env()

    def _init_env(self):
        self._current_item = {}
        self._filters = []
        self._selected_fields = [self.table]
        self._order_by = getattr(self.table.c, self._primary_key).desc()
        self._results = []
        self._current_index = -1
        self._unsaved_items = {}
        self.errors = {} # can be update outside

    def __del__(self):
        for key, engine in self._engines.items():
            self._dbs[key].close()

    @property
    def saved(self):
        return not bool(self._unsaved_items)

    def  __getattr__(self, key):
        if key in self._current_item:
            return getattr(self._current_item, key)
        raise ThingException('key:{key} not found'.format(key = key))

    def __setattr__(self, key, val):
        if key[0] != '_' and key != 'errors':
            self._unsaved_items[key] = val
        else:
            object.__setattr__(self, key, val)

    def save(self, db_section = None):
        db = self._default_db if not db_section else self._dbs[db_section]
        classname = self.__class__.__name__.lower()

        # fill the _unsaved_items with _current_item if not empty
        if self._current_item:
            for key, val in self._current_item.items():
                if not key in self._unsaved_items:
                    self._unsaved_items[key] = val

        # before validation
        sig = signal('{0}.before_validation'.format(classname))
        sig.send(self, data = self._unsaved_items)
        if self.errors:
            return self

        # validation
        try:
            self.to_python(self._unsaved_items)
        except formencode.Invalid, e:
            self.errors = e.error_dict
        if self.errors:
            return self.errors

        # after validation
        sig = signal('{0}.after_validation'.format(classname))
        sig.send(self, data = self._unsaved_items)
        if self.errors:
            return self

        if self._primary_key in self._unsaved_items.keys():
            # before update
            sig = signal('{0}.before_update'.format(classname))
            sig.send(self, data = self._unsaved_items)
            if self.errors:
                return self

            primary_key_val = self._unsaved_items.pop(self._primary_key)
            query = (self.table.update()
                    .where(getattr(self.table.c, self._primary_key) == primary_key_val)
                    .values(**self._unsaved_items))
            db.execute(query)

            # after update
            sig = signal('{0}.before_update'.format(classname))
        else:
            # before insert
            sig = signal('{0}.before_insert'.format(classname))
            sig.send(self, data = self._unsaved_items)
            if self.errors:
                return self

            query = self.table.insert().values(**self._unsaved_items)
            primary_key_val = db.execute(query).inserted_primary_key[0]

            # after insert
            sig = signal('{0}.after_insert'.format(classname))

        self._current_item = (db.execute(self.table.select()
                              .where(getattr(self.table.c, self._primary_key) == primary_key_val)
                              ).first())

        sig.send(self, data = self._current_item)
        if self.errors:
            return self

        self._unsaved_items = {}
        return primary_key_val

    @property
    def table(self):
        if not self._tablename:
            self._tablename = self.__class__.__name__.lower()
        if not hasattr(self, '_table'):
            self._table = Table(self._tablename, MetaData(), autoload = True, autoload_with = self._default_engine)
        return self._table

    def where(self, field, operation, val):
        # check if field has function in it
        field_obj = None
        if field.find('(') != -1:
            sql_func = getattr(func, field[:field.find('(')])
            field = field[field.find('(')+1, -1]
            field_obj = sql_func(getattr(self.table.c, field))
        else:
            field_obj = getattr(self.table.c, field)

        op_dict = {'=': '__eq__',
                   '>': '__gt__',
                   '>=': '__ge__',
                   '<': '__lt__',
                   '<=': '__le__',
                   '!=': '__ne__'}

        for op, op_method in op_dict.items():
            if op == operation:
                operation = op_method

        self._filters.append(getattr(field_obj, operation)(val))
        return self

    def order_by(self, order_by):
        """
        Args:
            order_by (string): if start with '-' means desc
        """
        if order_by[0] == '-':
            self._order_by = getattr(self.table.c, order_by[1:]).desc()
        else:
            self._order_by = getattr(self.table.c, order_by)
        return self

    def select(self, fields):
        for field in fields:
            self._selected_fields.append(getattr(self.table.c, field))
        return self

    def find(self, val = None, db_section = None):
        db = self._default_db if not db_section else self._dbs[db_section]
        if val:
            query = self.table.select().where(getattr(self.table.c, self._primary_key) == val)
        else:
            query = select([self.table], and_(*self._filters))
        self._current_item = db.execute(query).first()
        return self


    def findall(self, limit = 20, offset = 0, db_section = None):
        db = self._default_db if not db_section else self._dbs[db_section]

        query = partial(select, self._selected_fields)
        query = query(and_(*self._filters)) if self._filters else query()

        query = query.order_by(self._order_by).limit(limit).offset(offset)
        self._results = db.execute(query).fetchall()

        return self

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
