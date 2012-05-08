<pre>
     /\  \         /\__\          ___        /\__\         /\  \    
     \:\  \       /:/  /         /\  \      /::|  |       /::\  \   
      \:\  \     /:/__/          \:\  \    /:|:|  |      /:/\:\  \  
      /::\  \   /::\  \ ___      /::\__\  /:/|:|  |__   /:/  \:\  \ 
     /:/\:\__\ /:/\:\  /\__\  __/:/\/__/ /:/ |:| /\__\ /:/__/_\:\__\
    /:/  \/__/ \/__\:\/:/  / /\/:/  /    \/__|:|/:/  / \:\  /\ \/__/
   /:/  /           \::/  /  \::/__/         |:/:/  /   \:\ \:\__\  
   \/__/            /:/  /    \:\__\         |::/  /     \:\/:/  /  
                   /:/  /      \/__/         /:/  /       \::/  /   
                   \/__/                     \/__/         \/__/    

</pre>

# What is Thing

Thing is a lightweight SQLAlchemy based ORM, powerful meanwhile flexible.

# Why Thing

I like ORM, it's the way programmers deal with database. I like ROR's active record, though not all all them. I want it can be easily configured to master / slave, sharding mode, has validator, easy to be integrated with cache. SO I create Thing.

# Thing's Feature

* master / slave mode can be easily configured, even sharding strategy can be easily implemented. 
* has hook before / after CRUD, so you can easily implement cache strategy.
* blinker's signal is triggered before CUD, make your application more loose couple.
* integrated an validator (via formencode)
* support profile
* support ROR's dynamic query, like find_by_user_id, count_by_status

# Installation

`pip install -e 'git+git://github.com/lzyy/thing.git#egg=Thing'`

# Basic Usage

suppose we have an user table like this:

```
CREATE TABLE `user` (
  `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(50) DEFAULT NULL,
  `password` varchar(40) DEFAULT NULL,
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB CHARSET=utf8
```

## define user model

```
#user.py
import thing
class User(thing.Thing):
     pass


#conn.py
import thing

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

thing.Thing.db_config(db_config)


#main.py
import user
import conn

# create user
user_id = user.User(
    usernmae = 'foobar',
    password = 'p@ssword',
).save()

# find user
current_user = user.User().find(user_id)
print current_user.username # 'foobar'

# update user
current_user.username = 'test'
current_user.save()
print current_user.name # 'test'

# delete user
user.User().find(user_id).delete()
```

# Advanced Usage

## query

```
import user
import conn

some_users = user.User().where('id', '<', 10).findall()
print len(some_users) # 9
for some_user in some_users:
    print some_user.username

some_users = user.User().select(['id']).where('id', '<', 10).order_by('-id').findall(limit=5, offset=5)

user_ids = user.User().findall(limit=5).get_field('id') # [1, 2, 3, 4, 5]

max_user_id = user.User().select(['max(id) as max_id']).find().max_id
```

## update

```
import user
import conn

user.User().where('id', '<', 10).updateall(username = 'foobar') # return 9 (affected rows)
```

## delete

```
import user
import conn

user.User().where('id', '<', 5).delete() # return 4 (affected rows)
```

## raw sql

```
import user
import conn

user.User().query('do some special query')
```

# Dynamic Method

there are 4 kind of dynamic method: `find_by_{fields}`, `findall_by_{fields}`, `findall_in_{field}`, `count_by_{fields}`

i.e.

```
import conn
import user

user.User().findall_in_id([1, 3, 5]) # find users whose id is 1, 3, 5

user.User().find_by_id_and_username(3, 'foobar') # find user whose id is 3 and username is foobar

user.User().count_by_id_and_username(4, 'john') # how many rows meets the condition: id = 4 and username = 'john'
```

borrowed from ROR, if you want to add cache, just implement the method you called, that's it, totally transparent.


# Hooks

there are currently 8 hooks:

* _before_insert
* _after_insert
* _before_update
* _after_update
* _before_delete
* _after_delete
* _before_find
* _before_findall

if we want to add cache for the find method in User model, just implement some hooks

```
#user.py
import thing
import redis
import json

rc = redis.Redis()

class User(thing.Thing):
    def _before_insert(self):
        rc.set('user:{0}'.format(self.id), json.dumps(self.to_dict()))

    def _before_update(self):
        self._before_insert()

    def _before_read(self):
        user = rc.get('user:{0}')
        if user:
            return json.loads(user)
```

# Signal

suppose there are article and comment tables, article table has an field `comment_count`, so when a new comment added, article table should update its `comment_count` field. it can be done via signal.

there are 8 built in signals

* model.before_validation
* model.after_validation
* model.before_insert
* model.after_insert
* model.before_update
* model.after_update
* model.before_delete
* model.after_delete

```
#article.py
from blinker import signal
import thing

comment_add = signal('comment.after_insert')

class Article(thing.Thing):
    @comment_add.connect
    def _comment_add(comment):
        article = Article().find(comment.article_id)
        article.comment_count += 1
        article.save()

#comment.py
import thing

class Comment(thing.Thing):
    pass

#trigger.py
import conn
import article, comment

comment.Comment(content = 'hello world').save()
# that's it, article's `comment_count` field will be updated.
```

# validator

validate is implemented via [formencode](http://www.formencode.org/en/latest/Validator.html)

if we want to add some restrict to our User model's username field, it can be done like this:

```
import thing
class User(thing.Thing):
    username = formencode.All(
            validators.String(
                 not_empty = True,
                 strip = True,
                 min = 4,
                 max = 24,
                 messages = {
                     'empty': u'please enter an username',
                     'tooLong': u'username too long',
                     'tooShort': u'username too short'}),
             validators.PlainText(messages = {
                     'invalid': u'username can only contain "number", "_", "-" and "digit"'
                  }))

# if we want to save with invalid username, it can not be saved

user = User()
user.username = '!@#$%^&'
user.save()
print user.saved # False
print user.errors # a dict contains error field and message
```

with the help of formencode, the validator can be very flexible.

# Profile

sqlalchemy will print sql execution information if debug is set to True, but it is unreadable and not so detail.

```
import thing
import user

thing.Thing.enable_profile()
user.User().findall()
# any other db related operation
print thing.Thing.get_sql_stats # a dict with total_time, query_count, and executed query
```

# Partition

Thing support master / slave natively. if you have do some vertical partition, and the partition has its own master / slave, it's OK. if you have domain related sharding strategy, just implement `sharding_strategy` method.

take this db_config as an example.

```
db_config = {
        'master': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
        'slave': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
        'user.master': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
        'user.slave': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
        'article.sharding1': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
        'article.sharding2': {
            'url': 'mysql://username:password@127.0.0.1:3306/dbname?charset=utf8',
            'echo': False,
            },
    }
```

article model's implementation

```
import thing

class Article(thing.Thing):
    def sharding_strategy(self):
        if self.id % 2 == 0:
            return 'sharding1'
        else:
            return 'sharding2'
```

* user model's db write operation will go to `user.master` section, read go to `user.slave`
* article model's id is even, go to sharding1 else go to sharding2
* comment model's db write operation will go to `master` section, read go to `slave`