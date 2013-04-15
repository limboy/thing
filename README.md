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

# Thing 是什么？

Thing是一个基于SQLAlchemy的配置简单、使用简单且灵活的ORM。

# 使用方法

举个简单的例子，假如有3个表：comment, post, user, 3个表的字段分别是：

comment表:
```
+---------+------------------+------+-----+---------+----------------+
| Field   | Type             | Null | Key | Default | Extra          |
+---------+------------------+------+-----+---------+----------------+
| id      | int(11) unsigned | NO   | PRI | NULL    | auto_increment |
| user_id | int(11)          | YES  | MUL | NULL    |                |
| post_id | int(11)          | YES  | MUL | NULL    |                |
| content | text             | YES  |     | NULL    |                |
+---------+------------------+------+-----+---------+----------------+
```

post表：
```
+---------+------------------+------+-----+---------+----------------+
| Field   | Type             | Null | Key | Default | Extra          |
+---------+------------------+------+-----+---------+----------------+
| id      | int(11) unsigned | NO   | PRI | NULL    | auto_increment |
| user_id | int(11)          | YES  | MUL | NULL    |                |
| created | int(11)          | YES  |     | NULL    |                |
| content | text             | YES  |     | NULL    |                |
| title   | varchar(255)     | YES  |     | NULL    |                |
+---------+------------------+------+-----+---------+----------------+
```

user表：
```
+-------+------------------+------+-----+---------+----------------+
| Field | Type             | Null | Key | Default | Extra          |
+-------+------------------+------+-----+---------+----------------+
| id    | int(11) unsigned | NO   | PRI | NULL    | auto_increment |
| name  | varchar(30)      | YES  |     | NULL    |                |
+-------+------------------+------+-----+---------+----------------+
```

## 定义Model

先来看看目录结构
```
├── __init.py__
├── conn.py # 用于数据库连接
├── models
│   ├── __init__.py
│   ├── comment.py
│   ├── post.py
│   ├── user.py
└── test.py
```
test.py就是进行测试的地方，先来看看各个model的内容：

### comment.py

```
import thing

class Comment(thing.Thing):
    _belongs_to = {
            'post': {
                'model': 'models.post.Post',
                'foreign_key': 'post_id',
                },
            'author': {
                'model': 'models.user.User',
                'foreign_key': 'user_id',
                },
            }
```

### post.py

```
import thing

class Post(thing.Thing):
    _belongs_to = {
            'author': {
                'model': 'models.user.User',
                'foreign_key': 'user_id',
                }
            }
    _has_many = {
            'comments': {
                'model': 'models.comment.Comment',
                'foreign_key': 'user_id',
                }
            }
```

### user.py

```
import thing

class User(thing.Thing):
    _has_many = {
            'posts': {
                'model': 'models.post.Post',
                'foreign_key': 'user_id'
                },
            'comments': {
                'model':  'models.comment.Comment',
                'foreign_key': 'user_id'
                }
            }
```

再来看看conn.py

### conn.py

```
import thing

config = {
        'db': {
            'master': {
                'url': 'mysql://root:123456@127.0.0.1:3306/test?charset=utf8',
                'echo': False,
                },
            'slave': {
                'url': 'mysql://root:123456@127.0.0.1:3306/test?charset=utf8',
                'echo': False,
                },
            },
        'redis': {
            'host': 'localhost',
            'port': 6379,
            'db': 1,
            },
        'thing': {
            'debug': True,
            }
        }

thing.Thing.config(config)
```

OK，万事具备，开工！

```
import conn
from models.comment import Comment
from models.user import User
from models.post import Post

# -------- 插入数据 --------
user = User()
user.name = 'foo'
user.save()
# 或者 user = User(name='foo').save()

# -------- 获取数据 --------
user = User().find(1)
print user.name

# -------- 获取关联数据 -------
posts = User().find(1).posts.findall()
# 如果要设置offset / limit, 在findall里加入参数即可
# posts = User().find(1).posts.findall(offset = 0, limit = 20)

# ------- 删除数据 -------
User().find(1).delete()

# ------- 更新数据 -------
user = User().find(1)
user.name = 'bar'
user.save()
```

# 动态查询

这个是受Rails影响，觉得很方便就拿来了。比如 `Post().count_by_user_id(3)`，就可以找到user_id为3的用户发表的文章数量。要获取`user_id`为3的用户发表的文章，可以`Post().findall_by_user_id(3, limit=20)`，比起`Post().where('user_id', '=', 3).findall()`更加简洁和明了。

# 关于性能和缓存

Thing内置了Redis作为缓存，你甚至都不需要知道Redis的存在，正常该怎么用还怎么用，Thing会自动处理缓存的生成、读取、过期、删除等操作。

假设表posts里有5条数据，在获取每条post后，还想获取该post对应的用户信息，代码如下：

```
posts = Post().findall(limit=5)

for post in posts:
	print post.author
```

在开启Debug的情况下，可以在终端看到如下显示：

```
DEBUG - [cost:0.0032] - SELECT post.id, post.user_id, post.created, post.content, post.title
FROM post ORDER BY post.id DESC
LIMIT -1 OFFSET :param_1
DEBUG - Cache Read: thing.User:1
{u'id': 1, u'name': u'lzyy'}
DEBUG - Cache Read: thing.User:1
{u'id': 1, u'name': u'lzyy'}
DEBUG - Cache Read: thing.User:1
{u'id': 1, u'name': u'lzyy'}
DEBUG - Cache Read: thing.User:1
{u'id': 1, u'name': u'lzyy'}
DEBUG - Cache Read: thing.User:1
{u'id': 1, u'name': u'lzyy'}
```

可以看到用户的信息都是从缓存中读取的，所以不用担心n+1的问题。
假如用户的信息被更新，缓存也会自动更新。

# 其他

* 配置信息里的`master`和`slave`为必选项，可以相同。Thing会根据不同的查询，自动找到对应的db。如find/findall会找slave，update/delete会找master。
* 配置信息里的redis项为必选项。
* 动态查询目前支持`find_by`, `findall_by`, `findall_in`, `count_by`
* 内置了8个钩子，会在相应的事件发生时被调用，分别是：`_before_insert`,`_after_insert`,`_before_update`,`_after_update`,`_before_delete`,`_after_delete`,`_before_find`,`_after_find`，可以在子类里覆盖这些方法来实现自己的逻辑。
* 复杂的SQL可以使用`execute`方法，返回的结果是SQLAlchemy的ResultProxy
* 如果要一次更新多处的话，可以使用`updateall`方法，`Post().where('user_id', '=', 1).updateall(user_id=2)`
* 表名如果和小写的类名不一样的话，可以在子类里重新设置`_tablename`
* 每个表一定要有主键，默认为`id`，可以在子类里重新设置`_primary_key`
* 支持has_many和belongs_to，可以在子类里定义`_has_many`和`_belongs_to`
* 没有`join`方法
