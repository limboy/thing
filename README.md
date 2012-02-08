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

What is Thing ?
===============

Thing is an ORM (active record) based on sqlalchemy, with validations and callbacks

Why another ORM ?
=================

sqlalchemy itself integrates an ORM, using session, which is not so comfortable in use. but i can tolerant, yes, as a Chinese i can tolerant many things. what drive me to write this ORM is it's lack of limit / offset when calling `all()` like this:

```
user = session.query(User).filter(id=1).one()
print user.articles
# there is no way to limit / offset user's articles
# what i want see is like this
print user.articles.all(limit=10, offset=0)
```

Install
=======

virtualenvwrapper is suggested.

```
$ mkvirtualenv thing
cdvirtualenv
pip install -e https://github.com/lzyy/thing.git#egg=thing
```

Features
========

* Easy to Use
* Support Multi Db Connection (like Master / Slave)
* Active Record Pattern (Partly)
* Validation (via FormEncode)
* Callback (via Blinker, like before_insert / after_insert)

Usage
=====

Define Model
------------

if we have a table "member", and has an email field in it, and the relationship with answer is one-to-many. we can define it like this:

```
import thing
from formencode import validators

class Member(thing.Thing):
    email = validators.Email(messages = {'noAt': u'invalid email'})

    @property
    def answers(self):
        return Answer({'master': engine}).where('member_id', '=', self.id)
```

above class can be used like this

```
engine = create_engine('mysql://root:123456@localhost:3306/test')
member = Member({'master': engine}).find(1)

for answer in member.answers.where('id', '>', 10).findall(limit=10, offset=0):
    print answer.title

# or if you want to filter deleted articles
for answer in member.answers.where('status', '=', -1).findall():
    print answer.title
```

we can also create a Base Model to avoid pass engines to models everytime when init.

```
import thing
from sqlalchemy import create_engine
engine = create_engine('mysql://root:123456@localhost:3306/test')

class BaseThing(thing.Thing):
    def __init__(self):
        thing.Thing.__init__(self, {'master': engine})
```


*Tips:*

* model must extends Thing
* if _tablename not provided, lower class name will be used as _tablename
* table field is auto discovered
* if you want to validate some field, set its name as class's attribute like `email`
* FormEncode support many validate types, see it [here](http://www.formencode.org/en/latest/Validator.html)
* relationship is handled manually, more flexible
* multi engine support, as init params


Create
------

```
member = Member({'master': engine})
member.email = 'foo@bar.com'
member.password = '123'
member.save()
print member.saved # True
print member.email # foo@bar.com
```

Update
------

```
member = Member({'master': engine}).find(1)
member.email = 'foo@bar.com'
member.save()
print member.saved # True
print member.email # foo@bar.com
```

Validation
----------

```
member = Member({'master': engine})
member.password = '123'
member.email = 'foo'
member.save()
print member.errors['email'] # invalid email
```

more usage can be found in test.py

Callbacks
=========

there are 6 callbacks.

* before_validation
* after_validation
* before_insert
* after_insert
* before_update
* after_update

if an answer can be voted, and if answer doesn't exists, vote failed. we can do it like this:

```
import signal

vote_before_insert = signal('vote.before_insert')

class Answer(thing.Thing):
    @property
    def votes(self):
        return Vote({'master': engine}).where('answer_id', '=', self.id)

    @vote_before_insert.connect
    def _vote_before_insert(vote, data):
        # just for demostration
        if vote.answer.title == 'test':
            vote.errors = {'answer': 'test is not allowed'}

class Vote(thing.Thing):
    @property
    def answer(self):
        return Answer({'master': engine}).where('id', '=', self.answer_id).find()
```

if vote is inserting by calling `vote.save()`, a `vote.before_insert` will be triggered before insert, and `vote.after_insert` will be triggered after insert.

if condition not meeted in callback, callback can set errors on sender, in this example `vote.errors`, it will stop vote's save execution. if `vote.errors` is empty, this execution is successful, else failed with messages in `vote.errors`


Tips
====

* if validate failed, error messages can be accessed via `errors` attribute
* check `saved` attribute to see if an model has been saved
* if you want to start with a fresh model, call `reset` method, `fresh_member = member.reset()`
* if model instance has primary key (like `id`), it will execute update action, else execute insert action
