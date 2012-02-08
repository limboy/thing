#coding=utf-8
import unittest
import thing
from sqlalchemy import create_engine
from formencode import validators
from blinker import signal

engine = create_engine('mysql://root:123456@localhost:3306/test')
conn = engine.connect()
vote_before_insert = signal('vote.before_insert')

class Member(thing.Thing):
    email = validators.Email(messages = {'noAt': u'invalid email'})
    @property
    def answers(self):
        return Answer({'master': engine}).where('member_id', '=', self.id)

class Answer(thing.Thing):
    @property
    def votes(self):
        return Vote({'master': engine}).where('answer_id', '=', self.id)

    @vote_before_insert.connect
    def _vote_before_insert(vote, data):
        if vote.answer.title == 'test':
            vote.errors = {'answer': 'signal test'}

class Vote(thing.Thing):
    @property
    def member(self):
        return Member({'master': engine}).where('id', '=', self.member_id).find()

    @property
    def answer(self):
        return Answer({'master': engine}).where('id', '=', self.answer_id).find()

def create_table():
    conn.execute('''
    CREATE TABLE `member` (
      `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
      `email` varchar(100) DEFAULT NULL,
      `password` varchar(64) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8;
    ''')
    conn.execute('''
    CREATE TABLE  `answer` (
      `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
      `member_id` int(11) DEFAULT NULL,
      `title` varchar(100) DEFAULT NULL,
      `content` varchar(255) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8;
    ''')
    conn.execute('''
    CREATE TABLE `vote` (
      `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
      `member_id` int(11) DEFAULT NULL,
      `answer_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8;
    ''')

create_table()
answer_model = Answer({'master': engine})
member_model = Member({'master': engine})
vote_model = Vote({'master': engine})

class ThingTest(unittest.TestCase):

    def setUp(self):
        try:
            conn.execute('DROP Table member, answer, vote')
        except Exception:
            pass
        create_table()

    def test_create(self):
        member = member_model.reset()
        member.email = 'foo@bar.com'
        member.password = '123'
        member.save()
        self.assertEqual(member.email, 'foo@bar.com')

    def test_update(self):
        member = member_model.reset()
        member.email = 'foo@bar.com'
        member.password = '123'
        member.save()
        member.password = '%s456'%member.password
        member.save()
        self.assertEqual(member.password, '123456')

    def test_associate(self):
        member = member_model.reset()
        member.email = 'foo@bar.com'
        member.password = '123'
        member.save()

        answer1 = answer_model.reset()
        answer1.member_id = 1
        answer1.title = 'foo'
        answer1.content = 'bar'
        answer1.save()

        answer2 = answer_model.reset()
        answer2.member_id = 1
        answer2.title = 'fire'
        answer2.content = 'fox'
        answer2.save()

        answers = member.answers.findall()
        self.assertEqual(len(answers), 2)
        for answer in member.answers.findall():
            if answer.id == 1:
                self.assertEqual(answer.title, 'foo')
            elif answer.id == 2:
                self.assertEqual(answer.title, 'fire')

    def test_filter(self):
        member = member_model.reset()
        member.email = 'foo@bar.com'
        member.password = '123'
        member.save()

        answer1 = answer_model.reset()
        answer1.member_id = 1
        answer1.title = 'foo'
        answer1.content = 'bar'
        answer1.save()

        answer2 = answer_model.reset()
        answer2.member_id = 1
        answer2.title = 'fire'
        answer2.content = 'fox'
        answer2.save()

        answer3 = answer_model.reset()
        answer3.member_id = 1
        answer3.title = 'back'
        answer3.content = 'bone'
        answer3.save()

        vote = vote_model
        vote.member_id = 1
        vote.answer_id = 2
        vote.save()

        for answer in member.answers.where('id', '>', 1).order_by('-id').findall(limit = 1, offset = 1):
            self.assertEqual(answer.id, 2)
            self.assertEqual(answer.content, 'fox')
            for vote in answer.votes.findall():
                self.assertEqual(vote.member.id, 1)

    def test_validation(self):
        member = member_model.reset()
        member.password = '123'
        member.email = 'foo'
        member.save()
        self.assertEqual(member.errors['email'], 'invalid email')

    def test_signal(self):
        answer = answer_model.reset()
        answer.title = 'test'
        answer.content = 'test'
        answer.member_id = 1
        answer.save()

        vote = vote_model.reset()
        vote.answer_id = 1
        vote.member_id = 1
        vote.save()
        self.assertEqual(vote.errors['answer'], 'signal test')

    def tearDown(self):
        conn.execute('''
        DROP Table member, answer, vote
        ''' )

if __name__ == '__main__':
    unittest.main()
